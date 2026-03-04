from __future__ import annotations

"""
Simple test script for the RAGQueryTool.

目录与用法风格参考 `examples/agent_test.py`：
    - 使用同一个 runtime/source 目录下的 v2 索引与解析结果；
    - 直接构建 `RAGQueryTool`，对指定知识库执行一次问答；
    - 便于在不引入 Agent 的情况下，单独验证底层 RAG 查询工具是否工作正常。

Usage (example):
    python -m examples.tool_test
"""

from pathlib import Path

from agent.tools import RAGQueryTool


def _build_doc_meta() -> dict:
    """
    Build a minimal doc_meta for the given runtime directory.

    与 `examples.agent_test._build_doc_meta` 保持一致：
        - working_dir: points to rag_storage_v2
        - parsed_dir: points to the MinerU parsed output
    """
    root = Path("runtime/source/332505f3e56c4733a73a557d792730c7").resolve()
    working_dir_v2 = root / "rag_storage_v2"
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


def main() -> None:
    # 1. 准备当前知识库实例的 doc_meta
    doc_meta = _build_doc_meta()

    # 2. 构建 RAG 查询工具（绑定到该知识库）
    tool = RAGQueryTool(doc_meta=dict(doc_meta))

    # 3. 使用高层/低层关键词调用检索（RAGQueryTool 仅返回 entities）
    hl_keywords = ["product", "user guide", "specifications"]
    ll_keywords = ["name", "brand", "description", "key specifications"]

    # RAGQueryTool 继承自 BaseTool，推荐通过 invoke 入口调用，
    # 以便保持与 LangChain Agents 使用方式一致。
    result = tool.invoke({
        "hl_keywords": hl_keywords,
        "ll_keywords": ll_keywords,
        "top_k": 10,
    })

    # 4. 打印结果，包含答案与引用片段
    print("===== RAGQueryTool test result =====")
    print(result)


if __name__ == "__main__":
    main()

