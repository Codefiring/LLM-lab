\section{Formal Definition of ASDG}
\label{sec:asdg-definition}

We define the \textbf{Abstract State Dependency Graph (ASDG)} as a directed, attributed multigraph that captures both syntactic relationships and semantic dependencies among program entities in a given codebase. Formally, we denote an ASDG as:
\begin{equation}
\mathcal{G} = (\mathcal{V}, \mathcal{E}, \mathcal{A})
\end{equation}
where
$\mathcal{V}$ is the set of nodes (program facts),
$\mathcal{E} \subseteq \mathcal{V} \times \mathcal{V}$ is the set of directed edges, and
$\mathcal{A}$ is the collection of attribute functions that annotate nodes and edges.

\subsection{Node Definition}
Each node $v \in \mathcal{V}$ corresponds to a basic program entity:
\begin{equation}
\mathcal{V} = \mathcal{V}_{enum} \cup \mathcal{V}_{macro} \cup \mathcal{V}_{struct} \cup \mathcal{V}_{func}
\end{equation}
where $\mathcal{V}_{enum}$, $\mathcal{V}_{macro}$, $\mathcal{V}_{struct}$, and $\mathcal{V}_{func}$ denote sets of enumeration constants, macros, structure definitions, and function definitions (including target APIs), respectively.

Each category of nodes is associated with an attribute function $\alpha_v: \mathcal{V} \rightarrow \mathcal{A}_v$ defined as follows:

\paragraph*{Enumeration constant node}
\begin{equation}
\alpha_v(v_e) = \{ \texttt{name}(v_e), \texttt{value}(v_e) \}, \quad v_e \in \mathcal{V}_{enum}
\end{equation}

\paragraph*{Macro definition node}
\begin{equation}
\alpha_v(v_m) = \{ \texttt{name}(v_m), \texttt{text}(v_m) \}, \quad v_m \in \mathcal{V}_{macro}
\end{equation}

\paragraph*{Structure definition node}
\begin{equation}
\alpha_v(v_s) = \{ \texttt{name}(v_s), \texttt{definition}(v_s), \texttt{members}(v_s) \}, \quad v_s \in \mathcal{V}_{struct}
\end{equation}
Each member $f_i \in \texttt{members}(v_s)$ is represented as $f_i = (\texttt{name}(f_i), \texttt{type}(f_i))$.
If $\texttt{type}(f_i)$ is itself a structure, a nesting edge is added:
\begin{equation}
(v_s, f_i) \in \mathcal{E}_{nest}
\end{equation}

\paragraph*{Function node}
\begin{equation}
\alpha_v(v_f) =
\begin{cases}
\{ \texttt{name}, \texttt{code} \}, & v_f \text{ is not a target API}\\[3pt]
\{ \texttt{name}, \texttt{code}, \texttt{headers}, \texttt{params} \}, & v_f \text{ is a target API}
\end{cases}
\end{equation}
Each parameter $p_j$ has attributes
$p_j = (\texttt{name}(p_j), \texttt{type}(p_j), \texttt{structInfo}(p_j))$,
where $\texttt{structInfo}(p_j)$ recursively records structure members.

\subsection{Edge Definition}
Edges capture both syntactic and semantic relationships:
\begin{equation}
\mathcal{E} = \mathcal{E}_{call} \cup \mathcal{E}_{nest} \cup \mathcal{E}_{dep}
\end{equation}

\paragraph*{Function-call edge}
\begin{equation}
(v_f^1, v_f^2) \in \mathcal{E}_{call} \iff v_f^1 \text{ calls } v_f^2
\end{equation}

\paragraph*{Structure-nesting edge}
\begin{equation}
(v_s^1, v_s^2) \in \mathcal{E}_{nest} \iff v_s^1 \text{ contains } v_s^2 \text{ as a field type}
\end{equation}

\paragraph*{API dependency edge}
\begin{equation}
(v_a^1, v_a^2) \in \mathcal{E}_{dep} \iff v_a^2 \text{ semantically depends on the state modified by } v_a^1
\end{equation}
Each dependency edge has attributes:
\begin{equation}
\alpha_e(v_a^1, v_a^2) = \{ \texttt{stateDep}, \texttt{paramDep} \}
\end{equation}

\subsection{Semantic Attributes}
\paragraph*{Value range annotation}
\begin{equation}
\texttt{value\_range}(f_i) = [l_i, u_i] \subseteq \mathbb{Z}
\end{equation}

\paragraph*{Usage semantics}
\begin{equation}
\texttt{usage}(f_i) \in \{ \texttt{Address}, \texttt{Buffer}, \texttt{Flag}, \texttt{Count}, \ldots \}
\end{equation}

\paragraph*{State and parameter dependencies}
\begin{align}
\texttt{stateDep}(v_a^1, v_a^2) &= \{ (s_1, s_2) \mid s_1 \text{ produced by } v_a^1, s_2 \text{ consumed by } v_a^2 \} \\
\texttt{paramDep}(v_a^1, v_a^2) &= \{ (p_i, q_j) \mid p_i \text{ in } v_a^1 \text{ affects } q_j \text{ in } v_a^2 \}
\end{align}

\subsection{Summary}
ASDG unifies syntactic code facts and semantic dependencies into a single structure:
\begin{equation}
\mathcal{G} = (\mathcal{V}, \mathcal{E}, \alpha_v, \alpha_e)
\end{equation}
enabling both structural analysis and semantic reasoning over API behaviors.


To infer inter-\texttt{ioctl} dependencies with minimal hallucination, we design a \textbf{RAG-guided iterative reasoning framework}. Each \texttt{ioctl} is treated as a node whose behavioral semantics are derived through the LLM-based summarizer. For a given reasoning task (e.g., state transition or parameter dependency), the framework first queries the RAG backend to retrieve the \texttt{ioctl}'s implementation code and prompts the LLM to summarize its task-relevant functionality. The initial summary is then evaluated by a verification module to determine whether the reasoning is well-grounded and sufficiently captures the task semantics. If not, the framework automatically identifies the missing contextual code elements—such as enumerations, macros, structure definitions, or helper functions—and retrieves them via the RAG interfaces. These retrieved \emph{basic facts} are summarized and reintegrated into the reasoning context, forming an iterative loop of \emph{summarization–evaluation–refinement}.

This design constrains the LLM’s reasoning under verifiable static facts, effectively reducing hallucinations and ensuring that each semantic inference remains consistent with the actual code logic. Once all \texttt{ioctl} nodes have been refined into concise, fact-grounded summaries, the framework performs global reasoning over the merged summaries to infer their state and input dependencies. The resulting \textbf{API State Dependency Graph (ASDG)} captures accurate inter-\texttt{ioctl} relationships, serving as the foundation for downstream analyses such as state-aware fuzzing, where it enables exploration along only valid state transitions and meaningful parameter interactions, thus improving both coverage and bug discovery efficiency.