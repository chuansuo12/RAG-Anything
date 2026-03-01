from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .rag_service import build_rag_index_for_pdf
from .settings import SOURCE_DIR
from .storage import _doc_dir, _doc_meta_path, _read_json, _write_json
from .utils import _now_iso


router = APIRouter(prefix="/api/docs", tags=["docs"])


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
        raise HTTPException(status_code=404, detail="Document not found")
    return meta


@router.get("/{doc_id}/pdf")
async def get_doc_pdf(doc_id: str) -> FileResponse:
    """
    返回绑定文档的原始 PDF 文件。
    """
    meta = _read_json(_doc_meta_path(doc_id), default=None)
    if not isinstance(meta, dict):
        raise HTTPException(status_code=404, detail="Document not found")

    pdf_path = meta.get("pdf_path")
    if not pdf_path:
        raise HTTPException(status_code=404, detail="PDF not available for this document")

    path_obj = Path(pdf_path)
    if not path_obj.exists():
        raise HTTPException(status_code=404, detail="PDF file not found on disk")

    return FileResponse(
        path_obj,
        media_type="application/pdf",
        filename=path_obj.name,
    )


@router.get("/{doc_id}/parsed-asset")
async def get_doc_parsed_asset(doc_id: str, path: str) -> FileResponse:
    """
    返回解析目录中的资源（如图片）。path 为相对于 doc 目录的路径，如 parsed/xxx/images/yyy.jpg。
    """
    meta = _read_json(_doc_meta_path(doc_id), default=None)
    if not isinstance(meta, dict):
        raise HTTPException(status_code=404, detail="Document not found")

    doc_path = _doc_dir(doc_id).resolve()
    if not doc_path.exists():
        raise HTTPException(status_code=404, detail="Document directory not found")

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


@router.post("/upload")
async def upload_doc(file: UploadFile = File(...)) -> Dict[str, Any]:
    filename = file.filename or "document.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件")

    doc_id = uuid.uuid4().hex
    doc_path = _doc_dir(doc_id)
    parsed_root = doc_path / "parsed"
    file_stem = Path(filename).stem or "document"
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
    log_lines.append("开始通过 MinerU 云 API 解析文档，并构建 RAG 索引...")

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
        log_lines.append(f"处理失败: {e}")
        meta["status"] = "failed"
        meta["error"] = str(e)
        meta["log"] = log_lines
        _write_json(_doc_meta_path(doc_id), meta)
        raise HTTPException(status_code=500, detail=f"解析失败: {e}")

