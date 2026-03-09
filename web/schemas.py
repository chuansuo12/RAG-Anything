from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ConversationCreate(BaseModel):
    doc_id: str
    title: Optional[str] = None


class ConversationUpdate(BaseModel):
    title: Optional[str] = None


class MessageCreate(BaseModel):
    question: str
    kb_version: Optional[str] = "v1"
    use_agent: Optional[bool] = False
    agent_version: Optional[str] = "v1"  # "v1"=编排 Agent, "v2"=qa_agent(检索+验证)

