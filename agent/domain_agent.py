from __future__ import annotations

"""
DomainKnowledgeExtractionAgent — deepagents-based main agent for domain knowledge extraction.

Architecture
------------
This agent sits above the FileSkillSupervisor layer.  Instead of hard-coding
which skill to use, it:

  1. Uses RAG tools (kb_query / kb_chunk_query) to understand the document.
  2. Reads the SKILL.md of the matching skill (progressive disclosure via
     deepagents SkillsMiddleware).
  3. Executes ``run.py`` inside the skill directory via the LocalShellBackend's
     bash tool — which internally invokes FileSkillSupervisor.
  4. Returns the structured JSON written by run.py.

Backend
-------
``LocalShellBackend(root_dir=PROJECT_ROOT, virtual_mode=True)`` gives the agent:
  - read_file / ls / glob on all project files (virtual paths rooted at /).
  - execute() to run shell commands (used for ``python run.py ...``).

Skills discovery
----------------
``skills=["/agent/skills/"]`` causes the SkillsMiddleware to scan
agent/skills/<name>/SKILL.md and inject name + description into the system
prompt.  The agent reads the full SKILL.md only when it decides a skill applies.

Usage::

    from agent.domain_agent import DomainKnowledgeExtractionAgent
    from agent.agent import _build_default_llm

    agent = DomainKnowledgeExtractionAgent(doc_meta=doc_meta, llm=_build_default_llm())
    result = await agent.run()
"""

import asyncio
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend
from langchain_core.language_models.chat_models import BaseChatModel

from agent.tools import build_rag_agent_tools
from agent.util import get_last_ai_message_content

logger = logging.getLogger(__name__)

# Project root: agent/domain_agent.py → agent/ → RAG-Anything/
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_TEMPLATE = """\
# Role
You are the **DomainKnowledgeExtractionAgent** — an expert at extracting structured \
domain knowledge from documents of various types (product manuals, clinical guidelines, \
service documents, etc.).

# Goal
Given a document, you must:
1. **Identify** the document's domain type by querying the knowledge base.
2. **Select** the most appropriate skill from the Skills System (injected below).
3. **Execute** the skill's `run.py` script via the bash tool.
4. **Report** the result path and a brief summary.

# Document
- **doc_id**   : {DOC_ID}
- **meta_path**: {META_PATH}

# Execution Pattern
After reading the chosen skill's SKILL.md, execute its runner with:

```bash
{PYTHON} {SKILLS_DIR}/<skill-name>/run.py \\
    --meta_path {META_PATH} \\
    --output {OUTPUT_PATH}
```

Replace `<skill-name>` with the exact directory name of the chosen skill
(e.g. `product-knowledge`, `medical-service`).

> The script may run for several minutes.  It prints the extracted JSON to
> stdout and writes it to `{OUTPUT_PATH}`.  Stderr contains progress logs.

# How to Identify the Domain
Use `kb_query` with broad keywords (e.g. "product overview", "clinical service",
"device manual") to get a sense of the document's content, then match to the skill
whose description best fits.

# Output
When the script finishes, report:
1. The skill used and why.
2. The output file path: `{OUTPUT_PATH}`
3. The top-level keys present in the extracted JSON.
"""


def _build_system_prompt(
    doc_meta: Dict[str, Any],
    meta_path: Path,
    output_path: Path,
    skills_dir: Path,
) -> str:
    return _SYSTEM_PROMPT_TEMPLATE.format(
        DOC_ID=doc_meta["doc_id"],
        META_PATH=str(meta_path),
        OUTPUT_PATH=str(output_path),
        SKILLS_DIR=str(skills_dir),
        PYTHON=sys.executable,
    )


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

class DomainKnowledgeExtractionAgent:
    """
    Main agent for document-type-aware domain knowledge extraction.

    The agent uses the deepagents SKILL system to discover available skills,
    selects the right one for the input document, and executes its ``run.py``
    via shell — delegating the actual extraction to ``FileSkillSupervisor``.

    Parameters
    ----------
    doc_meta:
        Document metadata dict (must contain doc_id, working_dir, parsed_dir).
    llm:
        LangChain chat model for the agent.
    output_path:
        Where to write the final JSON.  Defaults to
        ``runtime/source/<doc_id>/domain_knowledge.json``.
    skills_dir:
        Override the skills directory (default: ``agent/skills/``).
    shell_timeout:
        Timeout in seconds for the ``run.py`` shell command.
        Should be longer than the expected FileSkillSupervisor run time.
    agent_timeout:
        Outer timeout (seconds) for the entire agent invocation.
    """

    def __init__(
        self,
        doc_meta: Dict[str, Any],
        llm: BaseChatModel,
        *,
        output_path: Optional[str | Path] = None,
        skills_dir: Optional[str | Path] = None,
        shell_timeout: int = 720,
        agent_timeout: float = 1200.0,
    ) -> None:
        self.doc_meta = doc_meta
        self.llm = llm
        self.shell_timeout = shell_timeout
        self.agent_timeout = agent_timeout

        # Skills directory (real path)
        self._skills_dir = (
            Path(skills_dir).resolve()
            if skills_dir
            else (_PROJECT_ROOT / "agent" / "skills").resolve()
        )

        # meta.json lives one level above working_dir
        # working_dir is typically: runtime/source/<doc_id>/<subdir>/
        self._meta_path = (
            Path(doc_meta["working_dir"]).resolve().parent / "meta.json"
        )

        # Output path
        if output_path:
            self._output_path = Path(output_path).resolve()
        else:
            doc_root = self._meta_path.parent
            self._output_path = doc_root / "domain_knowledge.json"

        # LocalShellBackend:
        #   - virtual_mode=True  → maps virtual "/" to PROJECT_ROOT on disk
        #   - inherit_env=True   → propagates DASHSCOPE_API_KEY, PATH, etc.
        #   - timeout            → per-execute() timeout (for run.py)
        self._backend = LocalShellBackend(
            root_dir=str(_PROJECT_ROOT),
            virtual_mode=True,
            inherit_env=True,
            timeout=shell_timeout,
        )

        # RAG tools so the agent can explore the KB to classify the document
        self._rag_tools = build_rag_agent_tools(doc_meta)

        # Virtual POSIX path for the skills= parameter
        # e.g. /agent/skills/ (relative to PROJECT_ROOT which is virtual "/")
        self._skills_posix = (
            "/" + self._skills_dir.relative_to(_PROJECT_ROOT).as_posix() + "/"
        )

        logger.info(
            "DomainKnowledgeExtractionAgent created: doc_id=%s  skills=%s  output=%s",
            doc_meta["doc_id"],
            self._skills_posix,
            self._output_path,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> Dict[str, Any]:
        """
        Invoke the agent and return the extracted domain knowledge dict.

        The agent will:
        1. Query the KB to identify the document domain.
        2. Choose and read the matching SKILL.md.
        3. Execute ``run.py`` via bash.
        4. Return the parsed JSON from the output file (or from stdout).
        """
        system_prompt = _build_system_prompt(
            self.doc_meta,
            self._meta_path,
            self._output_path,
            self._skills_dir,
        )

        agent = create_deep_agent(
            model=self.llm,
            tools=self._rag_tools,
            system_prompt=system_prompt,
            skills=[self._skills_posix],
            backend=self._backend,
        )

        task = (
            f"Extract domain knowledge from document '{self.doc_meta['doc_id']}'. "
            f"Identify the document type, activate the matching skill, run its "
            f"extraction script, and save the result to: {self._output_path}"
        )

        messages = [{"role": "user", "content": task}]
        config = {"recursion_limit": 120, "max_concurrency": 1}

        logger.info("DomainKnowledgeExtractionAgent: starting agent invocation")
        coro = asyncio.to_thread(agent.invoke, {"messages": messages}, config)
        result = await asyncio.wait_for(coro, timeout=self.agent_timeout)

        return self._resolve_result(result)

    def invoke(self, doc_meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Synchronous wrapper around ``run()``."""
        return asyncio.run(self.run())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_result(self, agent_result: Any) -> Dict[str, Any]:
        """
        Try to return a parsed JSON dict from the agent run.

        Priority:
        1. Read the output file (most reliable — written by run.py).
        2. Parse JSON from the agent's last text message.
        3. Return a dict with the raw text.
        """
        if self._output_path.exists():
            try:
                data = json.loads(self._output_path.read_text(encoding="utf-8"))
                logger.info(
                    "DomainKnowledgeExtractionAgent: result read from %s  keys=%s",
                    self._output_path,
                    list(data.keys()) if isinstance(data, dict) else type(data),
                )
                return data if isinstance(data, dict) else {"data": data}
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to read output file %s: %s", self._output_path, exc)

        text = get_last_ai_message_content(agent_result) or str(agent_result)
        obj = _try_parse_json_object(text)
        if obj:
            logger.info("DomainKnowledgeExtractionAgent: result parsed from agent text")
            return obj

        logger.warning("DomainKnowledgeExtractionAgent: could not parse JSON result")
        return {"raw_output": text}


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------

def create_dke_agent(
    doc_meta: Dict[str, Any],
    llm: BaseChatModel,
    **kwargs: Any,
) -> DomainKnowledgeExtractionAgent:
    """Convenience factory matching the style of other agent constructors."""
    return DomainKnowledgeExtractionAgent(doc_meta=doc_meta, llm=llm, **kwargs)


# ---------------------------------------------------------------------------
# Private utils
# ---------------------------------------------------------------------------

def _try_parse_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Find the first balanced {…} JSON object in text (handles code fences)."""
    if not text:
        return None
    cleaned = re.sub(r"```(?:json)?\s*", "", text)
    cleaned = re.sub(r"```", "", cleaned)
    depth = 0
    start: Optional[int] = None
    for i, ch in enumerate(cleaned):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    obj = json.loads(cleaned[start : i + 1])
                    if isinstance(obj, dict):
                        return obj
                except json.JSONDecodeError:
                    pass
                start = None
    return None
