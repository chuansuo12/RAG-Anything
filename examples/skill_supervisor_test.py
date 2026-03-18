from __future__ import annotations

"""
Test script for FileSkillSupervisor using document 11258b1255cc40b1bfe27f49fdd760fa
(watch_d.pdf — a product manual for a smartwatch).

Tests the full Skill-based extraction pipeline:
    product-knowledge skill  →  SKILL.md + schema.json + prompts/
    FileSkillSupervisor      →  create_deep_agent sub-agents
    Shared merger            →  combines all JSON outputs

Usage::

    conda run -n rag-any python -m examples.skill_supervisor_test

Environment::

    DASHSCOPE_API_KEY must be set (Qwen model via DashScope).
    Optional LangSmith tracing:
        LANGCHAIN_TRACING_V2=true
        LANGCHAIN_API_KEY=<your-key>
        LANGCHAIN_PROJECT=skill-supervisor-test
"""

import asyncio
import json
import logging
import os
from pathlib import Path

from agent.agent import _build_default_llm
from agent.skill_supervisor import FileSkillSupervisor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Document under test
# ---------------------------------------------------------------------------

DOC_ID = "11258b1255cc40b1bfe27f49fdd760fa"
_DOC_ROOT = (
    Path(__file__).parent.parent
    / "runtime" / "source" / DOC_ID
).resolve()

# Skill to use
SKILL_DIR = Path(__file__).parent.parent / "agent" / "skills" / "product-knowledge"


def _build_doc_meta() -> dict:
    """Build doc_meta from the on-disk meta.json."""
    meta_path = _DOC_ROOT / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"meta.json not found: {meta_path}")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    # Validate required paths exist
    working_dir = Path(meta["working_dir"])
    parsed_dir  = Path(meta["parsed_dir"])
    if not working_dir.exists():
        raise FileNotFoundError(f"working_dir not found: {working_dir}")
    if not parsed_dir.exists():
        raise FileNotFoundError(f"parsed_dir not found: {parsed_dir}")

    return {
        "doc_id":      meta["doc_id"],
        "working_dir": str(working_dir),
        "parsed_dir":  str(parsed_dir),
        "kb_version":  "v2",
    }


# ---------------------------------------------------------------------------
# Main test
# ---------------------------------------------------------------------------

async def main() -> None:
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_PROJECT", "skill-supervisor-test")

    logger.info("=== FileSkillSupervisor Test ===")
    logger.info("doc_id   : %s", DOC_ID)
    logger.info("skill_dir: %s", SKILL_DIR)

    # 1. Build doc_meta
    doc_meta = _build_doc_meta()
    logger.info("doc_meta: %s", {k: v for k, v in doc_meta.items() if k != "log"})

    # 2. Build LLM
    llm = _build_default_llm()

    # 3. Create supervisor from skill directory
    supervisor = FileSkillSupervisor.from_skill_dir(
        skill_dir=SKILL_DIR,
        doc_meta=doc_meta,
        llm=llm,
        max_retries=2,
        sub_agent_timeout=180.0,
        max_concurrency=3,
    )

    logger.info("Skill loaded: name=%s  steps=%s",
                supervisor.skill_def.name,
                [(s.key, s.type) for s in supervisor.skill_def.steps])
    logger.info("tmp_dir: %s", supervisor._tmp_dir)

    # 4. Run extraction
    result = await supervisor.run()

    # 5. Print result
    if result:
        print("\n===== Skill Extraction Result =====")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"\nTop-level keys: {list(result.keys())}")

        # Basic assertions
        assert isinstance(result, dict), "Result should be a dict"
        assert len(result) > 0, "Result should not be empty"

        for key in supervisor.skill_def.steps:
            if key.key in result:
                val = result[key.key]
                if key.type == "scalar":
                    assert isinstance(val, dict), f"{key.key} should be a dict"
                elif key.type == "list":
                    assert isinstance(val, list), f"{key.key} should be a list"
                logger.info("✓ %s: %s", key.key,
                            f"{len(val)} items" if isinstance(val, list) else "dict")
            else:
                logger.warning("⚠ Key '%s' missing from result", key.key)

        print("\n✅ All assertions passed.")
    else:
        print("\n⚠ Extraction returned empty result.")

    logger.info("tmp_dir preserved at: %s", supervisor._tmp_dir)

    # Let asyncio settle before exit
    await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
