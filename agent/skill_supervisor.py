from __future__ import annotations

"""
File-based Skill Supervisor for domain knowledge extraction.

Architecture
------------
Each domain skill lives in its own directory::

    agent/skills/{skill-name}/
        SKILL.md          ← YAML frontmatter: name, description, schema, steps
        schema.json       ← domain output structure
        prompts/
            {key}/
                scalar.md     ← prompt for scalar step (key-specific)
                discover.md   ← prompt for list discovery (key-specific)
                detail.md     ← prompt for single-item detail extraction (key-specific)

Each step carries its own prompts (loaded from paths declared in the frontmatter
``steps[].prompts`` map).  There are no shared fallback prompts.

``FileSkillSupervisor`` reads the SKILL.md, loads schema + per-key prompts into
memory, then drives extraction using ``create_deep_agent`` (deepagents) for each
sub-agent call.  Shared schema splitting and result merging are pure Python.

Shared utilities (schema_splitter, merger) are domain-agnostic and work
for any valid schema.json.

Usage::

    supervisor = FileSkillSupervisor.from_skill_dir(
        "agent/skills/product-knowledge",
        doc_meta=doc_meta,
        llm=llm,
    )
    result = await supervisor.run()
    supervisor.cleanup()
"""

import asyncio
import json
import logging
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_core.language_models.chat_models import BaseChatModel

from agent.tools import build_rag_agent_tools, WriteJsonFileTool
from agent.util import get_last_ai_message_content

logger = logging.getLogger(__name__)

# Project root — used as FilesystemBackend root_dir so skill paths resolve correctly.
_PROJECT_ROOT = Path(__file__).parent.parent


# =============================================================================
# Skill definition (parsed from SKILL.md)
# =============================================================================

@dataclass
class SkillStepConf:
    """One extraction step declared in SKILL.md frontmatter."""
    key: str
    type: str          # "scalar" | "list"
    # Prompt text loaded from per-key prompt files
    prompt_scalar: str = ""     # used for scalar steps
    prompt_discover: str = ""   # used for list discovery
    prompt_detail: str = ""     # used for list detail extraction


@dataclass
class SkillDef:
    """Parsed and fully loaded domain skill definition."""
    name: str
    description: str
    skill_dir: Path
    schema: Dict[str, Any]
    # Execution steps; each step carries its own prompts
    steps: List[SkillStepConf]


def load_skill(skill_dir: str | Path) -> SkillDef:
    """
    Parse SKILL.md and load all referenced files into a ``SkillDef``.

    Each step's prompts are loaded from paths declared in
    ``steps[].prompts`` in the frontmatter.  If ``steps`` is omitted,
    the schema structure is used to auto-derive them (dict → scalar,
    list → list) but no prompts will be loaded for auto-derived steps.
    """
    skill_dir = Path(skill_dir).resolve()
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        raise FileNotFoundError(f"SKILL.md not found in {skill_dir}")

    raw = skill_md.read_text(encoding="utf-8")
    front, _ = _parse_frontmatter(raw)

    name = front.get("name") or skill_dir.name
    description = front.get("description") or ""

    # Load schema
    schema_rel = front.get("schema", "./schema.json")
    schema_path = (skill_dir / schema_rel).resolve()
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    # Parse steps and load per-step prompts
    steps_raw = front.get("steps")
    if steps_raw:
        steps = []
        for s in steps_raw:
            step_prompts = s.get("prompts", {})
            step = SkillStepConf(key=s["key"], type=s["type"])
            if "scalar" in step_prompts:
                step.prompt_scalar = _load_prompt(skill_dir, step_prompts["scalar"])
            if "discover" in step_prompts:
                step.prompt_discover = _load_prompt(skill_dir, step_prompts["discover"])
            if "detail" in step_prompts:
                step.prompt_detail = _load_prompt(skill_dir, step_prompts["detail"])
            steps.append(step)
    else:
        steps = _derive_steps(schema)

    return SkillDef(
        name=name,
        description=description,
        skill_dir=skill_dir,
        schema=schema,
        steps=steps,
    )


def _parse_frontmatter(text: str):
    """Split YAML frontmatter from markdown body."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm_text = text[3:end].strip()
            body = text[end + 4:].strip()
            return yaml.safe_load(fm_text) or {}, body
    return {}, text


def _load_prompt(skill_dir: Path, rel_path: str) -> str:
    path = (skill_dir / rel_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def _derive_steps(schema: Dict[str, Any]) -> List[SkillStepConf]:
    """Auto-derive extraction steps from schema structure."""
    steps = []
    for key, value in schema.items():
        if isinstance(value, dict):
            steps.append(SkillStepConf(key=key, type="scalar"))
        elif isinstance(value, list):
            steps.append(SkillStepConf(key=key, type="list"))
    return steps


# =============================================================================
# FileSkillSupervisor
# =============================================================================

class FileSkillSupervisor:
    """
    Reads a domain skill from its directory and orchestrates knowledge extraction.

    Workflow::

        1. load_skill()  →  parse SKILL.md, load schema + prompts
        2. For each step in skill_def.steps:
              scalar  →  create_deep_agent extracts dict field   → {key}.json
              list    →  create_deep_agent discovers item names
                         create_deep_agent (×N, parallel) extracts each item
                         → {key}/{item}.json
        3. _merge()     →  pure Python, combines all JSON files

    The sub-agents are created with ``create_deep_agent`` (deepagents framework)
    which gives them built-in file tools.  The domain skill files are exposed
    via ``FilesystemBackend`` so sub-agents can ``read_file`` the schema or
    prompts for reference.

    Usage::

        supervisor = FileSkillSupervisor.from_skill_dir(
            "agent/skills/product-knowledge",
            doc_meta=doc_meta,
            llm=llm,
        )
        result = await supervisor.run()
        supervisor.cleanup()
    """

    def __init__(
        self,
        skill_def: SkillDef,
        doc_meta: Dict[str, Any],
        llm: BaseChatModel,
        *,
        max_retries: int = 2,
        sub_agent_timeout: float = 180.0,
        max_concurrency: int = 3,
    ) -> None:
        self.skill_def = skill_def
        self.doc_meta = doc_meta
        self.llm = llm
        self.max_retries = max_retries
        self.sub_agent_timeout = sub_agent_timeout
        self.max_concurrency = max_concurrency

        # Isolated tmp directory for this run
        runtime_root = Path(doc_meta.get("working_dir", ".")).resolve().parent
        self._tmp_dir = runtime_root / f"skill_tmp_{skill_def.name}"
        if self._tmp_dir.exists():
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        logger.info("FileSkillSupervisor[%s] tmp_dir: %s", skill_def.name, self._tmp_dir)

        self._rag_tools = build_rag_agent_tools(doc_meta)
        self._write_tool = WriteJsonFileTool(allowed_directory=str(self._tmp_dir))

        # FilesystemBackend scoped to project root so skills path resolves.
        # Sub-agents can read_file skill assets (schema.json, prompts) for reference.
        self._backend = FilesystemBackend(root_dir=str(_PROJECT_ROOT))

        # POSIX path to the skill dir relative to project root, for skills= param.
        self._skill_posix = "/" + skill_def.skill_dir.relative_to(_PROJECT_ROOT).as_posix() + "/"

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_skill_dir(
        cls,
        skill_dir: str | Path,
        doc_meta: Dict[str, Any],
        llm: BaseChatModel,
        **kwargs,
    ) -> "FileSkillSupervisor":
        """Load a skill from its directory and create a supervisor."""
        skill_def = load_skill(skill_dir)
        return cls(skill_def, doc_meta, llm, **kwargs)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> Dict[str, Any]:
        """Execute the full extraction workflow and return the merged result."""
        t0 = time.perf_counter()
        skill = self.skill_def

        logger.info(
            "FileSkillSupervisor[%s] starting: %d steps",
            skill.name, len(skill.steps),
        )

        for step in skill.steps:
            if step.type == "scalar":
                await self._run_scalar(step)
            elif step.type == "list":
                items = await self._run_discover(step)
                if items:
                    await self._run_detail_parallel(step, items)

        result = _merge(self._tmp_dir, self.skill_def.schema)
        elapsed = time.perf_counter() - t0
        logger.info(
            "FileSkillSupervisor[%s] done in %.1fs  keys=%s",
            skill.name, elapsed, list(result.keys()),
        )

        # Write the merged final result into the tmp directory for inspection.
        result_path = self._tmp_dir / "result.json"
        try:
            result_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            logger.info("FileSkillSupervisor[%s] result written to %s", skill.name, result_path)
        except OSError as exc:
            logger.warning("FileSkillSupervisor[%s] failed to write result.json: %s", skill.name, exc)

        return result

    def cleanup(self) -> None:
        """Remove the tmp directory."""
        if self._tmp_dir.exists():
            shutil.rmtree(self._tmp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Step runners
    # ------------------------------------------------------------------

    async def _run_scalar(self, step: SkillStepConf) -> None:
        target_path = self._tmp_dir / f"{step.key}.json"
        fragment = self.skill_def.schema.get(step.key, {})
        system_prompt = _format_prompt(
            step.prompt_scalar,
            key=step.key,
            schema_fragment=fragment,
            target_file=str(target_path),
        )
        task = (
            f"Extract the '{step.key}' information from the knowledge base "
            f"and write it to: {target_path}"
        )

        async def _do(attempt: int = 0) -> None:
            output = await self._invoke_sub_agent(
                system_prompt, _strengthen(task, attempt)
            )
            if not target_path.exists():
                _try_recover(output, target_path)
            if not target_path.exists():
                raise _FileNotWrittenError(target_path)

        await _with_retry(_do, label=f"scalar/{step.key}", max_retries=self.max_retries)

    async def _run_discover(self, step: SkillStepConf) -> List[str]:
        fragment = self.skill_def.schema.get(step.key, [{}])
        item_template = (fragment[0] if isinstance(fragment, list) and fragment else {})
        system_prompt = _format_prompt(
            step.prompt_discover,
            key=step.key,
            schema_fragment=item_template,
        )
        task = (
            f"Identify all items in the '{step.key}' category. "
            f'Return ONLY JSON: {{"items": ["name1", "name2", ...]}}'
        )

        async def _do(attempt: int = 0) -> List[str]:  # noqa: ARG001
            output = await self._invoke_sub_agent(system_prompt, task)
            items = _parse_items(output, step.key)
            if not items:
                raise ValueError(f"Discovery returned 0 items for '{step.key}'")
            return items

        try:
            items = await _with_retry(
                _do, label=f"discover/{step.key}", max_retries=self.max_retries
            )
            logger.info("Discovered %d items in '%s': %s", len(items), step.key, items)
            return items
        except Exception as exc:
            logger.error("Discovery failed for '%s': %s", step.key, exc)
            return []

    async def _run_detail_parallel(
        self, step: SkillStepConf, item_names: List[str]
    ) -> None:
        sem = asyncio.Semaphore(self.max_concurrency)

        async def _one(name: str) -> None:
            async with sem:
                await self._run_detail_one(step, name)

        await asyncio.gather(*[_one(n) for n in item_names], return_exceptions=True)

    async def _run_detail_one(self, step: SkillStepConf, item_name: str) -> None:
        cat_dir = self._tmp_dir / step.key
        cat_dir.mkdir(parents=True, exist_ok=True)
        target_path = cat_dir / _safe_filename(item_name)

        fragment = self.skill_def.schema.get(step.key, [{}])
        item_template = (fragment[0] if isinstance(fragment, list) and fragment else {})
        system_prompt = _format_prompt(
            step.prompt_detail,
            key=step.key,
            schema_fragment=item_template,
            target_file=str(target_path),
            item_name=item_name,
        )
        task = (
            f"Extract detailed information for '{step.key}' item '{item_name}' "
            f"and write it to: {target_path}"
        )

        async def _do(attempt: int = 0) -> None:
            output = await self._invoke_sub_agent(
                system_prompt, _strengthen(task, attempt)
            )
            if not target_path.exists():
                _try_recover(output, target_path)
            if not target_path.exists():
                raise _FileNotWrittenError(target_path)

        try:
            await _with_retry(
                _do,
                label=f"detail/{step.key}/{item_name}",
                max_retries=self.max_retries,
            )
        except Exception as exc:
            logger.error("Detail failed for '%s/%s': %s", step.key, item_name, exc)

    # ------------------------------------------------------------------
    # Sub-agent creation & invocation
    # ------------------------------------------------------------------

    def _make_sub_agent(self, system_prompt: str):
        """
        Create a fresh ``create_deep_agent`` for one extraction call.

        The agent receives:
        - Our RAG tools (kb_query, kb_chunk_query, …) + write_json_file
        - Access to the skill directory via FilesystemBackend + skills= param,
          so it can ``read_file`` schema.json or prompts for reference.
        """
        return create_deep_agent(
            model=self.llm,
            tools=[*self._rag_tools, self._write_tool],
            system_prompt=system_prompt,
            skills=[self._skill_posix],
            backend=self._backend,
        )

    async def _invoke_sub_agent(self, system_prompt: str, task: str) -> str:
        agent = self._make_sub_agent(system_prompt)
        messages = [{"role": "user", "content": task}]
        config = {"max_concurrency": 3, "recursion_limit": 50}

        coro = asyncio.to_thread(
            agent.invoke, {"messages": messages}, config
        )
        result = await asyncio.wait_for(coro, timeout=self.sub_agent_timeout)
        return get_last_ai_message_content(result) or str(result)


# =============================================================================
# Shared utilities — schema_splitter & merger (domain-agnostic)
# =============================================================================

def _merge(tmp_dir: Path, schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge all JSON files written by extraction steps into a final result dict.

    Rules:
    - ``{tmp_dir}/{key}.json``    → result[key] = dict   (scalar)
    - ``{tmp_dir}/{key}/``        → result[key] = list   (list items)
    """
    result: Dict[str, Any] = {}
    for key in schema.keys():
        scalar_path = tmp_dir / f"{key}.json"
        cat_dir = tmp_dir / key

        if scalar_path.exists():
            try:
                result[key] = json.loads(scalar_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("merge: failed to read %s: %s", scalar_path, exc)

        elif cat_dir.is_dir():
            items: List[Dict[str, Any]] = []
            for f in sorted(cat_dir.glob("*.json")):
                try:
                    obj = json.loads(f.read_text(encoding="utf-8"))
                    if isinstance(obj, dict):
                        items.append(obj)
                    elif isinstance(obj, list):
                        items.extend(x for x in obj if isinstance(x, dict))
                except (json.JSONDecodeError, OSError) as exc:
                    logger.warning("merge: failed to read %s: %s", f, exc)
            if items:
                result[key] = items

    logger.info("merge: result keys=%s", list(result.keys()))
    return result


def _format_prompt(
    template: str,
    *,
    key: str,
    schema_fragment: Any,
    target_file: str = "",
    item_name: str = "",
) -> str:
    """Format a prompt template with runtime values."""
    key_title = key.replace("_", " ").title()
    schema_str = json.dumps(schema_fragment, ensure_ascii=False, indent=2)
    return (
        template
        .replace("{KEY_TITLE}", key_title)
        .replace("{TARGET_KEY}", key)
        .replace("{SCHEMA_FRAGMENT}", schema_str)
        .replace("{TARGET_FILE}", target_file)
        .replace("{ITEM_NAME}", item_name)
    )


def _safe_filename(name: str) -> str:
    stem = re.sub(r"[^\w\-]", "_", name.strip())[:120]
    return (stem or "unnamed") + ".json"


def _strengthen(task: str, attempt: int) -> str:
    if attempt == 0:
        return task
    return (
        "CRITICAL: Your previous attempt FAILED because write_json_file was not called. "
        "You MUST call write_json_file this time to write the result to the specified path.\n\n"
        + task
    )


def _try_recover(text: str, target_path: Path) -> bool:
    obj = _try_parse_json_object(text)
    if obj is None:
        return False
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(
            json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("Recovered JSON from agent text → %s", target_path)
        return True
    except OSError as exc:
        logger.warning("Recovery write failed for %s: %s", target_path, exc)
        return False


def _try_parse_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    cleaned = re.sub(r"```(?:json)?\s*", "", text)
    cleaned = re.sub(r"```", "", cleaned)
    depth = 0
    start: Optional[int] = None
    for i, ch in enumerate(cleaned):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    obj = json.loads(cleaned[start : i + 1])
                    if isinstance(obj, dict):
                        return obj
                except json.JSONDecodeError:
                    pass
                start = None
    return None


def _parse_items(text: str, category: str) -> List[str]:
    if not text:
        return []
    for key in ("items", category):
        m = re.search(
            r'\{\s*"' + re.escape(key) + r'"\s*:\s*(\[.*?\])\s*\}',
            text, re.DOTALL,
        )
        if m:
            try:
                return [str(x).strip() for x in json.loads(m.group(1)) if str(x).strip()]
            except json.JSONDecodeError:
                pass
    m = re.search(r"\[.*?\]", text, re.DOTALL)
    if m:
        try:
            arr = json.loads(m.group())
            if arr and all(isinstance(x, str) for x in arr):
                return [x.strip() for x in arr if x.strip()]
        except json.JSONDecodeError:
            pass
    bullets = re.findall(r"(?:^|\n)\s*(?:[-*]|\d+\.)\s+(.+)", text)
    return [b.strip().strip('"').strip("'") for b in bullets if b.strip()]


async def _with_retry(fn, *, label: str = "", max_retries: int = 2) -> Any:
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            return await fn(attempt=attempt)
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries:
                wait = min(2 ** attempt * 2, 30)
                logger.warning(
                    "[%s] attempt %d/%d failed (%s). Retrying in %ds …",
                    label, attempt + 1, max_retries + 1, exc, wait,
                )
                await asyncio.sleep(wait)
    raise last_exc  # type: ignore[misc]


class _FileNotWrittenError(RuntimeError):
    def __init__(self, path: Path) -> None:
        super().__init__(
            f"Expected file not created: {path}. "
            "The agent may have returned JSON in text instead of calling write_json_file."
        )
