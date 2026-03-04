from __future__ import annotations

"""
Simple test script for the RAG Agent tooling.

Goal:
    - Use the existing v2 index under:
        runtime/source/11258b1255cc40b1bfe27f49fdd760fa/rag_storage_v2
    - Load the corresponding parsed content directory.
    - Create a LangChain tools Agent on top of RAG-Anything.
    - Ask the Agent to generate `product_info` JSON based on `DEFAULT_PRODUCT_INFO_SCHEMA`.

Notes:
    - This script assumes you have a LangChain-compatible chat model available.
      By default it uses `ChatOpenAI` from `langchain_openai` as an example.
      You can replace `ChatOpenAI` with any `BaseChatModel` implementation.

Usage (example):
    export OPENAI_API_KEY=sk-...
    python -m examples.agent_test
"""

import asyncio
import json
import os
from pathlib import Path

from agent import (
    build_rag_agent_tools,
    create_product_info_orchestrator_agent,
    get_last_agent_output,
)
from raganything.product import DEFAULT_PRODUCT_INFO_SCHEMA
from config.api_keys import DASHSCOPE_API_KEY


def _build_doc_meta() -> dict:
    """
    Build a minimal doc_meta for the given runtime directory.

    We only need:
        - working_dir: points to rag_storage_v2
        - parsed_dir: points to the MinerU parsed output
    """
    root = Path("runtime/source/332505f3e56c4733a73a557d792730c7").resolve()
    working_dir_v2 = root / "rag_storage"
    parsed_dir = root / "parsed" / "Logitech Wireless Mouse M560 Setup Guide"

    if not working_dir_v2.exists():
        raise FileNotFoundError(f"v2 working dir not found: {working_dir_v2}")
    if not parsed_dir.exists():
        raise FileNotFoundError(f"parsed dir not found: {parsed_dir}")

    return {
        "doc_id": "332505f3e56c4733a73a557d792730c7",
        "working_dir": str(working_dir_v2),
        "parsed_dir": str(parsed_dir),
    }


async def main() -> None:
    # --- LangSmith / LangChain Tracing ---
    # Set these in your shell for security (do NOT commit keys):
    #   export LANGCHAIN_TRACING_V2=true
    #   export LANGCHAIN_API_KEY="your-langsmith-token"
    #   export LANGCHAIN_PROJECT="agent-debug"
    #
    # For convenience, we enable tracing + set a default project name here if not provided.
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_PROJECT", "agent-debug")


    # 1. Prepare doc_meta for this specific runtime source
    doc_meta = _build_doc_meta()

    # 2. （可选）构建底层 RAG 工具，仅供调试使用；
    #    Product Info Orchestrator 父 Agent 本身只会暴露 CreateAndRunAgentTool，
    #    真正的 kb_query / kb_page_context / vlm_image_query 等工具仅对子 Agent 可见。
    _tools = build_rag_agent_tools(doc_meta)

    # 3. 构建 Product Info Orchestrator 父 Agent
    #    - 内部会注入 DEFAULT_PRODUCT_INFO_SCHEMA 并使用 CoT 方式拆解子 Agent；
    #    - 父 Agent 自己只具备 create_and_run_agent 工具能力；
    #    - 若未显式传入 llm，将在内部基于 DASHSCOPE_API_KEY / 环境变量自动构建默认 Qwen ChatOpenAI 模型。
    orchestrator = create_product_info_orchestrator_agent(
        doc_meta=doc_meta,
        product_schema=DEFAULT_PRODUCT_INFO_SCHEMA,
        include_history=False,
        verbose=True,
    )

    # 5. 定义交给父 Agent 的顶层任务说明
    user_task = (
        "Using the watch user manual in the current knowledge base, extract the complete product "
        "information strictly following the provided Product Schema.\n"
        "You are the parent Orchestrator Agent and may ONLY use `create_and_run_agent` to create "
        "Sub Agents. Sub Agents may use RAG tools to access the document and return JSON fragments.\n"
        "In the end, return ONLY a single JSON object that strictly matches the Schema, with no "
        "extra explanation text."
    )

    result = await orchestrator.ainvoke({"input": user_task})

    # 6. Print the final JSON result from orchestrator
    output = get_last_agent_output(result)
    print("===== Agent product_info result =====")
    print(output)

    # 为了避免退出时的 asyncio 清理日志淹没正常输出，这里额外等待片刻
    await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())

