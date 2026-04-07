#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCS_DIR="$ROOT_DIR/docs"
OUTPUT_PATH="${1:-$DOCS_DIR/thesis_merged.md}"

INPUT_FILES=(
  "$DOCS_DIR/abstract.md"
  "$DOCS_DIR/chapter1_introduction.md"
  "$DOCS_DIR/chapter2_related_work.md"
  "$DOCS_DIR/chapter3_schema_driven_kg_enhancement.md"
  "$DOCS_DIR/chapter4_flow_agentic_search_review.md"
  "$DOCS_DIR/chapter5_conclusion.md"
)

for file in "${INPUT_FILES[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "Error: missing file: $file" >&2
    exit 1
  fi
done

mkdir -p "$(dirname "$OUTPUT_PATH")"
: > "$OUTPUT_PATH"

for i in "${!INPUT_FILES[@]}"; do
  file="${INPUT_FILES[$i]}"
  printf '<!-- Source: %s -->\n\n' "${file#$ROOT_DIR/}" >> "$OUTPUT_PATH"
  cat "$file" >> "$OUTPUT_PATH"
  printf '\n' >> "$OUTPUT_PATH"
  if [[ "$i" -lt "$((${#INPUT_FILES[@]} - 1))" ]]; then
    printf '\n---\n\n' >> "$OUTPUT_PATH"
  fi
done

echo "Merged markdown generated at: $OUTPUT_PATH"
