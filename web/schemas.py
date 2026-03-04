from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ConversationCreate(BaseModel):
    doc_id: str
    title: Optional[str] = None


class MessageCreate(BaseModel):
    question: str
    kb_version: Optional[str] = "v1"

