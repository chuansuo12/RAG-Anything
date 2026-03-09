from __future__ import annotations

"""
LangChain-based Agent helpers for RAG-Anything.

- `create_product_info_orchestrator_agent`: 创建父级编排 Agent，内部直接使用
  LangChain 的 `create_agent`，仅在此处注入 max_concurrency、recursion_limit。
- `get_last_agent_output`: 从 create_agent 的返回结果中取出最后一次输出的内容。
"""

import json
from typing import Iterable, Optional

from langgraph.types import StreamMode
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

from agent.tools import CreateAndRunAgentTool, build_rag_agent_tools
from agent.prompt import (
    build_product_info_orchestrator_system_prompt,
    build_qa_orchestrator_system_prompt,
)
from raganything.product import DEFAULT_PRODUCT_INFO_SCHEMA

try:
    from config.api_keys import DASHSCOPE_API_KEY
except ImportError:  # pragma: no cover - fallback to environment variable
    DASHSCOPE_API_KEY = ""

from config.model_conf import DASHSCOPE_BASE_URL, QWEN_CHAT_MODEL


def _build_default_llm() -> BaseChatModel:
    """
    构建一个默认的 Qwen ChatOpenAI 模型实例，用于 Agent 调用 tools。

    - 模型名称：环境变量 QWEN_CHAT_MODEL，默认为 "qwen-flash"
    - API Key：使用 config.api_keys.DASHSCOPE_API_KEY
    - Base URL：使用 config.model_conf.DASHSCOPE_BASE_URL
    """
    model_name = QWEN_CHAT_MODEL
    api_key = (DASHSCOPE_API_KEY or "").strip()
    base_url = DASHSCOPE_BASE_URL

    if not api_key:
        raise ValueError("DASHSCOPE_API_KEY 未配置，无法构建默认的 Qwen ChatOpenAI 模型")

    return ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=0.1,
        max_retries=3,
        extra_body={"parallel_tool_calls": True},
    )


def create_product_info_orchestrator_agent(
    doc_meta: dict,
    product_schema: Optional[dict] = None,
    *,
    verbose: bool = False,
    stream_mode: StreamMode = "values",
) -> Runnable:
    """
    创建一个“父级” Product Info Orchestrator Agent。

    设计要点：
    - 父 Agent 只暴露一个工具：`create_and_run_agent`（CreateAndRunAgentTool）；
    - `CreateAndRunAgentTool` 内部持有完整的 RAG 工具列表（kb_query / kb_page_context / vlm_image_query 等），
      用于为不同子任务临时创建子 Agent；
    - Product Schema 作为 system prompt 的一部分注入，父 Agent 通过 CoT 规划拆解与汇总流程。

    Args:
        doc_meta: 单一知识库实例的元信息（与 build_rag_agent_tools 保持一致）。
        product_schema: 自定义的产品信息 Schema，默认为 DEFAULT_PRODUCT_INFO_SCHEMA。
        include_history: 是否在父 Agent 中包含 chat_history（默认 False，更偏向一次性任务）。
        verbose: 传递给底层 Agent 的 verbose 标记。
    """
    # 构建一个默认的 Qwen ChatOpenAI 实例，供父 / 子 Agent 共享
    shared_llm = _build_default_llm()

    # 1. 基础工具：面向当前知识库的 RAG 工具集合
    base_tools = build_rag_agent_tools(doc_meta)

    # 2. 元工具：只暴露给父 Agent 使用，但内部可以访问所有 base_tools
    meta_tool = CreateAndRunAgentTool(llm=shared_llm, available_tools=base_tools)

    # 3. 将 Product Schema 作为文本注入到 system prompt 中
    schema_obj = product_schema or DEFAULT_PRODUCT_INFO_SCHEMA
    schema_json = json.dumps(schema_obj, ensure_ascii=False, indent=2)

    # 4. 父 Agent 的 CoT 风格 system prompt：遵循 4 步编排流程，仅负责编排子 Agent
    system_prompt = build_product_info_orchestrator_system_prompt(schema_json)

    # 父 Agent 只暴露 meta_tool；底层 RAG 工具仅对子 Agent 可见
    parent_tools: Iterable[BaseTool] = [meta_tool]

    inner_agent = create_agent(
        model=shared_llm,
        tools=list(parent_tools),
        system_prompt=system_prompt,
    )

    agent_config = {
        "configurable": {"verbose": verbose},
        "max_concurrency": 3,
        "recursion_limit": 100,
    }

    def _invoke(inputs: dict) -> object:
        messages_state = inputs.get("messages")
        if not isinstance(messages_state, list):
            user_input = inputs.get("input", "")
            messages_state = [{"role": "user", "content": str(user_input)}]
        return inner_agent.invoke({"messages": messages_state}, config=agent_config, stream_mode=stream_mode)

    async def _ainvoke(inputs: dict) -> object:
        messages_state = inputs.get("messages")
        if not isinstance(messages_state, list):
            user_input = inputs.get("input", "")
            messages_state = [{"role": "user", "content": str(user_input)}]
        return await inner_agent.ainvoke(
            {"messages": messages_state},
            config=agent_config,
            stream_mode=stream_mode,
        )

    return RunnableLambda(_invoke, afunc=_ainvoke)


def create_rag_qa_orchestrator_agent(
    doc_meta: dict,
    *,
    verbose: bool = False,
    stream_mode: StreamMode = "values",
) -> Runnable:
    """
    创建用于「问答」的编排 Agent：根据用户问题通过 create_and_run_agent 调用子 Agent
    查询知识库，并汇总成自然语言回答。适用于 Web 端 Agent 模式问答。

    Args:
        doc_meta: 单一知识库实例的元信息（与 build_rag_agent_tools 一致）。
        verbose: 传递给底层 Agent 的 verbose 标记。
        stream_mode: 传递给 invoke 的 stream_mode。

    Returns:
        Runnable: 输入 {"input": str} 或 {"messages": [...]}，输出为完整 state（含 messages）。
    """
    shared_llm = _build_default_llm()
    base_tools = build_rag_agent_tools(doc_meta)
    meta_tool = CreateAndRunAgentTool(llm=shared_llm, available_tools=base_tools)
    system_prompt = build_qa_orchestrator_system_prompt()
    parent_tools: Iterable[BaseTool] = [meta_tool]

    inner_agent = create_agent(
        model=shared_llm,
        tools=list(parent_tools),
        system_prompt=system_prompt,
    )

    agent_config = {
        "configurable": {"verbose": verbose},
        "max_concurrency": 3,
        "recursion_limit": 100,
    }

    def _invoke(inputs: dict) -> object:
        messages_state = inputs.get("messages")
        if not isinstance(messages_state, list):
            user_input = inputs.get("input", "")
            messages_state = [{"role": "user", "content": str(user_input)}]
        return inner_agent.invoke(
            {"messages": messages_state}, config=agent_config, stream_mode=stream_mode
        )

    async def _ainvoke(inputs: dict) -> object:
        messages_state = inputs.get("messages")
        if not isinstance(messages_state, list):
            user_input = inputs.get("input", "")
            messages_state = [{"role": "user", "content": str(user_input)}]
        return await inner_agent.ainvoke(
            {"messages": messages_state},
            config=agent_config,
            stream_mode=stream_mode,
        )

    return RunnableLambda(_invoke, afunc=_ainvoke)

