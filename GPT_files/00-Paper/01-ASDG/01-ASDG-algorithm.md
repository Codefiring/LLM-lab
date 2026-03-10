下面给出两段符合 IEEE S&P 论文风格、基于 `algorithm` + `algorithmic` 宏包的 LaTeX 伪代码。第一段是“针对单个 ioctl 的 LLM+RAG 循环总结算法”，第二段是“面向任务的依赖图推理算法”。可直接粘贴进论文源码使用。

```latex
\begin{algorithm}[t]
\caption{LLM+RAG-Driven IOCTL Summarization (per ioctl)}
\label{alg:ioctl_summarization}
\begin{algorithmic}[1]
\REQUIRE Task description $\tau$; ioctl name $c$; RAG back-end with interfaces \texttt{enumerate}, \texttt{struct}, \texttt{macro}, \texttt{function}; max loop $T$.
\ENSURE Task-aware summary $S_c$ of ioctl $c$ (captures functionality and device-state updates).

\STATE $S_c \leftarrow \varnothing$ \COMMENT{current best summary}
\STATE $B \leftarrow \text{QueryRAG}(\texttt{function}, c)$ \COMMENT{fetch ioctl implementation}
\STATE $k \leftarrow 0$

\WHILE{$k < T$}
  \STATE $S^{(raw)} \leftarrow \textsc{IoctlSummarizerLLM}(B, \tau)$
  \STATE $(\textit{pass}, R)$ $\leftarrow$ \textsc{EvaluatorLLM}$(S^{(raw)}, \tau)$
  \COMMENT{Check: (i) code truly understood; (ii) task coverage; (iii) state-change extraction}
  \IF{$\textit{pass} = \textbf{true}$}
      \STATE $S_c \leftarrow \textsc{PostProcess}(S^{(raw)})$
      \STATE \textbf{break}
  \ELSE
      \COMMENT{$R$ encodes missing evidence needs over enums/structs/macros/functions}
      \STATE $Q \leftarrow \textsc{InferMissingQueriesLLM}(R, c, \tau)$
      \STATE $B_{\!\Delta} \leftarrow \varnothing$
      \IF{$Q.\texttt{enums} \neq \varnothing$}
          \STATE $B_{\!\Delta} \leftarrow B_{\!\Delta} \cup \text{QueryRAG}(\texttt{enumerate}, Q.\texttt{enums})$
      \ENDIF
      \IF{$Q.\texttt{structs} \neq \varnothing$}
          \STATE $B_{\!\Delta} \leftarrow B_{\!\Delta} \cup \text{QueryRAG}(\texttt{struct}, Q.\texttt{structs})$
      \ENDIF
      \IF{$Q.\texttt{macros} \neq \varnothing$}
          \STATE $B_{\!\Delta} \leftarrow B_{\!\Delta} \cup \text{QueryRAG}(\texttt{macro}, Q.\texttt{macros})$
      \ENDIF
      \IF{$Q.\texttt{functions} \neq \varnothing$}
          \STATE $B_{\!\Delta} \leftarrow B_{\!\Delta} \cup \text{QueryRAG}(\texttt{function}, Q.\texttt{functions})$
      \ENDIF
      \STATE $S_{\!\Delta} \leftarrow \textsc{CodeSummarizerLLM}(B_{\!\Delta}, \tau)$
      \STATE $B \leftarrow \textsc{MergeCode}(B, B_{\!\Delta})$
      \STATE $S_c \leftarrow \textsc{MergeSummary}(S_c, S^{(raw)}, S_{\!\Delta})$
      \STATE $k \leftarrow k + 1$
      \STATE \textbf{continue}
  \ENDIF
\ENDWHILE

\IF{$S_c = \varnothing$}
  \STATE $S_c \leftarrow \textsc{DegradeGracefully}(c, \tau)$
\ENDIF

\STATE \textbf{return} $S_c$
\end{algorithmic}
\end{algorithm}
```

```latex
\begin{algorithm}[t]
\caption{Task-Specific IOCTL Dependency Graph Inference}
\label{alg:graph_inference}
\begin{algorithmic}[1]
\REQUIRE Task description $\tau$; set of ioctl names $\mathcal{C}$; summarization budget $L$; dependence schema $\Sigma$ (e.g., input-dependence, state-dependence).
\ENSURE Task-specific graph $G_\tau = (\mathcal{V}, \mathcal{E})$ over ioctls.

\STATE $\mathcal{V} \leftarrow \varnothing$, $\mathcal{E} \leftarrow \varnothing$
\STATE $S \leftarrow \varnothing$ \COMMENT{compressed summaries keyed by ioctl}
\FORALL{$c \in \mathcal{C}$}
  \STATE $S_c \leftarrow \text{Algorithm~\ref{alg:ioctl_summarization}}(c, \tau)$
  \STATE $S_c^{(short)} \leftarrow \textsc{CompressLLM}(S_c, L)$
  \STATE $S[c] \leftarrow S_c^{(short)}$,\quad $\mathcal{V} \leftarrow \mathcal{V} \cup \{c\}$
\ENDFOR

\STATE $S_{\!\cup} \leftarrow \textsc{Concatenate}(S[c]\;|\;c \in \mathcal{C})$
\STATE $\mathcal{E} \leftarrow \textsc{InferEdgesLLM}(S_{\!\cup}, \tau, \Sigma)$
\COMMENT{Produce typed edges: \texttt{input-dep}, \texttt{state-dep}, \texttt{ordering}, etc.}

\STATE $\mathcal{E} \leftarrow \textsc{SanityCheckLLM}(\mathcal{E}, S, \tau)$
\COMMENT{Detect contradictions; request minimal evidence if needed}

\STATE $\mathcal{E} \leftarrow \textsc{RefineWithFacts}( \mathcal{E}, \text{BasicFactsFromRAG}() )$
\COMMENT{Use static facts as hard constraints to reduce hallucinations}

\STATE $G_\tau \leftarrow (\mathcal{V}, \mathcal{E})$
\STATE \textbf{return} $G_\tau$
\end{algorithmic}
\end{algorithm}
```

### 备注（可选，写入正文或附注）

* \textbf{IoctlSummarizer/Evaluator/MissingCode/CodeSummarizer} 为模块化 LLM 调用；\textbf{QueryRAG} 通过 \texttt{enumerate}/\texttt{struct}/\texttt{macro}/\texttt{function} 接口检索证据。
* \textbf{RefineWithFacts} 将静态 \emph{Basic Facts} 作为硬约束，降低 LLM 在代码任务上的幻觉，并引导更高效的推理，从而得到语义关系（\emph{Semantic Elements}）与最终图输出。


\begin{algorithm}[t]
\caption{End-to-End Task-Specific IOCTL Graph Construction via LLM+RAG}
\label{alg:e2e_ioctl_graph}
\begin{algorithmic}[1]
\REQUIRE Task description $\tau$; ioctl set $\mathcal{C}$; RAG back-end with interfaces \texttt{enumerate}, \texttt{struct}, \texttt{macro}, \texttt{function}; max inner loops $T$; summary length budget $L$; dependence schema $\Sigma$ (e.g., input-dep, state-dep).
\ENSURE Task-specific dependency graph $G_\tau=(\mathcal{V},\mathcal{E})$ over ioctls.

\STATE $\mathcal{V}\!\leftarrow\!\varnothing$, $\mathcal{E}\!\leftarrow\!\varnothing$, $S\!\leftarrow\!\varnothing$ \COMMENT{nodes, edges, per-ioctl summaries}
\FORALL{$c \in \mathcal{C}$} \label{line:for-each-ioctl}
  \STATE $B \leftarrow \text{QueryRAG}(\texttt{function}, c)$ \COMMENT{ioctl implementation as initial evidence}
  \STATE $k \leftarrow 0$, $S_c \leftarrow \varnothing$
  \WHILE{$k < T$} \label{line:inner-loop}
    \STATE $S^{(raw)} \leftarrow \textsc{IoctlSummarizerLLM}(B, \tau)$
    \STATE $(\textit{pass}, R) \leftarrow \textsc{EvaluatorLLM}(S^{(raw)}, \tau)$
    \IF{$\textit{pass}=\textbf{true}$}
      \STATE $S_c \leftarrow \textsc{PostProcess}(S^{(raw)})$; \textbf{break}
    \ENDIF
    \STATE $Q \leftarrow \textsc{InferMissingQueriesLLM}(R, c, \tau)$ \COMMENT{what enums/structs/macros/functions are missing}
    \STATE $B_{\!\Delta}\!\leftarrow\!\varnothing$
    \IF{$Q.\texttt{enums}\!\neq\!\varnothing$} \STATE $B_{\!\Delta}\!\cup=\!\text{QueryRAG}(\texttt{enumerate}, Q.\texttt{enums})$ \ENDIF
    \IF{$Q.\texttt{structs}\!\neq\!\varnothing$} \STATE $B_{\!\Delta}\!\cup=\!\text{QueryRAG}(\texttt{struct}, Q.\texttt{structs})$ \ENDIF
    \IF{$Q.\texttt{macros}\!\neq\!\varnothing$} \STATE $B_{\!\Delta}\!\cup=\!\text{QueryRAG}(\texttt{macro}, Q.\texttt{macros})$ \ENDIF
    \IF{$Q.\texttt{functions}\!\neq\!\varnothing$} \STATE $B_{\!\Delta}\!\cup=\!\text{QueryRAG}(\texttt{function}, Q.\texttt{functions})$ \ENDIF
    \STATE $S_{\!\Delta} \leftarrow \textsc{CodeSummarizerLLM}(B_{\!\Delta}, \tau)$
    \STATE $B \leftarrow \textsc{MergeCode}(B, B_{\!\Delta})$;\quad $S_c \leftarrow \textsc{MergeSummary}(S_c, S^{(raw)}, S_{\!\Delta})$
    \STATE $k \leftarrow k+1$
  \ENDWHILE
  \IF{$S_c=\varnothing$} \STATE $S_c \leftarrow \textsc{DegradeGracefully}(c,\tau)$ \ENDIF
  \STATE $S_c^{(short)} \leftarrow \textsc{CompressLLM}(S_c, L)$
  \STATE $S[c] \leftarrow S_c^{(short)}$;\quad $\mathcal{V} \leftarrow \mathcal{V} \cup \{c\}$
\ENDFOR

\STATE $S_{\!\cup} \leftarrow \textsc{Concatenate}(S[c]\;|\;c\in\mathcal{C})$ \COMMENT{global context built from task-aware summaries}
\STATE $\mathcal{E} \leftarrow \textsc{InferEdgesLLM}(S_{\!\cup}, \tau, \Sigma)$
\COMMENT{produce typed edges: \texttt{input-dep}, \texttt{state-dep}, \texttt{ordering}, etc.}
\STATE $\mathcal{E} \leftarrow \textsc{SanityCheckLLM}(\mathcal{E}, S, \tau)$ \COMMENT{detect contradictions/missing supports}
\STATE $\mathcal{E} \leftarrow \textsc{RefineWithFacts}\!\big(\mathcal{E}, \text{BasicFactsFromRAG}()\big)$
\COMMENT{treat Basic Facts as hard constraints to reduce hallucinations}
\STATE $G_\tau \leftarrow (\mathcal{V}, \mathcal{E})$
\STATE \textbf{return} $G_\tau$
\end{algorithmic}
\end{algorithm}


\begin{algorithm}[t]
\caption{RAG-Guided LLM for IOCTL Task Graph Inference}
\label{alg:ioctl_graph}
\begin{algorithmic}[1]
\REQUIRE Task description $T$; set of IOCTL names $\mathcal{I}$; RAG back-end with interfaces \textsc{Enumerate}, \textsc{Struct}, \textsc{Macro}, \textsc{Function}; modules \textsc{IoctlSummarizer}, \textsc{Evaluator}, \textsc{MissingCode}; maximum refinement rounds $K$
\ENSURE Dependency graph $G=(V,E_{\text{param}},E_{\text{state}})$ over $\mathcal{I}$ for task $T$
\STATE $V \gets \mathcal{I}$; $S \gets \emptyset$ \COMMENT{initialize vertices and per-IOCTL summaries}
\vspace{3pt}
\STATE \textbf{Phase I: RAG-grounded per-IOCTL semantic summarization}
\FORALL{$i \in \mathcal{I}$}
  \STATE $B_i \gets$ \textsc{Enumerate}$(i) \cup$ \textsc{Struct}$(i) \cup$ \textsc{Macro}$(i) \cup$ \textsc{Function}$(i)$ \COMMENT{collect basic facts}
  \STATE $s_i^{(0)} \gets$ \textsc{IoctlSummarizer}$(i, T, B_i)$ \COMMENT{LLM: initial task-focused summary}
  \STATE $t \gets 0$
  \WHILE{$t < K$}
    \STATE $ok,\,R \gets$ \textsc{Evaluator}$(s_i^{(t)}, T, B_i)$
    \IF{$ok$}
      \STATE \textbf{break}
    \ELSE
      \STATE $M \gets$ \textsc{MissingCode}$(s_i^{(t)}, T)$ \COMMENT{LLM: identify missing code evidence}
      \STATE $B_i \gets B_i \cup$ \textsc{QueryRAG}$(M)$ \COMMENT{fetch concrete code via RAG: enums/structs/macros/functions}
      \STATE $s_i^{(t+1)} \gets$ \textsc{IoctlSummarizer}$(i, T, B_i, R)$ \COMMENT{refine using newly grounded facts}
      \STATE $t \gets t+1$
    \ENDIF
  \ENDWHILE
  \STATE $S \gets S \cup \{\,\textsc{Finalize}(i, s_i^{(t)}, B_i)\,\}$ \COMMENT{freeze hallucination-checked summary}
\ENDFOR
\vspace{3pt}
\STATE \textbf{Phase II: Graph reasoning over all IOCTLs for task $T$}
\STATE $S' \gets \{\,\textsc{Compress}(s_i) \mid s_i \in S\,\}$ \COMMENT{length-normalized, salient facts only}
\STATE $C \gets \textsc{Merge}(S')$ \COMMENT{cross-IOCTL evidence pool}
\STATE $\widehat{E}_{\text{param}}, \widehat{E}_{\text{state}} \gets$ \textsc{LLM-Reason}$(C, T)$
\STATE $\widehat{E}_{\text{param}} \gets \textsc{Ground\&Filter}(\widehat{E}_{\text{param}}, S)$ \COMMENT{keep only edges supported by basic facts}
\STATE $\widehat{E}_{\text{state}} \gets \textsc{Ground\&Filter}(\widehat{E}_{\text{state}}, S)$
\STATE $E_{\text{param}}, E_{\text{state}} \gets \textsc{ResolveConflicts}(\widehat{E}_{\text{param}}, \widehat{E}_{\text{state}})$ \COMMENT{prefer fact-backed, conservative ties}
\STATE \textbf{return} $G=(V,E_{\text{param}},E_{\text{state}})$
\vspace{4pt}
\STATE \hrulefill
\STATE \textbf{Subroutine semantics (sketch).}
\STATE \textsc{IoctlSummarizer}$(i,T,B)$: Produces a task-centric summary including (a) input/parameter roles and preconditions; (b) read/write effects on device state; (c) error paths; (d) observable outputs. Uses $B$ (basic facts) to anchor claims.
\STATE \textsc{Evaluator}$(s,T,B)$: Verifies that the summary is faithful to code; returns $(ok,R)$ where $R$ lists missing evidence (e.g., specific enums, struct fields, macro guards, callee definitions).
\STATE \textsc{MissingCode}$(s,T)$: Extracts concrete code artifacts required to resolve gaps; expressed as RAG queries.
\STATE \textsc{QueryRAG}$(M)$: Executes \textsc{Enumerate}/\textsc{Struct}/\textsc{Macro}/\textsc{Function} queries to retrieve code snippets and definitions.
\STATE \textsc{Compress}$(s)$: Retains only grounded facts and minimal semantics for graph reasoning.
\STATE \textsc{LLM-Reason}$(C,T)$: Infers candidate edges:
\begin{itemize}
  \item $E_{\text{param}}$: input/return/data-flow dependencies between IOCTLs for $T$ (e.g., handle/descriptor/identifier propagation).
  \item $E_{\text{state}}$: state-precondition/effect dependencies (enable/disable, create/use/destroy, init$\rightarrow$use$\rightarrow$finalize).
\end{itemize}
\STATE \textsc{Ground\&Filter}: Discards edges lacking support in $S$'s basic-fact citations; downgrades speculative links.
\STATE \textsc{ResolveConflicts}: Reconciles contradictory edges, favoring conservative, code-backed relations; enforces acyclicity where required by $T$.
\end{algorithmic}
\end{algorithm}

\begin{algorithm}[t]
\caption{RAG-Guided Inference of Task-Specific Relations Among \texttt{ioctl}s}
\label{alg:ioctl-graph}
\begin{algorithmic}[1]
\REQUIRE Task description $T$; set of ioctl names $\mathcal{I}$; RAG backend interfaces $\mathsf{ENUM}$, $\mathsf{STRUCT}$, $\mathsf{MACRO}$, $\mathsf{FUNC}$; LLM modules $\mathsf{Summarizer}$, $\mathsf{Evaluator}$, $\mathsf{MissingCode}$, $\mathsf{Compressor}$, $\mathsf{GraphInfer}$; maximum refinement rounds $K$
\ENSURE Concise per-ioctl summaries $\{S_i^{\text{final}}\}_{i\in\mathcal{I}}$ and a task-specific relation graph $G=(V,E)$

\STATE $V \leftarrow \mathcal{I}$; $\mathcal{S} \leftarrow \emptyset$ \COMMENT{Graph nodes are ioctls; collect summaries in $\mathcal{S}$}
\FORALL{$i \in \mathcal{I}$}
    \STATE $C_i \leftarrow \mathsf{FUNC}.\mathsf{query}(i)$ \COMMENT{Primary code for ioctl $i$}
    \STATE $S_i \leftarrow \mathsf{Summarizer}(i, T, C_i)$ \COMMENT{Initial, task-focused code summary}
    \STATE $r \leftarrow 0$
    \REPEAT
        \STATE $(\textit{sufficient}, R_i) \leftarrow \mathsf{Evaluator}(S_i, T)$
        \IF{$\textit{sufficient} = \textbf{true}$}
            \STATE \textbf{break}
        \ELSE
            \STATE $\Delta_i \leftarrow \mathsf{MissingCode}(S_i, R_i, T)$
            \STATE $\mathcal{B}_i \leftarrow \emptyset$ \COMMENT{Bag of basic facts and code to fill gaps}
            \IF{$\Delta_i$ requires enumerations}
                \STATE $\mathcal{B}_i \leftarrow \mathcal{B}_i \cup \mathsf{ENUM}.\mathsf{fetch}(\Delta_i)$
            \ENDIF
            \IF{$\Delta_i$ requires macros}
                \STATE $\mathcal{B}_i \leftarrow \mathcal{B}_i \cup \mathsf{MACRO}.\mathsf{fetch}(\Delta_i)$
            \ENDIF
            \IF{$\Delta_i$ requires structs}
                \STATE $\mathcal{B}_i \leftarrow \mathcal{B}_i \cup \mathsf{STRUCT}.\mathsf{fetch}(\Delta_i)$
            \ENDIF
            \IF{$\Delta_i$ requires functions}
                \STATE $\mathcal{B}_i \leftarrow \mathcal{B}_i \cup \mathsf{FUNC}.\mathsf{fetch}(\Delta_i)$
            \ENDIF
            \STATE $S^{\text{aux}}_i \leftarrow \mathsf{Summarizer}(\mathcal{B}_i, T)$ \COMMENT{Summarize only the fetched missing pieces}
            \STATE $S_i \leftarrow \mathsf{Summarizer}(i, T, C_i, S^{\text{aux}}_i)$ \COMMENT{Re-summarize ioctl with gap-filling context}
            \STATE $r \leftarrow r + 1$
        \ENDIF
    \UNTIL{$\textit{sufficient}=\textbf{true}$ \OR $r \ge K$}
    \STATE $S_i^{\text{final}} \leftarrow \mathsf{Compressor}(S_i)$ \COMMENT{Length-controlled, task-focused summary}
    \STATE $\mathcal{S} \leftarrow \mathcal{S} \cup \{S_i^{\text{final}}\}$
\ENDFOR

\STATE $M \leftarrow \textsc{Merge}(\mathcal{S})$ \COMMENT{Global view over all ioctls under task $T$}
\STATE $G \leftarrow \mathsf{GraphInfer}(M, T)$
\STATE \textbf{return} $\{S_i^{\text{final}}\}_{i\in\mathcal{I}},\; G$

\vspace{0.25em}
\STATE \textbf{Notes on semantics and grounding:}
\STATE \hspace{0.6em}(a) \emph{Basic facts} (from $\mathsf{ENUM}$/$\mathsf{STRUCT}$/$\mathsf{MACRO}$/$\mathsf{FUNC}$) are treated as faithful, static signals.
\STATE \hspace{0.6em}(b) LLM reasoning is constrained to operate \emph{under} these facts to reduce hallucinations and to guide efficient inference.
\STATE \hspace{0.6em}(c) $\mathsf{GraphInfer}$ outputs labeled edges $E$ such as \textit{input-dependency} and \textit{state-dependency}, optionally with confidence scores.
\end{algorithmic}
\end{algorithm}
