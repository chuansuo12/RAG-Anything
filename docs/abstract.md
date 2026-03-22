# 摘要

---
本文基于RAG-Anything框架，提出PRAG与A-PRAG两类方法，从领域知识图谱构建与检索生成两个层面提升多模态产品长文档质量问答的准确性。

在知识图谱构建方面，本文提出 PRAG（Product Retrieval-Augmented Generation）。领域知识以技能（Skill）形式封装，包含结构定义、抽取步骤与提示模板三类文件。领域知识抽取智能体（DKEAgent）识别文档所属领域后，激活对应技能并调度子智能体在基础图谱上全局抽取产品级知识，经语义实体对齐融合至图谱，形成增强图谱 $G_{v2}$。该机制突破了传统分块抽取难以建立跨页语义关联的局限。

在检索生成方面，本文提出 A-PRAG（Agentic PRAG）。系统对问题进行类型判定（事实型、计数型、视觉型、列举型、不可回答型），据此为检索智能体注入差异化检索策略；检索智能体生成草稿回答后，独立验证智能体以差异化检索路径从证据充分性、完整性、可回答性与准确性四个维度进行交叉核查；验证不通过时，生成指向具体问题的结构化反馈，驱动检索智能体定向重检索，直至验证通过或达到最大迭代次数。上述控制逻辑以确定性程序实现，将传统开环生成流程升级为具备自纠错能力的多智能体闭环系统。

实验在 MMLongBench-Doc（Guidebooks 子集，23 篇，196 问答对）与 MPMQA（PM209 子集，45 篇，4,830 问答对）上开展。PRAG 平均准确率达 42.3%，较基线提升 1.9 个百分点；A-PRAG 进一步提升至 47.2%，较基线累计提升 6.8 个百分点。消融实验表明，验证智能体与增强图谱分别贡献 5.6 和 3.6 个百分点的性能增益，两者相互依存，缺一则系统性能显著下滑。

关键词：检索增强生成；知识图谱；领域知识驱动；多智能体；迭代验证反馈；多模态文档理解；产品质量

---

# Abstract

This thesis addresses two limitations of existing RAG systems on multimodal product documents: the difficulty of aggregating information scattered across pages, and the lack of reliability in the retrieval-generation process. Built on the RAG-Anything framework, two methods are proposed: PRAG, which enhances the knowledge graph with domain-specific structure, and A-PRAG, which introduces iterative verification feedback into the retrieval pipeline.

For knowledge graph construction, PRAG (Product Retrieval-Augmented Generation) encodes domain knowledge as modular Skills, each consisting of a schema definition, extraction steps, and prompt templates. The Domain Knowledge Extraction Agent (DKEAgent) identifies the document domain, activates the corresponding skill, and dispatches sub-agents to perform global structured extraction over the base graph. The extracted knowledge is then merged back via semantic entity alignment, producing an enhanced graph $G_{v2}$. This global aggregation approach overcomes the inherent limitation of chunk-level extraction, which fails to connect related product information distributed across distant pages.

For retrieval and generation, A-PRAG (Agentic PRAG) introduces a multi-agent closed-loop architecture with iterative verification feedback. The system first classifies each question into one of five types (factoid, counting, visual, list, or unanswerable) and injects a type-specific retrieval strategy accordingly. After the retrieval agent produces a draft answer, an independent verification agent examines it from four dimensions: evidence grounding, completeness, answerability, and accuracy. When issues are found, the verification agent generates structured feedback that identifies the specific problem, and the retrieval agent uses this feedback to perform targeted re-retrieval. This loop repeats until the answer passes verification or the retry limit is reached. All flow control logic is implemented deterministically, keeping the agents focused on retrieval and reasoning rather than scheduling decisions.

Experiments are conducted on two benchmarks: MMLongBench-Doc (Guidebooks subset, 23 documents, 196 QA pairs) and MPMQA (PM209 subset, 45 documents, 4,830 QA pairs). PRAG achieves an average accuracy of 42.3%, a gain of 1.9 percentage points over the baseline. A-PRAG further improves this to 47.2%, a cumulative gain of 6.8 percentage points. Ablation results show that the verification agent and the enhanced graph contribute 5.6 and 3.6 percentage points respectively, and removing either component causes a significant performance drop, confirming their synergistic rather than independently additive relationship.

Keywords: Retrieval-Augmented Generation; Knowledge Graph; Domain Knowledge; Multi-Agent; Iterative Verification Feedback; Multimodal Document Understanding; Product Quality
