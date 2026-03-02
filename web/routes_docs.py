from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .rag_service import (
    build_rag_index_for_pdf,
    get_doc_graph,
    get_doc_graph_node_detail,
)
from .settings import HISTORY_DIR, SOURCE_DIR
from .storage import _doc_dir, _doc_meta_path, _read_json, _write_json
from .utils import _now_iso


router = APIRouter(prefix="/api/docs", tags=["knowledge-base"])


@router.get("")
async def list_docs() -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []
    if not SOURCE_DIR.exists():
        return docs
    for doc_path in sorted(SOURCE_DIR.iterdir()):
        if not doc_path.is_dir():
            continue
        meta = _read_json(doc_path / "meta.json", default=None)
        if not isinstance(meta, dict):
            continue
        docs.append(
            {
                "doc_id": meta.get("doc_id") or doc_path.name,
                "file_name": meta.get("file_name"),
                "status": meta.get("status", "unknown"),
                "created_at": meta.get("created_at"),
            }
        )
    docs.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return docs


@router.get("/{doc_id}")
async def get_doc(doc_id: str) -> Dict[str, Any]:
    meta = _read_json(_doc_meta_path(doc_id), default=None)
    if not isinstance(meta, dict):
        raise HTTPException(status_code=404, detail="知识库不存在")
    return meta


@router.get("/{doc_id}/graph")
async def get_doc_graph_endpoint(doc_id: str) -> Dict[str, Any]:
    """
    返回指定知识库的图数据（基于 LightRAG 构建的实体关系图）。
    """
    meta = _read_json(_doc_meta_path(doc_id), default=None)
    if not isinstance(meta, dict):
        raise HTTPException(status_code=404, detail="知识库不存在")
    if meta.get("status") != "ready":
        raise HTTPException(status_code=400, detail="知识库尚未就绪，无法加载图数据")

    return get_doc_graph(meta)


@router.get("/{doc_id}/graph/node")
async def get_doc_graph_node_endpoint(doc_id: str, node_id: str) -> Dict[str, Any]:
    """
    返回指定知识库中某个节点的详细信息，用于前端点击节点时按需加载。
    """
    meta = _read_json(_doc_meta_path(doc_id), default=None)
    if not isinstance(meta, dict):
        raise HTTPException(status_code=404, detail="知识库不存在")
    if meta.get("status") != "ready":
        raise HTTPException(status_code=400, detail="知识库尚未就绪，无法加载图数据")

    return get_doc_graph_node_detail(meta, node_id)


@router.get("/{doc_id}/pdf")
async def get_doc_pdf(doc_id: str) -> FileResponse:
    """
    返回绑定知识库的原始 PDF 文件。
    """
    meta = _read_json(_doc_meta_path(doc_id), default=None)
    if not isinstance(meta, dict):
        raise HTTPException(status_code=404, detail="知识库不存在")

    pdf_path = meta.get("pdf_path")
    if not pdf_path:
        raise HTTPException(status_code=404, detail="该知识库未找到对应 PDF")

    path_obj = Path(pdf_path)
    if not path_obj.exists():
        raise HTTPException(status_code=404, detail="PDF 文件在磁盘上不存在")

    return FileResponse(
        path_obj,
        media_type="application/pdf",
        filename=path_obj.name,
    )


@router.get("/{doc_id}/parsed-asset")
async def get_doc_parsed_asset(doc_id: str, path: str) -> FileResponse:
    """
    返回解析目录中的资源（如图片）。path 为相对于知识库目录的路径，如 parsed/xxx/images/yyy.jpg。
    """
    meta = _read_json(_doc_meta_path(doc_id), default=None)
    if not isinstance(meta, dict):
        raise HTTPException(status_code=404, detail="知识库不存在")

    doc_path = _doc_dir(doc_id).resolve()
    if not doc_path.exists():
        raise HTTPException(status_code=404, detail="知识库目录不存在")

    # 防止路径遍历
    if ".." in path or path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid path")

    asset_path = (doc_path / path).resolve()
    if not asset_path.exists() or not asset_path.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")

    if not str(asset_path).startswith(str(doc_path)):
        raise HTTPException(status_code=403, detail="Access denied")

    suffix = asset_path.suffix.lower()
    media_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }
    media_type = media_types.get(suffix, "application/octet-stream")

    return FileResponse(asset_path, media_type=media_type, filename=asset_path.name)


@router.delete("/{doc_id}")
async def delete_doc(doc_id: str) -> Dict[str, Any]:
    """
    删除指定知识库目录，并清理与之关联的会话历史。
    """
    doc_path = _doc_dir(doc_id)
    if not doc_path.exists():
        raise HTTPException(status_code=404, detail="知识库不存在")

    # 清理关联会话
    deleted_conversations = 0
    if HISTORY_DIR.exists():
        for p in HISTORY_DIR.glob("*.json"):
            conv = _read_json(p, default=None)
            if isinstance(conv, dict) and conv.get("doc_id") == doc_id:
                try:
                    p.unlink()
                    deleted_conversations += 1
                except Exception:
                    # 某些文件可能被占用或已删除，忽略单个错误，继续处理
                    continue

    # 删除知识库目录
    try:
        shutil.rmtree(doc_path)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"删除知识库失败: {exc}") from exc

    return {
        "doc_id": doc_id,
        "deleted": True,
        "deleted_conversations": deleted_conversations,
    }


@router.post("/upload")
async def upload_doc(file: UploadFile = File(...)) -> Dict[str, Any]:
    filename = file.filename or "knowledge_base.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件")

    doc_id = uuid.uuid4().hex
    doc_path = _doc_dir(doc_id)
    parsed_root = doc_path / "parsed"
    file_stem = Path(filename).stem or "knowledge_base"
    parsed_dir = parsed_root / file_stem
    working_dir = doc_path / "rag_storage"
    for d in (doc_path, parsed_root, parsed_dir, working_dir):
        d.mkdir(parents=True, exist_ok=True)

    pdf_path = doc_path / "source.pdf"
    with pdf_path.open("wb") as out_f:
        shutil.copyfileobj(file.file, out_f)

    meta: Dict[str, Any] = {
        "doc_id": doc_id,
        "file_name": filename,
        "created_at": _now_iso(),
        "status": "processing",
        "pdf_path": str(pdf_path),
        "parsed_dir": str(parsed_dir),
        "working_dir": str(working_dir),
        "log": [],
    }
    _write_json(_doc_meta_path(doc_id), meta)

    log_lines: List[str] = []
    log_lines.append("开始通过 MinerU 云 API 解析知识库 PDF，并构建 RAG 索引...")

    try:
        await build_rag_index_for_pdf(pdf_path, parsed_dir, working_dir, log_lines)
        meta["status"] = "ready"
        meta["log"] = log_lines
        _write_json(_doc_meta_path(doc_id), meta)
        return {"doc_id": doc_id, "meta": meta}
    except HTTPException:
        # 直接抛出 HTTPException 由 FastAPI 处理
        raise
    except Exception as e:  # noqa: BLE001
        log_lines.append(f"处理知识库失败: {e}")
        meta["status"] = "failed"
        meta["error"] = str(e)
        meta["log"] = log_lines
        _write_json(_doc_meta_path(doc_id), meta)
        raise HTTPException(status_code=500, detail=f"解析失败: {e}")

