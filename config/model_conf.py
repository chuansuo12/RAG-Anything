"""
Model 配置：集中管理默认模型名称与相关 Base URL。

约定：仅使用此处常量（不从环境变量读取）。
"""

# 阿里云百炼 OpenAI 兼容 base_url（北京地域；新加坡请用 https://dashscope-intl.aliyuncs.com/compatible-mode/v1）
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# 默认模型名（百炼对话 / 视觉 / 向量 / 重排序）
QWEN_CHAT_MODEL = "qwen3.5-flash"
QWEN_VISION_MODEL = "qwen3-vl-flash"
QWEN_EMBED_MODEL = "text-embedding-v4"
QWEN_RERANK_MODEL = "qwen3-rerank"
QWEN_PLUS_3_5_MODEL = "qwen3.5-plus"

# 重排序接口单独的 base_url（兼容-api），默认使用官方示例地址
QWEN_RERANK_BASE_URL = "https://dashscope.aliyuncs.com/compatible-api/v1"

