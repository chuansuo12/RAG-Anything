#!/usr/bin/env python
"""
Skill runner — executes FileSkillSupervisor for this skill directory.

This script is self-contained: it resolves both the skill directory and the
project root from its own file path, so it works correctly regardless of the
current working directory when invoked.

Usage
-----
    python /path/to/agent/skills/product-knowledge/run.py \\
        --meta_path /path/to/runtime/source/<doc_id>/meta.json \\
        [--output /path/to/output.json]

Arguments
---------
--meta_path   Path to the document's meta.json file (required).
              meta.json must contain: doc_id, working_dir, parsed_dir.
--output      Optional path to write the extracted JSON result.
              If omitted, the result is only printed to stdout.

Output
------
The extracted domain knowledge JSON is always printed to stdout.
If --output is given, the same JSON is also written to that file.
Exit code 0 on success, 1 on error.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path resolution — works from any working directory
# ---------------------------------------------------------------------------

# This script lives at:  agent/skills/<skill-name>/run.py
# Project root is 3 levels up: agent/skills/<skill-name>/../../../
_SKILL_DIR = Path(__file__).parent.resolve()
_PROJECT_ROOT = _SKILL_DIR.parents[2]  # RAG-Anything/

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Project imports (after sys.path is set)
# ---------------------------------------------------------------------------

from agent.agent import _build_default_llm          # noqa: E402
from agent.skill_supervisor import FileSkillSupervisor  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_doc_meta(meta_path: str) -> dict:
    """Load and normalise doc_meta from a meta.json file."""
    path = Path(meta_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"meta.json not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))

    working_dir = Path(raw["working_dir"])
    parsed_dir  = Path(raw["parsed_dir"])

    if not working_dir.exists():
        raise FileNotFoundError(f"working_dir not found: {working_dir}")
    if not parsed_dir.exists():
        raise FileNotFoundError(f"parsed_dir not found: {parsed_dir}")

    return {
        "doc_id":      raw["doc_id"],
        "working_dir": str(working_dir),
        "parsed_dir":  str(parsed_dir),
        "kb_version":  raw.get("kb_version", "v2"),
    }


# ---------------------------------------------------------------------------
# Main async entry point
# ---------------------------------------------------------------------------

async def _run(meta_path: str, output_path: str | None) -> int:
    """Execute the skill and return exit code (0 = success, 1 = error)."""
    try:
        doc_meta = _load_doc_meta(meta_path)
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as exc:
        logger.error("Failed to load doc_meta: %s", exc)
        return 1

    logger.info("Skill dir : %s", _SKILL_DIR)
    logger.info("doc_id    : %s", doc_meta["doc_id"])

    try:
        llm = _build_default_llm()
    except ValueError as exc:
        logger.error("Failed to build LLM: %s", exc)
        return 1

    supervisor = FileSkillSupervisor.from_skill_dir(
        skill_dir=_SKILL_DIR,
        doc_meta=doc_meta,
        llm=llm,
        max_retries=2,
        sub_agent_timeout=180.0,
        max_concurrency=3,
    )

    try:
        result = await supervisor.run()
    except Exception as exc:  # noqa: BLE001
        logger.error("Skill execution failed: %s", exc, exc_info=True)
        return 1
    finally:
        supervisor.cleanup()

    output_json = json.dumps(result, ensure_ascii=False, indent=2)

    # Write to file if requested
    if output_path:
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(output_json, encoding="utf-8")
        logger.info("Result written to: %s", out)

    # Always print to stdout (the calling agent reads this)
    print(output_json)
    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the domain knowledge extraction skill for this directory.",
    )
    parser.add_argument(
        "--meta_path",
        required=True,
        help="Path to the document's meta.json file.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional path to write the extracted JSON result.",
    )
    args = parser.parse_args()

    exit_code = asyncio.run(_run(args.meta_path, args.output))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
