from __future__ import annotations

"""
Deterministic Python pipeline for Product Info extraction.

Architecture: each sub-agent writes its extraction result to a **JSON file**
on disk (via ``write_json_file`` tool).  The pipeline orchestrates the
workflow in code and merges the files into a single product info dict at
the end.

Directory layout created by the pipeline::

    {tmp_dir}/
      product.json
      components/
        left_button.json
        scroll_wheel.json
        …
      features/
        spo2_monitoring.json
        sleep_tracking.json
        …

Key robustness features:
- Hardcoded workflow steps (no LLM deciding "what to do next")
- File-based persistence — easy to inspect / debug
- Auto-recovery: if the LLM doesn't call the tool, parse JSON from its
  text output and write the file programmatically
- Exponential-backoff retry per step (with strengthened prompt on retry)
- Per-sub-agent timeout via asyncio.wait_for
- Graceful degradation (one failed item doesn't kill the pipeline)
- Final merge is pure Python — deterministic and reliable
"""

import asyncio
import json
import logging
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel

from agent.tools import build_rag_agent_tools, WriteJsonFileTool
from agent.prompt import (
    SUB_AGENT_PRODUCT_OVERVIEW_PROMPT,
    SUB_AGENT_DISCOVERY_PROMPT,
    SUB_AGENT_COMPONENT_DETAIL_PROMPT,
    SUB_AGENT_FEATURE_DETAIL_PROMPT,
)

logger = logging.getLogger(__name__)


def _safe_filename(name: str) -> str:
    """Turn an arbitrary component / feature name into a safe file stem."""
    stem = re.sub(r'[^\w\-]', '_', name.strip())[:120]
    return (stem or "unnamed") + ".json"


class ProductInfoPipeline:
    """
    Code-driven pipeline that extracts product info in deterministic
    steps, each backed by a focused sub-agent that writes to disk.

    Usage::

        pipeline = ProductInfoPipeline(doc_meta, schema, llm)
        product_info = await pipeline.run()
    """

    def __init__(
        self,
        doc_meta: Dict[str, Any],
        schema: Dict[str, Any],
        llm: BaseChatModel,
        *,
        max_retries: int = 2,
        sub_agent_timeout: float = 180.0,
        max_concurrency: int = 3,
        verbose: bool = False,
    ):
        self.doc_meta = doc_meta
        self.schema = schema
        self.llm = llm
        self.max_retries = max_retries
        self.sub_agent_timeout = sub_agent_timeout
        self.max_concurrency = max_concurrency
        self.verbose = verbose

        # Temp directory for sub-agent outputs — lives under runtime/{id}/tmp/
        runtime_root = Path(doc_meta.get("working_dir", ".")).resolve().parent
        self._tmp_dir = runtime_root / "tmp"
        if self._tmp_dir.exists():
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
            logger.info("Cleaned previous tmp_dir: %s", self._tmp_dir)
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Pipeline tmp_dir: %s", self._tmp_dir)

        self._rag_tools = build_rag_agent_tools(doc_meta)
        # The file-write tool, scoped to our tmp dir
        self._write_tool = WriteJsonFileTool(
            allowed_directory=str(self._tmp_dir),
        )
        self._all_tools = self._rag_tools + [self._write_tool]
        self._tool_map = {t.name: t for t in self._all_tools}

    # ------------------------------------------------------------------
    # Public entry
    # ------------------------------------------------------------------

    async def run(self) -> Dict[str, Any]:
        """Execute the full extraction pipeline and return merged result."""
        t0 = time.perf_counter()

        # Prepare subdirectories
        (self._tmp_dir / "components").mkdir(exist_ok=True)
        (self._tmp_dir / "features").mkdir(exist_ok=True)

        # Step 1 — Product overview
        await self._step_extract_product()

        # Step 2 + 3 — Discover & extract components
        components = await self._step_discover("components")
        if components:
            await self._step_extract_items("components", components)

        # Step 4 + 5 — Discover & extract features
        features = await self._step_discover("features")
        if features:
            await self._step_extract_items("features", features)

        # Final — Merge all files
        result = self._merge_results()

        elapsed = time.perf_counter() - t0
        logger.info(
            "Pipeline finished in %.1fs  keys=%s  components=%d  features=%d  tmp_dir=%s",
            elapsed,
            list(result.keys()),
            len(result.get("components", [])),
            len(result.get("features", [])),
            self._tmp_dir,
        )
        return result

    def cleanup(self) -> None:
        """Remove the temp directory.  Call manually if you want to clean up."""
        if self._tmp_dir.exists():
            shutil.rmtree(self._tmp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # File paths
    # ------------------------------------------------------------------

    def _product_path(self) -> Path:
        return self._tmp_dir / "product.json"

    def _item_path(self, category: str, item_name: str) -> Path:
        return self._tmp_dir / category / _safe_filename(item_name)

    # ------------------------------------------------------------------
    # Step implementations
    # ------------------------------------------------------------------

    async def _step_extract_product(self) -> None:
        """Step 1: extract product overview → tmp/product.json."""
        target = str(self._product_path())
        schema_fragment = json.dumps(
            self.schema.get("product", {}), ensure_ascii=False, indent=2
        )
        system_prompt = SUB_AGENT_PRODUCT_OVERVIEW_PROMPT.format(
            SCHEMA_FRAGMENT=schema_fragment,
            TARGET_FILE=target,
        )
        task = (
            f"Extract the product overview (name, brand, description, image, offers) "
            f"from the knowledge base and write it to: {target}"
        )
        tool_names = ["kb_query", "kb_chunk_query", "write_json_file"]

        async def _do(attempt: int = 0) -> None:
            effective_task = self._maybe_strengthen_task(task, attempt)
            output = await self._run_sub_agent(system_prompt, effective_task, tool_names)
            if not self._product_path().exists():
                self._try_recover_from_text(output, self._product_path())
            if not self._product_path().exists():
                raise _FileNotWrittenError(target)

        await self._with_retry(_do, label="extract_product")

    async def _step_discover(self, category: str) -> List[str]:
        """Discover component or feature names."""
        is_components = category == "components"
        system_prompt = SUB_AGENT_DISCOVERY_PROMPT.format(
            CATEGORY=category,
            CATEGORY_TITLE=category.title(),
            CATEGORY_SINGULAR=category.rstrip("s"),
            CATEGORY_DESCRIPTION=(
                "A component is a physical or logical PART of the product "
                "(e.g. body, strap, sensor, battery, button, display)."
                if is_components
                else "A feature is a FUNCTION or CAPABILITY the product provides "
                "(e.g. blood-pressure monitoring, SpO2, sleep tracking, Bluetooth connectivity)."
            ),
        )
        task = (
            f"Identify all {category} of this product from the knowledge base. "
            f'Return ONLY a JSON object: {{"items": ["name1", "name2", ...]}}.'
        )
        tool_names = ["kb_query", "kb_chunk_query"]

        async def _do(attempt: int = 0) -> List[str]:
            output = await self._run_sub_agent(system_prompt, task, tool_names)
            items = self._parse_discovery_output(output, category)
            if not items:
                raise ValueError(f"Discovery returned zero {category}")
            return items

        try:
            items = await self._with_retry(_do, label=f"discover_{category}")
        except Exception as exc:
            logger.error("Discovery for %s failed after retries: %s", category, exc)
            items = []
        logger.info("Discovered %d %s: %s", len(items), category, items)
        return items

    async def _step_extract_items(
        self, category: str, item_names: List[str]
    ) -> None:
        """Extract each item in parallel (bounded by semaphore)."""
        sem = asyncio.Semaphore(self.max_concurrency)

        async def _extract_one(name: str) -> None:
            async with sem:
                await self._extract_single_item(category, name)

        results = await asyncio.gather(
            *[_extract_one(n) for n in item_names],
            return_exceptions=True,
        )
        for name, res in zip(item_names, results):
            if isinstance(res, Exception):
                logger.error("Failed to extract %s/%s: %s", category, name, res)

    async def _extract_single_item(self, category: str, item_name: str) -> None:
        target = str(self._item_path(category, item_name))
        is_component = category == "components"
        schema_example = json.dumps(
            (self.schema.get(category) or [{}])[0],
            ensure_ascii=False,
            indent=2,
        )
        template = (
            SUB_AGENT_COMPONENT_DETAIL_PROMPT
            if is_component
            else SUB_AGENT_FEATURE_DETAIL_PROMPT
        )
        system_prompt = template.format(
            ITEM_NAME=item_name,
            SCHEMA_FRAGMENT=schema_example,
            TARGET_FILE=target,
        )
        task = (
            f"Extract detailed information for {category[:-1]} '{item_name}' "
            f"and write it to: {target}"
        )
        tool_names = [
            "kb_query",
            "kb_chunk_query",
            "kb_page_context",
            "write_json_file",
        ]

        async def _do(attempt: int = 0) -> None:
            effective_task = self._maybe_strengthen_task(task, attempt)
            output = await self._run_sub_agent(system_prompt, effective_task, tool_names)
            expected_path = self._item_path(category, item_name)
            if not expected_path.exists():
                self._try_recover_from_text(output, expected_path)
            if not expected_path.exists():
                raise _FileNotWrittenError(target)

        try:
            await self._with_retry(_do, label=f"extract_{category}/{item_name}")
        except Exception as exc:
            logger.error(
                "Giving up on %s/%s after retries: %s", category, item_name, exc
            )

    # ------------------------------------------------------------------
    # Merge: read all files → single dict
    # ------------------------------------------------------------------

    def _merge_results(self) -> Dict[str, Any]:
        """Read all JSON files from tmp dir and merge into one product info dict."""
        result: Dict[str, Any] = {}

        # product.json
        pp = self._product_path()
        if pp.exists():
            try:
                result["product"] = json.loads(pp.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to read %s: %s", pp, exc)

        # components/*.json
        comp_dir = self._tmp_dir / "components"
        comps: List[Dict[str, Any]] = []
        for f in sorted(comp_dir.glob("*.json")):
            try:
                obj = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(obj, dict):
                    comps.append(obj)
                elif isinstance(obj, list):
                    comps.extend(item for item in obj if isinstance(item, dict))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to read %s: %s", f, exc)
        if comps:
            result["components"] = comps

        # features/*.json
        feat_dir = self._tmp_dir / "features"
        feats: List[Dict[str, Any]] = []
        for f in sorted(feat_dir.glob("*.json")):
            try:
                obj = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(obj, dict):
                    feats.append(obj)
                elif isinstance(obj, list):
                    feats.extend(item for item in obj if isinstance(item, dict))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to read %s: %s", f, exc)
        if feats:
            result["features"] = feats

        return result

    # ------------------------------------------------------------------
    # Sub-agent runner
    # ------------------------------------------------------------------

    async def _run_sub_agent(
        self,
        system_prompt: str,
        task: str,
        tool_names: List[str],
        timeout: Optional[float] = None,
    ) -> str:
        """Create a fresh sub-agent, run it with timeout, return text output."""
        tools = [self._tool_map[n] for n in tool_names if n in self._tool_map]
        if not tools:
            raise ValueError(f"No valid tools for names: {tool_names}")

        agent = create_agent(
            model=self.llm,
            tools=tools,
            system_prompt=system_prompt,
        )

        messages = [{"role": "user", "content": task}]
        config = {"max_concurrency": 3, "recursion_limit": 50}

        coro = asyncio.to_thread(
            agent.invoke, {"messages": messages}, config=config
        )

        result = await asyncio.wait_for(
            coro, timeout=timeout or self.sub_agent_timeout
        )

        return _extract_text_from_state(result)

    # ------------------------------------------------------------------
    # Retry helper
    # ------------------------------------------------------------------

    async def _with_retry(self, fn, *, label: str = "", max_retries: int | None = None):
        """Call *fn(attempt)* with exponential-backoff retry."""
        retries = max_retries if max_retries is not None else self.max_retries
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                return await fn(attempt=attempt)
            except Exception as exc:
                last_exc = exc
                if attempt < retries:
                    wait = min(2 ** attempt * 2, 30)
                    logger.warning(
                        "[%s] attempt %d/%d failed (%s). Retrying in %ds …",
                        label,
                        attempt + 1,
                        retries + 1,
                        exc,
                        wait,
                    )
                    await asyncio.sleep(wait)
        raise last_exc  # type: ignore[misc]

    @staticmethod
    def _maybe_strengthen_task(task: str, attempt: int) -> str:
        if attempt == 0:
            return task
        return (
            "CRITICAL: Your previous attempt FAILED because you did NOT "
            "call the write_json_file tool. You MUST call it this time "
            "to write the result to the specified file path.\n\n"
            + task
        )

    # ------------------------------------------------------------------
    # Recovery: parse JSON from agent text → write file
    # ------------------------------------------------------------------

    @staticmethod
    def _try_recover_from_text(text: str, target_path: Path) -> bool:
        """
        If the sub-agent returned JSON in its text instead of calling the
        write_json_file tool, extract it and write the file ourselves.

        Returns True if recovery succeeded.
        """
        obj = _try_parse_json_object(text)
        if obj is None:
            return False

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(
                json.dumps(obj, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info(
                "Recovered JSON from agent text → wrote %s", target_path
            )
            return True
        except OSError as exc:
            logger.warning("Recovery write failed for %s: %s", target_path, exc)
            return False

    # ------------------------------------------------------------------
    # Discovery output parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_discovery_output(text: str, category: str) -> List[str]:
        """
        Best-effort extraction of an item list from sub-agent text.

        Tries: JSON with "items" key → JSON with category key → bare array → bullets.
        """
        if not text:
            return []

        for key in ("items", category):
            pattern = r'\{\s*"' + re.escape(key) + r'"\s*:\s*(\[.*?\])\s*\}'
            m = re.search(pattern, text, re.DOTALL)
            if m:
                try:
                    arr = json.loads(m.group(1))
                    return [str(x).strip() for x in arr if str(x).strip()]
                except json.JSONDecodeError:
                    pass

        m = re.search(r'\[.*?\]', text, re.DOTALL)
        if m:
            try:
                arr = json.loads(m.group())
                if arr and all(isinstance(x, str) for x in arr):
                    return [x.strip() for x in arr if x.strip()]
            except json.JSONDecodeError:
                pass

        bullets = re.findall(r'(?:^|\n)\s*(?:[-*]|\d+\.)\s+(.+)', text)
        if bullets:
            return [b.strip().strip('"').strip("'") for b in bullets if b.strip()]

        return []


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

class _FileNotWrittenError(RuntimeError):
    """Raised when a sub-agent finishes without writing the expected file."""

    def __init__(self, path: str):
        super().__init__(
            f"Expected file was not created: {path}. "
            "The agent may have returned JSON in text instead of calling write_json_file."
        )


def _extract_text_from_state(result: Any) -> str:
    """Pull the last AI message content from a LangGraph state dict."""
    if isinstance(result, dict):
        msgs = result.get("messages")
        if msgs:
            last = msgs[-1]
            content = (
                last.get("content")
                if isinstance(last, dict)
                else getattr(last, "content", None)
            )
            if content:
                return str(content)
        if "output" in result:
            return str(result["output"])
    return str(result)


def _try_parse_json_object(text: str) -> Optional[Dict[str, Any]]:
    """
    Find the first (largest) balanced ``{...}`` JSON object in *text*.

    Handles JSON embedded in markdown code fences.
    """
    if not text:
        return None

    cleaned = re.sub(r'```(?:json)?\s*', '', text)
    cleaned = re.sub(r'```', '', cleaned)

    brace_depth = 0
    start: int | None = None
    for i, ch in enumerate(cleaned):
        if ch == '{':
            if brace_depth == 0:
                start = i
            brace_depth += 1
        elif ch == '}':
            brace_depth -= 1
            if brace_depth == 0 and start is not None:
                candidate = cleaned[start:i + 1]
                try:
                    obj = json.loads(candidate)
                    if isinstance(obj, dict):
                        return obj
                except json.JSONDecodeError:
                    pass
                start = None

    return None
