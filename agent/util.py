"""
Agent 包内通用工具。

- `get_last_ai_message_content`: 从 create_agent / LangGraph 返回的 messages 中
  取出最后一次 AI 消息的 content。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union


def _is_ai_message(msg: Any) -> bool:
    """判断单条消息是否为 AI 消息。"""
    if isinstance(msg, dict):
        return msg.get("role") == "assistant"
    # LangChain AIMessage 等对象
    return type(msg).__name__ == "AIMessage" or getattr(msg, "type", None) == "ai"


def _get_message_content(msg: Any) -> Optional[str]:
    """从单条消息中取出 content，兼容 dict 与 LangChain 消息对象。"""
    if isinstance(msg, dict):
        content = msg.get("content")
        return str(content) if content is not None else None
    content = getattr(msg, "content", None)
    if content is None:
        return None
    return str(content) if not isinstance(content, str) else content


def get_last_ai_message_content(
    result: Union[dict, List[Any]],
) -> Optional[str]:
    """
    从 Agent 返回结果中取出「最后一次 AI 消息」的 content。

    入参可以是：
    - 完整返回：`{"messages": [HumanMessage(...), AIMessage(...), ...]}`
    - 或直接传入消息列表：`[HumanMessage(...), AIMessage(...), ...]`

    从列表末尾向前查找第一条 AI 消息，返回其 content 字符串；
    若没有 AI 消息或 content 为空则返回 None。

    Args:
        result: Agent 返回的 state 字典（含 "messages" 键）或 messages 列表。

    Returns:
        最后一次 AI 消息的 content，无则返回 None。
    """
    if result is None:
        return None
    messages: List[Any]
    if isinstance(result, dict):
        messages = result.get("messages") or []
    elif isinstance(result, (list, tuple)):
        messages = list(result)
    else:
        return None
    if not messages:
        return None
    for msg in reversed(messages):
        if _is_ai_message(msg):
            return _get_message_content(msg)
    return None


def _message_role_and_type(msg: Any) -> tuple:
    """Return (role, type) for a single message. type is human/ai/tool/system."""
    if isinstance(msg, dict):
        role = msg.get("role") or msg.get("type")
        if role in ("user", "human"):
            return "user", "human"
        if role in ("assistant", "ai"):
            return "assistant", "ai"
        if role == "tool":
            return "tool", "tool"
        if role == "system":
            return "system", "system"
        return str(role or "unknown"), str(role or "unknown")
    # LangChain message objects
    name = type(msg).__name__
    if "Human" in name:
        return "user", "human"
    if "AI" in name:
        return "assistant", "ai"
    if "Tool" in name:
        return "tool", "tool"
    if "System" in name:
        return "system", "system"
    role = getattr(msg, "type", None) or getattr(msg, "role", None)
    return str(role or "unknown"), str(role or "unknown")


def serialize_agent_messages_to_dicts(
    result: Union[dict, List[Any], None],
) -> List[Dict[str, Any]]:
    """
    将 Agent 返回结果中的 messages 序列化为前端可用的字典列表。
    每条为 {"role": "user"|"assistant"|"tool"|"system", "content": str, "type": str, "name": str?}。
    """
    if result is None:
        return []
    messages: List[Any]
    if isinstance(result, dict):
        messages = result.get("messages") or []
    elif isinstance(result, (list, tuple)):
        messages = list(result)
    else:
        return []
    out: List[Dict[str, Any]] = []
    for msg in messages:
        role, msg_type = _message_role_and_type(msg)
        content = _get_message_content(msg)
        if content is None:
            content = ""
        else:
            content = str(content).strip()
        item: Dict[str, Any] = {
            "role": role,
            "content": content,
            "type": msg_type,
        }
        if isinstance(msg, dict):
            if "name" in msg and msg["name"]:
                item["name"] = str(msg["name"])
        else:
            name = getattr(msg, "name", None)
            if name is not None:
                item["name"] = str(name)
        out.append(item)
    return out
