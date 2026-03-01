from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from .settings import INDEX_HTML_PATH


router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    if INDEX_HTML_PATH.exists():
        html = INDEX_HTML_PATH.read_text(encoding="utf-8")
    else:
        html = "<html><body><h1>RAGAnything Web UI</h1><p>index.html not found.</p></body></html>"
    return HTMLResponse(content=html)

