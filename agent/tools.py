from __future__ import annotations

"""
Tools for LangChain agents to interact with RAG-Anything.

设计原则：
- 工具面向“某一个知识库实例”，即在构建工具时注入 doc_meta / 目录信息；
- Agent 在调用时只需要传入问题、页码等“语义参数”，不关心底层路径；
- 查询工具直接复用现有的 RAG-Anything 查询能力；
- 上下文路由工具基于 MinerU 的解析结构（content_list.json）按页返回上下文。
"""

import asyncio
import inspect
import logging
import time
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
import xml.etree.ElementTree as ET

from pydantic import BaseModel, Field
from lightrag.utils import always_get_an_event_loop

# Lazy import web.rag_service inside tool methods to avoid circular import:
# web.rag_service -> agent -> agent.tools -> web.rag_service
from raganything.utils import encode_image_to_base64, validate_image_file
from raganything.product.resolve import resolve_working_dir_v2
from llm import vision_model_func


logger = logging.getLogger(__name__)


_ENTITY_DESC_MAX_CHARS = 200
_CHUNK_CONTENT_MAX_CHARS = 300
_TRUNCATED_SUFFIX = "...[truncated]"


def _truncate(text: str, limit: int) -> str:
    if not isinstance(text, str) or len(text) <= limit:
        return text
    return text[:limit] + _TRUNCATED_SUFFIX


def _strip_query_result_for_agent(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    从 query 返回结果中提取并清洗 entity 列表，减小 token 占用。

    仅返回 `entities` 字段，其它字段（relationships/chunks/references）不再包含在结果中。
    长文本字段（description）会被截断，Agent 可通过 kb_entity_neighbors 获取完整内容。
    """
    if not isinstance(data, dict):
        return {"entities": []}

    entities_raw = data.get("entities") or []
    if not isinstance(entities_raw, list):
        entities_raw = []

    entities = []
    for e in entities_raw:
        if not isinstance(e, dict):
            continue
        cleaned = {
            k: v
            for k, v in e.items()
            if k not in ("file_path", "created_at")
        }
        if "description" in cleaned:
            cleaned["description"] = _truncate(cleaned["description"], _ENTITY_DESC_MAX_CHARS)
        entities.append(cleaned)
    return {"entities": entities}


def _strip_chunks_result_for_agent(data: Dict[str, Any]) -> Dict[str, Any]:
    """从 query 返回结果中提取并清洗 chunk 列表，仅保留与内容理解直接相关的字段。

    长文本字段（content）会被截断，Agent 可通过 kb_chunks_by_id 获取完整内容。
    """
    if not isinstance(data, dict):
        return {"chunks": []}

    chunks_raw = data.get("chunks") or []
    if not isinstance(chunks_raw, list):
        chunks_raw = []

    chunks = []
    for c in chunks_raw:
        if not isinstance(c, dict):
            continue
        cleaned = {
            k: v
            for k, v in c.items()
            if k not in ("reference_id", "file_path", "created_at")
        }
        if "content" in cleaned:
            cleaned["content"] = _truncate(cleaned["content"], _CHUNK_CONTENT_MAX_CHARS)
        chunks.append(cleaned)
    return {"chunks": chunks}


class _QueryInput(BaseModel):
    hl_keywords: List[str] = Field(
        default_factory=list,
        description=(
            "High-level keywords that describe the main semantic intent of the query. "
            "These guide the overall direction of RAG retrieval."
        ),
    )
    ll_keywords: List[str] = Field(
        default_factory=list,
        description=(
            "Low-level, fine-grained keywords that provide additional retrieval hints, "
            "such as entity names, page numbers, or specific terms."
        ),
    )
    top_k: int = Field(
        default=10,
        ge=1,
        le=100,
        description=(
            "Maximum number of retrieved items to return. "
            "This value is passed to the underlying QueryParam.top_k."
        ),
    )


class RAGQueryTool(BaseTool):
    """仅返回实体（entities）的检索工具，面向单一知识库实例。

    - 不在工具内部调用 LLM，只调用 LightRAG 的检索接口；
    - 只返回结构化的实体列表 `entities`，不包含 relationships / chunks / references；
    - 由外层 Agent 负责阅读、推理与决策。
    """

    name: str = "kb_query"
    description: str = (
        "Query the currently bound knowledge base and return entity summaries "
        "(with truncated descriptions). "
        "Use this tool whenever you need to answer questions based on PDF / document content. "
        "NOTE: entity descriptions are truncated; use `kb_entity_neighbors` with a node id "
        "to retrieve the full description when needed."
    )

    doc_meta: Dict[str, Any]
    # 在同步 tool 执行（可能发生在线程池）时，将协程转发到该 loop 上执行，
    # 避免在不同事件循环间使用 LightRAG 的 asyncio.Lock。
    executor_loop: Any = Field(default=None, exclude=True)

    args_schema: type[BaseModel] = _QueryInput

    def _run(
        self,
        hl_keywords: List[str] | None = None,
        ll_keywords: List[str] | None = None,
        top_k: int = 10,
    ) -> str:
        # 在 tool 调用入口增加详细日志，方便排查上游调用问题
        try:
            # 尽量不引入新的依赖，使用标准输出打印关键信息
            print(
                "[RAGQueryTool._run] start, "
                f"doc_id={self.doc_meta.get('doc_id')}, "
                f"working_dir={self.doc_meta.get('working_dir')}, "
                f"parsed_dir={self.doc_meta.get('parsed_dir')}, "
                f"hl_keywords={hl_keywords!r}, "
                f"ll_keywords={ll_keywords!r}, "
                f"top_k={top_k}"
            )
        except Exception:
            pass

        # 归一化空值，便于后续传递
        from web.rag_service import query_data_only

        hl_keywords = hl_keywords or []
        ll_keywords = ll_keywords or []

        if self.executor_loop is not None and getattr(
            self.executor_loop, "is_running", lambda: False
        )():
            fut = asyncio.run_coroutine_threadsafe(
                query_data_only(
                    self.doc_meta,
                    hl_keywords=hl_keywords,
                    ll_keywords=ll_keywords,
                    top_k=top_k,
                    kb_version=self.doc_meta.get("kb_version", "v1"),
                ),
                self.executor_loop,
            )
            references = fut.result()
        else:
            loop = always_get_an_event_loop()
            references = loop.run_until_complete(
                query_data_only(
                    self.doc_meta,
                    hl_keywords=hl_keywords,
                    ll_keywords=ll_keywords,
                    top_k=top_k,
                    kb_version=self.doc_meta.get("kb_version", "v1"),
                )
            )

        stripped = _strip_query_result_for_agent(references)
        n = len(stripped.get("entities", []))
        logger.info("references: %d entities", n)
        # json.dumps 无“忽略空字段”参数，空值已在 _strip_query_result_for_agent 中剔除；不传 indent 保持紧凑
        return json.dumps(stripped, ensure_ascii=False)

    async def _arun(
        self,
        hl_keywords: List[str] | None = None,
        ll_keywords: List[str] | None = None,
        top_k: int = 10,
    ) -> str:
        from web.rag_service import query_data_only

        hl_keywords = hl_keywords or []
        ll_keywords = ll_keywords or []
        references = await query_data_only(
            self.doc_meta,
            hl_keywords=hl_keywords,
            ll_keywords=ll_keywords,
            top_k=top_k,
            kb_version=self.doc_meta.get("kb_version", "v1"),
        )
        stripped = _strip_query_result_for_agent(references)
        n = len(stripped.get("entities", []))
        logger.info("references: %d entities", n)
        # json.dumps 无“忽略空字段”参数，空值已在 _strip_query_result_for_agent 中剔除；不传 indent 保持紧凑
        return json.dumps(stripped, ensure_ascii=False)


class ChunkQueryTool(BaseTool):
    """仅返回 chunk 列表的检索工具，面向单一知识库实例。

    - 不在工具内部调用 LLM，只调用 LightRAG 的检索接口；
    - 只返回结构化的 chunk 列表 `chunks`，不包含 entities / relationships / references；
    - 适合需要直接基于原始文本块进行推理的 Agent。
    """

    name: str = "kb_chunk_query"
    description: str = (
        "Query the currently bound knowledge base and return chunk summaries "
        "(with truncated content). "
        "Use this tool when you want to reason directly over raw chunks instead of entities. "
        "NOTE: chunk content is truncated; use `kb_chunks_by_id` with specific chunk ids "
        "to retrieve the full text when needed."
    )

    doc_meta: Dict[str, Any]
    executor_loop: Any = Field(default=None, exclude=True)

    args_schema: type[BaseModel] = _QueryInput

    def _run(
        self,
        hl_keywords: List[str] | None = None,
        ll_keywords: List[str] | None = None,
        top_k: int = 10,
    ) -> str:
        try:
            print(
                "[ChunkQueryTool._run] start, "
                f"doc_id={self.doc_meta.get('doc_id')}, "
                f"working_dir={self.doc_meta.get('working_dir')}, "
                f"parsed_dir={self.doc_meta.get('parsed_dir')}, "
                f"hl_keywords={hl_keywords!r}, "
                f"ll_keywords={ll_keywords!r}, "
                f"top_k={top_k}"
            )
        except Exception:
            pass

        from web.rag_service import query_data_only

        hl_keywords = hl_keywords or []
        ll_keywords = ll_keywords or []

        if self.executor_loop is not None and getattr(
            self.executor_loop, "is_running", lambda: False
        )():
            fut = asyncio.run_coroutine_threadsafe(
                query_data_only(
                    self.doc_meta,
                    hl_keywords=hl_keywords,
                    ll_keywords=ll_keywords,
                    top_k=top_k,
                    kb_version=self.doc_meta.get("kb_version", "v1"),
                ),
                self.executor_loop,
            )
            data = fut.result()
        else:
            loop = always_get_an_event_loop()
            data = loop.run_until_complete(
                query_data_only(
                    self.doc_meta,
                    hl_keywords=hl_keywords,
                    ll_keywords=ll_keywords,
                    top_k=top_k,
                    kb_version=self.doc_meta.get("kb_version", "v1"),
                )
            )

        stripped = _strip_chunks_result_for_agent(data)
        n = len(stripped.get("chunks", []))
        logger.info("chunks: %d entries", n)
        return json.dumps(stripped, ensure_ascii=False)

    async def _arun(
        self,
        hl_keywords: List[str] | None = None,
        ll_keywords: List[str] | None = None,
        top_k: int = 10,
    ) -> str:
        from web.rag_service import query_data_only

        hl_keywords = hl_keywords or []
        ll_keywords = ll_keywords or []
        data = await query_data_only(
            self.doc_meta,
            hl_keywords=hl_keywords,
            ll_keywords=ll_keywords,
            top_k=top_k,
            kb_version=self.doc_meta.get("kb_version", "v1"),
        )
        stripped = _strip_chunks_result_for_agent(data)
        n = len(stripped.get("chunks", []))
        logger.info("chunks: %d entries", n)
        return json.dumps(stripped, ensure_ascii=False)


class _EntityNeighborsInput(BaseModel):
    node_id: str = Field(
        description=(
            "Graph node id of the entity (or chunk) whose 1-hop neighbors you want to inspect. "
            "This should be the `id` field from the knowledge graph, typically returned by "
            "other tools or the graph visualization."
        )
    )


class EntityNeighborsTool(BaseTool):
    """基于图数据查询某个实体节点及其一阶邻居。"""

    name: str = "kb_entity_neighbors"
    description: str = (
        "Given a graph node id, return the entity node detail and its 1-hop neighbors "
        "from the knowledge graph built for the current knowledge base. "
        "Use this tool when you need to explore nearby entities or chunks around a center entity."
    )

    doc_meta: Dict[str, Any]

    args_schema: type[BaseModel] = _EntityNeighborsInput

    def _run(self, node_id: str) -> str:
        from web.rag_service import get_doc_graph_node_detail

        try:
            detail = get_doc_graph_node_detail(self.doc_meta, node_id=node_id)
        except Exception as e:  # noqa: BLE001
            # 工具调用场景下尽量不要抛出 HTTPException，转成字符串错误信息即可
            return f"Failed to load entity neighbors for node_id={node_id!r}: {e}"

        return json.dumps(detail, ensure_ascii=False)

    async def _arun(self, node_id: str) -> str:
        # 后端实现是同步 IO + CPU 解析，这里放到线程池中执行以避免阻塞事件循环
        return await asyncio.to_thread(self._run, node_id)


class _ChunkByIdInput(BaseModel):
    chunk_ids: List[str] = Field(
        description=(
            "List of chunk_id strings whose metadata and descriptions you want to retrieve. "
            "These chunk_ids should come from previous retrieval results."
        )
    )


class ChunkByIdTool(BaseTool):
    """根据 chunk_id 列表，在图数据中查找对应的 chunk 节点及其描述。"""

    name: str = "kb_chunks_by_id"
    description: str = (
        "Given a list of chunk_id strings, look up the corresponding chunk nodes in the "
        "knowledge graph (graph_chunk_entity_relation.graphml) and return their basic "
        "metadata (chunk_id, node_id, type, description). "
        "Use this tool when you already know which chunks are relevant and just need "
        "their content/description again."
    )

    doc_meta: Dict[str, Any]

    args_schema: type[BaseModel] = _ChunkByIdInput

    def _run(self, chunk_ids: List[str]) -> str:
        normalized_ids = [
            str(cid).strip() for cid in (chunk_ids or []) if str(cid).strip()
        ]
        if not normalized_ids:
            return json.dumps({"chunks": []}, ensure_ascii=False)

        try:
            chunks = self._lookup_chunks_by_ids(normalized_ids)
        except Exception as e:  # noqa: BLE001
            return f"Failed to lookup chunks by ids {normalized_ids!r}: {e}"

        return json.dumps({"chunks": chunks}, ensure_ascii=False)

    async def _arun(self, chunk_ids: List[str]) -> str:
        return await asyncio.to_thread(self._run, chunk_ids)

    def _lookup_chunks_by_ids(self, chunk_ids: List[str]) -> List[Dict[str, Any]]:
        working_dir = (self.doc_meta.get("working_dir") or "").strip()
        if not working_dir:
            raise RuntimeError("知识库工作目录缺失，无法加载图数据")

        graph_path = Path(working_dir) / "graph_chunk_entity_relation.graphml"
        if not graph_path.exists():
            raise FileNotFoundError(f"图数据文件不存在: {graph_path}")

        try:
            root = ET.parse(graph_path).getroot()
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"解析图数据失败: {e}") from e

        ns = {"g": "http://graphml.graphdrawing.org/xmlns"}

        # 收集 node key -> attr_name 映射
        node_key_map: Dict[str, str] = {}
        for key in root.findall("g:key", ns):
            key_id = key.attrib.get("id")
            attr_name = key.attrib.get("attr.name")
            key_for = key.attrib.get("for")
            if key_id and attr_name and key_for == "node":
                node_key_map[key_id] = attr_name

        wanted = set(chunk_ids)
        results: List[Dict[str, Any]] = []

        for node in root.findall(".//g:node", ns):
            node_id = node.attrib.get("id") or ""
            attrs: Dict[str, Any] = {}
            for data in node.findall("g:data", ns):
                key_id = data.attrib.get("key")
                attr_name = node_key_map.get(key_id)
                if not attr_name:
                    continue
                text = (data.text or "").strip() if data.text is not None else ""
                attrs[attr_name] = text

            # chunk_id 可能存储在 entity_id 或单独的 chunk_id 字段中，这里做一个宽松匹配
            candidate_ids = {
                str(attrs.get("chunk_id") or "").strip(),
                str(attrs.get("entity_id") or "").strip(),
                str(node_id).strip(),
            }

            matched = wanted.intersection(candidate_ids)
            if not matched:
                continue

            # 若多个候选同时命中，只取第一个以避免重复
            matched_id = next(iter(matched))
            results.append(
                {
                    "chunk_id": matched_id,
                    "node_id": node_id,
                    "entity_id": attrs.get("entity_id"),
                    "type": attrs.get("entity_type"),
                    "description": attrs.get("description"),
                }
            )

            # 若不希望同一个 chunk_id 出现多次，可从 wanted 中移除
            wanted.discard(matched_id)
            if not wanted:
                break

        return results


class _PageContextInput(BaseModel):
    page_idx: int = Field(
        description=(
            "Zero-based page index whose context you want to inspect. "
            "This typically comes from the page_idx field in retrieval results."
        )
    )
    window: int = Field(
        default=1,
        ge=0,
        le=5,
        description=(
            "Context window size: how many extra pages before and after the target page "
            "should be included. For example, window=1 returns page_idx-1, page_idx, "
            "and page_idx+1."
        ),
    )


class PageContextTool(BaseTool):
    """Tool that returns page-level text context based on MinerU parsing results."""

    name: str = "kb_page_context"
    description: str = (
        "Given a page index (page_idx), return the original text context on that page "
        "and nearby pages. Use this tool when you already know which page is relevant "
        "and need to inspect more surrounding context."
    )

    parsed_dir: Path

    args_schema: type[BaseModel] = _PageContextInput

    def _load_content_list(self) -> List[Dict[str, Any]]:
        from web.rag_service import load_content_list_read_only

        content_list, _ = load_content_list_read_only(self.parsed_dir)
        return content_list

    def _run(self, page_idx: int, window: int = 1) -> str:
        content_list = self._load_content_list()

        start_page = max(0, page_idx - window)
        end_page = page_idx + window

        items: List[Dict[str, Any]] = [
            item
            for item in content_list
            if isinstance(item, dict)
            and isinstance(item.get("page_idx"), int)
            and start_page <= item["page_idx"] <= end_page
            and item.get("type") in {"text", "list", "header", "paragraph", "title"}
        ]

        # 将相同 page_idx 的内容拼接在一起
        pages: Dict[int, List[str]] = {}
        for item in items:
            page = int(item["page_idx"])
            text = ""
            if item.get("type") == "list" and isinstance(
                item.get("list_items"), list
            ):
                text = " ".join(str(x) for x in item["list_items"])
            else:
                text = str(item.get("text") or "")
            if not text.strip():
                continue
            pages.setdefault(page, []).append(text.strip())

        if not pages:
            return (
                f"No context found for page_idx={page_idx} "
                f"(window={window}) in parsed_dir={self.parsed_dir}"
            )

        lines: List[str] = []
        for p in sorted(pages.keys()):
            lines.append(f"[Page {p}]")
            lines.append("\n".join(pages[p]))
            lines.append("")

        return "\n".join(lines)

    async def _arun(self, page_idx: int, window: int = 1) -> str:
        # 解析 content_list 本身是同步 IO，这里直接复用同步实现即可。
        return self._run(page_idx=page_idx, window=window)


class _ImageVLMInput(BaseModel):
    image_path: str = Field(
        description=(
            "Path to the image file to analyze. Must be a locally accessible image "
            "file of type jpg/jpeg/png/gif/bmp/webp/tiff/tif."
        )
    )
    prompt: str = Field(
        description=(
            "User instruction or question about the image. This will be sent as the "
            "user prompt to the multimodal (vision-language) model."
        )
    )
    system_prompt: Optional[str] = Field(
        default=None,
        description=(
            "Optional system prompt for constraining the behavior of the multimodal model."
        ),
    )


class ImageVLMTool(BaseTool):
    """
    Tool for directly invoking the underlying VLM (e.g., Qwen-VL) to analyze a single image.

    - Input: local image path + user prompt (optional system prompt)
    - Output: text response from the multimodal model
    """

    name: str = "vlm_image_query"
    description: str = (
        "Given a local image path and a text instruction, call the multimodal model (VLM) "
        "to perform image understanding or visual question answering. "
        "Use this tool when you need to look at an image directly, explain its content, "
        "or perform visual reasoning."
    )

    args_schema: type[BaseModel] = _ImageVLMInput

    def _call_vlm(self, image_path: str, prompt: str, system_prompt: Optional[str]) -> str:
        # 校验图片
        if not validate_image_file(image_path):
            return f"Invalid or unsupported image file: {image_path}"

        image_b64 = encode_image_to_base64(image_path)
        if not image_b64:
            return f"Failed to read or encode image: {image_path}"

        # 调用底层 vision_model_func；兼容返回同步/异步两种情况
        result = vision_model_func(
            prompt,
            system_prompt=system_prompt,
            image_data=image_b64,
        )
        if inspect.isawaitable(result):
            loop = always_get_an_event_loop()
            return loop.run_until_complete(result)
        return str(result)

    def _run(self, image_path: str, prompt: str, system_prompt: Optional[str] = None) -> str:
        return self._call_vlm(image_path=image_path, prompt=prompt, system_prompt=system_prompt)

    async def _arun(
        self,
        image_path: str,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        # 若 vision_model_func 将来变为真正的 async，则直接 await
        result = vision_model_func(
            prompt,
            system_prompt=system_prompt,
            image_data=encode_image_to_base64(image_path)
            if validate_image_file(image_path)
            else None,
        )
        if inspect.isawaitable(result):
            return str(await result)
        # 当前实现是同步的，这里放到线程池避免阻塞事件循环
        return str(
            await asyncio.to_thread(
                self._call_vlm, image_path=image_path, prompt=prompt, system_prompt=system_prompt
            )
        )


class _ProductInfoInput(BaseModel):
    filter_type: str = Field(
        default="all",
        description=(
            "Which section of the product info to return. "
            "Options: 'all' (full JSON), 'product' (product overview only), "
            "'components' (components list), 'features' (features list), "
            "'parameters' (product-level parameters), 'attributes' (product-level attributes)."
        ),
    )
    filter_name: Optional[str] = Field(
        default=None,
        description=(
            "Optional name to filter a specific component or feature by name. "
            "Only effective when filter_type is 'components' or 'features'. "
            "Case-insensitive substring match."
        ),
    )


class ProductInfoTool(BaseTool):
    """Return structured Product Info extracted from the document.

    Reads the pre-generated ``product info.json`` from the v2 working directory.
    Use this as the FIRST tool call to get a high-level map of the product
    (components, features, parameters) before doing detailed retrieval.
    """

    name: str = "product_info"
    description: str = (
        "Return the structured Product Info (product overview, components, features, "
        "parameters, attributes) extracted from the document. "
        "Use this as the FIRST tool call to get a high-level map of the product "
        "before detailed retrieval. Supports filtering by section or name."
    )

    doc_meta: Dict[str, Any]

    args_schema: type[BaseModel] = _ProductInfoInput

    def _resolve_product_info_path(self) -> Path:
        working_dir = (self.doc_meta.get("working_dir") or "").strip()
        if not working_dir:
            raise FileNotFoundError("知识库工作目录缺失")

        v2_dir = resolve_working_dir_v2(working_dir)
        return Path(v2_dir) / "product info.json"

    def _load_product_info(self) -> Dict[str, Any]:
        info_path = self._resolve_product_info_path()
        if not info_path.exists():
            raise FileNotFoundError(
                f"product info.json not found at {info_path}. "
                "The v2 index may not have been generated yet."
            )
        return json.loads(info_path.read_text(encoding="utf-8"))

    @staticmethod
    def _filter_by_name(items: list, name: str) -> list:
        lower_name = name.lower()
        return [
            item for item in items
            if isinstance(item, dict)
            and lower_name in (item.get("name") or "").lower()
        ]

    def _run(
        self,
        filter_type: str = "all",
        filter_name: Optional[str] = None,
    ) -> str:
        try:
            info = self._load_product_info()
        except FileNotFoundError as e:
            return str(e)

        ft = (filter_type or "all").lower().strip()

        if ft == "product":
            result = {"product": info.get("product", {})}
        elif ft == "components":
            items = info.get("components") or []
            if filter_name:
                items = self._filter_by_name(items, filter_name)
            result = {"components": items}
        elif ft == "features":
            items = info.get("features") or []
            if filter_name:
                items = self._filter_by_name(items, filter_name)
            result = {"features": items}
        elif ft == "parameters":
            result = {"parameters": info.get("parameters") or []}
        elif ft == "attributes":
            result = {"attributes": info.get("attributes") or []}
        else:
            result = info

        return json.dumps(result, ensure_ascii=False)

    async def _arun(
        self,
        filter_type: str = "all",
        filter_name: Optional[str] = None,
    ) -> str:
        return await asyncio.to_thread(self._run, filter_type, filter_name)


class _WriteJsonFileInput(BaseModel):
    file_path: str = Field(
        description=(
            "Absolute path of the JSON file to write. "
            "The parent directories will be created automatically."
        )
    )
    content: Dict[str, Any] = Field(
        description="The JSON object to write to the file."
    )


class WriteJsonFileTool(BaseTool):
    """Write a JSON object to a file on disk.

    Designed for the ProductInfoPipeline: each sub-agent writes its
    extraction result to a designated file. The pipeline later reads
    and merges all files.

    A configurable ``allowed_directory`` restricts writes to a single
    directory tree for safety.
    """

    name: str = "write_json_file"
    description: str = (
        "Write a JSON object to the specified file path. "
        "Parent directories are created automatically. "
        "Use this tool to persist your extraction result."
    )

    allowed_directory: str = Field(
        description="Root directory that this tool is allowed to write into."
    )

    args_schema: type[BaseModel] = _WriteJsonFileInput

    def _run(self, file_path: str, content: Dict[str, Any]) -> str:
        from pathlib import Path as _P

        target = _P(file_path).resolve()
        allowed = _P(self.allowed_directory).resolve()
        if not str(target).startswith(str(allowed)):
            return (
                f"REJECTED: path '{file_path}' is outside the allowed "
                f"directory '{self.allowed_directory}'."
            )

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(content, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            return f"ERROR writing file: {exc}"

        return f"OK: wrote to {target}"

    async def _arun(self, file_path: str, content: Dict[str, Any]) -> str:
        return await asyncio.to_thread(self._run, file_path, content)


def build_rag_agent_tools(
    doc_meta: Dict[str, Any],
    *,
    include_page_context_tool: bool = True,
    include_vlm_image_tool: bool = True,
    include_product_info_tool: bool = True,
) -> List[BaseTool]:
    """
    Build a set of LangChain tools for a single knowledge base.

    Directory-related information (such as working_dir / parsed_dir) is injected here,
    so Agents do not need to pass these paths when calling tools.

    Args:
        doc_meta: Metadata for a single knowledge base, typically loaded from the web
                  layer's meta.json. Must contain at least `parsed_dir` and `working_dir`.
        include_page_context_tool: Whether to include the page-context viewing tool.
        include_vlm_image_tool: Whether to include the VLM image analysis tool.
        include_product_info_tool: Whether to include the product info tool (reads v2 JSON).

    Returns:
        List[BaseTool]: Tools that can be passed to agent creation (e.g. create_agent).
    """
    tools: List[BaseTool] = []

    try:
        executor_loop = asyncio.get_running_loop()
    except RuntimeError:
        executor_loop = None

    tools.append(RAGQueryTool(doc_meta=dict(doc_meta), executor_loop=executor_loop))
    tools.append(ChunkQueryTool(doc_meta=dict(doc_meta), executor_loop=executor_loop))
    tools.append(EntityNeighborsTool(doc_meta=dict(doc_meta)))
    tools.append(ChunkByIdTool(doc_meta=dict(doc_meta)))

    if include_page_context_tool:
        parsed_dir_raw: Optional[str] = (
            doc_meta.get("parsed_dir") if isinstance(doc_meta, dict) else None
        )
        if parsed_dir_raw:
            parsed_dir = Path(parsed_dir_raw).resolve()
            if parsed_dir.exists():
                tools.append(PageContextTool(parsed_dir=parsed_dir))

    if include_vlm_image_tool:
        tools.append(ImageVLMTool())

    if include_product_info_tool:
        tools.append(ProductInfoTool(doc_meta=dict(doc_meta)))

    return tools


class _CreateRunAgentInput(BaseModel):
    system_prompt: str = Field(
        description=(
            "System prompt used to create the new Agent. This defines the Agent's "
            "role and behavior style."
        )
    )
    tool_names: List[str] = Field(
        description=(
            "List of tool names (by `name` field) to assign to the new Agent. "
            "This list must not include this tool itself."
        )
    )
    task: str = Field(
        description=(
            "Task or problem for the new Agent to solve, e.g. "
            "'read the knowledge base and provide a summary', "
            "'answer questions by combining images and documents', etc."
        )
    )


class CreateAndRunAgentTool(BaseTool):
    """
    A "meta-tool" that dynamically creates a new Agent and runs it once.

    - The outer code injects the llm and available tool list at initialization time.
    - Input: system_prompt + tool_names + task.
    - Behavior: creates a new tools-based Agent (excluding this meta-tool itself),
      executes the task once, and returns the result.
    """

    name: str = "create_and_run_agent"
    description: str = (
        "Dynamically create a new Agent using the given system prompt and tool list, "
        "then immediately run it on a single task. "
        "The newly created Agent will not include this meta-tool itself to avoid recursion."
    )

    llm: BaseChatModel
    available_tools: List[BaseTool]

    args_schema: type[BaseModel] = _CreateRunAgentInput

    def _select_tools(self, tool_names: List[str]) -> List[BaseTool]:
        # 去重并按名称过滤，同时确保不包含自身
        wanted = {name for name in tool_names}
        selected: List[BaseTool] = []
        for t in self.available_tools:
            if t is self:
                continue
            if t.name in wanted:
                selected.append(t)
        return selected

    def _run(
        self,
        system_prompt: str,
        tool_names: List[str],
        task: str,
    ) -> str:
        started = time.perf_counter()
        sp_preview = (system_prompt or "")[:160].replace("\n", "\\n")
        task_preview = (task or "")[:200].replace("\n", "\\n")

        logger.info(
            "CreateAndRunAgentTool start: requested_tools=%s task_preview=%r system_prompt_preview=%r",
            tool_names,
            task_preview,
            sp_preview,
        )

        tools = self._select_tools(tool_names)
        if not tools:
            return (
                "No valid tools selected for new agent. "
                f"Requested tools: {tool_names}"
            )

        augmented_prompt = system_prompt

        inner_agent = create_agent(
            model=self.llm,
            tools=tools,
            system_prompt=augmented_prompt,
        )

        messages_state: List[Dict[str, Any]] = [
            {"role": "user", "content": task},
        ]

        # Set a fixed upper bound for the internal agent recursion to avoid
        # unbounded tool-calling loops. This is independent of any user-facing
        # notion of "tool call budget".
        recursion_limit = 80

        result = inner_agent.invoke(
            {"messages": messages_state},
            config={"max_concurrency": 3, "recursion_limit": recursion_limit},
        )

        # 从 LangGraph 风格 state 中抽取最终文本
        output: Optional[str] = None
        if isinstance(result, Dict):
            msgs = result.get("messages")
            if msgs:
                last_msg = msgs[-1]
                if isinstance(last_msg, dict):
                    output = last_msg.get("content")
                else:
                    output = getattr(last_msg, "content", None)

            # 有些实现可能仍然返回 "output" 字段
            if output is None and "output" in result:
                output = str(result["output"])

        if output is None:
            output = str(result)

        return output

    async def _arun(
        self,
        system_prompt: str,
        tool_names: List[str],
        task: str,
    ) -> str:
        return await asyncio.to_thread(
            self._run,
            system_prompt,
            tool_names,
            task,
        )


