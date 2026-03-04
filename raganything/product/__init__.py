"""
Product schema and v2 graph building for RAG-Anything.

- schema: default product info schema and loading from file
- resolve: resolve v2 working directory path
- graph: merge extracted product info into the v2 knowledge graph
"""

from raganything.product.schema import (
    DEFAULT_PRODUCT_INFO_SCHEMA,
    get_default_product_info_schema,
    load_schema_template,
)
from raganything.product.resolve import resolve_working_dir_v2
from raganything.product.graph import merge_product_info_into_v2_graph

__all__ = [
    "DEFAULT_PRODUCT_INFO_SCHEMA",
    "get_default_product_info_schema",
    "load_schema_template",
    "resolve_working_dir_v2",
    "merge_product_info_into_v2_graph",
]
