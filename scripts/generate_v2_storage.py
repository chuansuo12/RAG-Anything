#!/usr/bin/env python
"""
批量生成 v2 版本 RAG Storage 脚本
================================

功能：
- 扫描 source 目录下已有 v1 的文档，为其生成 v2（rag_storage_v2）
- 已存在 v2 的文档跳过
- 日志与汇总写入 runtime/generate/yyyy-MM-dd-HH-mm-ss/

用法示例：
  cd /path/to/RAG-Anything
  python scripts/generate_v2_storage.py --source_root runtime/source
  python scripts/generate_v2_storage.py --source_root runtime/source --limit 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 确保项目根目录在 path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from raganything import RAGAnything, RAGAnythingConfig
from raganything.parser import MineruParser
from raganything.product.resolve import resolve_working_dir_v2
from llm import embedding_func, llm_model_func, vision_model_func
from llm.qwen_llm import qwen_rerank_model_func


def _load_content_list_from_parsed_dir(
    parsed_dir: Path,
    *,
    fix_image_paths: bool = True,
) -> Tuple[List[Dict[str, Any]], str]:
    """从 MinerU 解析目录加载 content_list，用于计算 content_doc_id。"""
    parsed_dir = parsed_dir.resolve()
    if not parsed_dir.is_dir():
        raise FileNotFoundError(f"解析目录不存在: {parsed_dir}")
    candidates = list(parsed_dir.glob("*_content_list.json"))
    if not candidates:
        raise FileNotFoundError(
            f"在 {parsed_dir} 下未找到 *_content_list.json"
        )
    json_path = candidates[0]
    file_stem = json_path.stem.replace("_content_list", "")
    content_list, _ = MineruParser._read_output_files(
        parsed_dir, file_stem, method="auto", fix_image_paths=fix_image_paths
    )
    if not content_list:
        raise ValueError(f"content_list 为空: {json_path}")
    return content_list, str(parsed_dir)


def _read_json(path: Path, default: Any) -> Any:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _ensure_content_doc_id(
    meta: Dict[str, Any],
    parsed_dir: Path,
    working_dir: Path,
    logger: logging.Logger,
) -> str:
    """从 meta 获取或根据 content_list 计算 content_doc_id。"""
    content_doc_id = (meta.get("content_doc_id") or "").strip()
    if content_doc_id:
        return content_doc_id
    content_list, _ = _load_content_list_from_parsed_dir(parsed_dir)
    config = RAGAnythingConfig(
        working_dir=str(working_dir),
        parser="mineru",
        parse_method="auto",
        parser_output_dir=str(parsed_dir),
    )
    rag_tmp = RAGAnything(
        config=config,
        llm_model_func=llm_model_func,
        vision_model_func=vision_model_func,
        embedding_func=embedding_func,
        lightrag_kwargs={"rerank_model_func": qwen_rerank_model_func},
    )
    content_doc_id = rag_tmp._generate_content_based_doc_id(content_list)
    logger.info("从 content_list 计算得到 content_doc_id: %s", content_doc_id[:16] + "...")
    return content_doc_id


async def generate_v2_for_doc(
    doc_id: str,
    meta_path: Path,
    meta: Dict[str, Any],
    working_dir: Path,
    parsed_dir: Path,
    run_dir: Path,
    logger: logging.Logger,
) -> Tuple[str, bool, Optional[str]]:
    """
    为单个文档生成 v2。返回 (doc_id, success, error_message)。
    """
    try:
        content_doc_id = _ensure_content_doc_id(
            meta, parsed_dir, working_dir, logger
        )
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
            lightrag_kwargs={"rerank_model_func": qwen_rerank_model_func},
        )
        await rag._ensure_lightrag_initialized()
        v2_dir = await rag.generate_product_schema_v2(
            doc_id=content_doc_id,
            file_path_ref=parsed_dir.name,
            force_rebuild_v2=True,
        )
        if not v2_dir:
            return (doc_id, False, "generate_product_schema_v2 返回空")
        # 更新 meta.json
        meta["working_dir_v2"] = str(v2_dir)
        log_entries = list(meta.get("log") or [])
        log_entries.append(f"v2 生成完成：{v2_dir}")
        meta["log"] = log_entries
        _write_json(meta_path, meta)
        return (doc_id, True, None)
    except Exception as e:
        import traceback
        msg = str(e)
        tb = traceback.format_exc()
        logger.exception("生成 v2 失败: doc_id=%s", doc_id)
        return (doc_id, False, f"{msg}\n{tb}")


def setup_logging(run_dir: Path) -> logging.Logger:
    """
    配置日志：同时输出到 run_dir/generate.log 和控制台。
    将同一文件 handler 挂到 root logger，以便捕获 lightrag / raganything / agent 等
    内部 logger 的 ERROR/DEBUG 输出（含 generate_product_schema_v2 的详细报错与堆栈）。
    """
    log_file = run_dir / "generate.log"
    run_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    # 让所有库的日志（含 lightrag、raganything、agent）都写入 generate.log
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(fh)

    # 脚本自身 logger：写文件 + 控制台（不向 root 传播，避免重复写入文件）
    logger = logging.getLogger("generate_v2_storage")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.handlers.clear()
    logger.addHandler(fh)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger


def write_summary_md(
    run_dir: Path,
    total: int,
    skipped_no_v1: List[Dict[str, str]],
    skipped_has_v2: List[Dict[str, str]],
    success: List[str],
    failed: List[Dict[str, str]],
) -> None:
    """生成汇总 Markdown 文件。"""
    path = run_dir / "summary.md"
    lines = [
        "# V2 RAG Storage 生成汇总",
        "",
        f"**生成时间**: {run_dir.name}",
        "",
        "## 统计",
        "",
        f"- 扫描文档总数: {total}",
        f"- 跳过（无 v1）: {len(skipped_no_v1)}",
        f"- 跳过（已有 v2）: {len(skipped_has_v2)}",
        f"- 成功: {len(success)}",
        f"- 失败: {len(failed)}",
        "",
    ]
    if failed:
        lines.extend([
            "## 失败明细",
            "",
            "| doc_id | file_name | 原因 |",
            "|--------|-----------|------|",
        ])
        for item in failed:
            doc_id = item.get("doc_id", "")
            file_name = item.get("file_name", "")
            reason = (item.get("reason") or "").replace("\n", " ").strip()[:200]
            if "|" in reason:
                reason = reason.replace("|", "\\|")
            lines.append(f"| {doc_id} | {file_name} | {reason} |")
        lines.append("")
    if skipped_no_v1:
        lines.extend([
            "## 跳过（无 v1）",
            "",
            "| doc_id | file_name |",
            "|--------|-----------|",
        ])
        for item in skipped_no_v1:
            lines.append(f"| {item.get('doc_id', '')} | {item.get('file_name', '')} |")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="批量生成 v2 版本 RAG Storage"
    )
    parser.add_argument(
        "--source_root",
        type=Path,
        default=PROJECT_ROOT / "runtime" / "source",
        help="source 根目录，其下为各 doc 目录（含 meta.json、rag_storage 等）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="最多处理的文档数（用于测试）",
    )
    args = parser.parse_args()
    source_root = args.source_root.resolve()
    if not source_root.exists():
        print(f"source_root 不存在: {source_root}", file=sys.stderr)
        sys.exit(1)

    run_ts = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    run_dir = PROJECT_ROOT / "runtime" / "generate" / run_ts
    run_dir.mkdir(parents=True, exist_ok=True)
    logger = setup_logging(run_dir)
    logger.info("source_root=%s, run_dir=%s", source_root, run_dir)

    skipped_no_v1: List[Dict[str, str]] = []
    skipped_has_v2: List[Dict[str, str]] = []
    success: List[str] = []
    failed: List[Dict[str, str]] = []
    to_process: List[Tuple[Path, Dict[str, Any], Path, Path]] = []

    for meta_path in sorted(source_root.glob("*/meta.json")):
        doc_id = meta_path.parent.name
        try:
            meta = _read_json(meta_path, None)
            if not isinstance(meta, dict):
                logger.warning("跳过 %s: meta.json 无效", doc_id)
                continue
            working_dir_raw = meta.get("working_dir") or ""
            working_dir = (
                Path(working_dir_raw).resolve()
                if working_dir_raw
                else (meta_path.parent / "rag_storage").resolve()
            )
            parsed_dir_raw = meta.get("parsed_dir") or ""
            parsed_dir = (
                Path(parsed_dir_raw).resolve()
                if parsed_dir_raw
                else (meta_path.parent / "parsed").resolve()
            )
            if not working_dir.exists():
                skipped_no_v1.append({
                    "doc_id": doc_id,
                    "file_name": meta.get("file_name") or doc_id,
                })
                logger.info("跳过 %s: v1 不存在 (%s)", doc_id, working_dir)
                continue
            v2_dir = Path(resolve_working_dir_v2(str(working_dir)))
            if v2_dir.exists():
                skipped_has_v2.append({
                    "doc_id": doc_id,
                    "file_name": meta.get("file_name") or doc_id,
                })
                logger.info("跳过 %s: v2 已存在 (%s)", doc_id, v2_dir)
                continue
            if not parsed_dir.exists():
                failed.append({
                    "doc_id": doc_id,
                    "file_name": meta.get("file_name") or doc_id,
                    "reason": f"解析目录不存在: {parsed_dir}",
                })
                logger.warning("失败 %s: 解析目录不存在", doc_id)
                continue
            to_process.append((meta_path, meta, working_dir, parsed_dir))
        except Exception as e:
            logger.exception("扫描 %s 时出错", doc_id)
            failed.append({
                "doc_id": doc_id,
                "file_name": meta.get("file_name", "") if isinstance(meta, dict) else doc_id,
                "reason": str(e),
            })

    all_docs = list(source_root.glob("*/meta.json"))
    total = len(all_docs)
    if args.limit is not None:
        to_process = to_process[: args.limit]
        logger.info("限制处理数量: %d", args.limit)

    logger.info(
        "待生成 v2: %d, 跳过(无v1): %d, 跳过(已有v2): %d, 已失败(缺 parsed): %d",
        len(to_process),
        len(skipped_no_v1),
        len(skipped_has_v2),
        len(failed),
    )

    for meta_path, meta, working_dir, parsed_dir in to_process:
        doc_id = meta_path.parent.name
        file_name = meta.get("file_name") or doc_id
        logger.info("开始生成 v2: doc_id=%s", doc_id)
        _, ok, err = await generate_v2_for_doc(
            doc_id, meta_path, meta, working_dir, parsed_dir, run_dir, logger
        )
        if ok:
            success.append(doc_id)
            logger.info("完成: doc_id=%s", doc_id)
        else:
            failed.append({
                "doc_id": doc_id,
                "file_name": file_name,
                "reason": err or "未知错误",
            })
            logger.error("失败: doc_id=%s, reason=%s", doc_id, err)

    write_summary_md(
        run_dir,
        total=total,
        skipped_no_v1=skipped_no_v1,
        skipped_has_v2=skipped_has_v2,
        success=success,
        failed=failed,
    )
    logger.info(
        "汇总已写入 %s/summary.md；日志 %s/generate.log",
        run_dir,
        run_dir,
    )
    logger.info(
        "统计: 成功=%d, 失败=%d, 跳过(无v1)=%d, 跳过(已有v2)=%d",
        len(success),
        len(failed),
        len(skipped_no_v1),
        len(skipped_has_v2),
    )
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
