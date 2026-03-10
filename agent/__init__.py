"""
Agent utilities for RAG-Anything.

This package provides:

- `ProductInfoPipeline`: deterministic Python pipeline for product info
  extraction — sub-agents write JSON files, pipeline merges at the end.
- `build_rag_agent_tools`: helpers to construct tools that wrap the
  RAG-Anything query and context APIs for a given knowledge base.
- `run_qa_agent`: Q&A Agent pipeline (retrieval + verification + retry).
- `get_last_ai_message_content`: 从 Agent 返回的 messages 中取出最后一次 AI 消息的 content。
"""

from .agent import create_rag_qa_orchestrator_agent
from .pipeline import ProductInfoPipeline
from .tools import build_rag_agent_tools
from .qa_agent import run_qa_agent
from .util import (
    get_last_ai_message_content,
    serialize_agent_messages_to_dicts,
)

__all__ = [
    "ProductInfoPipeline",
    "create_rag_qa_orchestrator_agent",
    "build_rag_agent_tools",
    "run_qa_agent",
    "get_last_ai_message_content",
    "serialize_agent_messages_to_dicts",
]
