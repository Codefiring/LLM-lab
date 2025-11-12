<<<<<<< HEAD
非常好。这一部分属于 **ASDG 的设计动机与 LLM 推理机制** 的扩展说明，可以自然地放在上一节的 **Semantic Elements** 之后或单独作为一个 **“LLM-Guided Semantic Reasoning”** 小节。以下为改写后的完整 IEEE S&P 论文风格 LaTeX 文本，已无公式堆砌，保持学术正式、逻辑流畅。

---

```latex
\section{Formal Definition of the API State Dependency Graph (ASDG)}
\label{sec:asdg-formal}

We define the \textbf{API State Dependency Graph (ASDG)} as a comprehensive, directed, and attributed graph that unifies both the \emph{syntactic program facts} extracted from source code and the \emph{semantic knowledge} inferred through large language model (LLM) reasoning.  
Formally, an ASDG instance is denoted as $\mathcal{G} = (\mathcal{V}, \mathcal{E}, \mathcal{A})$, where $\mathcal{V}$ denotes the set of nodes, $\mathcal{E}$ represents the directed edges among them, and $\mathcal{A}$ is the collection of attributes attached to both nodes and edges.  
Each ASDG consists of two complementary categories: (1) \textbf{Basic Facts}, which represent static, verifiable program information, and (2) \textbf{Semantic Elements}, which capture higher-level meanings and state dependencies inferred by the LLM.

\subsection{Basic Facts}

The \textbf{basic facts} layer of ASDG encodes program entities and their direct structural relationships, all extracted by static analysis from the target codebase.  
It represents accurate, reproducible information that serves as the factual foundation for semantic reasoning.

\paragraph*{Nodes.}
Each node corresponds to a code-level entity, such as:
\begin{itemize}
    \item \textbf{Enumeration constants} --- nodes representing enumeration members, annotated with their names and values.
    \item \textbf{Macros} --- nodes representing macro constants, recording macro names and textual definitions.
    \item \textbf{Structures} --- nodes corresponding to all structure definitions, including the full list of member variables and recursively nested structures.
    \item \textbf{Functions / APIs} --- nodes representing both regular functions and target APIs. Each API node carries its definition, the list of header files it depends on, and detailed parameter information. For structure-type parameters, ASDG recursively records the corresponding structure layout.
\end{itemize}

\paragraph*{Edges.}
The edges in the basic layer capture verifiable syntactic or static dependencies:
\begin{itemize}
    \item \textbf{Function-call edges}, connecting functions that invoke one another.
    \item \textbf{Structure-nesting edges}, connecting structures that contain other structures.
    \item \textbf{Reference edges}, connecting macros, enums, and structures when one entity references another.
\end{itemize}

This layer constitutes the factual foundation of the ASDG, providing all the concrete information required for further reasoning.

\subsection{Semantic Elements}

The \textbf{semantic elements} layer builds upon the factual graph by incorporating contextual understanding inferred from large language models (LLMs).  
While the basic layer reflects what the code \emph{defines}, the semantic layer captures what the code \emph{implies}.  
It models latent relations between APIs, data fields, and states that are not explicitly written in code, but are critical for understanding program behavior.

\paragraph*{Node-level semantics.}
For structures and parameters, LLM inference enriches each node with additional annotations:
\begin{itemize}
    \item \textbf{Value ranges}, estimating the valid or expected numeric intervals of fields (e.g., buffer lengths, counts, or timeout values).
    \item \textbf{Usage roles}, describing the functional meaning of fields, such as \texttt{Address}, \texttt{Buffer}, or \texttt{Flag}.
\end{itemize}

\paragraph*{Edge-level semantics.}
Edges at the semantic layer capture implicit behavioral dependencies:
\begin{itemize}
    \item \textbf{State dependencies} describe how one API transitions a shared state that is later consumed by another (e.g., \texttt{init()} $\rightarrow$ \texttt{start()}).
    \item \textbf{Parameter dependencies} specify shared or conditionally related arguments between two APIs, revealing hidden data-flow or configuration coupling.
\end{itemize}

By combining these two layers, ASDG bridges the gap between syntactic accuracy and semantic understanding.

\subsection{LLM-Guided Semantic Reasoning}

Although large language models possess strong reasoning and summarization capabilities, their use in program analysis faces two inherent challenges: \textbf{hallucination} and \textbf{contextual drift}.  
LLMs may occasionally infer non-existent behaviors, misinterpret code semantics, or rely on prior knowledge inconsistent with the actual source code.  
Such hallucinations undermine the reliability of automated reasoning when models operate on free-form code text alone.

The ASDG framework mitigates this problem by grounding LLM reasoning in verifiable \textbf{basic facts}:
\begin{enumerate}
    \item \textbf{Grounded context.}  
    The LLM does not operate on raw code or comments; instead, it receives a structured summary of all relevant facts — function signatures, structure definitions, and dependency edges — directly extracted from the basic layer.  
    This constrains its reasoning to the real code context, significantly reducing speculative or inconsistent outputs.
    
    \item \textbf{Logic alignment.}  
    By following the logical constraints encoded in the basic facts (e.g., function call hierarchy, structure composition, and data types), the LLM can verify whether inferred relationships align with code-level dependencies.  
    This alignment naturally filters out many false or logically invalid inferences.
    
    \item \textbf{Efficient inference.}  
    With the factual graph as structural guidance, the LLM can focus on high-level semantic reasoning — such as state transition inference or parameter role deduction — rather than re-parsing or re-understanding the entire codebase.  
    As a result, its reasoning process becomes both more efficient and more accurate.
\end{enumerate}

Through this design, the ASDG achieves a synergistic integration between static analysis and language model reasoning:  
the static layer ensures factual precision, while the LLM contributes abstraction and semantic depth.  
This combination allows ASDG to model complex API behaviors and cross-function dependencies with both accuracy and interpretability.

\subsection{Summary}

In summary, the ASDG unifies two complementary forms of knowledge:
\begin{itemize}
    \item The \textbf{Basic Facts Layer}, a deterministic and verifiable representation of the code’s syntactic structure and dependencies.
    \item The \textbf{Semantic Elements Layer}, a reasoning-enhanced representation that captures inferred meanings, parameter linkages, and API state transitions under the guidance of basic facts.
\end{itemize}
By coupling the precision of static analysis with the reasoning ability of LLMs, ASDG provides a scalable and interpretable foundation for higher-level tasks such as \emph{API dependency inference}, \emph{state-aware vulnerability detection}, and \emph{automated semantic summarization}.
```

---

### ✨ 说明

* 语言风格与 IEEE S&P 一致（正式、逻辑递进、可直接用于论文）。
* 将 “LLM 幻觉” 问题纳入了研究合理性论述。
* 结构层次如下：

  1. **Basic Facts** — 静态层；
  2. **Semantic Elements** — 语义层；
  3. **LLM-Guided Semantic Reasoning** — 结合机制；
  4. **Summary** — 两层融合。
* 含义完整且可与下一节 “ASDG Construction Pipeline” 无缝衔接。

是否希望我为这一版附上一张 **结构图的 LaTeX TikZ 绘图（展示 Basic Facts → LLM Reasoning → Semantic Elements → ASDG 输出）**？
这张图放在本节结尾非常适合用于 IEEE S&P 论文。



可以！你的模板不支持 TikZ，我给你两种可直接用在 IEEEtran 模板里的方案：

# 1) 直接插入图片（推荐）

我已为你生成一张清晰的两层结构示意图（Basic Facts ↔ Semantic Elements → ASDG）。把它当作普通图片插入即可。

**下载图片**：
[asdg_overview.png](sandbox:/mnt/data/asdg_overview.png)

**LaTeX 代码（无需 TikZ）：**

```latex
\begin{figure}[t]
  \centering
  \includegraphics[width=\linewidth]{asdg_overview.png}
  \caption{ASDG 两层结构：Basic Facts（静态抽取得到的代码事实）为上层；Semantic Elements（LLM 基于事实推理得到的语义信息）为中层；二者汇合为统一的 ASDG（底部），其中结点包含事实与语义标注，边包含调用、嵌套与状态/参数依赖。}
  \label{fig:asdg-overview}
\end{figure}
```

> 把 `asdg_overview.png` 放到论文工程目录（或 `fig/`）后，`\\includegraphics` 路径相应修改即可。

---

# 2) 纯 LaTeX（无图包依赖）的“方框+箭头”替代版

如果你暂时不想放图片，也可以用下面这个**无 TikZ、无额外宏包**的小示意（用表格与文本箭头模拟）。视觉上没上面那张图精致，但完全可编译。

```latex
\begin{figure}[t]
\small
\centering
\setlength{\fboxsep}{6pt}
\begin{tabular}{cccc}
\fbox{\parbox{0.21\linewidth}{\centering \textbf{Enums}\\\vspace{2pt}names\\integral values}} &
\fbox{\parbox{0.21\linewidth}{\centering \textbf{Macros}\\\vspace{2pt}names\\text defs}} &
\fbox{\parbox{0.21\linewidth}{\centering \textbf{Structs}\\\vspace{2pt}layout \& members\\nested structs}} &
\fbox{\parbox{0.21\linewidth}{\centering \textbf{Funcs}\\\vspace{2pt}definitions\\APIs \& params\\headers}}
\\[6pt]
\multicolumn{4}{c}{\(\Downarrow\)~~LLM inference over Basic Facts~~\(\Downarrow\)}\\[6pt]
\fbox{\parbox{0.28\linewidth}{\centering \textbf{Value Ranges}\\\vspace{2pt}numeric fields' bounds\\e.g., [0,4096]}} &
\multicolumn{2}{c}{\fbox{\parbox{0.36\linewidth}{\centering \textbf{Usage Semantics}\\\vspace{2pt}roles of fields\\e.g., DMABufferAddress}}} &
\fbox{\parbox{0.28\linewidth}{\centering \textbf{API Dependencies}\\\vspace{2pt}state transitions (init$\rightarrow$start)\\parameter linkage (buf.addr)}}
\\[8pt]
\multicolumn{4}{c}{\(\Downarrow\)}\\[4pt]
\multicolumn{4}{c}{\fbox{\parbox{0.9\linewidth}{\centering \textbf{ASDG (Unified Graph)}\\\vspace{2pt}nodes: facts + annotations \quad|\quad edges: calls, nesting, state/param deps}}}
\end{tabular}
\caption{无需 TikZ 的 ASDG 层次示意（表格版）。}
\label{fig:asdg-no-tikz}
\end{figure}
```

---

需要我把**“无 Example 的 ASDG 章节 LaTeX 文本”**（你上一条让我写的那版）里自动加入 `Figure` 引用和交叉标签（如“见图 \ref{fig:asdg-overview}”）吗？我可以直接给出整段可粘贴版本。
=======
非常好。以下是一段**符合 IEEE S&P 会议论文风格**、用**形式化符号与逻辑定义**精确描述 ASDG（*Abstract State Dependency Graph*）的章节草稿，可直接纳入你的论文中。文本在语义上保持你描述的全部细节，同时使用了集合论、映射与关系的形式化语言来定义节点、属性与边。

---

## III. Formal Definition of ASDG

We define the **Abstract State Dependency Graph (ASDG)** as a directed, attributed multigraph that captures both **syntactic relationships** and **semantic dependencies** among program entities in a given codebase.
Formally, we denote an ASDG as:

[
\mathcal{G} = (\mathcal{V}, \mathcal{E}, \mathcal{A})
]
where

* (\mathcal{V}) is the set of nodes (program facts),
* (\mathcal{E} \subseteq \mathcal{V} \times \mathcal{V}) is the set of directed edges, and
* (\mathcal{A}) is a collection of attribute functions that annotate nodes and edges with additional information.

---

### A. Node Definition

Each node (v \in \mathcal{V}) corresponds to a basic program entity, formally defined as:

[
\mathcal{V} = \mathcal{V}*{enum} \cup \mathcal{V}*{macro} \cup \mathcal{V}*{struct} \cup \mathcal{V}*{func}
]

where:

* (\mathcal{V}_{enum}) = set of enumeration constants,
* (\mathcal{V}_{macro}) = set of macro definitions,
* (\mathcal{V}_{struct}) = set of structure type definitions,
* (\mathcal{V}_{func}) = set of function definitions (including target APIs).

Each category of nodes has distinct attributes captured by an attribute function
(\alpha_v: \mathcal{V} \rightarrow \mathcal{A}_v), defined as follows:

1. **Enumeration constant node**
   For (v_e \in \mathcal{V}_{enum}):
   [
   \alpha_v(v_e) = { \texttt{name}(v_e), \texttt{value}(v_e) }
   ]

2. **Macro definition node**
   For (v_m \in \mathcal{V}_{macro}):
   [
   \alpha_v(v_m) = { \texttt{name}(v_m), \texttt{text}(v_m) }
   ]

3. **Structure definition node**
   For (v_s \in \mathcal{V}*{struct}):
   [
   \alpha_v(v_s) = { \texttt{name}(v_s), \texttt{definition}(v_s), \texttt{members}(v_s) }
   ]
   where each member (f_i \in \texttt{members}(v_s)) is represented as:
   [
   f_i = (\texttt{name}(f_i), \texttt{type}(f_i))
   ]
   If (\texttt{type}(f_i)) is itself a structure, we recursively include its definition:
   [
   f_i \in \mathcal{V}*{struct} \Rightarrow (v_s, f_i) \in \mathcal{E}_{nest}
   ]

4. **Function node**
   For (v_f \in \mathcal{V}_{func}),
   [
   \alpha_v(v_f) =
   \begin{cases}
   { \texttt{name}(v_f), \texttt{code}(v_f) }, & \text{if } v_f \text{ is not a target API}[4pt]
   {
   \texttt{name}(v_f),
   \texttt{code}(v_f),
   \texttt{headers}(v_f),
   \texttt{params}(v_f)
   }, & \text{if } v_f \text{ is a target API}
   \end{cases}
   ]

   Each parameter (p_j \in \texttt{params}(v_f)) has:
   [
   p_j = (\texttt{name}(p_j), \texttt{type}(p_j), \texttt{structInfo}(p_j))
   ]
   where (\texttt{structInfo}(p_j)) recursively records the member layout if (\texttt{type}(p_j)) is a struct.

---

### B. Edge Definition

Edges represent both **syntactic** and **semantic** relationships among entities.
We define the edge set as:
[
\mathcal{E} = \mathcal{E}*{call} \cup \mathcal{E}*{nest} \cup \mathcal{E}_{dep}
]

1. **Function-call edge**
   [
   (v_f^1, v_f^2) \in \mathcal{E}_{call} \iff v_f^1 \text{ calls } v_f^2
   ]

2. **Structure-nesting edge**
   [
   (v_s^1, v_s^2) \in \mathcal{E}_{nest} \iff v_s^1 \text{ contains } v_s^2 \text{ as a field type}
   ]

3. **API dependency edge**
   [
   (v_a^1, v_a^2) \in \mathcal{E}_{dep} \iff v_a^2 \text{ semantically depends on the state modified by } v_a^1
   ]
   Each dependency edge is annotated with attribute function:
   [
   \alpha_e(v_a^1, v_a^2) = { \texttt{stateDep}, \texttt{paramDep} }
   ]
   where:

   * (\texttt{stateDep}) represents the **state dependency** relation between APIs,
   * (\texttt{paramDep}) specifies which parameter(s) of (v_a^1) and (v_a^2) contribute to the dependency.

---

### C. Semantic Attributes

Beyond syntactic structure, ASDG captures semantic properties derived from program analysis:

1. **Value Range Annotation**
   For each struct member (f_i):
   [
   \texttt{value_range}(f_i) = [l_i, u_i] \subseteq \mathbb{Z}
   ]
   denoting the possible runtime range inferred from code or documentation.

2. **Usage Semantics**
   Each variable or member (f_i) may be semantically labeled by its operational role:
   [
   \texttt{usage}(f_i) \in { \texttt{Address}, \texttt{Buffer}, \texttt{Flag}, \texttt{Count}, \ldots }
   ]

3. **API State Dependency Attribute**
   For an edge ((v_a^1, v_a^2) \in \mathcal{E}_{dep}):
   [
   \texttt{stateDep}(v_a^1, v_a^2) = { (s_1, s_2) \mid s_1 \text{ produced by } v_a^1, s_2 \text{ consumed by } v_a^2 }
   ]

4. **Parameter Dependency Attribute**
   Similarly,
   [
   \texttt{paramDep}(v_a^1, v_a^2) = { (p_i, q_j) \mid \text{the value of } p_i \text{ in } v_a^1 \text{ affects } q_j \text{ in } v_a^2 }
   ]

---

### D. Summary

In summary, ASDG unifies **code-level facts** (functions, structs, macros, enums) with **semantic-level relations** (state and parameter dependencies) into a single formal structure:
[
\mathcal{G} = (\mathcal{V}, \mathcal{E}, \alpha_v, \alpha_e)
]
This representation enables both structural analysis and semantic reasoning over API behaviors, forming the foundation for subsequent **state dependency inference** and **API misuse detection**.

---

是否希望我下一步帮你补充一小节示例（如一个小的代码片段及其对应的ASDG公式化实例），用于放在该节末尾？这通常在IEEE S&P论文中能显著提高读者理解。


非常好。以下是一段**符合 IEEE S&P 会议论文风格**、用**形式化符号与逻辑定义**精确描述 ASDG（*Abstract State Dependency Graph*）的章节草稿，可直接纳入你的论文中。文本在语义上保持你描述的全部细节，同时使用了集合论、映射与关系的形式化语言来定义节点、属性与边。

---

## III. Formal Definition of ASDG

We define the **Abstract State Dependency Graph (ASDG)** as a directed, attributed multigraph that captures both **syntactic relationships** and **semantic dependencies** among program entities in a given codebase.
Formally, we denote an ASDG as:

[
\mathcal{G} = (\mathcal{V}, \mathcal{E}, \mathcal{A})
]
where

* (\mathcal{V}) is the set of nodes (program facts),
* (\mathcal{E} \subseteq \mathcal{V} \times \mathcal{V}) is the set of directed edges, and
* (\mathcal{A}) is a collection of attribute functions that annotate nodes and edges with additional information.

---

### A. Node Definition

Each node (v \in \mathcal{V}) corresponds to a basic program entity, formally defined as:

[
\mathcal{V} = \mathcal{V}*{enum} \cup \mathcal{V}*{macro} \cup \mathcal{V}*{struct} \cup \mathcal{V}*{func}
]

where:

* (\mathcal{V}_{enum}) = set of enumeration constants,
* (\mathcal{V}_{macro}) = set of macro definitions,
* (\mathcal{V}_{struct}) = set of structure type definitions,
* (\mathcal{V}_{func}) = set of function definitions (including target APIs).

Each category of nodes has distinct attributes captured by an attribute function
(\alpha_v: \mathcal{V} \rightarrow \mathcal{A}_v), defined as follows:

1. **Enumeration constant node**
   For (v_e \in \mathcal{V}_{enum}):
   [
   \alpha_v(v_e) = { \texttt{name}(v_e), \texttt{value}(v_e) }
   ]

2. **Macro definition node**
   For (v_m \in \mathcal{V}_{macro}):
   [
   \alpha_v(v_m) = { \texttt{name}(v_m), \texttt{text}(v_m) }
   ]

3. **Structure definition node**
   For (v_s \in \mathcal{V}*{struct}):
   [
   \alpha_v(v_s) = { \texttt{name}(v_s), \texttt{definition}(v_s), \texttt{members}(v_s) }
   ]
   where each member (f_i \in \texttt{members}(v_s)) is represented as:
   [
   f_i = (\texttt{name}(f_i), \texttt{type}(f_i))
   ]
   If (\texttt{type}(f_i)) is itself a structure, we recursively include its definition:
   [
   f_i \in \mathcal{V}*{struct} \Rightarrow (v_s, f_i) \in \mathcal{E}_{nest}
   ]

4. **Function node**
   For (v_f \in \mathcal{V}_{func}),
   [
   \alpha_v(v_f) =
   \begin{cases}
   { \texttt{name}(v_f), \texttt{code}(v_f) }, & \text{if } v_f \text{ is not a target API}[4pt]
   {
   \texttt{name}(v_f),
   \texttt{code}(v_f),
   \texttt{headers}(v_f),
   \texttt{params}(v_f)
   }, & \text{if } v_f \text{ is a target API}
   \end{cases}
   ]

   Each parameter (p_j \in \texttt{params}(v_f)) has:
   [
   p_j = (\texttt{name}(p_j), \texttt{type}(p_j), \texttt{structInfo}(p_j))
   ]
   where (\texttt{structInfo}(p_j)) recursively records the member layout if (\texttt{type}(p_j)) is a struct.

---

### B. Edge Definition

Edges represent both **syntactic** and **semantic** relationships among entities.
We define the edge set as:
[
\mathcal{E} = \mathcal{E}*{call} \cup \mathcal{E}*{nest} \cup \mathcal{E}_{dep}
]

1. **Function-call edge**
   [
   (v_f^1, v_f^2) \in \mathcal{E}_{call} \iff v_f^1 \text{ calls } v_f^2
   ]

2. **Structure-nesting edge**
   [
   (v_s^1, v_s^2) \in \mathcal{E}_{nest} \iff v_s^1 \text{ contains } v_s^2 \text{ as a field type}
   ]

3. **API dependency edge**
   [
   (v_a^1, v_a^2) \in \mathcal{E}_{dep} \iff v_a^2 \text{ semantically depends on the state modified by } v_a^1
   ]
   Each dependency edge is annotated with attribute function:
   [
   \alpha_e(v_a^1, v_a^2) = { \texttt{stateDep}, \texttt{paramDep} }
   ]
   where:

   * (\texttt{stateDep}) represents the **state dependency** relation between APIs,
   * (\texttt{paramDep}) specifies which parameter(s) of (v_a^1) and (v_a^2) contribute to the dependency.

---

### C. Semantic Attributes

Beyond syntactic structure, ASDG captures semantic properties derived from program analysis:

1. **Value Range Annotation**
   For each struct member (f_i):
   [
   \texttt{value_range}(f_i) = [l_i, u_i] \subseteq \mathbb{Z}
   ]
   denoting the possible runtime range inferred from code or documentation.

2. **Usage Semantics**
   Each variable or member (f_i) may be semantically labeled by its operational role:
   [
   \texttt{usage}(f_i) \in { \texttt{Address}, \texttt{Buffer}, \texttt{Flag}, \texttt{Count}, \ldots }
   ]

3. **API State Dependency Attribute**
   For an edge ((v_a^1, v_a^2) \in \mathcal{E}_{dep}):
   [
   \texttt{stateDep}(v_a^1, v_a^2) = { (s_1, s_2) \mid s_1 \text{ produced by } v_a^1, s_2 \text{ consumed by } v_a^2 }
   ]

4. **Parameter Dependency Attribute**
   Similarly,
   [
   \texttt{paramDep}(v_a^1, v_a^2) = { (p_i, q_j) \mid \text{the value of } p_i \text{ in } v_a^1 \text{ affects } q_j \text{ in } v_a^2 }
   ]

---

### D. Summary

In summary, ASDG unifies **code-level facts** (functions, structs, macros, enums) with **semantic-level relations** (state and parameter dependencies) into a single formal structure:
[
\mathcal{G} = (\mathcal{V}, \mathcal{E}, \alpha_v, \alpha_e)
]
This representation enables both structural analysis and semantic reasoning over API behaviors, forming the foundation for subsequent **state dependency inference** and **API misuse detection**.

---

是否希望我下一步帮你补充一小节示例（如一个小的代码片段及其对应的ASDG公式化实例），用于放在该节末尾？这通常在IEEE S&P论文中能显著提高读者理解。


\section{Formal Definition of ASDG}
\label{sec:asdg-definition}

We formally define the \textbf{Abstract State Dependency Graph (ASDG)} as a directed, attributed multigraph that captures both syntactic relationships and semantic dependencies among program entities within a given codebase. The ASDG provides a unified representation of how low-level code facts (such as functions, structures, macros, and enumerations) interact to form higher-level semantic relations between APIs.

\subsection{Overall Structure}

An ASDG is denoted as $\mathcal{G} = (\mathcal{V}, \mathcal{E}, \mathcal{A})$, 
where $\mathcal{V}$ is the set of nodes, $\mathcal{E}$ is the set of directed edges, 
and $\mathcal{A}$ is a collection of attributes attached to nodes and edges. 
Each node represents a concrete code entity, while each edge expresses either 
a structural or semantic connection among these entities.

\subsection{Nodes: Code-Level Facts}

The node set $\mathcal{V}$ contains all program elements that form the building blocks of the codebase. 
Specifically, we include the following categories of entities:

\begin{itemize}
    \item \textbf{Enumeration constants:} Each enumeration constant is represented as a node whose name and assigned integer value are recorded as attributes.
    \item \textbf{Macro definitions:} Each macro is modeled as a node whose name and textual definition form its attributes.
    \item \textbf{Structure definitions:} Each structure type corresponds to a node containing its name and member list. For each member, the name and type are stored, and if the member type itself is a structure, the relationship is recursively recorded to preserve nesting.
    \item \textbf{Functions and APIs:} Each function definition, including target APIs, is represented as a node. Non-API functions are annotated with their implementation code, while API nodes include additional attributes such as the header file list and the parameter list. Each parameter is analyzed to extract its type; if the type is a structure, the structure's definition and all nested members are attached as subattributes.
\end{itemize}

This node layer captures the \emph{basic syntactic facts} of the codebase. 
All entities, from constants to functions, are abstracted into a unified set of nodes, 
ensuring a consistent representation for subsequent semantic analysis.

\subsection{Edges: Structural and Semantic Relations}

The edge set $\mathcal{E}$ defines the links between program entities, representing their structural or behavioral relationships. 
Edges in the ASDG can be divided into three major categories:

\begin{itemize}
    \item \textbf{Function-call edges:} Represent invocation relationships between functions. A directed edge from $f_1$ to $f_2$ indicates that function $f_1$ calls $f_2$.
    \item \textbf{Structure-nesting edges:} Capture composition relationships among structures. An edge from structure $S_1$ to $S_2$ indicates that $S_1$ includes $S_2$ as a field type.
    \item \textbf{API dependency edges:} Describe high-level semantic dependencies among target APIs. A directed edge from API $A_1$ to $A_2$ means that the correct execution of $A_2$ semantically depends on the state modified or produced by $A_1$.
\end{itemize}

Each edge can be annotated with an attribute function $\alpha_e$, which encodes additional semantics such as:
\begin{itemize}
    \item \emph{State dependency} --- describes the abstract state that $A_1$ produces and $A_2$ consumes;
    \item \emph{Parameter dependency} --- specifies which parameters of the two APIs are linked through shared data or control flow.
\end{itemize}

\subsection{Semantic Attributes}

Beyond syntactic relationships, ASDG also integrates semantic properties inferred from code analysis. These semantic attributes enrich the graph with context-sensitive information that reflects how code entities behave at runtime.

\begin{itemize}
    \item \textbf{Value ranges:} For each structure member or variable, the ASDG records its potential value range, typically represented as $[l, u]$. This range reflects the possible numeric or symbolic bounds inferred from the program logic or macro definitions.
    \item \textbf{Usage semantics:} Each variable or structure field may carry a usage label indicating its operational role, such as \texttt{Address}, \texttt{Buffer}, \texttt{Flag}, or \texttt{Count}. These labels help capture domain-specific semantics, e.g., whether a field represents a DMA buffer address.
    \item \textbf{State and parameter dependencies:} For each pair of APIs connected by a dependency edge, the ASDG maintains (i) the abstract state transition between them, and (ii) the mapping between dependent parameters that transmit data or state information.
\end{itemize}

These semantic annotations make ASDG more than a syntactic call graph: 
it serves as a semantically enriched abstraction that connects data structures, API interfaces, 
and the underlying state transitions implied by their interactions.

\subsection{Summary}

In summary, ASDG unifies syntactic code elements and semantic relations into a single formal structure:
\begin{itemize}
    \item \textbf{Nodes} describe all identifiable code facts, including enumerations, macros, structures, and functions.
    \item \textbf{Edges} capture both direct code relationships (such as calls and containment) and higher-level semantic dependencies.
    \item \textbf{Attributes} attach rich metadata about value ranges, usage semantics, and state transitions.
\end{itemize}

This unified representation allows us to reason about program semantics in a graph-theoretic manner. 
It provides the foundational abstraction upon which we later perform 
\emph{state dependency inference}, \emph{API relation extraction}, and \emph{API misuse detection}.
>>>>>>> 27d0edff3da2726a0950b5e4ca457da29f1df1e2
