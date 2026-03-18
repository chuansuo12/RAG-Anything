---
name: product-knowledge
description: >
  Extracts structured product knowledge from technical product documents,
  including product overview, physical components, functional features,
  and quantitative specifications. Use this skill for product manuals,
  datasheets, brochures, and technical documentation.
schema: ./schema.json
steps:
  - key: product
    type: scalar
    prompts:
      scalar: ./prompts/product/scalar.md
  - key: components
    type: list
    prompts:
      discover: ./prompts/components/discover.md
      detail: ./prompts/components/detail.md
  - key: features
    type: list
    prompts:
      discover: ./prompts/features/discover.md
      detail: ./prompts/features/detail.md
  - key: parameters
    type: list
    prompts:
      discover: ./prompts/parameters/discover.md
      detail: ./prompts/parameters/detail.md
  - key: attributes
    type: list
    prompts:
      discover: ./prompts/attributes/discover.md
      detail: ./prompts/attributes/detail.md
---

# Product Knowledge Extraction Skill

## Overview

This skill extracts structured product knowledge from technical documents
by combining knowledge graph retrieval with domain-specific prompts.

## Execution Flow

1. **Scalar extraction** (`product`) — extracts the top-level product overview
   (name, brand, description, images, pricing) as a single JSON object.

2. **List extraction** (`components`, `features`, `parameters`, `attributes`) —
   for each list-type field the skill first **discovers** all item names, then
   **extracts detailed information** for every item in parallel.

3. **Merge** — all JSON files written during extraction are merged into a
   single structured result following `schema.json`.

## Schema

See `./schema.json` for the expected output structure.

## Domain Knowledge

- **Components** are physical or logical sub-units of the product
  (e.g. body, strap, display, battery, sensor module).
- **Features** are functional capabilities or modes
  (e.g. SpO2 monitoring, sleep tracking, GPS navigation).
- **Parameters** are quantitative product-level specifications
  (e.g. battery life: 14 days, weight: 32 g).
- **Attributes** are qualitative product-level properties
  (e.g. water resistance rating, material, color options).

## How to Run

This skill is executed via `run.py` located in the same directory as this
`SKILL.md` file. Derive the script path from the skill path shown in the
skills list, then run:

```bash
python <skill_dir>/run.py \
    --meta_path <path_to_meta.json> \
    --output <path_to_output.json>
```

**Arguments**

| Argument | Required | Description |
|---|---|---|
| `--meta_path` | Yes | Absolute path to the document's `meta.json` |
| `--output` | No | Path to write the result JSON (also printed to stdout) |

**`meta.json` location**: `runtime/source/<doc_id>/meta.json` relative to the
project root, where `<doc_id>` is the document identifier.

**Example**

```bash
python /project/agent/skills/product-knowledge/run.py \
    --meta_path /project/runtime/source/abc123/meta.json \
    --output /project/runtime/source/abc123/product_knowledge.json
```

**Output**

The script prints the extracted JSON to stdout and exits with code `0` on
success or `1` on error. Diagnostics are written to stderr.

The output follows `schema.json` and contains top-level keys:
`product`, `components`, `features`, `parameters`, `attributes`.
