from __future__ import annotations

"""
LangChain-based Agent helpers for RAG-Anything.

The main entry point is `create_rag_agent`, which builds a tools-based
agent that:
- 接受自定义 system prompt；
- 接受一组已经构建好的 LangChain tools；
- 使用 LangChain 的 `create_openai_tools_agent` 来生成 Agent。
"""

import json
from typing import Iterable, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

from agent.tools import CreateAndRunAgentTool, build_rag_agent_tools
from agent.prompt import build_product_info_orchestrator_system_prompt
from raganything.product import DEFAULT_PRODUCT_INFO_SCHEMA

try:
    from config.api_keys import DASHSCOPE_API_KEY
except ImportError:  # pragma: no cover - fallback to environment variable
    DASHSCOPE_API_KEY = ""

from config.model_conf import DASHSCOPE_BASE_URL, QWEN_PLUS_3_5_MODEL


def _build_default_llm() -> BaseChatModel:
    """
    构建一个默认的 Qwen ChatOpenAI 模型实例，用于 Agent 调用 tools。

    - 模型名称：环境变量 QWEN_CHAT_MODEL，默认为 "qwen-flash"
    - API Key：使用 config.api_keys.DASHSCOPE_API_KEY
    - Base URL：使用 config.model_conf.DASHSCOPE_BASE_URL
    """
    model_name = QWEN_PLUS_3_5_MODEL
    api_key = (DASHSCOPE_API_KEY or "").strip()
    base_url = DASHSCOPE_BASE_URL

    if not api_key:
        raise ValueError("DASHSCOPE_API_KEY 未配置，无法构建默认的 Qwen ChatOpenAI 模型")

    return ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=0.1,
        extra_body={"parallel_tool_calls": True},
    )


def create_rag_agent(
    tools: Optional[Iterable[BaseTool]] = None,
    system_prompt: Optional[str] = None,
    *,
    include_history: bool = True,
    verbose: bool = False,
) -> Runnable:
    """
    创建一个用于 RAG-Anything 的 LangChain Agent。

    Args:
        tools: 供 Agent 使用的工具列表（通常由 `build_rag_agent_tools` 构建）。
        system_prompt: 自定义 system prompt。若为空则使用一个通用的 RAG 助手提示词。
        include_history: 是否在 prompt 中加入 `chat_history` 占位，用于上层传入对话历史。
        verbose: 是否在执行时输出更详细的日志（AgentExecutor.verbose）。

    Returns:
        Runnable: 可直接通过 `.invoke()` / `.stream()` 调用的 Agent。
    """
    if tools is None:
        raise ValueError("tools 参数不能为空，请传入由 build_rag_agent_tools 构建的工具列表")

    llm = _build_default_llm()
    base_system_prompt = (
        "You are an intelligent assistant built on top of RAG-Anything. "
        "You can call tools to查询知识库内容、获取指定页码的上下文等。"
        "Always优先使用可用的 tools 来检索和定位原文，而不是凭空臆测。"
    )
    system = system_prompt.strip() if system_prompt else base_system_prompt

    messages = [
        ("system", system),
    ]

    if include_history:
        messages.append(MessagesPlaceholder("chat_history"))

    messages.append(("human", "{input}"))
    messages.append(MessagesPlaceholder("agent_scratchpad"))

    # 使用官方推荐的 create_agent API
    # 参考文档：https://docs.langchain.com/oss/python/langchain/agents
    #
    # create_agent 接受一个 model 和 tools，期望输入形如：
    #   {"messages": [{"role": "...", "content": "..."}]}
    #
    # 为了保持向后兼容，这里用一个 RunnableLambda 做一层适配，
    # 继续接受 {"input": "..."} 的调用方式。

    inner_agent = create_agent(model=llm, tools=list(tools), system_prompt=system)

    def _extract_output(result: object) -> object:
        output = None
        try:
            msgs = result.get("messages") if isinstance(result, dict) else None
            if msgs:
                last_msg = msgs[-1]
                if isinstance(last_msg, dict):
                    output = last_msg.get("content")
                else:
                    output = getattr(last_msg, "content", None)
        except Exception:  # pragma: no cover - 仅为健壮性
            output = None
        return output if output is not None else result

    def _invoke(inputs: dict) -> dict:
        user_input = inputs.get("input", "")

        # 若上层传入 "messages"，则直接使用；否则只传一条 user 消息
        messages_state = inputs.get("messages")
        if not isinstance(messages_state, list):
            messages_state = [{"role": "user", "content": str(user_input)}]

        result = inner_agent.invoke(
            {"messages": messages_state},
            config={"configurable": {"verbose": verbose}, "max_concurrency": 2, "recursion_limit": 100},
        )

        return {"output": _extract_output(result), "raw": result}

    async def _ainvoke(inputs: dict) -> dict:
        user_input = inputs.get("input", "")

        messages_state = inputs.get("messages")
        if not isinstance(messages_state, list):
            messages_state = [{"role": "user", "content": str(user_input)}]

        result = await inner_agent.ainvoke(
            {"messages": messages_state},
            config={"configurable": {"verbose": verbose}, "max_concurrency": 3},
            stream_mode="debug",
        )

        return {"output": _extract_output(result), "raw": result}

    return RunnableLambda(_invoke, afunc=_ainvoke)


def create_product_info_orchestrator_agent(
    doc_meta: dict,
    product_schema: Optional[dict] = None,
    *,
    include_history: bool = False,
    verbose: bool = False,
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

    # 4. 父 Agent 的 CoT 风格 system prompt：遵循 6 步编排流程，仅负责编排子 Agent
    system_prompt = build_product_info_orchestrator_system_prompt(schema_json)

    # 父 Agent 只暴露 meta_tool；底层 RAG 工具仅对子 Agent 可见
    parent_tools: Iterable[BaseTool] = [meta_tool]

    return create_rag_agent(
        tools=parent_tools,
        system_prompt=system_prompt,
        include_history=include_history,
        verbose=verbose,
    )

