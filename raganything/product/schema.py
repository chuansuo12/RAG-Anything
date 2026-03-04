"""
Product information schema for extraction and graph building.

Centralizes the default JSON schema and loading from file so it can be shared
by the processor, agent, and downstream consumers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


DEFAULT_PRODUCT_INFO_SCHEMA: Dict[str, Any] = {
    "product": {
        "name": None,
        "image": [],
        "brand": None,
        "offers": [],
        "description": None,
    },
    # Component-level structure describing physical / logical parts of the product
    "components": [
        {
            "name": None,
            "description": None,
            "attributes": [
                {
                    "name": None,
                    "value": None,
                    "unit": None,  # e.g. "mm", "kg", "V", or null
                    "description": None,
                    "source": None,  # short text snippet supporting the value
                }
            ],
        }
    ],
    # Feature-level structure describing functions or capabilities of the product
    "features": [
        {
            "name": None,
            "description": None,
            # Link back to the related component when applicable
            "component_name": None,
            "parameters": [
                {
                    "name": None,
                    # value may be text or numeric represented as string
                    "value": None,
                    "unit": None,
                    "description": None,
                    "source": None,
                }
            ],
            "attributes": [
                {
                    "name": None,
                    "value": None,
                    "unit": None,
                    "description": None,
                    "source": None,
                }
            ],
        }
    ],
    # Product-level parameters that are not tied to a specific component/feature
    "parameters": [
        {
            "name": None,
            "value": None,
            "unit": None,
            "description": None,
            "scope_type": None,
            "source": None,
        }
    ],
    # Product-level attributes that are not strictly numerical parameters
    "attributes": [
        {
            "name": None,
            "value": None,
            "unit": None,
            "description": None,
            "scope_type": None,
            "source": None,
        }
    ],
}


def get_default_product_info_schema() -> dict:
    """Return a deep copy of the default schema to avoid mutation."""
    return json.loads(json.dumps(DEFAULT_PRODUCT_INFO_SCHEMA))


def load_schema_template(working_dir_v2: str) -> dict:
    """
    Load product info schema template.

    Priority:
    1. product_info_schema.json in the given v2 working dir (if exists)
    2. Built-in default schema
    """
    try:
        base = Path(working_dir_v2).resolve()
        schema_path = base / "product_info_schema.json"
        if schema_path.is_file():
            text = schema_path.read_text(encoding="utf-8")
            data = json.loads(text)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return get_default_product_info_schema()
