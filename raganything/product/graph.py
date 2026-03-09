"""
Merge product information into the v2 knowledge graph.

Builds product / component / feature / parameter / attribute nodes and edges
in a LightRAG v2 working directory from an extracted product info dict.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Dict
import xml.etree.ElementTree as ET

from lightrag.utils import compute_mdhash_id


async def merge_product_info_into_v2_graph(
    doc_id: str,
    file_path_ref: str,
    info: dict,
    src_dir: str | Path,
    dst_dir: str | Path,
    *,
    llm_model_func: Callable,
    embedding_func: Callable,
    lightrag_kwargs: dict | None = None,
    merge_threshold: float = 0.9,
    force_rebuild_v2: bool = False,
) -> str | None:
    """
    Copy v1 storage to v2 (if needed), persist product info JSON, then merge
    product/components/features/parameters/attributes into the v2 graph.

    Caller is responsible for flushing the source LightRAG to disk before
    calling this (e.g. await self._flush_lightrag_to_disk()).

    Returns:
        Resolved dst_dir path as string on success, None if info is empty.
    """
    if not info:
        return None

    src_dir = Path(src_dir).resolve()
    dst_dir = Path(dst_dir).resolve()

    if src_dir != dst_dir:
        if force_rebuild_v2 and dst_dir.exists():
            shutil.rmtree(dst_dir)
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True)

    try:
        product_info_path = dst_dir / "product info.json"
        product_info_path.write_text(
            json.dumps(info, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass

    from lightrag import LightRAG

    params: Dict[str, Any] = {
        "working_dir": str(dst_dir),
        "llm_model_func": llm_model_func,
        "embedding_func": embedding_func,
    }
    params.update(lightrag_kwargs or {})
    lr = LightRAG(**params)
    await lr.initialize_storages()

    product = info.get("product") or {}
    product_name = (product.get("name") or "product").strip() or "product"
    product_desc = (product.get("description") or "").strip()
    created_at = str(int(time.time()))

    # 从 v1 graphml 中预加载 entity_id -> description 映射，用于在合并时继承 V1 描述
    v1_entity_desc_map: Dict[str, str] = {}
    _v1_desc_loaded = False

    def _load_v1_entity_desc_map() -> None:
        nonlocal _v1_desc_loaded
        if _v1_desc_loaded:
            return
        _v1_desc_loaded = True

        graph_path = src_dir / "graph_chunk_entity_relation.graphml"
        if not graph_path.exists():
            return

        try:
            root = ET.parse(graph_path).getroot()
        except Exception:
            return

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

        def _extract_node_attrs(elem) -> Dict[str, Any]:
            attrs: Dict[str, Any] = {}
            for data in elem.findall("g:data", ns):
                key_id = data.attrib.get("key")
                attr_name = node_key_map.get(key_id)
                if not attr_name:
                    continue
                text = (data.text or "").strip() if data.text is not None else ""
                attrs[attr_name] = text
            return attrs

        for node in root.findall(".//g:node", ns):
            attrs = _extract_node_attrs(node)
            eid = (attrs.get("entity_id") or "").strip()
            desc = (attrs.get("description") or "").strip()
            if eid and desc and eid not in v1_entity_desc_map:
                v1_entity_desc_map[eid] = desc

    async def pick_existing_entity(query: str) -> tuple[str | None, str]:
        """
        Query entity VDB by name+description; if similarity >= merge_threshold,
        return (existing_entity_name, existing_content). Otherwise (None, "").
        Merge 时以已有节点信息（名称、描述）为主。
        """
        try:
            hits = await lr.entities_vdb.query(query=query, top_k=5)
        except Exception:
            return None, ""
        if not hits:
            return None, ""
        best = hits[0]
        try:
            score = float(best.get("distance"))
        except Exception:
            score = 0.0
        if score < merge_threshold:
            return None, ""
        name = (best.get("entity_name") or "").strip()
        content = (best.get("content") or "").strip()
        return (name or None, content)

    async def get_existing_node_description(node_id: str) -> str:
        """
        若 V1 图中已存在同名实体（依据 entity_id），则优先返回其 description；
        否则再回退到当前图存储中的节点描述。
        """
        if not node_id:
            return ""

        # 1) 优先从 V1 graphml 中继承描述（与前端图展示的描述严格对齐）
        try:
            _load_v1_entity_desc_map()
        except Exception:
            # 加载失败时忽略，继续走存储读取逻辑
            pass

        key = node_id.strip()
        if key:
            desc = v1_entity_desc_map.get(key)
            if isinstance(desc, str) and desc.strip():
                return desc.strip()

        # 2) 回退：从当前 chunk_entity_relation_graph 存储中读取
        try:
            node = await lr.chunk_entity_relation_graph.get_by_id(node_id)
        except Exception:
            return ""
        if isinstance(node, dict):
            desc2 = (node.get("description") or "").strip()
            if desc2:
                return desc2
        return ""

    product_query = f"{product_name}\n{product_desc}".strip()
    matched_product, existing_product_content = await pick_existing_entity(product_query) if product_query else (None, "")
    product_node_id = matched_product or product_name
    # 以节点信息为主：若图中已存在同名节点，则优先继承其描述（即 V1 中的描述）
    existing_product_node_desc = await get_existing_node_description(product_node_id)
    if existing_product_node_desc:
        product_desc_final = existing_product_node_desc
    else:
        # 否则回退到向量库中的内容或本次抽取的描述
        product_desc_final = existing_product_content or product_desc
    product_content_final = f"{product_node_id}\n{product_desc_final or ''}".strip()

    await lr.chunk_entity_relation_graph.upsert_node(
        product_node_id,
        {
            "entity_id": product_node_id,
            "entity_type": "product",
            "description": product_desc_final,
            "source_id": f"product_info:{doc_id}",
            "file_path": str(file_path_ref),
            "created_at": created_at,
        },
    )

    await lr.entities_vdb.upsert(
        {
            compute_mdhash_id(product_node_id, prefix="ent-"): {
                "entity_name": product_node_id,
                "entity_type": "product",
                "content": product_content_final or f"{product_node_id}\n{product_desc or ''}",
                "source_id": f"product_info:{doc_id}",
                "file_path": str(file_path_ref),
            }
        }
    )

    components = info.get("components") or []
    features = info.get("features") or []
    parameters = info.get("parameters") or []
    attributes = info.get("attributes") or []

    component_id_map: Dict[str, str] = {}
    feature_id_map: Dict[str, str] = {}
    entities_to_upsert: Dict[str, Dict[str, Any]] = {}
    rels_to_upsert: Dict[str, Dict[str, Any]] = {}
    source_id = f"product_info:{doc_id}"

    for c in components:
        if not isinstance(c, dict):
            continue
        raw_id = (c.get("id") or "").strip()
        raw_name = (c.get("name") or "").strip()
        if not raw_name:
            continue
        base_id = raw_name or raw_id
        comp_desc = (c.get("description") or "").strip()
        query = "\n".join([raw_name, comp_desc]).strip()
        matched_comp, existing_comp_content = await pick_existing_entity(query) if query else (None, "")
        component_node_id = matched_comp or base_id
        component_id_map[raw_id or raw_name] = component_node_id
        # 若图中已存在同名节点（通常来自 V1），则优先继承其描述
        existing_comp_node_desc = await get_existing_node_description(component_node_id)
        if existing_comp_node_desc:
            comp_desc_final = existing_comp_node_desc
        else:
            # 否则按“已有向量库内容 -> 当前 schema 描述 -> 名称”顺序回退
            comp_desc_final = existing_comp_content or comp_desc or raw_name

        await lr.chunk_entity_relation_graph.upsert_node(
            component_node_id,
            {
                "entity_id": component_node_id,
                "entity_type": "product_component",
                "description": comp_desc_final,
                "source_id": source_id,
                "file_path": str(file_path_ref),
                "created_at": created_at,
            },
        )
        edge_desc = f"{product_node_id} has component {component_node_id}"
        await lr.chunk_entity_relation_graph.upsert_edge(
            product_node_id,
            component_node_id,
            {
                "description": edge_desc,
                "keywords": "has_component,product_component",
                "source_id": source_id,
                "weight": 8.0,
                "file_path": str(file_path_ref),
            },
        )
        ent_id = compute_mdhash_id(component_node_id, prefix="ent-")
        entities_to_upsert[ent_id] = {
            "entity_name": component_node_id,
            "entity_type": "product_component",
            "content": f"{component_node_id}\n{comp_desc_final}".strip(),
            "source_id": source_id,
            "file_path": str(file_path_ref),
        }
        rel_id = compute_mdhash_id(
            product_node_id + component_node_id + "has_component", prefix="rel-"
        )
        rels_to_upsert[rel_id] = {
            "src_id": product_node_id,
            "tgt_id": component_node_id,
            "keywords": "has_component,product_component",
            "content": f"has_component\t{product_node_id}\n{component_node_id}\n{edge_desc}",
            "source_id": source_id,
            "file_path": str(file_path_ref),
        }

    for f in features:
        if not isinstance(f, dict):
            continue
        raw_id = (f.get("id") or "").strip()
        raw_name = (f.get("name") or "").strip()
        if not raw_name:
            continue
        base_id = raw_name or raw_id
        feat_desc = (f.get("description") or "").strip()
        query = "\n".join([raw_name, feat_desc]).strip()
        matched_feat, existing_feat_content = await pick_existing_entity(query) if query else (None, "")
        feature_node_id = matched_feat or base_id
        feature_id_map[raw_id or raw_name] = feature_node_id
        # 若图中已存在同名节点（通常来自 V1），则优先继承其描述
        existing_feat_node_desc = await get_existing_node_description(feature_node_id)
        if existing_feat_node_desc:
            feat_desc_final = existing_feat_node_desc
        else:
            # 否则按“已有向量库内容 -> 当前 schema 描述 -> 名称”顺序回退
            feat_desc_final = existing_feat_content or feat_desc or raw_name

        await lr.chunk_entity_relation_graph.upsert_node(
            feature_node_id,
            {
                "entity_id": feature_node_id,
                "entity_type": "product_feature",
                "description": feat_desc_final,
                "source_id": source_id,
                "file_path": str(file_path_ref),
                "created_at": created_at,
            },
        )
        comp_ref = (f.get("component_id") or f.get("component_name") or "").strip()
        parent_id = component_id_map.get(comp_ref, product_node_id) if comp_ref else product_node_id
        edge_desc = f"{parent_id} has feature {feature_node_id}"
        await lr.chunk_entity_relation_graph.upsert_edge(
            parent_id,
            feature_node_id,
            {
                "description": edge_desc,
                "keywords": "has_feature,product_feature",
                "source_id": source_id,
                "weight": 8.0,
                "file_path": str(file_path_ref),
            },
        )
        ent_id = compute_mdhash_id(feature_node_id, prefix="ent-")
        entities_to_upsert[ent_id] = {
            "entity_name": feature_node_id,
            "entity_type": "product_feature",
            "content": f"{feature_node_id}\n{feat_desc_final}".strip(),
            "source_id": source_id,
            "file_path": str(file_path_ref),
        }
        rel_id = compute_mdhash_id(parent_id + feature_node_id + "has_feature", prefix="rel-")
        rels_to_upsert[rel_id] = {
            "src_id": parent_id,
            "tgt_id": feature_node_id,
            "keywords": "has_feature,product_feature",
            "content": f"has_feature\t{parent_id}\n{feature_node_id}\n{edge_desc}",
            "source_id": source_id,
            "file_path": str(file_path_ref),
        }

    def _resolve_scope(scope_type: str, scope_id: str) -> str:
        st = (scope_type or "").lower()
        sid = (scope_id or "").strip()
        if st == "component" and sid:
            return component_id_map.get(sid, product_node_id)
        if st == "feature" and sid:
            return feature_id_map.get(sid, product_node_id)
        return product_node_id

    for p in parameters:
        if not isinstance(p, dict):
            continue
        name = (p.get("name") or "").strip()
        if not name:
            continue
        value = p.get("value")
        unit = (p.get("unit") or "").strip()
        desc_text = (p.get("description") or "").strip()
        scope_type = p.get("scope_type") or "product"
        scope_id = p.get("scope_id") or ""
        source_snippet = (p.get("source") or "").strip()
        parent_id = _resolve_scope(scope_type, scope_id)
        node_label = f"{name}={value}" if value is not None else name
        param_node_id = f"{parent_id}::param::{name}"
        param_desc_parts = [node_label]
        if unit:
            param_desc_parts.append(f"unit={unit}")
        if desc_text:
            param_desc_parts.append(f"description={desc_text}")
        if source_snippet:
            param_desc_parts.append(f"source={source_snippet}")
        param_desc = "\n".join(param_desc_parts)

        await lr.chunk_entity_relation_graph.upsert_node(
            param_node_id,
            {
                "entity_id": param_node_id,
                "entity_type": "product_parameter",
                "description": param_desc,
                "source_id": source_id,
                "file_path": str(file_path_ref),
                "created_at": created_at,
            },
        )
        edge_desc = f"{parent_id} has parameter {node_label}"
        await lr.chunk_entity_relation_graph.upsert_edge(
            parent_id,
            param_node_id,
            {
                "description": edge_desc,
                "keywords": "has_parameter,product_parameter",
                "source_id": source_id,
                "weight": 6.0,
                "file_path": str(file_path_ref),
            },
        )
        ent_id = compute_mdhash_id(param_node_id, prefix="ent-")
        entities_to_upsert[ent_id] = {
            "entity_name": param_node_id,
            "entity_type": "product_parameter",
            "content": f"{param_node_id}\n{param_desc}",
            "source_id": source_id,
            "file_path": str(file_path_ref),
        }
        rel_id = compute_mdhash_id(parent_id + param_node_id + "has_parameter", prefix="rel-")
        rels_to_upsert[rel_id] = {
            "src_id": parent_id,
            "tgt_id": param_node_id,
            "keywords": "has_parameter,product_parameter",
            "content": f"has_parameter\t{parent_id}\n{param_node_id}\n{edge_desc}",
            "source_id": source_id,
            "file_path": str(file_path_ref),
        }

    for a in attributes:
        if not isinstance(a, dict):
            continue
        name = (a.get("name") or "").strip()
        if not name:
            continue
        value = a.get("value")
        unit = (a.get("unit") or "").strip()
        desc_text = (a.get("description") or "").strip()
        scope_type = a.get("scope_type") or "product"
        scope_id = a.get("scope_id") or ""
        source_snippet = (a.get("source") or "").strip()
        parent_id = _resolve_scope(scope_type, scope_id)
        node_label = f"{name}={value}" if value is not None else name
        attr_node_id = f"{parent_id}::attr::{name}"
        attr_desc_parts = [node_label]
        if unit:
            attr_desc_parts.append(f"unit={unit}")
        if desc_text:
            attr_desc_parts.append(f"description={desc_text}")
        if source_snippet:
            attr_desc_parts.append(f"source={source_snippet}")
        attr_desc = "\n".join(attr_desc_parts)

        await lr.chunk_entity_relation_graph.upsert_node(
            attr_node_id,
            {
                "entity_id": attr_node_id,
                "entity_type": "product_attribute",
                "description": attr_desc,
                "source_id": source_id,
                "file_path": str(file_path_ref),
                "created_at": created_at,
            },
        )
        edge_desc = f"{parent_id} has attribute {node_label}"
        await lr.chunk_entity_relation_graph.upsert_edge(
            parent_id,
            attr_node_id,
            {
                "description": edge_desc,
                "keywords": "has_attribute,product_attribute",
                "source_id": source_id,
                "weight": 6.0,
                "file_path": str(file_path_ref),
            },
        )
        ent_id = compute_mdhash_id(attr_node_id, prefix="ent-")
        entities_to_upsert[ent_id] = {
            "entity_name": attr_node_id,
            "entity_type": "product_attribute",
            "content": f"{attr_node_id}\n{attr_desc}",
            "source_id": source_id,
            "file_path": str(file_path_ref),
        }
        rel_id = compute_mdhash_id(parent_id + attr_node_id + "has_attribute", prefix="rel-")
        rels_to_upsert[rel_id] = {
            "src_id": parent_id,
            "tgt_id": attr_node_id,
            "keywords": "has_attribute,product_attribute",
            "content": f"has_attribute\t{parent_id}\n{attr_node_id}\n{edge_desc}",
            "source_id": source_id,
            "file_path": str(file_path_ref),
        }

    if entities_to_upsert:
        await lr.entities_vdb.upsert(entities_to_upsert)
        await lr.entities_vdb.index_done_callback()
    if rels_to_upsert and getattr(lr, "relationships_vdb", None):
        await lr.relationships_vdb.upsert(rels_to_upsert)
        await lr.relationships_vdb.index_done_callback()

    try:
        ds = await lr.doc_status.get_by_id(doc_id)
        if isinstance(ds, dict):
            await lr.doc_status.upsert(
                {
                    doc_id: {
                        **ds,
                        "product_info_processed": True,
                        "product_info_product_node_id": product_node_id,
                        "product_info_updated_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                    }
                }
            )
            await lr.doc_status.index_done_callback()
    except Exception:
        pass

    await lr.chunk_entity_relation_graph.index_done_callback()
    return str(dst_dir)
