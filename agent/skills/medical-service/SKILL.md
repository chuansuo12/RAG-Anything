---
name: medical-service
description: >
  Extracts structured medical service knowledge from clinical documents,
  including service overview, clinical procedures, medications, diagnostic
  criteria, and treatment protocols. Use this skill for clinical guidelines,
  medical service manuals, drug formularies, and healthcare documentation.
schema: ./schema.json
steps:
  - key: service
    type: scalar
    prompts:
      scalar: ./prompts/service/scalar.md
  - key: procedures
    type: list
    prompts:
      discover: ./prompts/procedures/discover.md
      detail: ./prompts/procedures/detail.md
  - key: medications
    type: list
    prompts:
      discover: ./prompts/medications/discover.md
      detail: ./prompts/medications/detail.md
  - key: diagnostic_criteria
    type: list
    prompts:
      discover: ./prompts/diagnostic_criteria/discover.md
      detail: ./prompts/diagnostic_criteria/detail.md
  - key: contraindications
    type: list
    prompts:
      discover: ./prompts/contraindications/discover.md
      detail: ./prompts/contraindications/detail.md
---

# Medical Service Knowledge Extraction Skill

## Overview

This skill extracts structured medical service knowledge from clinical documents
by combining knowledge graph retrieval with domain-specific clinical prompts.

## Execution Flow

1. **Scalar extraction** (`service`) — extracts the top-level service overview
   (name, department, ICD codes, description, applicable population).

2. **List extraction** (`procedures`, `medications`, `diagnostic_criteria`,
   `contraindications`) — for each list-type field the skill first **discovers**
   all item names, then **extracts detailed information** for every item in parallel.

3. **Merge** — all JSON files written during extraction are merged into a
   single structured result following `schema.json`.

## Schema

See `./schema.json` for the expected output structure.

## Domain Knowledge

- **Procedures** are clinical actions performed on patients
  (e.g. blood draw, ECG, physical examination, surgical intervention).
- **Medications** are drugs or therapeutic substances
  (e.g. Aspirin 100mg, Metformin 500mg, insulin injection).
- **Diagnostic criteria** are conditions or findings that confirm a diagnosis
  (e.g. fasting glucose ≥ 7.0 mmol/L, HbA1c ≥ 6.5%).
- **Contraindications** are conditions that prohibit a treatment or procedure
  (e.g. pregnancy, renal impairment, known allergy).

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
python /project/agent/skills/medical-service/run.py \
    --meta_path /project/runtime/source/abc123/meta.json \
    --output /project/runtime/source/abc123/medical_service.json
```

**Output**

The script prints the extracted JSON to stdout and exits with code `0` on
success or `1` on error. Diagnostics are written to stderr.

The output follows `schema.json` and contains top-level keys:
`service`, `procedures`, `medications`, `diagnostic_criteria`, `contraindications`.
