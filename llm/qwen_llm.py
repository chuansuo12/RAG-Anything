"""
Qwen LLM / Vision / Embedding 封装，基于阿里云百炼（DashScope）OpenAI 兼容接口。

- 文本对话：llm_model_func
- 视觉/多模态：vision_model_func
- 文本向量：embedding_func（EmbeddingFunc 实例，内部为 text-embedding-v4）、qwen_embed

参考：
- 向量化与模型：https://help.aliyun.com/zh/model-studio/embedding
- OpenAI 兼容：https://help.aliyun.com/zh/model-studio/developer-reference/compatibility-of-openai-with-dashscope
"""

import logging
import asyncio
import numpy as np
import requests
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc

logger = logging.getLogger(__name__)

# Qwen text-embedding-v4 输出维度，与 EmbeddingFunc(embedding_dim=2048) 一致
QWEN_EMBED_DIM = 2048

# 优先使用 config 中的常量，其次环境变量
try:
    from config.api_keys import DASHSCOPE_API_KEY
except ImportError:
    DASHSCOPE_API_KEY = ""

from config.model_conf import (
    DASHSCOPE_BASE_URL,
    QWEN_CHAT_MODEL,
    QWEN_VISION_MODEL,
    QWEN_EMBED_MODEL,
    QWEN_RERANK_MODEL,
    QWEN_RERANK_BASE_URL,
)


def _get_api_key():
    """优先使用 config.api_keys，其次环境变量。"""
    key = (DASHSCOPE_API_KEY or "").strip()
    return key or None


def llm_model_func(prompt, system_prompt=None, history_messages=None, **kwargs):
    """
    文本对话：调用 Qwen 对话模型（OpenAI 兼容接口）。
    供 RAGAnything 等使用，与 openai_complete_if_cache 签名一致。
    """
    if history_messages is None:
        history_messages = []
    return openai_complete_if_cache(
        QWEN_CHAT_MODEL,
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
        api_key=_get_api_key(),
        base_url=DASHSCOPE_BASE_URL,
        extra_body={"enable_thinking":False},
        **kwargs,
    )


def vision_model_func(
    prompt,
    system_prompt=None,
    history_messages=None,
    image_data=None,
    messages=None,
    **kwargs,
):
    """
    视觉/多模态：支持 messages 多轮格式或单图 + prompt。
    供 RAGAnything 多模态查询、图像描述等使用。
    """
    if history_messages is None:
        history_messages = []
    if messages:
        return openai_complete_if_cache(
            QWEN_VISION_MODEL,
            "",
            system_prompt=None,
            history_messages=[],
            messages=messages,
            api_key=_get_api_key(),
            base_url=DASHSCOPE_BASE_URL,
            **kwargs,
        )
    if image_data:
        # 只加入 system 消息当 system_prompt 非空，避免 messages 中出现 None 导致 API 报 "message must be json_object"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_data}"},
                },
            ],
        })
        return openai_complete_if_cache(
            QWEN_VISION_MODEL,
            "",
            system_prompt=None,
            history_messages=[],
            messages=messages,
            api_key=_get_api_key(),
            base_url=DASHSCOPE_BASE_URL,
            **kwargs,
        )
    return llm_model_func(prompt, system_prompt, history_messages, **kwargs)


async def qwen_embed(texts, **kwargs):
    """
    文本向量：使用 Qwen text-embedding-v4。

    - 默认模型：text-embedding-v4（可通过环境变量 QWEN_EMBED_MODEL 覆盖）
    - 默认 base_url：DASHSCOPE_BASE_URL
    - 默认 API Key：config.api_keys.DASHSCOPE_API_KEY 或环境变量 DASHSCOPE_API_KEY

    可通过关键字参数覆盖：
    - api_key
    - base_url
    - dimensions 等（参考阿里云文档）

    注意：必须调用 openai_embed.func 而非 openai_embed，否则会触发 LightRAG 自带的
    EmbeddingFunc(embedding_dim=1536) 校验，与 Qwen 2048 维输出不一致导致报错。

    对空字符串：仅对非空文本请求 API，空位用零向量填充，保证返回 len(texts) 个向量，
    避免 DashScope 跳过空串导致 "expected N vectors but got M" 报错。
    """
    api_key = kwargs.pop("api_key", _get_api_key())
    base_url = kwargs.pop("base_url", DASHSCOPE_BASE_URL)
    texts = list(texts)
    n = len(texts)
    non_empty_indices = [i for i, t in enumerate(texts) if (t is not None and str(t).strip())]
    non_empty_texts = [texts[i] for i in non_empty_indices]
    n_non_empty = len(non_empty_texts)

    if n_non_empty == n:
        # 全部非空，直接请求
        emb = await openai_embed.func(
            texts,
            model=QWEN_EMBED_MODEL,
            api_key=api_key,
            base_url=base_url,
            embedding_dim=QWEN_EMBED_DIM,
            **kwargs,
        )
        n_out = emb.shape[0] if hasattr(emb, "shape") and len(emb.shape) >= 1 else len(emb)
        # logger.info("qwen_embed: all non-empty path, n_out=%s emb.shape=%s", n_out, getattr(emb, "shape", None))
        if n_out != n:
            logger.warning("qwen_embed: vector count mismatch (expected %d got %d), padding to match", n, n_out)
            out = np.zeros((n, QWEN_EMBED_DIM), dtype=np.float32)
            emb_2d = emb.reshape(-1, QWEN_EMBED_DIM) if emb.size == n_out * QWEN_EMBED_DIM else emb
            copy_n = min(n, emb_2d.shape[0])
            out[:copy_n] = emb_2d[:copy_n]
            return out
        return emb

    if n_non_empty == 0:
        logger.info("qwen_embed: all empty, returning %d zero vectors", n)
        return np.zeros((n, QWEN_EMBED_DIM), dtype=np.float32)

    # 仅对非空文本请求，再按原顺序拼回（空位填零向量）
    emb = await openai_embed.func(
        non_empty_texts,
        model=QWEN_EMBED_MODEL,
        api_key=api_key,
        base_url=base_url,
        embedding_dim=QWEN_EMBED_DIM,
        **kwargs,
    )
    n_out = emb.shape[0] if hasattr(emb, "shape") and len(emb.shape) >= 1 else len(emb)
    # logger.info("qwen_embed: partial path n_non_empty=%d n_returned=%s emb.shape=%s", n_non_empty, n_out, getattr(emb, "shape", None))
    if n_out != n_non_empty:
        logger.warning("qwen_embed: API returned %d vectors for %d non-empty texts", n_out, n_non_empty)
    out = np.zeros((n, QWEN_EMBED_DIM), dtype=np.float32)
    for idx, pos in enumerate(non_empty_indices):
        if idx < n_out:
            out[pos] = emb[idx]
    return out


# 与 llm_model_func、vision_model_func 同级的可引用对象：EmbeddingFunc 实例，直接传入 RAGAnything 的 embedding_func 参数即可（无需调用）
embedding_func = EmbeddingFunc(
    embedding_dim=2048,
    max_token_size=8192,
    func=qwen_embed,
)


async def qwen_rerank_model_func(
    query: str,
    documents: list[str],
    top_n: int | None = None,
    **kwargs,
):
    """
    使用百炼 qwen3-rerank 对候选文本进行重排序。

    约定：
    - 输入：query（查询语句）、documents（候选文档内容列表）
    - 输出：与 documents 等长的浮点分数列表，数值越大表示与 query 越相关
    """
    api_key = _get_api_key()
    if not api_key:
        raise ValueError("DASHSCOPE_API_KEY 未配置，无法调用 qwen3-rerank")

    if not documents:
        return []

    # 百炼文档推荐的 rerank URL 形如：
    #   https://dashscope.aliyuncs.com/compatible-api/v1/reranks
    base_url = QWEN_RERANK_BASE_URL.rstrip("/")
    url = base_url + "/reranks"

    # 严格按照官方示例构造请求体：
    # {
    #   "model": "qwen3-rerank",
    #   "documents": ["doc1", "doc2", ...],
    #   "query": "xxx",
    #   "top_n": 2,
    #   "instruct": "..."
    # }
    payload: dict[str, object] = {
        "model": QWEN_RERANK_MODEL,
        "documents": [str(doc) for doc in documents],
        "query": query,
        "instruct": kwargs.pop(
            "instruct",
            "Given a web search query, retrieve relevant passages that answer the query.",
        ),
    }
    if top_n is not None:
        payload["top_n"] = min(top_n, len(documents))

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # 在异步环境中以非阻塞方式调用同步 requests.post
    resp = await asyncio.to_thread(
        requests.post,
        url,
        headers=headers,
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    # 根据百炼 qwen3-rerank 返回格式提取分数
    # 典型结构：
    # {
    #   "output": {
    #     "results": [
    #       {"index": 0, "relevance_score": 0.98, ...},
    #       {"index": 2, "relevance_score": 0.80, ...},
    #       ...
    #     ]
    #   },
    #   "usage": {...},
    #   "request_id": "..."
    # }
    items = data.get("output", {}).get("results", [])
    score_by_index: dict[int, float] = {}
    for i, item in enumerate(items):
        try:
            idx = int(item.get("index", i))
        except Exception:  # noqa: BLE001
            idx = i
        try:
            score = float(item.get("relevance_score", 0.0))
        except Exception:  # noqa: BLE001
            score = 0.0
        score_by_index[idx] = score

    # 文档对象类型：可能是 chunk dict，也可能是纯字符串
    first_doc = documents[0] if documents else None
    is_dict_like = isinstance(first_doc, dict)

    # 按得分排序
    sorted_indices = sorted(
        range(len(documents)),
        key=lambda i: score_by_index.get(i, 0.0),
        reverse=True,
    )

    if is_dict_like:
        # 直接返回重排后的 chunk 字典列表（LightRAG 旧格式）
        reranked_docs = [documents[i] for i in sorted_indices]
    else:
        # 为避免 LightRAG 对元素调用 .copy() 报错，将字符串包装成 dict
        reranked_docs = [
            {"content": documents[i]} for i in sorted_indices
        ]

    logger.info(
        "qwen_rerank_model_func: reranked %d docs (top score=%.4f, min=%.4f, dict_like=%s)",
        len(reranked_docs),
        max(score_by_index.values() or [0.0]),
        min(score_by_index.values() or [0.0]),
        is_dict_like,
    )

    return reranked_docs

