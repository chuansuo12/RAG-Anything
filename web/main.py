from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import json
import os
import logging

from web.routes_conversations import router as conversations_router
from web.routes_docs import router as docs_router
from web.routes_index import router as index_router
from web.settings import ensure_runtime_dirs
from config.graph_conf import ENTITY_TYPES


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "runtime"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / "main.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)


app = FastAPI(title="RAGAnything 知识库问答 Web UI")

ensure_runtime_dirs()

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "front"), name="static")

# 设置 ENTITY_TYPES 环境变量，供后端逻辑使用（从配置集中读取）
os.environ["ENTITY_TYPES"] = json.dumps(ENTITY_TYPES, ensure_ascii=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(index_router)
app.include_router(docs_router)
app.include_router(conversations_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "web.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )

