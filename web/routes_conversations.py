from __future__ import annotations

import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from .rag_service import answer_question
from .schemas import ConversationCreate, MessageCreate
from .settings import HISTORY_DIR
from .storage import _conversation_path, _doc_meta_path, _read_json, _write_json
from .utils import _now_iso


router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("")
async def list_conversations() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not HISTORY_DIR.exists():
        return items
    for p in sorted(HISTORY_DIR.glob("*.json")):
        conv = _read_json(p, default=None)
        if not isinstance(conv, dict):
            continue
        items.append(
            {
                "conversation_id": conv.get("conversation_id") or p.stem,
                "doc_id": conv.get("doc_id"),
                "title": conv.get("title"),
                "created_at": conv.get("created_at"),
                "updated_at": conv.get("updated_at"),
            }
        )
    items.sort(key=lambda x: x.get("updated_at") or x.get("created_at") or "", reverse=True)
    return items


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: str) -> Dict[str, Any]:
    conv = _read_json(_conversation_path(conversation_id), default=None)
    if not isinstance(conv, dict):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.post("")
async def create_conversation(payload: ConversationCreate) -> Dict[str, Any]:
    meta = _read_json(_doc_meta_path(payload.doc_id), default=None)
    if not isinstance(meta, dict) or meta.get("status") != "ready":
        raise HTTPException(status_code=400, detail="指定的文档不存在或尚未解析完成")

    conversation_id = uuid.uuid4().hex
    now = _now_iso()
    conv: Dict[str, Any] = {
        "conversation_id": conversation_id,
        "doc_id": payload.doc_id,
        "title": payload.title or meta.get("file_name") or f"Conversation {conversation_id[:8]}",
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    _write_json(_conversation_path(conversation_id), conv)
    return conv


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    payload: MessageCreate,
) -> Dict[str, Any]:
    question = (payload.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    conv_path = _conversation_path(conversation_id)
    conv = _read_json(conv_path, default=None)
    if not isinstance(conv, dict):
        raise HTTPException(status_code=404, detail="Conversation not found")

    doc_id = conv.get("doc_id")
    doc_meta = _read_json(_doc_meta_path(doc_id), default=None)
    if not isinstance(doc_meta, dict) or doc_meta.get("status") != "ready":
        raise HTTPException(status_code=400, detail="关联文档不存在或尚未解析完成")

    answer, references = await answer_question(doc_meta, question)

    user_msg: Dict[str, Any] = {"role": "user", "content": question}
    assistant_msg: Dict[str, Any] = {
        "role": "assistant",
        "content": answer,
        "references": references,
    }
    conv.setdefault("messages", [])
    conv["messages"].append(user_msg)
    conv["messages"].append(assistant_msg)
    conv["updated_at"] = _now_iso()
    _write_json(conv_path, conv)

    return {
        "answer": answer,
        "conversation_id": conversation_id,
        "references": assistant_msg["references"],
    }

