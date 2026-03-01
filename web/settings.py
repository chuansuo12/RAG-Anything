from __future__ import annotations

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
RUNTIME_DIR = BASE_DIR / "runtime"
SOURCE_DIR = RUNTIME_DIR / "source"
HISTORY_DIR = RUNTIME_DIR / "history"

WEB_DIR = Path(__file__).resolve().parent
INDEX_HTML_PATH = WEB_DIR / "front" / "index.html"


def ensure_runtime_dirs() -> None:
    for d in (RUNTIME_DIR, SOURCE_DIR, HISTORY_DIR):
        d.mkdir(parents=True, exist_ok=True)

