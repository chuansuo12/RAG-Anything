"""
API Keys 配置：将各服务 API Token 以常量方式集中放置，便于替换与管理。

使用前请在此处或环境变量中填写有效的 Key。
参考：https://help.aliyun.com/zh/model-studio/get-api-key
"""

# 阿里云百炼（DashScope）API Key，用于 Qwen 对话/视觉/向量化等
# 北京地域与新加坡地域的 Key 不同，获取：https://help.aliyun.com/zh/model-studio/get-api-key
DASHSCOPE_API_KEY = "sk-406ee7f1fa2d4bb4abd4a76ee8684b38"

MINERU_API_TOKEN = "eyJ0eXBlIjoiSldUIiwiYWxnIjoiSFM1MTIifQ.eyJqdGkiOiI0ODUwMDQ1OCIsInJvbCI6IlJPTEVfUkVHSVNURVIiLCJpc3MiOiJPcGVuWExhYiIsImlhdCI6MTc3MjM2MTQwNywiY2xpZW50SWQiOiJsa3pkeDU3bnZ5MjJqa3BxOXgydyIsInBob25lIjoiIiwib3BlbklkIjpudWxsLCJ1dWlkIjoiODQ1Y2RjOTEtOWZmNC00Nzg1LWFjYzItYzNjZGIyY2JhNGEwIiwiZW1haWwiOiIiLCJleHAiOjE3ODAxMzc0MDd9.6NreXyEjGwHQbhJCj4Nf3QcHk1wA0Eub8YHJHDEvUqQ9t-Ij_dqei9uXRnQUn0Po2eXLkWGPmTH45STnsvYwUQ"
