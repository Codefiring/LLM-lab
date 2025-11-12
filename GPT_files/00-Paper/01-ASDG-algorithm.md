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
