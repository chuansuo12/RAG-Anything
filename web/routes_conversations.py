from __future__ import annotations

import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from .rag_service import answer_question, answer_question_agent, answer_question_agent_v2
from .schemas import ConversationCreate, ConversationUpdate, MessageCreate
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


@router.patch("/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    payload: ConversationUpdate,
) -> Dict[str, Any]:
    """
    更新会话信息（如标题）。仅更新 payload 中提供的字段。
    """
    conv_path = _conversation_path(conversation_id)
    conv = _read_json(conv_path, default=None)
    if not isinstance(conv, dict):
        raise HTTPException(status_code=404, detail="Conversation not found")

    if payload.title is not None:
        conv["title"] = (payload.title or "").strip() or conv.get("title")
    conv["updated_at"] = _now_iso()
    _write_json(conv_path, conv)
    return conv


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str) -> Dict[str, Any]:
    """
    删除指定会话及其历史记录文件。
    """
    conv_path = _conversation_path(conversation_id)
    conv = _read_json(conv_path, default=None)
    if not isinstance(conv, dict):
        raise HTTPException(status_code=404, detail="Conversation not found")

    # 删除会话文件
    try:
        if conv_path.exists():
            conv_path.unlink()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"删除会话失败: {exc}") from exc

    return {
        "conversation_id": conversation_id,
        "doc_id": conv.get("doc_id"),
        "deleted": True,
    }


@router.post("")
async def create_conversation(payload: ConversationCreate) -> Dict[str, Any]:
    meta = _read_json(_doc_meta_path(payload.doc_id), default=None)
    if not isinstance(meta, dict) or meta.get("status") != "ready":
        raise HTTPException(status_code=400, detail="指定的知识库不存在或尚未解析完成")

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
        raise HTTPException(status_code=400, detail="关联的知识库不存在或尚未解析完成")

    use_agent = getattr(payload, "use_agent", False) or False
    agent_ver = getattr(payload, "agent_version", None) or "v1"
    kb_ver = payload.kb_version or "v1"
    agent_messages: List[Dict[str, Any]] = []

    if use_agent:
        if (agent_ver or "v1").lower() == "v2":
            answer, references, agent_messages = await answer_question_agent_v2(
                doc_meta, question, kb_version=kb_ver
            )
        else:
            answer, references, agent_messages = await answer_question_agent(
                doc_meta, question, kb_version=kb_ver
            )
    else:
        answer, references = await answer_question(doc_meta, question, kb_version=kb_ver)

    user_msg: Dict[str, Any] = {
        "role": "user",
        "content": question,
        "kb_version": kb_ver,
        "agent_version": agent_ver,
        "use_agent": use_agent,
    }
    assistant_msg: Dict[str, Any] = {
        "role": "assistant",
        "content": answer,
        "references": references,
    }
    if agent_messages:
        assistant_msg["agent_messages"] = agent_messages
    conv.setdefault("messages", [])
    conv["messages"].append(user_msg)
    conv["messages"].append(assistant_msg)
    conv["updated_at"] = _now_iso()
    _write_json(conv_path, conv)

    out: Dict[str, Any] = {
        "answer": answer,
        "conversation_id": conversation_id,
        "references": assistant_msg["references"],
    }
    if agent_messages:
        out["agent_messages"] = agent_messages
    return out

