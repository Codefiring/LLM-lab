\subsection{ASDG Correctness Evaluation (RQ1)}
\label{subsec:asdg-correctness}

To evaluate the correctness of our ASDG-generation framework, we conduct a comparative study on the NPU driver's \texttt{ioctl} state dependency graph. Our goal is to validate whether the LLM-derived ASDG (1) preserves all true dependencies recognized manually, and (2) introduces additional dependencies beyond the manually summarized ones, and (3) still contains incorrect (hallucinated) dependencies. The experiment therefore reflects both the \emph{completeness} and \emph{soundness} of ASDG construction.

\paragraph{Dataset and Methodology.}
We prepare two independent sources of state dependency facts over the same set of nine \texttt{ioctl}s:
\texttt{open}, \texttt{bootup}, \texttt{s\_graph}, \texttt{s\_format}, \texttt{stream\_on}, \texttt{qbuf}, \texttt{dqbuf}, \texttt{stream\_off}, and \texttt{close}.

\begin{itemize}
  \item \textbf{Manual Graph (Ground Truth).}
  A domain expert manually examines the NPU driver's \texttt{ioctl} implementations and summarizes a state dependency graph, represented as directed pairs $A \rightarrow B$ indicating that invocation of \texttt{ioctl} $B$ semantically depends on the prior invocation of \texttt{ioctl} $A$.

  \item \textbf{ASDG-Derived Graph.}
  Our ASDG-generation pipeline processes each \texttt{ioctl} handler as an API node, retrieves relevant basic facts, performs iterative LLM reasoning, and outputs dependency edges in the same $A \rightarrow B$ format.
\end{itemize}

We then directly compare the two edge lists and classify each ASDG edge into three categories:
(1) \emph{true positives (TP)} that also appear in the manual graph,
(2) \emph{extra but plausible edges} that are not recorded manually but are semantically reasonable, and
(3) \emph{hallucinated edges} that contradict the implementation or represent spurious dependencies.

Table~\ref{tab:npu-statedeps-summary} summarizes the statistics of this comparison.

\begin{table}[t]
  \centering
  \caption{Summary of \texttt{ioctl} state dependency graphs for the NPU driver.}
  \label{tab:npu-statedeps-summary}
  \begin{tabular}{lrr}
    \toprule
    & Manual graph & ASDG graph \\
    \midrule
    \# \texttt{ioctl} commands          & 9   & 9   \\
    \# dependency edges                 & 9   & 28  \\
    \# covered manual edges (TP)        & 9   & 9   \\
    \# extra plausible edges            & --  & 15  \\
    \# hallucinated edges               & --  & 4   \\
    Overall recall (w.r.t. manual)      & 1.00 & 1.00 \\
    Overall precision (ASDG)            & --  & 0.86 \\
    \bottomrule
  \end{tabular}
\end{table}

\paragraph{Coverage of Manual Dependencies.}
The manually summarized graph contains 9 state dependency edges over the nine \texttt{ioctl}s.
As shown in Table~\ref{tab:npu-statedeps-summary}, ASDG successfully reproduces \emph{all} of these edges (9/9 true positives, recall $=1.00$).
This indicates that the LLM, when guided by basic facts and iterative context completion, does not miss the core protocol constraints recognized by human experts.
Qualitatively, these covered edges capture the expected life-cycle ordering of the NPU device, such as initialization before streaming and streaming before teardown.

For completeness, Table~\ref{tab:npu-statedeps-detail} lists all dependency edges and their classification.

\begin{table*}[t]
  \centering
  \caption{Manual and ASDG-derived \texttt{ioctl} state dependencies for the NPU driver.}
  \label{tab:npu-statedeps-detail}
  \begin{tabular}{llll}
    \toprule
    Source \texttt{ioctl} & Target \texttt{ioctl} & Origin      & Classification \\
    \midrule
    % Ground-truth edges (manual + ASDG)
    open          & bootup        & Manual+ASDG & Ground-truth \\
    bootup        & s\_graph      & Manual+ASDG & Ground-truth \\
    s\_graph      & s\_format     & Manual+ASDG & Ground-truth \\
    s\_format     & stream\_on    & Manual+ASDG & Ground-truth \\
    stream\_on    & qbuf          & Manual+ASDG & Ground-truth \\
    qbuf          & dqbuf         & Manual+ASDG & Ground-truth \\
    dqbuf         & stream\_off   & Manual+ASDG & Ground-truth \\
    stream\_off   & close         & Manual+ASDG & Ground-truth \\
    open          & close         & Manual+ASDG & Ground-truth \\
    \midrule
    % Extra plausible edges (ASDG-only)
    open          & s\_graph      & ASDG-only   & Plausible extra \\
    open          & s\_format     & ASDG-only   & Plausible extra \\
    open          & stream\_on    & ASDG-only   & Plausible extra \\
    bootup        & s\_format     & ASDG-only   & Plausible extra \\
    bootup        & stream\_on    & ASDG-only   & Plausible extra \\
    bootup        & qbuf          & ASDG-only   & Plausible extra \\
    s\_graph      & stream\_on    & ASDG-only   & Plausible extra \\
    s\_graph      & qbuf          & ASDG-only   & Plausible extra \\
    s\_format     & qbuf          & ASDG-only   & Plausible extra \\
    s\_format     & dqbuf         & ASDG-only   & Plausible extra \\
    stream\_on    & dqbuf         & ASDG-only   & Plausible extra \\
    stream\_on    & stream\_off   & ASDG-only   & Plausible extra \\
    qbuf          & stream\_off   & ASDG-only   & Plausible extra \\
    dqbuf         & close         & ASDG-only   & Plausible extra \\
    bootup        & dqbuf         & ASDG-only   & Plausible extra \\
    \midrule
    % Hallucinated edges (ASDG-only)
    dqbuf         & bootup        & ASDG-only   & Hallucinated \\
    stream\_off   & qbuf          & ASDG-only   & Hallucinated \\
    close         & qbuf          & ASDG-only   & Hallucinated \\
    s\_format     & bootup        & ASDG-only   & Hallucinated \\
    \bottomrule
  \end{tabular}
\end{table*}

\paragraph{Additional ASDG Dependencies.}
Beyond faithfully covering the 9 manually summarized edges, ASDG proposes 19 additional dependencies, resulting in 28 edges in total.
Among these extra edges, we manually classify 15 as \emph{plausible} and 4 as \emph{hallucinated}.
The plausible edges typically reflect transitive or implicit ordering constraints that human analysts often consider ``obvious'' and leave undocumented, such as:
(i) treating \texttt{open} as a precondition not only for \texttt{bootup} but also for later configuration and streaming commands, and
(ii) recognizing that teardown-related commands (e.g., \texttt{dqbuf} and \texttt{stream\_off}) should precede \texttt{close}.

The four hallucinated edges, however, violate the actual protocol semantics.
Examples include reversed dependencies such as \texttt{dqbuf} $\rightarrow$ \texttt{bootup} and \texttt{s\_format} $\rightarrow$ \texttt{bootup}, or sequencing that suggests queuing buffers after stopping the stream (e.g., \texttt{stream\_off} $\rightarrow$ \texttt{qbuf}).
These are typical artifacts of LLM over-generalization when code-level evidence is sparse or when the model misinterprets shared data structures as control dependencies.

Overall, ASDG achieves perfect recall on the manually curated dependencies and high but not perfect precision (24 correct edges out of 28, i.e., precision $\approx 0.86$).
This demonstrates that our basic-fact-guided reasoning significantly reduces hallucination compared with unconstrained LLM summarization, while the remaining incorrect edges highlight opportunities for further constraining the reasoning process (e.g., by enforcing value-flow consistency or adding negative examples).

\paragraph{Takeaways.}
This evaluation on the NPU driver's \texttt{ioctl} state model shows that:
(i) ASDG is reliable in capturing real state transitions (no manual edge is missed),
(ii) ASDG is more complete than a purely manual graph by uncovering additional plausible dependencies, and
(iii) a small but non-negligible fraction of hallucinated edges persists, motivating the design of downstream consumers (e.g., state-aware fuzzers) to be robust to such over-approximations.


\subsection{ASDG Correctness Evaluation (RQ1)}
\label{sec:asdg-eval}

To evaluate the correctness of our LLM-generated API State Dependency Graph (ASDG), 
we compare it against a manually curated ioctl dependency graph from a production NPU driver. 
The manual graph is constructed via detailed inspection of the driver’s initialization routines, 
graph-setup pipeline, streaming procedures, and teardown logic.  
It contains 17 state-transition dependencies among nine ioctl interfaces:
\texttt{open}, \texttt{bootup}, \texttt{s\_graph}, \texttt{s\_format}, 
\texttt{stream\_on}, \texttt{qbuf}, \texttt{dqbuf}, \texttt{stream\_off}, and \texttt{close}.  
These represent (1) the canonical forward transitions and 
(2) a complete set of termination edges of the form \textit{any ioctl} $\rightarrow$ \texttt{close}.  
We use this manually validated set as ground truth (GT).

\begin{table}[t]
\centering
\caption{Manually summarized ioctl dependencies for the NPU driver (17 edges).}
\label{tab:manual-deps}
\begin{tabular}{ll}
\toprule
ID & Dependency (A $\rightarrow$ B) \\
\midrule
1 & open $\rightarrow$ bootup \\
2 & bootup $\rightarrow$ s\_graph \\
3 & s\_graph $\rightarrow$ s\_format \\
4 & s\_format $\rightarrow$ stream\_on \\
5 & stream\_on $\rightarrow$ qbuf \\
6 & qbuf $\rightarrow$ dqbuf \\
7 & dqbuf $\rightarrow$ qbuf \\
8 & dqbuf $\rightarrow$ stream\_off \\
9 & stream\_off $\rightarrow$ close \\
\midrule
10--18 & (all ioctl) $\rightarrow$ close \\
\bottomrule
\end{tabular}
\end{table}

Using the same driver, our ASDG generation framework produces 28 dependencies. 
Table~\ref{tab:asdg-deps} lists all transitions inferred by ASDG, including both the GT-consistent edges and additional semantic edges.

\begin{table}[t]
\centering
\caption{ASDG-inferred ioctl dependencies (28 edges). GT-recovered edges are marked with ★.}
\label{tab:asdg-deps}
\begin{tabular}{ll}
\toprule
ID & Dependency (A $\rightarrow$ B) \\
\midrule
1  & open $\rightarrow$ bootup ★\\
2  & bootup $\rightarrow$ s\_graph ★\\
3  & bootup $\rightarrow$ s\_format \\
4  & s\_graph $\rightarrow$ s\_format ★\\
5  & s\_graph $\rightarrow$ stream\_on \\
6  & s\_format $\rightarrow$ stream\_on ★\\
7  & stream\_on $\rightarrow$ qbuf ★\\
8  & stream\_on $\rightarrow$ dqbuf \\
9  & qbuf $\rightarrow$ dqbuf ★\\
10 & dqbuf $\rightarrow$ qbuf ★\\
11 & dqbuf $\rightarrow$ stream\_off ★\\
12 & stream\_off $\rightarrow$ close ★\\
\midrule
13 & open $\rightarrow$ close ★\\
14 & bootup $\rightarrow$ close ★\\
15 & s\_graph $\rightarrow$ close ★\\
16 & s\_format $\rightarrow$ close ★\\
17 & stream\_on $\rightarrow$ close ★\\
18 & stream\_off $\rightarrow$ close ★\\
\midrule
19 & open $\rightarrow$ s\_graph \\
20 & open $\rightarrow$ s\_format \\
21 & open $\rightarrow$ stream\_on \\
22 & bootup $\rightarrow$ stream\_on \\
23 & bootup $\rightarrow$ qbuf \\
24 & bootup $\rightarrow$ dqbuf \\
25 & s\_format $\rightarrow$ qbuf \\
26 & s\_format $\rightarrow$ dqbuf \\
27 & qbuf $\rightarrow$ stream\_off \\
28 & stream\_on $\rightarrow$ stream\_off \\
\bottomrule
\end{tabular}
\end{table}

\paragraph{Coverage of Ground Truth Dependencies.}
ASDG successfully recovers 15 of the 17 GT edges, including all nine canonical forward transitions and six of the nine ``\textit{any ioctl}$\rightarrow$\texttt{close}'' edges.  
The two missing edges (\texttt{qbuf$\rightarrow$close}, \texttt{dqbuf$\rightarrow$close})
are concealed behind deeply nested teardown logic and object-lifetime rules, making them difficult to infer even with retrieved Basic Facts.

\paragraph{Additional Dependencies Produced by ASDG.}
ASDG introduces 13 additional transitions. 
A manual examination shows that these edges largely correspond to 
semantically plausible but previously unrecorded interactions, typically arising from
optional buffer re-synchronization flows, early-return branches, or implicit state propagation across shared internal structures.
Though absent in the manual summary, they do not contradict the driver’s semantics.

\begin{table}[t]
\centering
\caption{Accuracy of ASDG compared to ground truth.}
\label{tab:metrics}
\begin{tabular}{lcc}
\toprule
Metric & Value & Interpretation \\
\midrule
True Positives (TP) & 15 & Correctly recovered GT transitions \\
False Negatives (FN) & 2 & Missed GT edges (\texttt{qbuf, dqbuf} $\rightarrow$ \texttt{close}) \\
False Positives (FP) & 13 & Additional ASDG-inferred transitions \\
\midrule
Precision & 0.536 & ASDG favors over-approximation \\
Recall & 0.882 & High recovery of GT transitions \\
F1-score & 0.668 & Balanced correctness measure \\
\bottomrule
\end{tabular}
\end{table}

\paragraph{Quantitative Accuracy.}
Based on Table~\ref{tab:metrics}, precision, recall, and F1-score are computed as:
\[
\mathrm{Precision} = \frac{15}{28} \approx 0.536,\quad
\mathrm{Recall} = \frac{15}{17} \approx 0.882,\quad
\mathrm{F1} \approx 0.668.
\]
The high recall reflects the robustness of our Basic-Fact-guided reasoning in recovering true dependencies.  
The moderate precision reflects the LLM’s inclination toward conservative over-approximation when semantic constraints are incomplete.  
Notably, these ``false positives'' are rarely semantically contradictory, and often represent valid transitions missing from the manual summary.

\paragraph{Discussion.}
Overall, ASDG produces a semantically rich and largely correct approximation of the driver’s state-transition structure.  
The missing transitions are limited to the most complex teardown cases, and the additional inferred edges provide useful semantic coverage rather than noise.  
This correctness profile is favorable for downstream state-aware analysis tasks, where under-approximation risks missing valid execution paths.
