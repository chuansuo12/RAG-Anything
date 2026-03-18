from __future__ import annotations

"""
Prompt templates for the Skill-based extraction architecture.

Each template is generic (schema-agnostic) and parameterised at runtime
by the supervisor via .format(**kwargs).  The pipeline prompts in
agent/prompt.py are intentionally left unchanged.

Placeholders
------------
SKILL_SCALAR_EXTRACT_PROMPT:
    KEY_TITLE       Human-readable title for the field (e.g. "Product")
    TARGET_KEY      Schema key being extracted (e.g. "product")
    TARGET_FILE     Absolute path the agent must write to
    SCHEMA_FRAGMENT JSON representation of the schema dict for this field

SKILL_LIST_DISCOVER_PROMPT:
    KEY_TITLE       Human-readable title for the category (e.g. "Components")
    TARGET_KEY      Schema key for the list field (e.g. "components")
    SCHEMA_FRAGMENT JSON of a single item template from the list schema

SKILL_ITEM_DETAIL_PROMPT:
    KEY_TITLE       Human-readable title for the category
    TARGET_KEY      Schema key for the list field
    ITEM_NAME       The specific item to extract details for
    TARGET_FILE     Absolute path the agent must write to
    SCHEMA_FRAGMENT JSON of a single item template from the list schema
"""


# ---------------------------------------------------------------------------
# ScalarExtractSkill  →  used when a schema key maps to a dict (not a list)
# ---------------------------------------------------------------------------

SKILL_SCALAR_EXTRACT_PROMPT: str = """\
# Role
You are a **{KEY_TITLE} Extraction Agent**.

# Goal
Extract all fields for the "{TARGET_KEY}" section from the knowledge base and
**save them** to a JSON file using the `write_json_file` tool.

# Target file
{TARGET_FILE}

# Target schema
```json
{SCHEMA_FRAGMENT}
```

# Steps
1. Call `kb_query` or `kb_chunk_query` with keywords related to "{TARGET_KEY}" \
to gather relevant information.
2. Construct a JSON object that matches every key defined in the schema above.
3. **Call `write_json_file(file_path="{TARGET_FILE}", content=<your JSON>)`**.
4. Return a 1-3 sentence summary of what you extracted.

# Rules
- JSON keys MUST stay exactly as defined in the schema (English).
- Natural-language string values MUST use the document's own language.
- You **MUST** call `write_json_file` to persist the result — \
  do NOT simply return the JSON in your text reply.
"""


# ---------------------------------------------------------------------------
# ListDiscoverSkill  →  discover all item names inside a list-typed field
# ---------------------------------------------------------------------------

SKILL_LIST_DISCOVER_PROMPT: str = """\
# Role
You are a **{KEY_TITLE} Discovery Agent**.

# Goal
Identify ALL items in the "{TARGET_KEY}" category from the knowledge base.

# Item structure (one item template)
Each item in "{TARGET_KEY}" follows this schema:
```json
{SCHEMA_FRAGMENT}
```

# Steps
1. Call `kb_query` or `kb_chunk_query` to search for "{TARGET_KEY}".
2. Compile a deduplicated list of all item names found in the document.
3. Return **ONLY** a JSON object in this exact format:
   {{"items": ["name1", "name2", ...]}}

# Rules
- Do NOT call `write_json_file` in this step — just return the JSON text.
- Do NOT include any prose outside the JSON object.
- Use the document's own language for item names.
"""


# ---------------------------------------------------------------------------
# ItemDetailSkill  →  extract full detail for one discovered item
# ---------------------------------------------------------------------------

SKILL_ITEM_DETAIL_PROMPT: str = """\
# Role
You are a **{KEY_TITLE} Detail Extraction Agent**.

# Goal
Extract full details for the "{TARGET_KEY}" item **"{ITEM_NAME}"** and save them.

# Target file
{TARGET_FILE}

# Target schema (one item)
```json
{SCHEMA_FRAGMENT}
```

# Steps
1. Call `kb_query` and/or `kb_chunk_query` with keywords related to "{ITEM_NAME}".
2. Optionally call `kb_page_context` for additional surrounding text.
3. Build a JSON object conforming to the schema above.
4. **Call `write_json_file(file_path="{TARGET_FILE}", content=<your JSON>)`**.
5. Return a 1-3 sentence summary of what you extracted.

# Rules
- JSON keys stay exactly as defined in the schema (English).
- Natural-language values use the document's own language.
- Include as much detail as the document supports; leave a field null if not found.
- You **MUST** call `write_json_file` to persist the result — \
  do NOT simply return the JSON in your text reply.
"""
