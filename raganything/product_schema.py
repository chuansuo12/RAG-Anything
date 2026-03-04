"""
Backward compatibility: re-export product schema from raganything.product.

Prefer: from raganything.product import DEFAULT_PRODUCT_INFO_SCHEMA
"""

from __future__ import annotations

from raganything.product.schema import DEFAULT_PRODUCT_INFO_SCHEMA

__all__ = ["DEFAULT_PRODUCT_INFO_SCHEMA"]
