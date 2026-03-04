"""
Agent utilities for RAG-Anything.

This package provides:

- `create_rag_agent`: helper to build a LangChain tools agent that can
  accept a custom system prompt and a list of tools.
- `create_product_info_orchestrator_agent`: build a parent Agent that
  only has the CreateAndRunAgentTool capability and orchestrates
  sub-Agents to fill a product info JSON schema.
- `build_rag_agent_tools`: helpers to construct tools that wrap the
  RAG-Anything query and context APIs for a given knowledge base.
"""

from .agent import create_rag_agent, create_product_info_orchestrator_agent
from .tools import build_rag_agent_tools

__all__ = [
    "create_rag_agent",
    "create_product_info_orchestrator_agent",
    "build_rag_agent_tools",
]

