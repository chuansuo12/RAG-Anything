from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple
import xml.etree.ElementTree as ET

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
    基于已构建的知识库进行问答，并返回引用内容块。

    Returns:
        tuple: (answer_text, references)
            references: 检索到的内容块列表，每项含 content, file_path, chunk_id, reference_id
    """
    working_dir = doc_meta.get("working_dir")
    if not working_dir:
        raise RuntimeError("知识库工作目录缺失")

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

