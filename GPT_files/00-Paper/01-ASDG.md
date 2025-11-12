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
