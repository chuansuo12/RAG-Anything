from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .rag_service import (
    build_rag_index_for_pdf,
    _resolve_working_dir_for_version,
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
async def get_doc_graph_endpoint(
    doc_id: str,
    q: str | None = None,
    with_neighbors: bool = True,
    version: str = "v1",
) -> Dict[str, Any]:
    """
    返回指定知识库的图数据（基于 LightRAG 构建的实体关系图）。
    """
    meta = _read_json(_doc_meta_path(doc_id), default=None)
    if not isinstance(meta, dict):
        raise HTTPException(status_code=404, detail="知识库不存在")
    if meta.get("status") != "ready":
        raise HTTPException(status_code=400, detail="知识库尚未就绪，无法加载图数据")

    if (version or "v1").lower() == "v2":
        meta = {**meta, "working_dir": _resolve_working_dir_for_version(meta, "v2")}
    return get_doc_graph(meta, query=q, with_neighbors=with_neighbors)


@router.get("/{doc_id}/graph/node")
async def get_doc_graph_node_endpoint(
    doc_id: str, node_id: str, version: str = "v1"
) -> Dict[str, Any]:
    """
    返回指定知识库中某个节点的详细信息，用于前端点击节点时按需加载。
    """
    meta = _read_json(_doc_meta_path(doc_id), default=None)
    if not isinstance(meta, dict):
        raise HTTPException(status_code=404, detail="知识库不存在")
    if meta.get("status") != "ready":
        raise HTTPException(status_code=400, detail="知识库尚未就绪，无法加载图数据")

    if (version or "v1").lower() == "v2":
        meta = {**meta, "working_dir": _resolve_working_dir_for_version(meta, "v2")}
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


@router.get("/{doc_id}/product-schema")
async def get_doc_product_schema(doc_id: str) -> FileResponse:
    """
    返回该知识库的结构化领域知识 JSON。

    查找顺序：
    1. domain_knowledge.json（DomainKnowledgeExtractionAgent 输出，优先）
    2. rag_storage_v2/product info.json（旧版 generate_product_schema_v2 输出，兼容）
    """
    meta = _read_json(_doc_meta_path(doc_id), default=None)
    if not isinstance(meta, dict):
        raise HTTPException(status_code=404, detail="知识库不存在")
    if meta.get("status") != "ready":
        raise HTTPException(status_code=400, detail="知识库尚未就绪，无法获取 product schema")

    # 1. DKE Agent 输出（新）
    dk_path = (_doc_dir(doc_id) / "domain_knowledge.json").resolve()
    if dk_path.exists():
        return FileResponse(
            dk_path,
            media_type="application/json",
            filename="domain_knowledge.json",
        )

    # 2. 旧 v2 product info（兼容）
    v2_dir = _resolve_working_dir_for_version(meta, "v2")
    if not v2_dir:
        raise HTTPException(status_code=404, detail="未找到 v2 工作目录")

    info_path = Path(v2_dir).resolve() / "product info.json"
    if not info_path.exists():
        raise HTTPException(status_code=404, detail="该知识库尚未生成 product info（v2）")

    return FileResponse(
        info_path,
        media_type="application/json",
        filename="product info.json",
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
async def upload_doc(
    file: UploadFile = File(...),
    kb_version: str = Form("v1"),
    force_v1_then_v2: bool = Form(False),
) -> Dict[str, Any]:
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
        result = await build_rag_index_for_pdf(
            pdf_path,
            parsed_dir,
            working_dir,
            log_lines,
            kb_version=kb_version,
            force_v1_then_v2=force_v1_then_v2,
        )
        if isinstance(result, dict):
            meta["content_doc_id"] = result.get("content_doc_id")
            if result.get("working_dir_v2"):
                meta["working_dir_v2"] = result.get("working_dir_v2")
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


@router.post("/{doc_id}/generate-v2")
async def generate_v2_index(
    doc_id: str,
    force_v1_then_v2: bool = Form(False),
) -> Dict[str, Any]:
    """
    为已有知识库生成 v2 索引（产品 schema + rag_storage_v2）。

    - 默认：基于现有 v1 索引直接生成/更新 v2
    - force_v1_then_v2=True：先清理并重建 v1，再生成 v2（更耗时）
    """
    meta = _read_json(_doc_meta_path(doc_id), default=None)
    if not isinstance(meta, dict):
        raise HTTPException(status_code=404, detail="知识库不存在")
    if meta.get("status") != "ready":
        raise HTTPException(status_code=400, detail="知识库尚未就绪，无法生成 v2")

    parsed_dir = Path(str(meta.get("parsed_dir") or "")).resolve()
    working_dir = Path(str(meta.get("working_dir") or "")).resolve()
    if not parsed_dir.exists() or not working_dir.exists():
        raise HTTPException(status_code=400, detail="缺少解析目录或 v1 工作目录，无法生成 v2")

    from .rag_service import _load_content_list_from_parsed_dir
    from raganything import RAGAnything, RAGAnythingConfig
    from llm import embedding_func, llm_model_func, vision_model_func
    from llm.qwen_llm import qwen_rerank_model_func
    import shutil

    log_lines: List[str] = list(meta.get("log") or [])
    log_lines.append("开始生成 v2 索引...")

    # Optional rebuild v1 from parsed outputs
    if force_v1_then_v2:
        try:
            if working_dir.exists():
                shutil.rmtree(working_dir)
            v2_dir = working_dir.with_name("rag_storage_v2")
            if v2_dir.exists():
                shutil.rmtree(v2_dir)
            working_dir.mkdir(parents=True, exist_ok=True)
            log_lines.append("已清理旧 v1/v2 索引目录，将重建 v1 再生成 v2。")
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"清理旧索引目录失败: {e}")

        content_list, file_path_ref = _load_content_list_from_parsed_dir(parsed_dir)
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
        meta["content_doc_id"] = rag._generate_content_based_doc_id(content_list)
        await rag.insert_content_list(
            content_list=content_list,
            file_path=file_path_ref,
            display_stats=False,
        )
        log_lines.append("v1 重建完成。")

    content_doc_id = (meta.get("content_doc_id") or "").strip()
    if not content_doc_id:
        # Fallback: derive from parsed outputs
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
        meta["content_doc_id"] = content_doc_id

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
        raise HTTPException(status_code=500, detail="生成 v2 失败：未得到有效输出")

    meta["working_dir_v2"] = str(v2_dir)
    meta["log"] = log_lines + [f"v2 生成完成：{v2_dir}"]
    _write_json(_doc_meta_path(doc_id), meta)
    return {"doc_id": doc_id, "meta": meta, "working_dir_v2": v2_dir}


@router.post("/{doc_id}/regenerate")
async def regenerate_index(
    doc_id: str,
    include_v2: bool = Form(False),
) -> Dict[str, Any]:
    """
    重新生成索引（不重新解析 PDF）：

    - 重建 v1：清理 working_dir 后，基于 parsed_dir 重建索引
    - 可选 include_v2：在 v1 重建后生成 v2（rag_storage_v2）
    """
    meta = _read_json(_doc_meta_path(doc_id), default=None)
    if not isinstance(meta, dict):
        raise HTTPException(status_code=404, detail="知识库不存在")
    if meta.get("status") != "ready":
        raise HTTPException(status_code=400, detail="知识库尚未就绪，无法重新生成")

    parsed_dir = Path(str(meta.get("parsed_dir") or "")).resolve()
    working_dir = Path(str(meta.get("working_dir") or "")).resolve()
    if not parsed_dir.exists():
        raise HTTPException(status_code=400, detail="缺少解析目录 parsed_dir，无法重新生成")
    if not working_dir.parent.exists():
        raise HTTPException(status_code=400, detail="知识库目录不存在，无法重新生成")

    from .rag_service import _load_content_list_from_parsed_dir
    from raganything import RAGAnything, RAGAnythingConfig
    from llm import embedding_func, llm_model_func, vision_model_func
    from llm.qwen_llm import qwen_rerank_model_func

    log_lines: List[str] = list(meta.get("log") or [])
    log_lines.append("开始重新生成索引...")

    # Clear v1/v2 dirs
    try:
        if working_dir.exists():
            shutil.rmtree(working_dir)
        working_dir.mkdir(parents=True, exist_ok=True)
        v2_dir_path = working_dir.with_name("rag_storage_v2")
        if v2_dir_path.exists():
            shutil.rmtree(v2_dir_path)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"清理旧索引目录失败: {e}")

    content_list, file_path_ref = _load_content_list_from_parsed_dir(parsed_dir)
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

    content_doc_id = rag._generate_content_based_doc_id(content_list)
    meta["content_doc_id"] = content_doc_id
    await rag.insert_content_list(
        content_list=content_list,
        file_path=file_path_ref,
        display_stats=False,
    )
    log_lines.append("v1 重建完成。")

    if include_v2:
        await rag._ensure_lightrag_initialized()
        v2_dir = await rag.generate_product_schema_v2(
            doc_id=content_doc_id,
            file_path_ref=parsed_dir.name,
            force_rebuild_v2=True,
        )
        if not v2_dir:
            raise HTTPException(status_code=500, detail="生成 v2 失败：未得到有效输出")
        meta["working_dir_v2"] = str(v2_dir)
        log_lines.append(f"v2 生成完成：{v2_dir}")

    meta["log"] = log_lines
    _write_json(_doc_meta_path(doc_id), meta)
    return {"doc_id": doc_id, "meta": meta}


@router.post("/{doc_id}/extract-domain")
async def extract_domain_knowledge(doc_id: str) -> Dict[str, Any]:
    """
    使用 DomainKnowledgeExtractionAgent 为指定知识库提取结构化领域知识。

    Agent 自动识别文档类型（product-knowledge / medical-service），激活对应 skill，
    并将结构化 JSON 写入 runtime/source/<doc_id>/domain_knowledge.json。

    结果可通过 GET /api/docs/{doc_id}/product-schema 读取。
    """
    meta = _read_json(_doc_meta_path(doc_id), default=None)
    if not isinstance(meta, dict):
        raise HTTPException(status_code=404, detail="知识库不存在")
    if meta.get("status") != "ready":
        raise HTTPException(status_code=400, detail="知识库尚未就绪，无法提取领域知识")

    # 优先使用 v2 工作目录，以便 RAG 工具访问更完整的知识图谱
    working_dir = _resolve_working_dir_for_version(meta, "v2") or meta.get("working_dir")
    if not working_dir or not Path(str(working_dir)).exists():
        working_dir = meta.get("working_dir")
    if not working_dir:
        raise HTTPException(status_code=400, detail="无法确定工作目录，请先构建知识库索引")

    parsed_dir = meta.get("parsed_dir") or ""
    output_path = _doc_dir(doc_id) / "domain_knowledge.json"

    doc_agent_meta = {
        "doc_id": doc_id,
        "working_dir": str(working_dir),
        "parsed_dir": str(parsed_dir),
        "kb_version": "v2",
    }

    from agent.agent import _build_default_llm
    from agent.domain_agent import DomainKnowledgeExtractionAgent

    llm = _build_default_llm()
    agent = DomainKnowledgeExtractionAgent(
        doc_meta=doc_agent_meta,
        llm=llm,
        output_path=output_path,
    )

    try:
        result = await agent.run()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"领域知识提取失败: {exc}") from exc

    meta["domain_knowledge_path"] = str(output_path)
    _write_json(_doc_meta_path(doc_id), meta)

    return {
        "doc_id": doc_id,
        "output_path": str(output_path),
        "keys": list(result.keys()) if isinstance(result, dict) else [],
    }
