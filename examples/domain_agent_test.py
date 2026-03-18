from __future__ import annotations

"""
Test script for DomainKnowledgeExtractionAgent.

Tests the full top-level extraction pipeline:
    DomainKnowledgeExtractionAgent  →  identifies document domain via RAG
                                    →  selects matching skill (product-knowledge / medical-service)
                                    →  executes skill's run.py via LocalShellBackend
                                    →  returns merged JSON result

Usage::

    # Default: watch_d.pdf (product manual)
    conda run -n rag-any python -m examples.domain_agent_test

    # Other documents (all are product docs)
    conda run -n rag-any python -m examples.domain_agent_test --doc_id 332505f3e56c4733a73a557d792730c7  # Logitech mouse
    conda run -n rag-any python -m examples.domain_agent_test --doc_id e0df634fa94741c590545b9f2c14ba07  # MacBook Air

    # Save output to a specific path
    conda run -n rag-any python -m examples.domain_agent_test --output /tmp/result.json

Environment::

    DASHSCOPE_API_KEY must be set (Qwen model via DashScope).
    Optional LangSmith tracing:
        LANGCHAIN_TRACING_V2=true
        LANGCHAIN_API_KEY=<your-key>
        LANGCHAIN_PROJECT=domain-agent-test
"""

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

from agent.agent import _build_default_llm
from agent.domain_agent import DomainKnowledgeExtractionAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Available test documents
# ---------------------------------------------------------------------------

_DOCS: dict[str, str] = {
    "11258b1255cc40b1bfe27f49fdd760fa": "watch_d.pdf (smartwatch manual)",
    "332505f3e56c4733a73a557d792730c7": "Logitech Wireless Mouse M560 Setup Guide.pdf",
    "55597e43e7d84eecb07b5131dce1bf22": "mi_phone.pdf",
    "635135550a2745b4a2fa865c893738ad": "nova_y70.pdf",
    "e0df634fa94741c590545b9f2c14ba07": "Macbook_air.pdf",
}

_DEFAULT_DOC_ID = "11258b1255cc40b1bfe27f49fdd760fa"
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_doc_meta(doc_id: str) -> dict:
    """Load and validate doc_meta from the on-disk meta.json."""
    doc_root = _PROJECT_ROOT / "runtime" / "source" / doc_id
    meta_path = doc_root / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"meta.json not found: {meta_path}")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    working_dir = Path(meta["working_dir"])
    parsed_dir = Path(meta["parsed_dir"])
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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test DomainKnowledgeExtractionAgent")
    parser.add_argument(
        "--doc_id",
        default=_DEFAULT_DOC_ID,
        help=f"Document ID to test (default: {_DEFAULT_DOC_ID}). "
             f"Available: {list(_DOCS.keys())}",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Override output JSON path (default: runtime/source/<doc_id>/domain_knowledge.json)",
    )
    parser.add_argument(
        "--agent_timeout",
        type=float,
        default=1200.0,
        help="Outer agent timeout in seconds (default: 1200)",
    )
    parser.add_argument(
        "--shell_timeout",
        type=int,
        default=720,
        help="Shell command timeout for run.py in seconds (default: 720)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main test
# ---------------------------------------------------------------------------

async def main() -> None:
    args = _parse_args()

    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_PROJECT", "domain-agent-test")

    doc_id = args.doc_id
    doc_label = _DOCS.get(doc_id, doc_id)

    logger.info("=== DomainKnowledgeExtractionAgent Test ===")
    logger.info("doc_id : %s", doc_id)
    logger.info("file   : %s", doc_label)

    # 1. Build doc_meta
    doc_meta = _build_doc_meta(doc_id)
    logger.info("doc_meta: %s", {k: v for k, v in doc_meta.items() if k != "log"})

    # 2. Build LLM
    llm = _build_default_llm()

    # 3. Create the top-level domain agent
    agent = DomainKnowledgeExtractionAgent(
        doc_meta=doc_meta,
        llm=llm,
        output_path=args.output,
        shell_timeout=args.shell_timeout,
        agent_timeout=args.agent_timeout,
    )

    logger.info("Output path: %s", agent._output_path)
    logger.info("Skills dir : %s", agent._skills_dir)

    # 4. Run extraction
    result = await agent.run()

    # 5. Validate and print result
    print("\n===== DomainKnowledgeExtractionAgent Result =====")

    if not result:
        print("⚠  Extraction returned empty result.")
        return

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nTop-level keys: {list(result.keys())}")

    # Basic assertions
    assert isinstance(result, dict), "Result must be a dict"
    assert len(result) > 0, "Result must not be empty"

    # Warn if it looks like an error fallback
    if "raw_output" in result:
        logger.warning(
            "Result contains 'raw_output' — the agent may not have written the JSON file. "
            "Check stderr for run.py errors."
        )
    else:
        # Expect product-knowledge keys for all current test docs (all are product manuals)
        product_keys = {"product", "components", "features", "parameters", "attributes"}
        medical_keys = {"service", "procedures", "medications", "diagnostic_criteria", "contraindications"}
        found_keys = set(result.keys())

        if found_keys & product_keys:
            logger.info("✓ Skill identified: product-knowledge")
            for key in sorted(product_keys & found_keys):
                val = result[key]
                if isinstance(val, list):
                    logger.info("  ✓ %s: %d items", key, len(val))
                elif isinstance(val, dict):
                    logger.info("  ✓ %s: dict with keys %s", key, list(val.keys()))
        elif found_keys & medical_keys:
            logger.info("✓ Skill identified: medical-service")
            for key in sorted(medical_keys & found_keys):
                val = result[key]
                if isinstance(val, list):
                    logger.info("  ✓ %s: %d items", key, len(val))
                elif isinstance(val, dict):
                    logger.info("  ✓ %s: dict with keys %s", key, list(val.keys()))
        else:
            logger.warning("⚠ Result keys don't match any known skill: %s", found_keys)

    print("\n✅ All assertions passed.")

    logger.info("Output file: %s", agent._output_path)
    if agent._output_path.exists():
        logger.info("Output file size: %d bytes", agent._output_path.stat().st_size)

    await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
