from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple
import xml.etree.ElementTree as ET

from fastapi import HTTPException

from raganything import RAGAnything, RAGAnythingConfig
from raganything.parser import MineruParser
from raganything.cache import default_rag_cache

from llm import embedding_func, llm_model_func, vision_model_func
from llm.qwen_llm import qwen_rerank_model_func

from .mineru_client import _mineru_upload_and_download
from .utils import (
    _parse_reference_location,
    _reference_display_label,
    _extract_reference_ids_from_answer,
)


def _load_content_list_from_parsed_dir(
    parsed_dir: Path,
    *,
    fix_image_paths: bool = True,
) -> Tuple[List[Dict[str, Any]], str]:
    """
    从 MinerU 解析目录加载 content_list（参考 examples/run_qa_from_parsed_dir.py）。
    目录内需包含 *_{content_list}.json。
    fix_image_paths=True 时会把图片路径转为绝对路径；False 时仅读 JSON 不做路径处理（简版/只读，如 agent 按页取上下文）。
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

    content_list, _ = MineruParser._read_output_files(
        parsed_dir, file_stem, method="auto", fix_image_paths=fix_image_paths
    )
    if not content_list:
        raise ValueError(f"content_list 为空: {json_path}")
    return content_list, str(parsed_dir)


def load_content_list_read_only(parsed_dir: Path) -> Tuple[List[Dict[str, Any]], str]:
    """
    简版加载：仅读取 content_list JSON，不重写图片路径。
    适用于只需按页取文本上下文的场景（如 agent kb_page_context），避免重复 fix image paths。
    """
    return _load_content_list_from_parsed_dir(parsed_dir, fix_image_paths=False)


async def build_rag_index_for_pdf(
    pdf_path: Path,
    parsed_dir: Path,
    working_dir: Path,
    log_lines: List[str],
    kb_version: str = "v1",
    force_v1_then_v2: bool = False,
) -> Dict[str, Any]:
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
    if (kb_version or "v1").lower() == "v2":
        config.enable_product_schema_extraction = True

    rag = RAGAnything(
        config=config,
        llm_model_func=llm_model_func,
        vision_model_func=vision_model_func,
        embedding_func=embedding_func,
        lightrag_kwargs={
            "rerank_model_func": qwen_rerank_model_func,
        },
    )

    if force_v1_then_v2 and (kb_version or "v1").lower() == "v2":
        import shutil

        try:
            if working_dir.exists():
                shutil.rmtree(working_dir)
            v2_dir = working_dir.with_name("rag_storage_v2")
            if v2_dir.exists():
                shutil.rmtree(v2_dir)
            working_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:  # noqa: BLE001
            log_lines.append(f"清理旧索引目录失败（将继续尝试构建）：{e}")

    log_lines.append("正在将解析结果插入 RAG 索引...")
    content_doc_id = rag._generate_content_based_doc_id(content_list)
    await rag.insert_content_list(
        content_list=content_list,
        file_path=file_path_ref,
        display_stats=True,
    )

    log_lines.append("解析与索引构建完成。")
    if (kb_version or "v1").lower() == "v2":
        v2_dir = working_dir.with_name("rag_storage_v2")
        if v2_dir.exists():
            log_lines.append(f"已生成 v2 索引：{v2_dir}")

    result: Dict[str, Any] = {"content_doc_id": content_doc_id}
    if (kb_version or "v1").lower() == "v2":
        v2_dir = working_dir.with_name("rag_storage_v2")
        result["working_dir_v2"] = str(v2_dir)
    return result


def _resolve_working_dir_for_version(doc_meta: Dict[str, Any], kb_version: str) -> str:
    version = (kb_version or "v1").lower()
    base = str(doc_meta.get("working_dir") or "").strip()
    if not base:
        return base

    if version == "v2":
        v2 = str(doc_meta.get("working_dir_v2") or "").strip()
        if v2:
            return v2
        p = Path(base).resolve()
        if p.name == "rag_storage":
            return str(p.with_name("rag_storage_v2"))
        if p.name.endswith("_v2"):
            return str(p)
        return str(p.parent / f"{p.name}_v2")

    return base


async def answer_question(
    doc_meta: Dict[str, Any], question: str, kb_version: str = "v1"
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    基于已构建的知识库进行问答，并返回引用内容块。

    Returns:
        tuple: (answer_text, references)
            references: 检索到的内容块列表，每项含 content, file_path, chunk_id, reference_id
    """
    working_dir = _resolve_working_dir_for_version(doc_meta, kb_version)
    if not working_dir:
        raise RuntimeError("知识库工作目录缺失")
    if (kb_version or "v1").lower() == "v2":
        if not Path(working_dir).exists():
            raise RuntimeError("请求使用 v2 知识库，但 v2 索引尚未生成")

    # 使用与构建索引时一致的配置来（懒加载并）复用 LightRAG 索引
    parsed_dir_raw = doc_meta.get("parsed_dir")
    rag = await default_rag_cache.get_rag(
        working_dir=working_dir,
        parsed_dir=parsed_dir_raw,
        kb_version=kb_version,
    )

    try:
        answer, references = await rag.aquery_with_references(question, mode="hybrid", vlm_enhanced=True)
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

    # 为了兼容 LightRAG 返回的 reference_id 形如 "[0]"、"[1]" 等情况，
    # 这里对 reference_id 做一次规范化，仅保留数字部分再参与匹配。
    def _normalize_ref_id(raw: Any) -> str:
        s = str(raw or "").strip()
        if s.startswith("[") and s.endswith("]"):
            inner = s[1:-1].strip()
            return inner if inner.isdigit() else s
        return s

    if selected_ids:
        order = {ref_id: idx for idx, ref_id in enumerate(selected_ids)}

        def _key(ref: Dict[str, Any]) -> int:
            rid_norm = _normalize_ref_id(ref.get("reference_id"))
            return order.get(rid_norm, len(order) + 1)

        # 先过滤掉未在 References 中出现的引用
        enriched = [
            ref for ref in enriched if _normalize_ref_id(ref.get("reference_id")) in order
        ]
        # 再按 References 中的顺序排序
        enriched.sort(key=_key)

    # 不改写 LLM 原始回答内容，保留其自身生成的 "### References" 区块。
    return answer, enriched


async def query_data_only(
    doc_meta: Dict[str, Any],
    hl_keywords: List[str] | None = None,
    ll_keywords: List[str] | None = None,
    top_k: int = 10,
    kb_version: str = "v1",
) -> Dict[str, Any]:
    """
    仅基于知识库执行检索，返回 LightRAG 定义的 data 字段，
    不在本函数内调用 LLM 生成答案。

    参数设计：
        - hl_keywords: high-level keywords，高层语义关键词列表；
        - ll_keywords: low-level keywords，细粒度关键词列表；
        - top_k: 检索返回的最大条目数，将传递给底层 QueryParam。

    用于 Agent 工具等场景：由外层大模型负责阅读和推理，这里只做检索。
    返回的数据结构与 answer_question 中的 enriched 引用基本一致，
    data 字段的结构参考 LightRAG 文档中的说明，通常包含：
        - entities
        - relationships
        - chunks
        - references

    若调用失败或返回格式异常，则打印错误信息并返回空 dict。
    """
    working_dir = _resolve_working_dir_for_version(doc_meta, kb_version)
    if not working_dir:
        raise RuntimeError("知识库工作目录缺失")
    if (kb_version or "v1").lower() == "v2":
        if not Path(working_dir).exists():
            raise RuntimeError("请求使用 v2 知识库，但 v2 索引尚未生成")

    parsed_dir_raw = doc_meta.get("parsed_dir")
    rag = await default_rag_cache.get_rag(
        working_dir=working_dir,
        parsed_dir=parsed_dir_raw,
        kb_version=kb_version,
    )

    # 直接调用 LightRAG 的数据检索接口，避免内部再做一次 LLM 生成。
    if not hasattr(rag, "lightrag") or rag.lightrag is None:
        raise HTTPException(status_code=500, detail="LightRAG 实例尚未初始化")

    from lightrag import QueryParam  # 局部导入以避免循环依赖

    # 构造 QueryParam，将关键词与 top_k 一并传入底层检索
    extra_kwargs: Dict[str, Any] = {"top_k": top_k}
    if hl_keywords:
        extra_kwargs["hl_keywords"] = hl_keywords
    if ll_keywords:
        extra_kwargs["ll_keywords"] = ll_keywords

    query_param = QueryParam(mode="hybrid", **extra_kwargs)
    lightrag = rag.lightrag

    # 注意：在异步环境下不要直接调用 sync 的 query_data，
    # 其内部会使用 loop.run_until_complete，导致
    # "This event loop is already running" 错误。
    aquery_data = getattr(lightrag, "aquery_data", None)
    if aquery_data is None:
        raise HTTPException(
            status_code=500,
            detail="当前 LightRAG 版本不支持 aquery_data 接口，请升级 LightRAG。",
        )

    # 基于关键字构造用于 aquery_data 的查询串（主要用于日志与回溯）
    query_parts: List[str] = []
    if hl_keywords:
        query_parts.append("HL: " + ", ".join(hl_keywords))
    if ll_keywords:
        query_parts.append("LL: " + ", ".join(ll_keywords))
    query_str = " | ".join(query_parts)

    try:
        raw = await lightrag.aquery_data(query_str, param=query_param)
    except Exception as e:  # noqa: BLE001
        # 按约定：失败时打印 message，返回空 data
        print(f"LightRAG aquery_data 调用异常: {e}")
        return {}

    if not isinstance(raw, dict):
        print(f"LightRAG aquery_data 返回格式异常: {raw!r}")
        return {}

    status = raw.get("status")
    if status != "success":
        message = raw.get("message") or "LightRAG aquery_data 调用失败（无详细错误信息）"
        print(f"LightRAG aquery_data 调用失败: {message}")
        return {}

    data = raw.get("data")
    if data is None:
        print("LightRAG aquery_data 返回中缺少 data 字段。")
        return {}

    if not isinstance(data, dict):
        print(f"LightRAG aquery_data 返回的 data 字段格式异常: {data!r}")
        return {}

    return data


def _load_graphml(doc_meta: Dict[str, Any]) -> ET.Element:
    """加载并返回 graphml 根节点，供图相关函数复用。"""
    working_dir = doc_meta.get("working_dir")
    if not working_dir:
        raise HTTPException(status_code=400, detail="知识库工作目录缺失，无法加载图数据")

    graph_path = Path(working_dir) / "graph_chunk_entity_relation.graphml"
    if not graph_path.exists():
        raise HTTPException(status_code=204, detail="该知识库暂无图数据")

    try:
        tree = ET.parse(graph_path)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"解析图数据失败: {e}")

    return tree.getroot()


def get_doc_graph(
    doc_meta: Dict[str, Any],
    query: str | None = None,
    with_neighbors: bool = True,
) -> Dict[str, Any]:
    """
    从 LightRAG 的 graphml 文件中解析知识库图，返回给前端使用的 nodes/edges 结构。

    这里只返回轻量级信息（不包含长描述），节点详情在点击时单独查询。
    """
    try:
        root = _load_graphml(doc_meta)
    except HTTPException as e:
        if e.status_code == 204:
            return {"nodes": [], "edges": []}
        raise

    ns = {"g": "http://graphml.graphdrawing.org/xmlns"}

    # 收集 key -> (for, attr_name) 映射
    key_info: Dict[str, Dict[str, str]] = {}
    for key in root.findall("g:key", ns):
        key_id = key.attrib.get("id")
        attr_name = key.attrib.get("attr.name")
        key_for = key.attrib.get("for")
        if key_id and attr_name and key_for:
            key_info[key_id] = {"for": key_for, "name": attr_name}

    node_key_map = {k: v["name"] for k, v in key_info.items() if v["for"] == "node"}
    edge_key_map = {k: v["name"] for k, v in key_info.items() if v["for"] == "edge"}

    nodes: List[Dict[str, Any]] = []
    for node in root.findall(".//g:node", ns):
        node_id = node.attrib.get("id") or ""
        attrs: Dict[str, Any] = {"id": node_id}
        for data in node.findall("g:data", ns):
            key_id = data.attrib.get("key")
            attr_name = node_key_map.get(key_id)
            if not attr_name:
                continue
            text = (data.text or "").strip() if data.text is not None else ""
            attrs[attr_name] = text

        label = attrs.get("entity_id") or node_id
        node_type = attrs.get("entity_type") or ""
        created_at_raw = attrs.get("created_at")
        try:
            created_at = int(created_at_raw) if created_at_raw is not None else None
        except (TypeError, ValueError):
            created_at = None

        nodes.append(
            {
                "id": node_id,
                "label": label,
                "type": node_type,
                "created_at": created_at,
            }
        )

    total_nodes = len(nodes)

    edges: List[Dict[str, Any]] = []
    for idx, edge in enumerate(root.findall(".//g:edge", ns)):
        source = edge.attrib.get("source") or ""
        target = edge.attrib.get("target") or ""
        attrs: Dict[str, Any] = {}
        for data in edge.findall("g:data", ns):
            key_id = data.attrib.get("key")
            attr_name = edge_key_map.get(key_id)
            if not attr_name:
                continue
            text = (data.text or "").strip() if data.text is not None else ""
            attrs[attr_name] = text

        weight_raw = attrs.get("weight")
        try:
            weight = float(weight_raw) if weight_raw is not None else None
        except (TypeError, ValueError):
            weight = None

        edges.append(
            {
                "id": f"{source}-{target}-{idx}",
                "source": source,
                "target": target,
                "weight": weight,
            }
        )

    # 如果带查询，按名称搜索并可选扩展到一阶邻居
    q = (query or "").strip().lower()
    if q:
        matched_ids = {
            n["id"]
            for n in nodes
            if q in str(n.get("label") or "").lower() or q in str(n["id"]).lower()
        }
        if not matched_ids:
            return {"nodes": [], "edges": [], "total_nodes": total_nodes}

        allowed_ids = set(matched_ids)
        if with_neighbors:
            for e in edges:
                s = e.get("source")
                t = e.get("target")
                if s in matched_ids or t in matched_ids:
                    if s:
                        allowed_ids.add(s)
                    if t:
                        allowed_ids.add(t)

        nodes = [n for n in nodes if n["id"] in allowed_ids]
        edges = [
            e
            for e in edges
            if e.get("source") in allowed_ids and e.get("target") in allowed_ids
        ]
    else:
        # 无查询时，为避免前端在极大图上卡顿，仅展示最近的部分节点
        max_nodes = 300
        if len(nodes) > max_nodes:
            nodes_sorted = sorted(
                nodes,
                key=lambda n: n.get("created_at") or 0,
                reverse=True,
            )
            nodes = nodes_sorted[:max_nodes]
            allowed_ids = {n["id"] for n in nodes}
            edges = [
                e
                for e in edges
                if e.get("source") in allowed_ids and e.get("target") in allowed_ids
            ]

    return {"nodes": nodes, "edges": edges, "total_nodes": total_nodes}


def get_doc_graph_node_detail(doc_meta: Dict[str, Any], node_id: str) -> Dict[str, Any]:
    """
    返回单个节点的详细信息及邻居列表，用于前端点击节点时按需加载。
    """
    if not node_id:
        raise HTTPException(status_code=400, detail="缺少 node_id")

    try:
        root = _load_graphml(doc_meta)
    except HTTPException as e:
        if e.status_code == 204:
            raise HTTPException(status_code=404, detail="该知识库暂无图数据")
        raise

    ns = {"g": "http://graphml.graphdrawing.org/xmlns"}

    # 收集 key -> (for, attr_name) 映射
    key_info: Dict[str, Dict[str, str]] = {}
    for key in root.findall("g:key", ns):
        key_id = key.attrib.get("id")
        attr_name = key.attrib.get("attr.name")
        key_for = key.attrib.get("for")
        if key_id and attr_name and key_for:
            key_info[key_id] = {"for": key_for, "name": attr_name}

    node_key_map = {k: v["name"] for k, v in key_info.items() if v["for"] == "node"}
    edge_key_map = {k: v["name"] for k, v in key_info.items() if v["for"] == "edge"}

    # 先构建一个 id -> 节点元素 的索引，便于后续查邻居信息
    node_elems: Dict[str, ET.Element] = {}
    for node in root.findall(".//g:node", ns):
        nid = node.attrib.get("id") or ""
        node_elems[nid] = node

    node_elem = node_elems.get(node_id)
    if node_elem is None:
        raise HTTPException(status_code=404, detail="未找到对应节点")

    def _extract_node_attrs(elem: ET.Element) -> Dict[str, Any]:
        nid = elem.attrib.get("id") or ""
        attrs: Dict[str, Any] = {"id": nid}
        for data in elem.findall("g:data", ns):
            key_id = data.attrib.get("key")
            attr_name = node_key_map.get(key_id)
            if not attr_name:
                continue
            text = (data.text or "").strip() if data.text is not None else ""
            attrs[attr_name] = text
        return attrs

    # 当前节点属性
    cur_attrs = _extract_node_attrs(node_elem)
    label = cur_attrs.get("entity_id") or node_id
    node_type = cur_attrs.get("entity_type") or ""
    description = cur_attrs.get("description") or ""
    created_at_raw = cur_attrs.get("created_at")
    try:
        created_at = int(created_at_raw) if created_at_raw is not None else None
    except (TypeError, ValueError):
        created_at = None

    # 统计邻居：扫描所有边
    neighbor_ids: set[str] = set()
    for edge in root.findall(".//g:edge", ns):
        source = edge.attrib.get("source") or ""
        target = edge.attrib.get("target") or ""
        if source == node_id and target:
            neighbor_ids.add(target)
        elif target == node_id and source:
            neighbor_ids.add(source)

    neighbors: List[Dict[str, Any]] = []
    for nid in neighbor_ids:
        elem = node_elems.get(nid)
        if elem is None:
            continue
        attrs = _extract_node_attrs(elem)
        n_label = attrs.get("entity_id") or nid
        n_type = attrs.get("entity_type") or ""
        neighbors.append({"id": nid, "label": n_label, "type": n_type})

    return {
        "id": node_id,
        "label": label,
        "type": node_type,
        "description": description,
        "created_at": created_at,
        "neighbors": neighbors,
    }

