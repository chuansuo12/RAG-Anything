# 摘要 / Abstract

---
本文在RAG-Anything多模态统一RAG框架基础上，提出A-PRAG（Agentic-Product Retrieval-Augmented Generation）框架，从知识存储与知识检索生成两个层面协同提升多模态长文档召回准确性。
在知识存储层面，本文提出一种基于领域模型驱动的产品知识图谱增强构建方法。该方法引入预定义的产品领域模型（Product Schema），规定"产品-组件-功能-参数-属性"五层概念域结构，并以此驱动确定性知识抽取流水线（Deterministic Knowledge Extraction Pipeline, DKE Pipeline）在已构建的基础图谱上执行全局产品信息抽取。抽取完成后，通过基于向量相似度的语义实体对齐机制将产品级结构化知识融合回图谱，形成具备完整层次结构的增强图谱，从根本上弥补了分块级图谱在远距离语义关联上的不足。
在知识检索与生成层面，本文进一步提出A-PRAG（Agentic Product Retrieval-Augmented Generation）方法，以代码编排器为调度核心构建迭代验证反馈（Retrieve-Verify-Refine）闭环架构。系统首先对用户问题进行类型分类（事实型、计数型、视觉型、列举型、不可回答型），并向自适应检索Agent注入类型特定的检索策略，引导其通过分层检索与渐进式证据收集生成有据可查的草稿回答。草稿回答随后进入独立的验证Agent进行交叉核查——验证Agent采用差异化检索路径对证据充分性、完整性、可回答性与准确性四个维度逐一审核，一旦发现问题则生成结构化反馈，驱动检索Agent针对性地进行重检索与修正，直至验证通过或达到最大重试次数。这一闭环机制将传统开环的"检索-生成"管道升级为具备自我纠错能力的多智能体协作系统，与增强图谱中的产品层次化结构知识相互配合，进一步提升了回答的准确性与可靠性。
在两个多模态产品文档问答数据集——MMLongBench-Doc（Guidebooks子集）和MPMQA（PM209子集）上的系统性实验表明，PRAG平均准确率为42.3%，较RAG-Anything基线提升1.9个百分点；在此基础上引入多智能体闭环检索架构的A-PRAG进一步将平均准确率提升至47.2%，较PRAG提升4.9个百分点，较RAG-Anything累计提升6.8个百分点。消融实验验证了各设计模块的独立贡献及其协同互补关系，案例分析从图谱结构与问答效果两个层面直观展示了所提方法在跨页面信息聚合与多跳推理任务上的实际效果。

关键词： 检索增强生成；知识图谱；领域模型驱动；多智能体；迭代验证反馈；多模态文档理解；产品质量

---

## Abstract

This thesis proposes the A-PRAG (Agentic Product Retrieval-Augmented Generation) framework, built upon the RAG-Anything multimodal unified RAG framework, to jointly improve the recall accuracy of multimodal long documents from two perspectives: knowledge storage and knowledge retrieval-generation.

On the knowledge storage side, this thesis proposes a schema-driven product knowledge graph enhancement method. A predefined Product Schema is introduced to specify a five-tier concept domain structure of "Product–Component–Feature–Parameter–Attribute," which drives a Deterministic Knowledge Extraction Pipeline (DKE Pipeline) to perform global product information extraction over the already-constructed base knowledge graph. Upon completion, a vector similarity-based semantic entity alignment mechanism merges the extracted product-level structured knowledge back into the graph, forming an enhanced graph with a complete hierarchical structure that fundamentally addresses the long-range semantic association deficiencies of chunk-level graphs.

On the knowledge retrieval and generation side, this thesis further proposes an iterative verification feedback mechanism under the A-PRAG framework, using a code orchestrator as the scheduling core to construct a Retrieve-Verify-Refine closed-loop architecture. The system first classifies the user question by type (factoid, counting, visual, list, or unanswerable) and injects a type-specific retrieval strategy into an adaptive retrieval agent, guiding it to generate evidence-grounded draft answers through hierarchical retrieval and progressive evidence collection. The draft answer then enters an independent verification agent for cross-checking—the verification agent audits the answer across four dimensions (evidence grounding, completeness, answerability, and accuracy) using differentiated retrieval paths. Upon detecting issues, it generates structured feedback to drive the retrieval agent to perform targeted re-retrieval and correction, repeating until verification passes or the maximum retry count is reached. This closed-loop mechanism upgrades the traditional open-loop "retrieve-generate" pipeline into a self-correcting multi-agent collaborative system, working in concert with the hierarchical product knowledge in the enhanced graph to further improve answer accuracy and reliability.

Systematic experiments on two multimodal product document QA datasets—MMLongBench-Doc (Guidebooks subset) and MPMQA (PM209 subset)—demonstrate that PRAG achieves an average accuracy of 42.3%, a 1.9 percentage point improvement over the RAG-Anything baseline. Building on this, A-PRAG further raises average accuracy to 47.2%, a 4.9 percentage point improvement over PRAG and a cumulative 6.8 percentage point improvement over RAG-Anything. Ablation studies validate the independent contributions of each design module and their synergistic complementarity, while case studies provide intuitive demonstrations of the proposed methods' practical effectiveness on cross-page information aggregation and multi-hop reasoning tasks.

**Keywords:** Retrieval-Augmented Generation; Knowledge Graph; Schema-Driven; Multi-Agent; Iterative Verification Feedback; Multimodal Document Understanding; Product Quality
