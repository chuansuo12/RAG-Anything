"""
Resolve v2 working directory for product schema / graph storage.
"""

from __future__ import annotations

from pathlib import Path


def resolve_working_dir_v2(
    working_dir: str,
    product_schema_working_dir: str = "",
) -> str:
    """
    Resolve the v2 working directory path for product info and graph.

    Priority:
    1. If product_schema_working_dir is set, use it.
    2. Otherwise derive from working_dir: rag_storage -> rag_storage_v2,
       or {name} -> {name}_v2.
    """
    v2 = (product_schema_working_dir or "").strip()
    if v2:
        return v2

    base = Path(working_dir or "./rag_storage").resolve()
    if base.name == "rag_storage":
        return str(base.with_name("rag_storage_v2"))
    if base.name.endswith("_v2"):
        return str(base)
    return str(base.parent / f"{base.name}_v2")
