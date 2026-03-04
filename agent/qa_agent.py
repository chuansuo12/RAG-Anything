from __future__ import annotations

"""
Q&A Agent for RAG-Anything.

Architecture:
    Python Orchestrator (code-controlled loop)
        -> Retrieval Agent (tool-calling LangChain agent)
        -> Verification Agent (tool-calling LangChain agent)
        -> retry if verification fails (max 2 retries)

Entry point: ``run_qa_agent(question, doc_meta, ...)``
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from agent.tools import build_rag_agent_tools
from agent.qa_prompt import (
    QUESTION_CLASSIFY_PROMPT,
    VERIFICATION_SYSTEM_PROMPT,
    build_retrieval_system_prompt,
    build_retrieval_retry_prompt,
)

try:
    from config.api_keys import DASHSCOPE_API_KEY
except ImportError:
    DASHSCOPE_API_KEY = ""

from config.model_conf import DASHSCOPE_BASE_URL, QWEN_PLUS_3_5_MODEL

logger = logging.getLogger(__name__)

VALID_QUESTION_TYPES = frozenset({
    "factoid", "counting", "visual", "list", "unanswerable_possible",
})


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------

def _build_qa_llm() -> BaseChatModel:
    api_key = (DASHSCOPE_API_KEY or "").strip()
    if not api_key:
        raise ValueError("DASHSCOPE_API_KEY 未配置")
    return ChatOpenAI(
        model=QWEN_PLUS_3_5_MODEL,
        api_key=api_key,
        base_url=DASHSCOPE_BASE_URL,
        temperature=0.1,
        extra_body={"parallel_tool_calls": True},
    )


# ---------------------------------------------------------------------------
# Sub-agent factories
# ---------------------------------------------------------------------------

def _create_sub_agent(
    llm: BaseChatModel,
    tools: List[BaseTool],
    system_prompt: str,
) -> Runnable:
    """Create a LangChain agent (via ``create_agent``) with the given prompt and tools."""
    return create_agent(model=llm, tools=tools, system_prompt=system_prompt)


def _extract_agent_output(result: object) -> str:
    """Extract the final text content from a LangGraph-style agent result."""
    if isinstance(result, dict):
        msgs = result.get("messages")
        if msgs:
            last = msgs[-1]
            content = last.get("content") if isinstance(last, dict) else getattr(last, "content", None)
            if content is not None:
                return str(content)
        if "output" in result:
            return str(result["output"])
    return str(result)


# ---------------------------------------------------------------------------
# Question classifier
# ---------------------------------------------------------------------------

async def classify_question(question: str, llm: BaseChatModel) -> str:
    """Classify *question* into one of the predefined types using the LLM."""
    messages = [
        {"role": "system", "content": QUESTION_CLASSIFY_PROMPT},
        {"role": "user", "content": question},
    ]
    try:
        resp = await llm.ainvoke(messages)
        raw = (resp.content if hasattr(resp, "content") else str(resp)).strip().lower()
        # Take the first token as the type label
        label = raw.split()[0].strip(".,;:!?\"'") if raw else "factoid"
        if label not in VALID_QUESTION_TYPES:
            logger.warning("Unknown question type %r, falling back to 'factoid'", label)
            label = "factoid"
        return label
    except Exception as e:  # noqa: BLE001
        logger.warning("Question classification failed (%s), defaulting to 'factoid'", e)
        return "factoid"


# ---------------------------------------------------------------------------
# Parse verification output
# ---------------------------------------------------------------------------

def _parse_verification_output(raw: str) -> Dict[str, Any]:
    """Parse the JSON output from the Verification Agent."""
    text = raw.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        text = text[start : end + 1]

    try:
        data = json.loads(text)
        return {
            "passed": bool(data.get("passed", False)),
            "final_answer": str(data.get("final_answer", "")),
            "feedback": str(data.get("feedback", "")),
            "issues": data.get("issues", []),
        }
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("Failed to parse verification JSON: %s — raw=%r", e, raw[:300])
        return {
            "passed": False,
            "final_answer": "",
            "feedback": f"Verification output was not valid JSON: {e}",
            "issues": ["parse_error"],
        }


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

async def run_qa_agent(
    question: str,
    doc_meta: Dict[str, Any],
    *,
    max_retries: int = 2,
    llm: Optional[BaseChatModel] = None,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Run the Q&A Agent pipeline: classify -> retrieve -> verify -> (retry).

    Args:
        question: The user question.
        doc_meta: Knowledge-base metadata (must contain ``working_dir``, ``parsed_dir``).
        max_retries: Maximum number of retrieval retries after verification failure.
        llm: Optional pre-built LLM; if None a default Qwen instance is created.
        verbose: Whether to log extra debug information.

    Returns:
        Dict with keys: ``answer``, ``confidence`` ("high" / "low"),
        ``question_type``, ``attempts``, ``verification``.
    """
    if llm is None:
        llm = _build_qa_llm()

    tools = build_rag_agent_tools(doc_meta)

    # Step 1 — classify the question
    q_type = await classify_question(question, llm)
    logger.info("Question classified as: %s", q_type)

    # Step 2 — build sub-agents
    retrieval_prompt = build_retrieval_system_prompt(q_type)
    retrieval_agent = _create_sub_agent(llm, tools, retrieval_prompt)
    verification_agent = _create_sub_agent(llm, tools, VERIFICATION_SYSTEM_PROMPT)

    # Step 3 — first retrieval pass
    retrieval_input = {"messages": [{"role": "user", "content": question}]}
    retrieval_result = await retrieval_agent.ainvoke(
        retrieval_input,
        config={"max_concurrency": 2, "recursion_limit": 50},
    )
    draft_answer = _extract_agent_output(retrieval_result)
    logger.info("Retrieval pass 1 draft answer length: %d", len(draft_answer))

    # Step 4 — verification loop
    best_answer = draft_answer
    verification_data: Dict[str, Any] = {}

    for attempt in range(max_retries + 1):
        verification_input_text = (
            f"Question: {question}\n\n"
            f"Question type: {q_type}\n\n"
            f"Draft answer to verify:\n{best_answer}"
        )
        verification_input = {
            "messages": [{"role": "user", "content": verification_input_text}],
        }
        verification_result = await verification_agent.ainvoke(
            verification_input,
            config={"max_concurrency": 2, "recursion_limit": 50},
        )
        raw_verification = _extract_agent_output(verification_result)
        verification_data = _parse_verification_output(raw_verification)

        if verification_data["passed"]:
            final = verification_data["final_answer"] or best_answer
            logger.info("Verification PASSED on attempt %d", attempt + 1)
            return {
                "answer": final,
                "confidence": "high",
                "question_type": q_type,
                "attempts": attempt + 1,
                "verification": verification_data,
            }

        logger.info(
            "Verification FAILED on attempt %d: issues=%s feedback=%s",
            attempt + 1,
            verification_data.get("issues"),
            (verification_data.get("feedback") or "")[:200],
        )

        if attempt < max_retries:
            # Retry with feedback
            retry_msg = build_retrieval_retry_prompt(
                question=question,
                question_type=q_type,
                previous_answer=best_answer,
                feedback=verification_data.get("feedback", ""),
            )
            retry_input = {"messages": [{"role": "user", "content": retry_msg}]}
            retry_result = await retrieval_agent.ainvoke(
                retry_input,
                config={"max_concurrency": 2, "recursion_limit": 50},
            )
            best_answer = _extract_agent_output(retry_result)
            logger.info("Retrieval retry %d draft answer length: %d", attempt + 1, len(best_answer))

    # Exhausted retries — return best-effort answer
    final = verification_data.get("final_answer") or best_answer
    return {
        "answer": final,
        "confidence": "low",
        "question_type": q_type,
        "attempts": max_retries + 1,
        "verification": verification_data,
    }
