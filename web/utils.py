from __future__ import annotations

import datetime as dt
import re
from typing import Any, Dict, List


def _now_iso() -> str:
    return dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat()


def _parse_reference_location(content: str) -> Dict[str, Any]:
    """
    从 reference content 中解析位置信息：page_idx, bbox, type, img_path。
    用于生成展示文案并支持 PDF 定位。
    """
    result: Dict[str, Any] = {"page_idx": None, "bbox": None, "type": "text", "img_path": None}

    # page_idx: 'page_idx': 8 或 "page_idx": 8
    m = re.search(r"['\"]?page_idx['\"]?\s*:\s*(\d+)", content)
    if m:
        result["page_idx"] = int(m.group(1))

    # bbox: [x, y, w, h] 或 [x1, y1, x2, y2]
    m = re.search(r"['\"]?bbox['\"]?\s*:\s*\[([^\]]+)\]", content)
    if m:
        try:
            result["bbox"] = [float(x.strip()) for x in m.group(1).split(",")]
        except (ValueError, AttributeError):
            pass

    # type: 'type': 'image' | 'table' | 'page_number' | 'footer' 等
    m = re.search(r"['\"]?type['\"]?\s*:\s*['\"]([^'\"]+)['\"]", content)
    if m:
        result["type"] = m.group(1).lower()

    # Image Path: /absolute/path/to/image.jpg
    m = re.search(r"Image\s+Path:\s*([^\s\n]+\.(?:jpg|jpeg|png|gif|webp|bmp))", content, re.I)
    if m:
        result["img_path"] = m.group(1).strip()
        if result["type"] == "text":
            result["type"] = "image" if "image" in content[:200].lower() else "table"

    # Table/Image 分析块中的 Image Path
    if not result["img_path"]:
        m = re.search(r"(?:Table|Image)\s+Analysis:.*?Image\s+Path:\s*([^\s\n]+\.(?:jpg|jpeg|png|gif|webp|bmp))", content, re.S | re.I)
        if m:
            result["img_path"] = m.group(1).strip()
            result["type"] = "table" if "Table Analysis" in content[:100] else "image"

    return result


def _reference_display_label(ref: Dict[str, Any], index: int) -> str:
    """生成引用的展示文案。"""
    loc = _parse_reference_location(ref.get("content", ""))
    page_idx = loc.get("page_idx")
    ref_type = loc.get("type", "text")

    if ref_type == "image":
        return f"第 {page_idx + 1} 页 · 图片" if page_idx is not None else "图片"
    if ref_type == "table":
        return f"第 {page_idx + 1} 页 · 表格" if page_idx is not None else "表格"
    if page_idx is not None:
        return f"第 {page_idx + 1} 页"
    return f"引用 {index + 1}"


def _format_references_markdown(references: List[Dict[str, Any]]) -> str:
    """
    将引用列表格式化为 Markdown 的 `### References` 区块。

    约定：
    - 每条形如 `- [id] label`，id 为数字字符串。
    - label 优先使用 display_label，其次回退到 _reference_display_label。
    - 如有 img_rel_path，则附加在末尾，便于人工识别图片来源。
    """
    if not references:
        return ""

    items: List[str] = []
    for i, ref in enumerate(references):
        # reference_id 为空时用顺序号兜底
        ref_id = str(ref.get("reference_id") or (i + 1))
        label = ref.get("display_label") or _reference_display_label(ref, i)
        img_rel_path = ref.get("img_rel_path")

        extra = f" · {img_rel_path}" if img_rel_path else ""
        items.append(f"- [{ref_id}] {label}{extra}")

    if not items:
        return ""

    return "### References\n\n" + "\n".join(items)


def _extract_reference_ids_from_answer(answer: str) -> List[str]:
    """
    从模型回答中的 `### References` 区块解析出被引用的 id 列表。

    预期格式：
        ### References

        - [3] Document Title One
        - [4] Document Title Two
        ...

    返回值为字符串形式的数字 id 列表，如 ["3", "4", "5"]，按出现顺序排列。
    若未找到 `### References` 或没有合法条目，则返回空列表。
    """
    # 找到 "### References" 开头的位置
    m = re.search(r"^### References\s*$", answer, re.MULTILINE)
    if not m:
        return []

    start = m.end()
    refs_block = answer[start:]

    ids: List[str] = []
    for line in refs_block.splitlines():
        line = line.strip()
        if not line:
            continue
        # 匹配形如 "- [3] xxx" 的行
        m_line = re.match(r"^-\s*\[(\d+)\]", line)
        if m_line:
            ids.append(m_line.group(1))

    return ids



