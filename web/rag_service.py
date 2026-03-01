from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from fastapi import HTTPException

from raganything import RAGAnything, RAGAnythingConfig
from raganything.parser import MineruParser

from llm import embedding_func, llm_model_func, vision_model_func
from llm.qwen_llm import qwen_rerank_model_func

from .mineru_client import _mineru_upload_and_download
from .utils import (
    _parse_reference_location,
    _reference_display_label,
    _extract_reference_ids_from_answer,
)


def _load_content_list_from_parsed_dir(parsed_dir: Path) -> Tuple[List[Dict[str, Any]], str]:
    """
    从 MinerU 解析目录加载 content_list（参考 examples/run_qa_from_parsed_dir.py）。
    目录内需包含 *_{content_list}.json，图片路径会被转为基于该目录的绝对路径。
    """
    parsed_dir = parsed_dir.resolve()
    if not parsed_dir.is_dir():
        raise FileNotFoundError(f"解析目录不存在: {parsed_dir}")

    candidates = list(parsed_dir.glob("*_content_list.json"))
    if not candidates:
        raise FileNotFoundError(
            f"在 {parsed_dir} 下未找到 *_content_list.json，请确认是 MinerU 解析输出目录"
        )

    json_path = candidates[0]
    file_stem = json_path.stem.replace("_content_list", "")

    content_list, _ = MineruParser._read_output_files(parsed_dir, file_stem, method="auto")
    if not content_list:
        raise ValueError(f"content_list 为空: {json_path}")
    return content_list, str(parsed_dir)


async def build_rag_index_for_pdf(
    pdf_path: Path,
    parsed_dir: Path,
    working_dir: Path,
    log_lines: List[str],
) -> None:
    """
    通过 MinerU 解析 PDF，并将结果插入 RAGAnything 索引。
    """
    # 1. 调用 MinerU 云 API 完成解析并下载结果
    from asyncio import to_thread

    await to_thread(_mineru_upload_and_download, pdf_path, parsed_dir, log_lines)

    # 2. 从解析目录加载 content_list
    content_list, file_path_ref = _load_content_list_from_parsed_dir(parsed_dir)
    log_lines.append(f"已从 MinerU 解析目录加载 {len(content_list)} 个内容块。")

    # 3. 使用 RAGAnything 将 content_list 插入 LightRAG
    config = RAGAnythingConfig(
        working_dir=str(working_dir),
        parser="mineru",
        parse_method="auto",
        parser_output_dir=str(parsed_dir),
    )

    rag = RAGAnything(
        config=config,
        llm_model_func=llm_model_func,
        vision_model_func=vision_model_func,
        embedding_func=embedding_func,
        lightrag_kwargs={
            "rerank_model_func": qwen_rerank_model_func,
        },
    )

    log_lines.append("正在将解析结果插入 RAG 索引...")
    await rag.insert_content_list(
        content_list=content_list,
        file_path=file_path_ref,
        display_stats=True,
    )

    log_lines.append("解析与索引构建完成。")


async def answer_question(
    doc_meta: Dict[str, Any], question: str
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    问答并返回引用文档块。

    Returns:
        tuple: (answer_text, references)
            references: 检索到的文档块列表，每项含 content, file_path, chunk_id, reference_id
    """
    working_dir = doc_meta.get("working_dir")
    if not working_dir:
        raise RuntimeError("文档工作目录缺失")

    # 使用与构建索引时一致的配置来重新加载 LightRAG 索引
    parsed_dir = doc_meta.get("parsed_dir")
    config = RAGAnythingConfig(
        working_dir=str(working_dir),
        parser="mineru",
        parse_method="auto",
        parser_output_dir=str(parsed_dir) if parsed_dir else None,
    )

    rag = RAGAnything(
        config=config,
        llm_model_func=llm_model_func,
        vision_model_func=vision_model_func,
        embedding_func=embedding_func,
        lightrag_kwargs={
            "rerank_model_func": qwen_rerank_model_func,
        },
    )

    # 确保基于已有 working_dir 初始化 / 加载 LightRAG 实例
    await rag._ensure_lightrag_initialized()

    try:
        answer, references = await rag.aquery_with_references(question, mode="hybrid")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"生成回答失败: {e}")

    # 解析位置信息并生成展示文案
    doc_dir = Path(doc_meta.get("working_dir", "")).resolve().parent
    enriched = []
    for i, ref in enumerate(references):
        loc = _parse_reference_location(ref.get("content", ""))
        r = {
            **ref,
            "page_idx": loc.get("page_idx"),
            "bbox": loc.get("bbox"),
            "ref_type": loc.get("type", "text"),
            "display_label": _reference_display_label(ref, i),
        }
        img_path = loc.get("img_path")
        if img_path:
            p = Path(img_path)
            try:
                rel = p.relative_to(doc_dir)
                r["img_rel_path"] = str(rel)
            except ValueError:
                pass
        enriched.append(r)

    # 解析模型回答中的 "### References" 区块，提取被引用的 id，
    # 只保留这些 id 对应的引用，并按出现顺序排序。
    selected_ids = _extract_reference_ids_from_answer(answer)
    if selected_ids:
        order = {ref_id: idx for idx, ref_id in enumerate(selected_ids)}

        def _key(ref: Dict[str, Any]) -> int:
            rid = str(ref.get("reference_id") or "")
            return order.get(rid, len(order) + 1)

        # 先过滤掉未在 References 中出现的引用
        enriched = [
            ref for ref in enriched if str(ref.get("reference_id") or "") in order
        ]
        # 再按 References 中的顺序排序
        enriched.sort(key=_key)

    # 不改写 LLM 原始回答内容，保留其自身生成的 "### References" 区块。
    return answer, enriched


