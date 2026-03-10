# 第二章 国内外研究现状与相关工作

本章对与本文研究密切相关的四个领域进行系统综述：知识图谱的构建与信息抽取方法、检索增强生成（RAG）范式及其图结构扩展、面向多模态文档的理解与处理方法，以及基于大语言模型的智能体与多智能体协作机制。在各节综述的基础上，本章最后梳理现有方法在产品文档问答场景下的局限性，明确本文研究的出发点。

---

## 2.1 知识图谱构建与信息抽取

### 2.1.1 传统知识图谱表示学习

知识图谱以"实体-关系-实体"三元组为基本单元，将领域知识组织为结构化的有向图。知识表示学习（Knowledge Representation Learning，KRL），又称知识图谱嵌入（Knowledge Graph Embedding，KGE），旨在将知识图谱中的实体和关系映射到低维连续向量空间，以支持链接预测、实体对齐等下游任务，是知识图谱研究的核心方向之一 [1]。

基于翻译的模型是知识图谱嵌入中应用最为广泛的一类方法。Bordes等 [2] 提出的TransE将关系建模为实体向量空间中的平移操作，其简洁的形式化与较强的表示能力使其成为该领域的经典基线。然而，TransE在同一嵌入空间中同时表征实体与关系，无法有效处理一对多、多对一等复杂关系。针对这一问题，Lin等 [3] 提出TransR，分别为实体和关系构建独立的表示空间，通过投影矩阵建立两个空间之间的映射。此后，TransH [4]、TransD [5]、TransA [6] 等系列模型在距离度量、映射矩阵设计等方面对TransE进行了持续改进，共同构成了翻译类嵌入方法的主体脉络。

基于因子分解的方法从张量分解的角度切入。Nickel等 [7] 提出RESCAL，将知识图谱的邻接张量进行三向分解，实现了多关系数据上的集体学习。Yang等 [8] 在此基础上提出DistMult，通过对关系矩阵施加对角化约束简化了计算复杂度。Balažević等 [9] 提出的TuckER将知识图谱三元组的评分函数建模为Tucker分解，提供了对多类双线性模型的统一表示。

随着深度学习的发展，基于神经网络的方法逐渐成为主流。Dettmers等 [10] 提出ConvE，使用二维卷积对实体-关系对进行特征交互，在链接预测任务上以大幅减少的参数量取得了与复杂模型相当的性能。在图神经网络方向，Schlichtkrull等 [11] 提出关系图卷积网络（R-GCN），利用节点邻域聚合在知识图谱上进行关系感知的实体表示学习。Liu等 [12] 进一步提出关系感知图注意力网络（RAGAT），为不同关系类型构建独立的注意力消息函数，更充分地利用了知识图谱的异构性。

在语言模型与知识图谱的结合方面，Wang等 [13] 较早探索了将实体与单词联合嵌入同一向量空间的方法。Yao等 [14] 提出KG-BERT，将实体和关系的描述文本输入BERT进行三元组分类与链接预测，证明了预训练语言模型在知识图谱任务上的潜力。Chen等 [15] 提出HittER，采用分层Transformer结构分别捕获实体的局部邻域特征和全局关系语境，取得了更精细的语义建模效果。

上述工作奠定了知识图谱表示学习的理论基础，但主要聚焦于已有三元组的编码与链接预测，对于如何从非结构化文档中自动构建领域知识图谱、以及如何在图谱构建阶段引入领域先验约束，关注相对不足。

### 2.1.2 基于大语言模型的知识图谱构建

传统知识图谱构建依赖预定义的本体或模式，通过人工标注、远程监督或规则匹配从文本中抽取三元组。这类方法在通用领域取得了较好的效果，但在面向特定领域的长文档时，受限于标注成本和规则覆盖范围，难以实现高质量、大规模的自动化构建。

大语言模型的出现为自动化知识图谱构建开辟了新路径。基于提示工程（Prompt Engineering）的方法通过精心设计的指令引导LLM从文本中识别实体、抽取关系并输出结构化三元组，无需针对特定领域进行大量标注训练。Ye等 [16] 研究表明，经过适当的指令设计，GPT-4等大模型在零样本实体关系抽取任务上已能接近有监督方法的性能。进一步地，通过结构化输出约束（如JSON模式）和思维链提示（Chain-of-Thought，CoT [17]），可以引导LLM输出符合预定义模式的结构化知识，从而与知识图谱的存储格式无缝对接 [18]。

在从文档到知识图谱的端到端流程设计上，Edge等 [19] 提出GraphRAG，通过两阶段处理——先用LLM对文本块进行实体和关系抽取，再通过社区检测算法生成层次化摘要——将非结构化文本转化为适用于全局查询的图结构知识库。GraphRAG通过图摘要聚合分散在不同文本块中的相关信息，在一定程度上缓解了分块局部性问题，但其摘要生成过程依赖LLM，对于需要精确数值的产品参数类信息存在引入噪声的风险。Guo等 [20] 提出LightRAG，采用轻量化的双层图索引设计，通过实体级和关系级的向量化表示支持高效的语义检索，在无需大规模预训练的前提下实现了图结构知识的快速构建，是当前图RAG领域的重要基线。

如何将领域先验知识引入LLM驱动的知识图谱构建，已成为一个值得深入研究的问题。部分工作通过在提示中注入领域本体或实体类型约束，引导LLM将抽取到的实体按预设分类进行规范化 [21]；另一些工作则采用结构化输出模式（Schema-constrained generation）来保证抽取结果与目标知识库结构的一致性 [22]。然而，这些方法仍受制于分块抽取的局部性——每个文本块的实体抽取仅能依赖该块自身的上下文，无法跨块整合同一实体在文档不同位置的完整信息。本文第三章提出的DKE Pipeline正是针对这一根本局限，通过在已构建的基础图谱上进行全局语义检索，实现跨页面的产品级信息聚合。

---

## 2.2 检索增强生成

### 2.2.1 基础RAG范式与进展

检索增强生成（Retrieval-Augmented Generation, RAG）由Lewis等 [23] 提出，其核心思想是在LLM生成回答之前，首先从外部知识库中检索与问题相关的上下文片段，将其与问题一并输入模型，从而将参数化知识（模型权重）与非参数化知识（外部检索结果）相融合，有效缓解LLM的幻觉问题，同时支持知识库的动态更新而无需重新训练模型。

在基础RAG框架的基础上，研究者从索引、检索、生成三个环节提出了大量改进。在索引方面，分层分块、句子窗口、命题索引等策略 [24] 被引入以改善检索粒度与上下文完整性之间的平衡；向量索引之外，混合索引方案（稠密向量+稀疏BM25）[25] 被用于提升检索的准确率与召回率。在检索方面，查询扩展 [26]、HyDE（假设文档嵌入）[27]、步进回溯提示（Step-Back Prompting）[28] 等技术被用于提升初始查询与目标内容之间的语义匹配质量；重排序模型（Reranker）被引入检索后处理阶段以提升候选文档的相关性排序 [29]。在生成方面，上下文压缩 [30]、证据聚合 [31] 等方法被用于在减少模型输入噪声的同时保留关键信息。

Gao等 [32] 对RAG的发展脉络进行了系统综述，将其划分为朴素RAG（Naive RAG）、高级RAG（Advanced RAG）和模块化RAG（Modular RAG）三个阶段，并指出现有RAG方法在多跳推理、长文档理解和多模态信息融合方面仍存在明显局限。这些局限恰恰是本文所关注的产品文档问答场景中最为突出的技术挑战。

### 2.2.2 基于图结构的RAG方法

基于纯向量检索的RAG方法在处理需要多实体关联的问题时存在天然局限：向量检索以语义相似度为排序依据，难以显式建模实体间的结构化依赖关系，对于需要沿知识图谱关系路径进行多跳推理的问题，单轮向量检索往往无法覆盖所有必要的证据。

图结构RAG方法通过将知识组织为图的形式，为多跳检索提供了结构化基础。GraphRAG [19] 以实体-关系图为核心，通过社区摘要聚合局部知识，在全局查询上取得了显著优于纯向量RAG的性能。LightRAG [20] 采用低开销的双层检索策略，在本地查询（精确实体匹配）与全局查询（社区级语义检索）之间取得平衡，支持对大规模知识图谱的高效访问。PathRAG [33] 则进一步专注于在图上发现关键关系路径，通过流行度加权的路径剪枝降低无效路径对生成质量的干扰。HippoRAG [34] 受人类记忆机制启发，构建了一种可持续增量更新的图记忆结构，以支持对跨会话积累知识的高效检索与回答。

近期，将知识图谱与大语言模型深度整合的工作也受到广泛关注。KGRAG [35] 将知识图谱中的结构化事实以自然语言形式注入提示上下文，通过实体链接将用户问题锚定到图谱相关子图；ToG（Think-on-Graph）[36] 引导LLM在推理过程中以图谱路径为思维骨架，沿实体-关系链进行显式的多跳推理，在多跳问答基准上取得了领先性能。上述工作共同指向一个核心结论：高质量的图谱结构与有效的图检索策略是图结构RAG性能的关键基础，而这正是本文第三章通过增强图谱构建所着力解决的问题。

---

## 2.3 多模态文档理解与处理

### 2.3.1 多模态文档解析

产品说明书等工业文档以PDF格式为主，其中包含文本、图片、表格、公式等多种内容形式，如何将这类富格式文档转化为可供后续处理的结构化表示，是多模态文档理解的基础性问题。

早期的PDF解析方法主要依赖规则和启发式算法，通过提取文字层、分析版面几何特征来恢复文本内容和结构。Shen等 [37] 提出PDFPlumber等基于规则的解析工具，能够在格式规范的文档上取得较好的文本提取效果，但对于包含复杂图表、双栏布局或扫描内容的文档，解析质量明显下降。深度学习方法的引入显著提升了文档版面分析的鲁棒性：Zhong等 [38] 提出PubLayNet，基于大规模标注数据训练了用于文档版面区域检测的模型，能够自动识别段落、图片、表格等区域类型。LayoutLM系列 [39] 将文字内容、位置信息与视觉特征联合建模，在文档信息抽取、表单理解等任务上大幅超越了纯文本方法。

近年来，面向复杂多模态文档的端到端解析框架持续涌现。MinerU [40] 是一个高精度的多模态文档解析工具，支持对PDF中文本、表格、公式和图片的统一提取与结构化输出，其输出的Markdown格式内容便于后续的分块与知识抽取处理。Marker [41] 基于多个专用深度学习模型的流水线设计，在速度与精度之间取得了较好的平衡，支持大批量的文档转换任务。此外，以GPT-4V [42]、Qwen-VL [43] 为代表的多模态大模型能够直接对文档页面图像进行端到端理解，在版面复杂、文字嵌入图形等传统工具难以处理的情形下展现出独特的优势。本文采用MinerU作为文档解析组件，实现对产品说明书中文本与视觉内容的统一提取。

### 2.3.2 面向多模态文档的RAG框架

将多模态信息纳入RAG框架，是近年来研究的热点方向。Zhao等 [44] 提出MMRAG，针对文档中的图片和表格建立独立的视觉编码索引，通过多通道检索将视觉语义信息引入生成阶段。Chen等 [45] 探索了基于视觉问答（VQA）模型的文档检索增强方案，通过对相关页面图像直接运行视觉推理回答用户问题，有效利用了图文交织的文档内容。ColPali [46] 提出以文档页面的视觉表示为索引单元，通过视觉语言模型对页面图像进行整体嵌入，支持跨模态语义检索，在多模态文档问答任务上取得了显著进展。

RAG-Anything [47] 是由HKUDS团队提出的多模态统一RAG框架，以LightRAG为底层图谱引擎，在其基础上增加了多模态内容的解析、编码与跨模态融合能力，能够统一处理文档中的文本、图片、表格和数学公式，并将多模态内容的语义表示融合进知识图谱的构建与检索流程。RAG-Anything代表了当前面向复杂文档的多模态RAG框架的先进水平，是本文PRAG框架的基础版本。然而，RAG-Anything在知识图谱构建阶段仍采用通用的分块级实体关系抽取方式，对产品文档领域特有的层次化知识结构缺乏针对性建模；同时，其问答阶段沿用单次"检索-生成"管道，不具备策略自适应与事实验证能力。本文的工作正是在RAG-Anything的基础上，针对这两方面不足提出了系统性的改进方案。

### 2.3.3 多模态产品文档问答的评测基准

随着多模态文档理解研究的深入，专用评测基准的构建也取得了重要进展。

MMLongBench-Doc [48] 由Ma等人提出，发表于NeurIPS 2024，是目前最具代表性的多模态长文档理解基准之一。该基准包含135篇PDF格式的长文档，平均页数达47.5页，涵盖研究报告、教程、学术论文、操作指南、宣传册等7个文档类别，共标注1,082个专家级问答对，其中约33.7%为跨页问题，约20.6%为不可回答问题。其操作指南（Guidebooks）子集包含23篇产品类操作指南文档及196个问答对，高度契合本文的产品质量因素挖掘场景。

MPMQA [49] 由Li等人提出，发表于AAAI 2023，是专门面向产品说明书的多模态问答数据集。其PM209评测集包含来自27个消费电子品牌的209份产品说明书及22,021个问答对，答案同时涵盖文本与视觉两个组成部分，充分反映了产品文档理解中视觉信息不可或缺的特点。

上述两个数据集均采用大语言模型辅助的准确率评分（LLM-as-judge）作为主要评价指标，以事实一致性为判断依据，兼顾了评测效率与语义准确性。本文的实验验证采用这两个数据集，并沿用相同的评价方式，以保证实验结果的可比性与可信度。

---

## 2.4 基于大语言模型的智能体方法

### 2.4.1 LLM智能体的推理与规划

大语言模型不仅能够执行单次的文本生成任务，也逐渐被赋予工具使用、多步推理和任务规划的能力，推动了"LLM智能体"（LLM Agent）这一新范式的兴起。

思维链提示（Chain-of-Thought, CoT）[17] 的提出标志着LLM推理能力研究的重要突破——通过在少样本示例中展示逐步推理过程，可以激发LLM在复杂推理任务上的显著性能提升。此后，Tree of Thoughts [50] 将推理路径从单链扩展为树状搜索，支持对多条推理路径进行评估与剪枝。ReAct [51] 将推理（Reasoning）与行动（Acting）交织为统一的决策循环，使Agent能够在每一步根据当前证据状态动态选择工具调用或输出推理结论，极大地提升了Agent在多步信息检索与问答任务上的灵活性。本文第四章中检索Agent采用的推理-行动决策范式正是基于ReAct框架的思想。

在工具使用方面，Toolformer [52] 通过自监督方式训练语言模型学习何时调用外部工具（计算器、搜索引擎、日历等），并如何将工具返回结果整合进续写推理。WebGPT [53]、WebShop [54] 等工作则针对特定任务场景设计了与外部环境交互的专用工具集，验证了LLM与工具调用深度结合的可行性。近期，大规模多功能工具调用基准（如ToolBench [55]）的建立推动了通用工具调用能力的系统性研究与评测。

在任务规划方面，基于规划-执行分离的架构逐渐成为处理复杂多步任务的主流范式：规划模块（通常为LLM）负责将高层目标分解为子任务序列，执行模块负责调用工具完成各子任务，控制逻辑负责汇聚子任务结果并决定后续行动。Plan-and-Execute [56]、HuggingGPT [57] 等工作在不同任务场景下验证了该范式的有效性。

### 2.4.2 多智能体协作系统

随着单一LLM Agent在复杂任务上能力边界的显现，多智能体协作系统（Multi-Agent System）受到了广泛关注。在多智能体框架中，不同Agent承担不同的角色分工，通过消息传递、共享状态或流水线等方式协作完成复杂任务，以突破单一模型的能力瓶颈。

MetaGPT [58] 模拟软件工程团队的协作模式，将不同Agent分配为产品经理、架构师、程序员等角色，通过标准化流程接口实现结构化的多智能体协作，在代码生成任务上展现了强大的工程能力。AutoGen [59] 提供了一个通用的多智能体对话框架，支持人机混合、全自动等多种协作模式，使开发者能够灵活定义Agent的角色、能力与交互策略。CAMEL [60] 探索了"角色扮演"式的双Agent对话机制，通过模拟指令者-执行者的对话推动任务的逐步完成。

在代码编排与确定性流程控制方面，CrewAI [61]、LangGraph [62] 等框架将多智能体的任务调度逻辑从LLM中分离出来，以代码显式定义Agent的依赖关系、执行顺序和数据流，从而在保持Agent推理灵活性的同时，确保整体流程的可控性与可复现性。这一"代码编排+Agent推理"的解耦思想与本文第四章的A-PRAG架构设计高度契合——本文将流程控制（问题分类、验证判断、重试触发）从Agent推理中剥离，交由代码编排器以确定性逻辑实现。

### 2.4.3 自我验证与迭代修正机制

LLM在生成过程中不可避免地会产生幻觉，即生成与事实不符但语言流畅的内容。如何赋予LLM或Agent系统自我检测和修正错误的能力，是近年来的重要研究方向。

Self-Refine [63] 提出一种迭代自我修正范式：模型在生成初稿后，对自身的输出进行反馈评估，并依据反馈修正输出，循环直至达到满意质量。Reflexion [64] 将自我反思与长期记忆相结合，Agent通过将过往失败经验以自然语言形式存入记忆，在后续尝试中规避已知错误路径。CRITIC [65] 则引入外部工具（如搜索引擎、代码执行器）对LLM输出进行独立验证，通过工具返回的客观反馈纠正模型的参数化偏见，在事实性问答和数学计算任务上显著降低了错误率。

在RAG场景中，CRAG（Corrective RAG）[66] 提出在检索结果上额外运行一个轻量级评估模块，当检索质量被判定为低时，自动触发基于网络搜索的补充检索，有效提升了RAG系统在检索失败场景下的鲁棒性。Self-RAG [67] 训练模型在生成过程中自主判断是否需要检索、评估检索结果的相关性，并对最终输出进行事实一致性验证，以特殊反思标记（Reflection Token）将上述判断内嵌进生成序列，实现了检索必要性与输出质量的自适应控制。

上述工作均从不同角度探索了"生成-验证-修正"的闭环思路，但大多依赖模型对自身输出的自我评估，或使用通用外部工具进行验证。在产品文档问答这一特定场景中，验证需要基于专属知识库进行精确的事实交叉核查，且检索Agent与验证Agent应采用差异化的检索路径以保障独立性。本文第四章在上述工作的基础上，针对产品文档问答场景设计了具有四维审核框架的专用验证Agent，并通过结构化反馈实现了精准的定向修正。

---

## 2.5 本章小结

综合上述综述，现有研究在以下几个方面已取得重要进展：知识图谱表示学习提供了丰富的实体-关系建模方法；基于LLM的知识抽取使大规模自动化图谱构建成为可能；图结构RAG在多跳推理问题上相较于纯向量RAG展现出明显优势；多模态文档解析工具为复杂格式文档的内容提取提供了坚实基础；多智能体与自我修正机制则为构建具备自主推理与错误纠正能力的问答系统提供了方法论支撑。

然而，面向产品文档的质量关键因素挖掘这一特定场景，现有方法存在以下尚未解决的关键不足：

**（1）分块级图谱构建无法建立跨页面产品级结构化知识。** 现有基于LLM的图谱构建方法（包括LightRAG、RAG-Anything等）均采用分块级实体关系抽取策略，受制于单块上下文窗口的局部性，无法将散布在文档不同位置的同一产品组件或功能的完整信息系统性地组织为"产品-组件-功能-参数-属性"层次结构，导致图谱中的产品级知识严重碎片化。

**（2）检索策略缺乏对产品文档问题类型的适应性。** 现有RAG框架通常对所有问题采用统一的检索策略，无法针对计数型、视觉型、列举型等具有特殊检索需求的问题类型提供差异化的检索模式，导致特定类型问题的检索质量受制于通用策略的局限。

**（3）"检索-生成"管道缺乏独立的事实验证机制。** 现有方法普遍将检索结果直接送入LLM生成最终回答，缺乏独立的事实核查环节。在检索结果存在噪声或不完整的情况下，模型易产生幻觉性回答，而这一问题在产品质量管理场景中可能引发严重的决策失误。

针对上述三方面不足，本文第三章提出领域模型驱动的知识图谱增强构建方法，第四章提出基于迭代验证反馈的自适应多智能体检索架构，分别从知识存储与检索生成两个层面加以解决，并通过系统性实验验证各方法的有效性及两者的协同增益。

---

## 参考文献

[1] JI S, PAN S, CAMBRIA E, et al. A survey on knowledge graphs: representation, acquisition, and applications[J]. IEEE Transactions on Neural Networks and Learning Systems, 2021, 33(2): 494-514.

[2] BORDES A, USUNIER N, GARCIA-DURAN A, et al. Translating embeddings for modeling multi-relational data[J]. Advances in Neural Information Processing Systems, 2013, 26: 1-9.

[3] LIN Y, LIU Z, SUN M, et al. Learning entity and relation embeddings for knowledge graph completion[C]// Proceedings of the Twenty-Ninth AAAI Conference on Artificial Intelligence. 2015: 2181-2187.

[4] WANG Z, ZHANG J, FENG J, et al. Knowledge graph embedding by translating on hyperplanes[C]// Proceedings of the Twenty-Eighth AAAI Conference on Artificial Intelligence. 2014: 1112-1119.

[5] JI G, HE S, XU L, et al. Knowledge graph embedding via dynamic mapping matrix[C]// Proceedings of ACL-IJCNLP 2015. 2015: 687-696.

[6] XIAO H, HUANG M, HAO Y, et al. TransA: an adaptive approach for knowledge graph embedding[C]// Proceedings of the AAAI Conference on Artificial Intelligence. 2015: 1-7.

[7] NICKEL M, TRESP V, KRIEGEL H P. A three-way model for collective learning on multi-relational data[C]// Proceedings of the 28th ICML. 2011: 809-816.

[8] YANG B, YIH S W, HE X, et al. Embedding entities and relations for learning and inference in knowledge bases[C]// Proceedings of ICLR 2015. 2015: 1-13.

[9] BALAŽEVIĆ I, ALLEN C, HOSPEDALES T. TuckER: tensor factorization for knowledge graph completion[C]// Proceedings of EMNLP-IJCNLP 2019. 2019: 5185-5194.

[10] DETTMERS T, MINERVINI P, STENETORP P, et al. Convolutional 2D knowledge graph embeddings[C]// Proceedings of the AAAI Conference on Artificial Intelligence. 2018, 32(1): 1811-1818.

[11] SCHLICHTKRULL M, KIPF T N, BLOEM P, et al. Modeling relational data with graph convolutional networks[C]// Proceedings of ESWC 2018. 2018: 593-607.

[12] LIU X, TAN H, CHEN Q, et al. RAGAT: relation aware graph attention network for knowledge graph completion[J]. IEEE Access, 2021, 9: 20840-20849.

[13] WANG Z, ZHANG J, FENG J, et al. Knowledge graph and text jointly embedding[C]// Proceedings of EMNLP 2014. 2014: 1591-1601.

[14] YAO L, MAO C, LUO Y. KG-BERT: BERT for knowledge graph completion[EB/OL]. arXiv:1909.03193, 2019.

[15] CHEN S, LIU X, GAO J, et al. HittER: hierarchical transformers for knowledge graph embeddings[C]// Proceedings of EMNLP 2021. 2021: 10395-10407.

[16] YE H, ZHANG N, CHEN H, et al. Generative knowledge graph construction: a review[C]// Proceedings of EMNLP 2022. 2022: 9556-9580.

[17] WEI J, WANG X, SCHUURMANS D, et al. Chain-of-thought prompting elicits reasoning in large language models[J]. Advances in Neural Information Processing Systems, 2022, 35: 24824-24837.

[18] CARTA S, GIULIANI A, PIANO L, et al. Iterative zero-shot LLM prompting for knowledge graph construction[EB/OL]. arXiv:2307.01128, 2023.

[19] EDGE D, TRINH H, CHENG N, et al. From local to global: a graph RAG approach to query-focused summarization[EB/OL]. arXiv:2404.16130, 2024.

[20] GUO Z, CHEN Y, ZHANG Z, et al. LightRAG: simple and fast retrieval-augmented generation[EB/OL]. arXiv:2410.05779, 2024.

[21] PAN S, LUO L, WANG Y, et al. Unifying large language models and knowledge graphs: a roadmap[J]. IEEE Transactions on Knowledge and Data Engineering, 2024, 36(7): 3580-3599.

[22] ZHU Y, WANG X, CHEN J, et al. LLMs for knowledge graph construction and reasoning: recent capabilities and future opportunities[EB/OL]. arXiv:2305.13168, 2023.

[23] LEWIS P, PEREZ E, PIKTUS A, et al. Retrieval-augmented generation for knowledge-intensive NLP tasks[J]. Advances in Neural Information Processing Systems, 2020, 33: 9459-9474.

[24] CHEN J, LIN H, HAN X, et al. Benchmarking large language models in retrieval-augmented generation[C]// Proceedings of AAAI 2024. 2024: 17754-17762.

[25] MA X, GURURANGAN S, CHEN D, et al. Fine-tuning LLaMA for multi-stage text retrieval[EB/OL]. arXiv:2310.08319, 2023.

[26] WANG L, YANG N, WEI F. Query2doc: query expansion with large language models[EB/OL]. arXiv:2303.07678, 2023.

[27] GAO L, MA X, LIN J, et al. Precise zero-shot dense retrieval without relevance labels[C]// Proceedings of ACL 2023. 2023: 1762-1777.

[28] ZHENG H S, MISHRA S, CHEN X, et al. Take a step back: evoking reasoning via abstraction in large language models[EB/OL]. arXiv:2310.06117, 2023.

[29] GLASS M, ROSSIELLO G, CHOWDHURY M F M, et al. Re2G: retrieve, rerank, generate[C]// Proceedings of NAACL 2022. 2022: 2701-2715.

[30] XU P, PING Y, WU X, et al. RECOMP: improving retrieval-augmented LMs with context compression and selective augmentation[EB/OL]. arXiv:2310.04408, 2023.

[31] TRIVEDI H, BALASUBRAMANIAN N, KHOT T, et al. Interleaving retrieval with chain-of-thought reasoning for knowledge-intensive multi-step questions[C]// Proceedings of ACL 2023. 2023: 10014-10037.

[32] GAO Y, XIONG Y, GAO X, et al. Retrieval-augmented generation for large language models: a survey[EB/OL]. arXiv:2312.10997, 2023.

[33] CHEN B, GAO J, TAN J, et al. PathRAG: pruning graph-based retrieval augmented generation with relational paths[EB/OL]. arXiv:2502.14902, 2025.

[34] GUTIERREZ B J, SHEN J, YU D, et al. HippoRAG: neurobiologically inspired long-term memory for large language models[J]. Advances in Neural Information Processing Systems, 2024, 37.

[35] EDGE D, HU Y, SURI S, et al. KGRAG: knowledge graph enhanced retrieval augmented generation[EB/OL]. arXiv:2502.06864, 2025.

[36] SUN J, XU C, TANG L, et al. Think-on-graph: deep and responsible reasoning of large language model on knowledge graph[C]// Proceedings of ICLR 2024. 2024.

[37] SHEN Z, ZHANG K, DELL M, et al. LayoutParser: a unified toolkit for deep learning based document image analysis[C]// Proceedings of ICDAR 2021. 2021: 131-146.

[38] ZHONG X, TANG J, YEPES A J. PubLayNet: largest dataset ever for document layout analysis[C]// Proceedings of ICDAR 2019. 2019: 1015-1022.

[39] XU Y, LI M, CUI L, et al. LayoutLM: pre-training of text and layout for document image understanding[C]// Proceedings of KDD 2020. 2020: 1192-1200.

[40] WANG Y, CHEN X, SHI S, et al. MinerU: an open-source solution for precise document content extraction[EB/OL]. arXiv:2409.18839, 2024.

[41] VIKRAM P. Marker: a high quality PDF to markdown converter[EB/OL]. https://github.com/VikParuchuri/marker, 2024.

[42] OPENAI. GPT-4 technical report[EB/OL]. arXiv:2303.08774, 2023.

[43] BAI J, BAI S, CHU Y, et al. Qwen-VL: a versatile vision-language model for understanding, localization, text reading, and beyond[EB/OL]. arXiv:2308.12966, 2023.

[44] ZHAO R, CHEN H, WANG W, et al. Retrieving multimodal information for augmented generation: a survey[EB/OL]. arXiv:2303.10868, 2023.

[45] CHEN W, HU Z, CHEN X, et al. MuRAG: multimodal retrieval-augmented generator for open question answering over images and text[C]// Proceedings of EMNLP 2022. 2022: 5558-5570.

[46] FAYSSE M, SIBILLE H, WU T, et al. ColPali: efficient document retrieval with vision language models[EB/OL]. arXiv:2407.01449, 2024.

[47] HE X, CHEN Z, ZHAO Z, et al. RAG-Anything: all-in-one multimodal RAG system with universal parsing and graph-enhanced indexing[EB/OL]. arXiv:2505.11444, 2025.

[48] MA Y, ZHANG Z, WANG J, et al. MMLongBench-Doc: benchmarking long-context document understanding with visualizations[J]. Advances in Neural Information Processing Systems, 2024, 37.

[49] LI L, WANG J, YANG C, et al. MPMQA: multimodal question answering on product manuals[C]// Proceedings of AAAI 2023. 2023.

[50] YAO S, YU D, ZHAO J, et al. Tree of thoughts: deliberate problem solving with large language models[J]. Advances in Neural Information Processing Systems, 2023, 36.

[51] YAO S, ZHAO J, YU D, et al. ReAct: synergizing reasoning and acting in language models[C]// Proceedings of ICLR 2023. 2023.

[52] SCHICK T, DWIVEDI-YU J, DESSÌ R, et al. Toolformer: language models can teach themselves to use tools[J]. Advances in Neural Information Processing Systems, 2023, 36.

[53] NAKANO R, HILTON J, BALWIT A, et al. WebGPT: browser-assisted question-answering with human feedback[EB/OL]. arXiv:2112.09332, 2021.

[54] YAO S, CHEN H, YANG J, et al. WebShop: towards scalable real-world web interaction with grounded language agents[J]. Advances in Neural Information Processing Systems, 2022, 35: 20744-20757.

[55] QIN Y, LIANG S, YE Y, et al. ToolLLM: facilitating large language models to master 16000+ real-world APIs[C]// Proceedings of ICLR 2024. 2024.

[56] WANG L, MA C, FENG X, et al. A survey on large language model based autonomous agents[J]. Frontiers of Computer Science, 2024, 18(6): 186345.

[57] SHEN Y, SONG K, TAN X, et al. HuggingGPT: solving AI tasks with ChatGPT and its friends in Hugging Face[J]. Advances in Neural Information Processing Systems, 2023, 36.

[58] HONG S, ZHUGE M, CHEN J, et al. MetaGPT: meta programming for a multi-agent collaborative framework[C]// Proceedings of ICLR 2024. 2024.

[59] WU Q, BANSAL G, ZHANG J, et al. AutoGen: enabling next-gen LLM applications via multi-agent conversation[EB/OL]. arXiv:2308.08155, 2023.

[60] LI G, HAMMOUD H A A K, ITANI H, et al. CAMEL: communicative agents for "mind" exploration of large language model society[J]. Advances in Neural Information Processing Systems, 2023, 36.

[61] MOURA J. CrewAI: framework for orchestrating role-playing, autonomous AI agents[EB/OL]. https://github.com/crewAIInc/crewAI, 2023.

[62] CHASE H. LangGraph: building stateful, multi-actor applications with LLMs[EB/OL]. https://github.com/langchain-ai/langgraph, 2024.

[63] MADAAN A, TANDON N, GUPTA P, et al. Self-refine: iterative refinement with self-feedback[J]. Advances in Neural Information Processing Systems, 2023, 36.

[64] SHINN N, CASSANO F, LABASH B, et al. Reflexion: language agents with verbal reinforcement learning[J]. Advances in Neural Information Processing Systems, 2023, 36.

[65] GOU Z, SHAO Z, GONG Y, et al. CRITIC: large language models can self-correct with tool-interactive critiquing[C]// Proceedings of ICLR 2024. 2024.

[66] YAN S H, GU J C, ZHU Y, et al. Corrective retrieval augmented generation[EB/OL]. arXiv:2401.15884, 2024.

[67] ASAI A, WU Z, WANG Y, et al. Self-RAG: learning to retrieve, generate, and critique through self-reflection[C]// Proceedings of ICLR 2024. 2024.
