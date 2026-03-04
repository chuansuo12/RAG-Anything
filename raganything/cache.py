from __future__ import annotations

"""
缓存与复用 RAGAnything 实例的简单管理类。

设计目标：
- 以 (working_dir, parsed_dir, kb_version) 作为 key 复用同一个 RAGAnything；
- 避免每次查询都从磁盘重新加载 LightRAG 索引；
- 封装到独立类中，方便在 web / agent 等场景中通用。
"""

from pathlib import Path
from typing import Dict, Optional, Tuple

from raganything import RAGAnything, RAGAnythingConfig
from llm import embedding_func, llm_model_func, vision_model_func
from llm.qwen_llm import qwen_rerank_model_func


CacheKey = Tuple[str, str, str]


class RAGInstanceCache:
    """
    按工作目录 / 解析目录 / 版本维度缓存 RAGAnything 实例。

    注意：
    - 当前实现是进程级别缓存，适用于单进程 FastAPI / 脚本场景；
    - 若在多进程部署（如多 worker）下，每个进程各自维护一份缓存。
    """

    def __init__(self) -> None:
        self._cache: Dict[CacheKey, RAGAnything] = {}

    async def get_rag(
        self,
        working_dir: str,
        parsed_dir: Optional[str] = None,
        kb_version: str = "v1",
    ) -> RAGAnything:
        """
        获取（或懒加载创建）一个 RAGAnything 实例。

        Args:
            working_dir: LightRAG 索引所在工作目录。
            parsed_dir: MinerU 解析输出目录，可为空。
            kb_version: 知识库版本标识（例如 "v1"/"v2"），用于 key 维度区分。
        """
        working_dir_resolved = str(Path(working_dir).resolve())
        parsed_dir_resolved = str(Path(parsed_dir).resolve()) if parsed_dir else ""
        version_normalized = (kb_version or "v1").lower()

        key: CacheKey = (working_dir_resolved, parsed_dir_resolved, version_normalized)

        rag = self._cache.get(key)
        if rag is not None:
            return rag

        config = RAGAnythingConfig(
            working_dir=working_dir_resolved,
            parser="mineru",
            parse_method="auto",
            parser_output_dir=parsed_dir_resolved or None,
        )

        rag = RAGAnything(
            config=config,
            llm_model_func=llm_model_func,
            vision_model_func=vision_model_func,
            embedding_func=embedding_func,
            lightrag_kwargs={
                "rerank_model_func": qwen_rerank_model_func,
            },
        )

        # 懒加载 LightRAG 索引，只在首次命中该 key 时执行。
        await rag._ensure_lightrag_initialized()
        self._cache[key] = rag
        return rag


# 默认导出一个全局缓存实例，方便直接复用。
default_rag_cache = RAGInstanceCache()

