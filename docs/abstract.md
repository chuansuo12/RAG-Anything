# 摘要

---
产品质量受组件选型、参数配置等多种因素影响，相关信息散布在规格书、技术手册等长文档中。在缺陷根因分析与质量改进场景下，工程师需要从文档中挖掘关键因素及其关联。现有基于知识图谱的检索增强生成方法应用于此类场景时，面临两方面不足。其一，远距离领域关系难以构建，产品文档中"功能—组件—参数"呈 1-N-N 层次结构，常跨越数十页分布，而分块式图谱构建仅能在局部窗口内抽取实体与关系，无法关联同一产品散落各处的信息，导致大量实体孤立。其二，单轮生成缺乏可靠性保障，现有系统对所有问题类型采用相同检索策略，且不对生成结果做独立验证；检索不完整时，模型易以参数知识填充空白而产生幻觉，但企业场景下错误回答的代价往往高于拒答。

针对上述两项挑战，本文基于 RAG-Anything 框架，提出 PRAG 与 A-PRAG 两类方法，分别从领域知识图谱构建与检索生成两个层面提升多模态产品长文档质量问答的准确性。

在知识图谱构建方面，本文提出 PRAG（Product Retrieval-Augmented Generation），通过领域知识驱动的全局抽取解决远距离关系缺失问题。领域知识以技能（Skill）形式封装，包含结构定义、抽取步骤与提示模板三类文件。领域知识抽取智能体（DKEAgent）识别文档所属领域后，激活对应技能并调度子智能体在基础图谱上全局抽取产品级知识，显式构建"产品—组件—功能—参数—属性"的层次关系；抽取结果经语义实体对齐融合至基础图谱，形成增强图谱 $G_{v2}$，将原本散落各处的碎片化实体连通为结构化知识网络。

在检索生成方面，本文提出 A-PRAG（Agentic PRAG），通过多智能体闭环架构解决生成幻觉与置信度不足问题。系统对问题进行类型判定（事实型、计数型、视觉型、列举型、不可回答型），据此为检索智能体注入差异化检索策略；检索智能体生成草稿回答后，独立验证智能体以差异化检索路径从证据充分性、完整性、可回答性与准确性四个维度进行交叉核查；验证不通过时，生成指向具体问题的结构化反馈，驱动检索智能体定向重检索，直至验证通过或达到最大迭代次数。上述控制逻辑以确定性程序实现，将传统开环生成流程升级为具备自纠错能力的多智能体闭环系统。

实验在 MMLongBench-Doc（Guidebooks 子集，23 篇，196 问答对）与 MPMQA（PM209 子集，45 篇，4,830 问答对）上开展。PRAG 平均准确率达 42.3%，较基线提升 1.9 个百分点；A-PRAG 进一步提升至 47.2%，较基线累计提升 6.8 个百分点。消融实验表明，验证智能体与增强图谱分别贡献 5.6 和 3.6 个百分点的性能增益，两者相互依存，缺一则系统性能显著下滑。

关键词：检索增强生成；知识图谱；领域知识驱动；多智能体；迭代验证反馈；多模态文档理解；产品质量

---

# Abstract

Product quality is influenced by many factors such as component selection and parameter configuration, and the relevant information is spread across lengthy documents including specifications and technical manuals. In scenarios like defect root-cause analysis and quality improvement, engineers need to extract these key factors and their relationships from documents. When existing knowledge-graph-based retrieval-augmented generation methods are applied to such scenarios, two problems arise. First, distant domain relationships are hard to construct: the "function–component–parameter" hierarchy in product documents follows a 1-to-N-to-N structure and is often distributed across dozens of pages, yet chunk-based graph construction can only extract entities and relations within local windows and cannot link information about the same product scattered across distant locations, leaving many entities isolated. Second, single-pass generation lacks reliability: existing systems apply the same retrieval strategy to all question types and do not independently verify the generated answers; when retrieval is incomplete, the model tends to fill gaps with its parametric knowledge, producing hallucinations, yet in enterprise settings the cost of an incorrect answer is often higher than that of declining to answer.

To address these two problems, this thesis builds on the RAG-Anything framework and proposes PRAG and A-PRAG, improving multimodal product long-document quality QA from the perspectives of domain knowledge graph construction and retrieval-generation, respectively.

For knowledge graph construction, PRAG (Product Retrieval-Augmented Generation) resolves the missing distant relationships through domain-knowledge-driven global extraction. Domain knowledge is encoded as modular Skills, each consisting of a schema definition, extraction steps, and prompt templates. The Domain Knowledge Extraction Agent (DKEAgent) identifies the document domain, activates the corresponding skill, and dispatches sub-agents to perform global structured extraction over the base graph, explicitly constructing the "product–component–feature–parameter–attribute" hierarchy. The extracted knowledge is then merged back via semantic entity alignment, producing an enhanced graph $G_{v2}$ that connects previously scattered entities into a structured knowledge network.

For retrieval and generation, A-PRAG (Agentic PRAG) addresses hallucination and insufficient reliability through a multi-agent closed-loop architecture. The system classifies each question into one of five types (factoid, counting, visual, list, or unanswerable) and injects a type-specific retrieval strategy accordingly. After the retrieval agent produces a draft answer, an independent verification agent cross-checks it along four dimensions—evidence grounding, completeness, answerability, and accuracy—using different retrieval paths. When issues are found, the verification agent generates structured feedback identifying the specific problem, and the retrieval agent uses this feedback for targeted re-retrieval. This loop repeats until the answer passes verification or the retry limit is reached. All flow control logic is implemented deterministically, upgrading the traditional open-loop pipeline into a multi-agent closed-loop system with self-correction capability.

Experiments are conducted on two benchmarks: MMLongBench-Doc (Guidebooks subset, 23 documents, 196 QA pairs) and MPMQA (PM209 subset, 45 documents, 4,830 QA pairs). PRAG achieves an average accuracy of 42.3%, a gain of 1.9 percentage points over the baseline. A-PRAG further improves this to 47.2%, a cumulative gain of 6.8 percentage points. Ablation results show that the verification agent and the enhanced graph contribute 5.6 and 3.6 percentage points respectively; removing either component causes a significant performance drop, confirming their synergistic relationship.

Keywords: Retrieval-Augmented Generation; Knowledge Graph; Domain Knowledge; Multi-Agent; Iterative Verification Feedback; Multimodal Document Understanding; Product Quality
