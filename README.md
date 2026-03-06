# A-PRAG

基于 [LightRAG](https://github.com/HKUDS/LightRAG) 的多模态文档 RAG 框架，支持文档解析、知识图谱构建、Agentic 检索与问答。

---

## 一、知识图谱（Graph）的生成过程

RAG-Anything 的图谱分为两阶段：**基础图谱 G_v1** 与可选的 **增强图谱 G_v2（PRAG）**。

### 1.1 基础图谱 G_v1 的构建

1. **文档解析**  
   使用 MinerU / Docling / PaddleOCR 等解析器，将 PDF/Office/图片等转为结构化内容列表（`content_list`），包含文本块、图片、表格、公式等。

2. **多模态内容处理**  
   - 文本：按 chunk 模板格式化后送入后续流程。  
   - 图片：经 VLM 生成描述，形成「描述 + 实体信息」。  
   - 表格/公式：由对应 ModalProcessor 生成描述与实体信息。

3. **写入文本与向量**  
   - 每个内容块生成 `chunk_id`，写入 `text_chunks_db` 与向量库 `chunks_vdb`。  
   - 多模态主实体写入 `entities_vdb`，并写入 `chunk_entity_relation_graph`（图谱节点）。

4. **实体与关系抽取（图谱边）**  
   - 调用 LightRAG 风格的 **批量实体关系抽取**：`_batch_extract_entities_lightrag_style_type_aware`，对 chunk 做实体/关系抽取。  
   - 增加多模态特有的 **belongs_to** 等关系。  
   - 通过 **batch merge** 将实体、关系写回图谱与向量库。

整体数据流：**解析 → content_list → 多模态描述/实体 → chunks + 图谱节点 → 实体关系抽取 → 图谱边 + 向量索引**，得到 G_v1。

### 1.2 增强图谱 G_v2（PRAG：领域模型驱动的图谱增强）

在 G_v1 之上，通过「产品领域模型（Product Schema）」做结构化信息抽取，并融合回图谱：

1. **领域模型**  
   预定义 `product_info_schema.json`（或使用默认 Schema），描述产品、组件、特征、参数、属性等类型及其关系。

2. **多智能体协作抽取**  
   - **编排 Agent（Orchestrator）**：仅暴露元工具 `create_and_run_agent`，按阶段创建子 Agent。  
   - **阶段 1**：产品基本信息抽取（名称、品牌、描述等）。  
   - **阶段 2**：组件发现，得到组件列表。  
   - **阶段 3**：对每个组件并行运行「组件详情抽取子 Agent」（属性、参数等）。  
   - **阶段 4**：汇总、校验必填/类型/完整性，失败则重试或修正。

3. **子 Agent 的检索工具**  
   子 Agent 使用 RAG 工具在 G_v1 上检索：`kb_query`、`kb_chunk_query`、`kb_entity_neighbors`、`kb_page_context`、`vlm_image_query`、`product_info` 等，从全文/图谱中聚合产品级信息。

4. **融合进图谱**  
   - `merge_product_info_into_v2_graph`：将抽取结果转为产品/组件/特征/参数/属性节点及 `has_component`、`has_feature`、`has_parameter` 等边。  
   - 与已有实体做 **语义对齐**（向量相似度 ≥ 阈值则合并节点），避免重复节点。  
   - 输出写入 `rag_storage_v2`（即 G_v2）。

因此，**Graph 的生成** = 解析 + 多模态描述与实体 → G_v1（chunk 级实体关系）→ 可选的产品 Schema 多智能体抽取 → 融合 → G_v2。

---

## 二、Agentic 检索过程（A-PRAG：Flow-Agentic Search-Review）

问答时可采用 **Agentic 检索**（Q&A Agent），实现「搜索-审核-修正」闭环，而不是单次检索即生成答案。

1. **问题分类**  
   用户问题先经 LLM 分类为：`factoid` / `counting` / `visual` / `list` / `unanswerable_possible` 等类型。

2. **检索 Agent（Retrieval Agent）**  
   - 根据问题类型注入不同策略（如事实型优先文本+页面验证，计数型逐页扫描，视觉型必须调 VLM 等）。  
   - Agent 通过工具与知识库交互：`product_info`、`kb_query`、`kb_chunk_query`、`kb_page_context`、`vlm_image_query` 等。  
   - 在工具调用次数上限内（如 8 次）完成检索并生成初版答案。

3. **验证 Agent（Verification Agent）**  
   - 对初版答案做 **独立事实验证**：用不同关键词/策略再检索，交叉核对答案是否与文档一致。  
   - 输出是否通过验证及反馈（如缺失、错误点）。

4. **重试与输出**  
   - 若验证未通过且未达最大重试次数：将验证反馈注入检索 Agent，重新检索并生成答案，再验证。  
   - 达到最大重试或验证通过后，输出最终答案（并可能标记置信度）。

流程由 **Python 代码编排器** 控制（分类 → 检索 Agent → 验证 Agent → 判断是否重试），而不是由 LLM 调度，保证可控与可复现。

---

## 三、安装

### 3.1 从 PyPI 安装（推荐）

```bash
# 基础安装
pip install raganything

# 可选依赖（按需）
pip install 'raganything[image]'   # 图片格式：BMP, TIFF, GIF, WebP
pip install 'raganything[text]'    # 文本：TXT, MD
pip install 'raganything[all]'     # 上述全部
```

### 3.2 从源码安装

```bash
# 安装 uv（如未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

git clone https://github.com/HKUDS/RAG-Anything.git
cd RAG-Anything

# 创建虚拟环境并安装依赖
uv sync

# 可选：带 image/text 等
uv sync --extra image --extra text
# 或全部
uv sync --all-extras
```

### 3.3 其他依赖说明

- **Office 文档**（.doc/.docx/.ppt/.pptx/.xls/.xlsx）：需安装 [LibreOffice](https://www.libreoffice.org/download/download/)（如 macOS：`brew install --cask libreoffice`）。  
- **MinerU**：首次使用时会自动拉取所需模型；也可参考 [MinerU 文档](https://github.com/opendatalab/MinerU) 配置模型路径。  
- **API 密钥**：使用 LLM/Embedding/VLM 时需配置相应 API（如 OpenAI 兼容接口、DashScope 等），见项目中的 `config` 与 `.env.example`。

---

## 四、Eval 怎么用

评测脚本：`eval/raganything_eval.py`。从 parquet/csv 读入「doc_id、query、Answer」，按 doc 加载对应 RAG 工作目录，对每条 query 用 RAG 生成答案，再用评估 LLM 打准确率（0/1），并输出整体准确率与明细。

### 4.1 数据与目录约定

- **数据集**：parquet 或 csv，需包含列（列名可通过 `--docid_col` / `--question_col` / `--answer_col` 覆盖）：  
  - `doc_id`：文档 ID，与下面目录对应。  
  - `question`（或 `query`）：问题。  
  - `answer`（或 `Answer`）：标准答案（用于评估）。
- **知识库目录**：每个 doc_id 对应一个 RAG 工作目录，默认为：  
  `{source_root}/{doc_id}/rag_storage`（或使用 v2 时 `rag_storage_v2`）。  
  需事先对这些文档跑完索引（或 `generate_v2_storage`）再评测。

### 4.2 基本用法

```bash
# 进入项目根目录
cd /path/to/RAG-Anything

# 使用默认列名（doc_id, query, Answer）、默认 source_root
python eval/raganything_eval.py \
  --dataset_path runtime/eval/train-00000-of-00001.parquet \
  --source_root runtime/source \
  --limit 100

# 指定只评测某几个文档
python eval/raganything_eval.py \
  --dataset_path runtime/eval/train-00000-of-00001.csv \
  --source_root runtime/source \
  --docid_filter "Macbook_air.pdf,watch_d.pdf"

# 使用 v2 知识库（需先对 source 跑 scripts/generate_v2_storage.py）
python eval/raganything_eval.py \
  --dataset_path runtime/eval/train-00000-of-00001.parquet \
  --source_root runtime/source \
  --use_v2 \
  --limit 100

# 使用 Agent 流程（检索+验证+重试）而不是单纯 rag.aquery
python eval/raganything_eval.py \
  --dataset_path runtime/eval/train-00000-of-00001.parquet \
  --source_root runtime/source \
  --use_agent
```

### 4.3 常用参数

| 参数 | 说明 | 默认 |
|------|------|------|
| `--dataset_path` | 评测集路径（.parquet 或 .csv） | `runtime/eval/train-00000-of-00001.parquet` |
| `--source_root` | 按 doc_id 存放 RAG 工作目录的根目录 | `runtime/source` |
| `--docid_col` | 数据集中文档 ID 列名 | `doc_id` |
| `--question_col` | 问题列名 | `question` |
| `--answer_col` | 标准答案列名 | `answer` |
| `--query_mode` | LightRAG 查询模式（如 local/global/hybrid） | `hybrid` |
| `--docid_filter` | 只评测的 doc_id 列表，逗号分隔 | 无 |
| `--limit` | 最多评测条数 | 无限制 |
| `--use_agent` | 使用 Q&A Agent 流程（检索+验证+重试） | False |
| `--use_v2` | 使用 v2 知识库（rag_storage_v2） | False |

结果会写入 `runtime/eval/<timestamp>/`，包含汇总与明细（如 details.csv、eval.log 等）。

---

## 五、Web 端怎么启动

Web 端提供知识库管理、文档上传/解析、对话式问答等，由 FastAPI + 前端静态资源构成。

### 5.1 启动方式

在项目根目录下：

```bash
# 方式一：直接运行 main
python web/main.py

# 方式二：用 uvicorn 指定模块
uvicorn web.main:app --host 0.0.0.0 --port 8000 --reload
```

默认地址：**http://0.0.0.0:8000**（本机访问可用 `http://127.0.0.1:8000`）。

### 5.2 依赖与配置

- 安装时已包含 `fastapi`、`uvicorn` 等（见 `pyproject.toml`）。  
- 文档解析、建索引、问答会用到 LLM/Embedding/VLM，需在 `config` 或环境中配置好 API Key 与 Base URL。  
- 静态前端在 `web/front`，由 `web/main.py` 挂载到 `/static`。

---

## 六、相关文档与引用

- 论文与仓库： [arXiv:2510.12323](https://arxiv.org/abs/2510.12323)，[GitHub: HKUDS/RAG-Anything](https://github.com/HKUDS/RAG-Anything)。
