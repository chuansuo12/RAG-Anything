"""
Agent utilities for RAG-Anything.

This package provides:

- `create_product_info_orchestrator_agent`: build a parent Agent that
  only has the CreateAndRunAgentTool capability and orchestrates
  sub-Agents to fill a product info JSON schema.
- `build_rag_agent_tools`: helpers to construct tools that wrap the
  RAG-Anything query and context APIs for a given knowledge base.
- `run_qa_agent`: Q&A Agent pipeline (retrieval + verification + retry).
- `get_last_ai_message_content`: 从 Agent 返回的 messages 中取出最后一次 AI 消息的 content。
"""

from .agent import create_product_info_orchestrator_agent
from .tools import build_rag_agent_tools
from .qa_agent import run_qa_agent
from .util import get_last_ai_message_content

__all__ = [
    "create_product_info_orchestrator_agent",
    "build_rag_agent_tools",
    "run_qa_agent",
    "get_last_ai_message_content",
]

