from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .settings import SOURCE_DIR, HISTORY_DIR


def _read_json(path: Path, default: Any) -> Any:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _doc_dir(doc_id: str) -> Path:
    return SOURCE_DIR / doc_id


def _doc_meta_path(doc_id: str) -> Path:
    return _doc_dir(doc_id) / "meta.json"


def _conversation_path(conversation_id: str) -> Path:
    return HISTORY_DIR / f"{conversation_id}.json"

