#!/usr/bin/env python
"""
仅执行“节点合并”的辅助脚本
================================

使用场景：
- 已经有 v1 知识库（例如 runtime/source/<doc_id>/rag_storage）
- 已经离线生成过 product info.json（例如 runtime/source/<doc_id>/rag_storage_v2/product info.json）
- 现在只想基于现有 product info，将 v1 的图复制到 v2，并做一次节点合并（不重新跑抽取）

脚本逻辑：
1. 传入 v1 working_dir（通常为 rag_storage）
2. 通过 resolve_working_dir_v2 推导出对应的 rag_storage_v2 路径
3. 检查 rag_storage_v2 下是否存在 product info.json，若不存在则报错退出
4. 删除 rag_storage_v2 下除 product info.json 以外的所有文件/子目录
5. 调用 merge_product_info_into_v2_graph：
   - 从 v1 working_dir 复制基础存储到 rag_storage_v2
   - 把 product info.json 中的 product/components/features/parameters/attributes 合并进 v2 图

用法示例：
    cd /path/to/RAG-Anything
    python scripts/merge_nodes_from_v1.py \\
        --working-dir runtime/source/11258b1255cc40b1bfe27f49fdd760fa/rag_storage

可选参数：
    --doc-id           用于标记 source_id=product_info:<doc_id>，默认为 v1 working_dir 的上级目录名
    --product-info     指定 product info.json 路径（默认：自动从 v2 目录中寻找）
    --merge-threshold  节点合并相似度阈值，默认 0.9（与 ProcessorConfig 一致）
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from raganything.product.graph import merge_product_info_into_v2_graph
from raganything.product.resolve import resolve_working_dir_v2
from llm import embedding_func, llm_model_func
from llm.qwen_llm import qwen_rerank_model_func


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"读取 JSON 失败: {path} ({e})") from e


def _cleanup_v2_dir_keep_product_info(v2_dir: Path, product_info_path: Path) -> None:
    """
    删除 v2 目录下除 product info.json 外的所有文件/子目录。
    """
    from shutil import rmtree

    for child in v2_dir.iterdir():
        if child.resolve() == product_info_path.resolve():
            continue
        if child.is_dir():
            rmtree(child)
        else:
            try:
                child.unlink()
            except FileNotFoundError:
                pass


async def _run_merge(
    working_dir: Path,
    doc_id: str,
    product_info_path: Path,
    merge_threshold: float,
) -> str | None:
    """
    执行一次“仅节点合并”的流程：
    - 读取 product info.json
    - 清理 v2 目录（仅保留 product info）
    - 调用 merge_product_info_into_v2_graph 完成从 v1 -> v2 的合并
    """
    working_dir = working_dir.resolve()
    if not working_dir.is_dir():
        raise RuntimeError(f"v1 working_dir 不存在或不是目录: {working_dir}")

    v2_dir_str = resolve_working_dir_v2(str(working_dir))
    v2_dir = Path(v2_dir_str).resolve()
    if not v2_dir.exists():
        # 若 v2 目录不存在，但 product info 在自定义路径下，也允许后续 copytree 时创建
        v2_dir.mkdir(parents=True, exist_ok=True)

    if not product_info_path.exists():
        raise RuntimeError(f"未找到 product info.json: {product_info_path}")

    if not product_info_path.is_file():
        raise RuntimeError(f"product info 路径不是文件: {product_info_path}")

    print(f"[merge] v1 working_dir: {working_dir}")
    print(f"[merge] v2 working_dir: {v2_dir}")
    print(f"[merge] product info:   {product_info_path}")
    print(f"[merge] doc_id:         {doc_id}")
    print(f"[merge] merge_threshold:{merge_threshold}")

    info = _load_json(product_info_path)
    if not isinstance(info, dict) or not info:
        raise RuntimeError(f"product info 内容为空或格式错误: {product_info_path}")

    # 先清理 v2 目录，只保留 product info.json
    _cleanup_v2_dir_keep_product_info(v2_dir, product_info_path)

    # 从 v1 复制存储到 v2，并基于 product info 做节点合并
    lightrag_kwargs = {"rerank_model_func": qwen_rerank_model_func}
    result = await merge_product_info_into_v2_graph(
        doc_id=doc_id,
        file_path_ref=product_info_path.name,
        info=info,
        src_dir=working_dir,
        dst_dir=v2_dir,
        llm_model_func=llm_model_func,
        embedding_func=embedding_func,
        lightrag_kwargs=lightrag_kwargs,
        merge_threshold=merge_threshold,
        force_rebuild_v2=False,
    )
    return result


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="仅基于 product info.json 执行一次从 v1 到 v2 的节点合并",
    )
    parser.add_argument(
        "--working-dir",
        type=Path,
        required=True,
        help="v1 working_dir 路径，通常为 rag_storage 目录",
    )
    parser.add_argument(
        "--doc-id",
        type=str,
        default="",
        help="用于标记 source_id=product_info:<doc_id>，默认取 working_dir 上级目录名",
    )
    parser.add_argument(
        "--product-info",
        type=Path,
        default=None,
        help="product info.json 路径，默认从 v2 目录中自动推导 (rag_storage_v2/product info.json)",
    )
    parser.add_argument(
        "--merge-threshold",
        type=float,
        default=0.9,
        help="合并相似度阈值（与 ProcessorConfig.product_schema_merge_threshold 一致，默认 0.9）",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    working_dir: Path = args.working_dir.resolve()
    if not working_dir.is_dir():
        raise SystemExit(f"指定的 working_dir 不是有效目录: {working_dir}")

    # doc_id 默认取 v1 working_dir 的上级目录名（例如 runtime/source/<doc_id>/rag_storage）
    doc_id = (args.doc_id or working_dir.parent.name).strip()
    if not doc_id:
        raise SystemExit("无法推导 doc_id，请通过 --doc-id 显式指定")

    # product info 路径默认：v2_dir/product info.json
    if args.product_info is not None:
        product_info_path = args.product_info.resolve()
    else:
        v2_dir_str = resolve_working_dir_v2(str(working_dir))
        v2_dir = Path(v2_dir_str).resolve()
        product_info_path = v2_dir / "product info.json"

    merge_threshold = float(args.merge_threshold)

    try:
        result = asyncio.run(
            _run_merge(
                working_dir=working_dir,
                doc_id=doc_id,
                product_info_path=product_info_path,
                merge_threshold=merge_threshold,
            )
        )
    except Exception as e:  # noqa: BLE001
        print(f"[merge] 合并失败: {e}")
        raise SystemExit(1) from e

    if not result:
        print("[merge] merge_product_info_into_v2_graph 返回空结果（可能 product info 为空）。")
        raise SystemExit(1)

    print(f"[merge] 节点合并完成，v2 working_dir: {result}")


if __name__ == "__main__":
    main()

