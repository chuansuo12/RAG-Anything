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

from agent import ProductInfoPipeline
from agent.agent import _build_default_llm
from raganything.product import DEFAULT_PRODUCT_INFO_SCHEMA


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

    # 2. Run the deterministic pipeline (recommended)
    llm = _build_default_llm()
    pipeline = ProductInfoPipeline(
        doc_meta=doc_meta,
        schema=DEFAULT_PRODUCT_INFO_SCHEMA,
        llm=llm,
        max_retries=2,
        sub_agent_timeout=180.0,
        max_concurrency=3,
        verbose=True,
    )

    print(f"Temp directory: {pipeline._tmp_dir}")
    product_info = await pipeline.run()

    if product_info:
        print("===== Product info from pipeline =====")
        print(json.dumps(product_info, ensure_ascii=False, indent=2))
    else:
        print("===== Pipeline returned empty result =====")

    print(f"\nIntermediate files preserved at: {pipeline._tmp_dir}")

    # 为了避免退出时的 asyncio 清理日志淹没正常输出，这里额外等待片刻
    await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())

