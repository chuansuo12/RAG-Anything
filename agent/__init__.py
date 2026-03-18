"""
Agent utilities for RAG-Anything.

This package provides two extraction architectures (both coexist):

Pipeline architecture (product-schema-specific):
- `ProductInfoPipeline`: deterministic Python pipeline for product info
  extraction — sub-agents write JSON files, pipeline merges at the end.

Skill architecture (schema-agnostic):
- `SkillSupervisor`: schema-driven supervisor that activates skills to
  extract any domain knowledge defined by an arbitrary JSON schema.
- `SkillRegistry`: maps skill names to implementation classes.
- Individual skills: `SchemaAnalyzeSkill`, `ScalarExtractSkill`,
  `ListDiscoverSkill`, `ItemDetailSkill`, `MergeSkill`.

Shared:
- `build_rag_agent_tools`: helpers to construct tools that wrap the
  RAG-Anything query and context APIs for a given knowledge base.
- `run_qa_agent`: Q&A Agent pipeline (retrieval + verification + retry).
- `get_last_ai_message_content`: 从 Agent 返回的 messages 中取出最后一次 AI 消息的 content。
"""

from .agent import create_rag_qa_orchestrator_agent
from .domain_agent import DomainKnowledgeExtractionAgent, create_dke_agent
from .pipeline import ProductInfoPipeline
from .skill_supervisor import FileSkillSupervisor, load_skill, SkillDef
from .skill import (
    SkillSupervisor,
    SkillRegistry,
    SkillContext,
    SkillResult,
    SkillPlan,
    SkillStep,
    BaseSkill,
    SchemaAnalyzeSkill,
    ScalarExtractSkill,
    ListDiscoverSkill,
    ItemDetailSkill,
    MergeSkill,
)
from .tools import build_rag_agent_tools
from .qa_agent import run_qa_agent
from .util import (
    get_last_ai_message_content,
    serialize_agent_messages_to_dicts,
)

__all__ = [
    # Domain knowledge agent
    "DomainKnowledgeExtractionAgent",
    "create_dke_agent",
    # Pipeline architecture
    "ProductInfoPipeline",
    # Skill architecture
    "FileSkillSupervisor",
    "load_skill",
    "SkillDef",
    "SkillSupervisor",
    "SkillRegistry",
    "SkillContext",
    "SkillResult",
    "SkillPlan",
    "SkillStep",
    "BaseSkill",
    "SchemaAnalyzeSkill",
    "ScalarExtractSkill",
    "ListDiscoverSkill",
    "ItemDetailSkill",
    "MergeSkill",
    # Shared
    "create_rag_qa_orchestrator_agent",
    "build_rag_agent_tools",
    "run_qa_agent",
    "get_last_ai_message_content",
    "serialize_agent_messages_to_dicts",
]
