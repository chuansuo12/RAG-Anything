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
    merge_threshold: float = 0.85,
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

    async def pick_existing_entity_name(query: str) -> str | None:
        try:
            hits = await lr.entities_vdb.query(query=query, top_k=5)
        except Exception:
            return None
        if not hits:
            return None
        best = hits[0]
        try:
            score = float(best.get("distance"))
        except Exception:
            score = 0.0
        if score >= merge_threshold:
            name = (best.get("entity_name") or "").strip()
            return name or None
        return None

    product_query = f"{product_name}\n{product_desc}".strip()
    matched_product = await pick_existing_entity_name(product_query) if product_query else None
    product_node_id = matched_product or product_name

    await lr.chunk_entity_relation_graph.upsert_node(
        product_node_id,
        {
            "entity_id": product_node_id,
            "entity_type": "product",
            "description": product_desc,
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
                "content": f"{product_node_id}\n{product_desc or ''}",
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
        matched = await pick_existing_entity_name(query) if query else None
        component_node_id = matched or base_id
        component_id_map[raw_id or raw_name] = component_node_id

        await lr.chunk_entity_relation_graph.upsert_node(
            component_node_id,
            {
                "entity_id": component_node_id,
                "entity_type": "product_component",
                "description": comp_desc or raw_name,
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
            "content": f"{component_node_id}\n{comp_desc or raw_name}",
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
        matched = await pick_existing_entity_name(query) if query else None
        feature_node_id = matched or base_id
        feature_id_map[raw_id or raw_name] = feature_node_id

        await lr.chunk_entity_relation_graph.upsert_node(
            feature_node_id,
            {
                "entity_id": feature_node_id,
                "entity_type": "product_feature",
                "description": feat_desc or raw_name,
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
            "content": f"{feature_node_id}\n{feat_desc or raw_name}",
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
