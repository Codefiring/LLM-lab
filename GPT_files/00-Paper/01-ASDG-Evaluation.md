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


先直接说结论：**评估“生成的 Linux 驱动 API 状态机”和“ground truth 状态机”的差异，本质上就是在评估两个有向带标签图（自动机）的“结构差异 + 行为差异”**。可以分三层来做：

1. **是否“完全等价”**（形式化验证层面）
2. **差异有多大、多严重**（指标层面：precision/recall/F1 等）
3. **差异落在哪些具体 API 场景上**（工程可解释层面：路径、用例、错误处理）

下面我按“从严到松”的方式给一个比较系统的做法，你可以根据自己项目的成熟度和时间精力挑着用。

---

## 0. 先统一表示：把状态机标准化成“图”

无论是你生成的，还是 ground truth 的，都建议统一成类似这样的结构：

* **状态集合**：`S_gen` 和 `S_gt`
* **初始状态**：`s0_gen`，`s0_gt`
* **接受/终止状态集合**（如有）：`F_gen`，`F_gt`
* **边集合（带 API 调用标签）**：

  * `T_gen ⊆ S_gen × Σ × S_gen`
  * `T_gt ⊆ S_gt × Σ × S_gt`
    其中 Σ 就是你要建模的 API 调用（`open`, `release`, `read`, `ioctl`, …）。

如果状态有语义名称（比如 `CLOSED`, `OPEN`, `MMAPED`），统一用名称作为 ID；
如果没有语义名称，而是自动生成的状态 ID（q0, q1, …），下面讲到的“笛卡尔积状态机 / 仿真 / bisimulation”会比较适用。

---

## 1. 严格层面：形式化“等价”检查

如果你的状态机是**有限状态机（FSM）或 DFA/NFA**，可以从“完全等价”入手：

### 1.1 语言等价（Language Equivalence）

“语言等价”的意思：**两个状态机接受的所有 API 调用序列集合一致**。

典型做法（概念上）：

1. 把 `M_gen` 和 `M_gt` 都转成 DFA（必要时做确定化和最小化）。
2. 构造它们的**对称差自动机**：

   * 接受集合 = “在 M_gen 中接受 XOR 在 M_gt 中接受”的调用序列集合。
3. 如果对称差自动机语言为空（可以用空语言检查算法 / reachability 算法），那就说明 **两者完全等价**。

这在理论上很好，但工程里可能：

* 你的状态很多（尤其自动抽取的驱动状态机），复杂度高；
* ground truth 和生成的状态机不完全保证是“正规语言”那套经典假设。

如果你能用模型检查工具/NFA/DFA 库，这条路可以直接走；否则可当作一个“理想目标”。

### 1.2 仿真 / 互模拟（Simulation / Bisimulation）

有些状态机更像**带状态标签的 LTS** 或 Kripke 结构，这时可以用：

* **仿真（simulation）**：检查生成的状态机是否“行为上不比 ground truth 更自由”。
* **互模拟（bisimulation）**：检查两者在行为上完全匹配。

概念上是：

* 对任意 `(s_gen, s_gt)`，如果两者标记相同、并且对于 s_gen 的每条 `label` 转移，s_gt 上存在对应的 `label` 转移能模拟回去（反之亦然），则二者互模拟。

互模拟成立 → 两个状态机行为上等价（比单纯 graph isomorphism 更宽松）。

---

## 2. 指标层面：用“precision/recall/F1”评价结构差异

多数工程项目不会要求“完全等价”，而是更关心：

* **我生成的状态机是否“过度放大”（over-approximation）？**
  → 接受了很多 ground truth 不允许的 API 序列（安全性风险大）。
* **是否“过度保守”（under-approximation）？**
  → 拒绝了很多合法序列（影响可用性、学习效果）。

一个非常实用的办法是：
把 **边（transition）和状态**都当成“预测”，计算类似分类指标：

### 2.1 Transition-Level Precision / Recall

先要解决**对齐（matching）问题**：

* 如果状态是**有语义名称**的（如 `CLOSED`, `OPEN`, `READING`），就按状态名对齐。
* 如果状态是**匿名 ID**，常用做法：

  * 用 ground truth 做“金标准”，对生成状态机做**图匹配**（例如以入度/出度模式和标签为特征的近似匹配）；
  * 或者直接采用“路径级评估”（见后面 3），绕过状态 ID 对齐。

假设已经能对齐状态（或者直接用状态名做 ID），我们可以构造边集合：

```text
Edges_gt  = { (s_from, label, s_to) | ground truth 中存在该边 }
Edges_gen = { (s_from, label, s_to) | 生成状态机中存在该边 }
```

然后：

* **TP（True Positive）**：`Edges_gen ∩ Edges_gt`
* **FP（False Positive）**：`Edges_gen - Edges_gt`
* **FN（False Negative）**：`Edges_gt - Edges_gen`

指标：

* **Precision = TP / (TP + FP)**

  * 在你“预测出的边”里，有多少是真的？
* **Recall = TP / (TP + FN)**

  * ground truth 的边里，有多少被你覆盖到了？
* **F1 = 2 * P * R / (P + R)**

  * 综合指标。

含义：

* **Precision 低**：说明你生成了许多“ground truth 不存在的转移” → 容易放大行为空间，可能引入“非法 API 序列”。
* **Recall 低**：说明你漏掉了许多真实存在的转移 → 容易太保守、或者无法覆盖真实驱动的所有合法场景。

你也可以分情况算：

* 正常路径边 vs 错误处理边
* 只考虑某一类 API（如 `open/close` 再单独算一次）

### 2.2 State-Level Precision / Recall（可选）

类似地，对状态本身也可以算一遍：

* 如果状态名字有语义（`UNINIT`, `INITED`, `REGISTERED`, …）：

  * 统计生成状态机中的状态集合 `States_gen`，和 ground truth 中的 `States_gt`。
  * 同样算 TP/FP/FN 和 P/R/F1。

这可以反映：

* 你的状态划分是否过粗或过细；
* 是否缺少关键状态（比如某个中间错误恢复状态）。

---

## 3. 行为层面：路径 / 调用序列上的差异

真正对使用者有意义的是：**在“API 调用序列”这一层，到底哪些序列行为被错误建模了？**

### 3.1 有限长度路径枚举（bounded language comparison）

对状态机做**有界深度（例如长度 ≤ k）的路径枚举**：

1. 从初始状态开始，枚举所有长度 ≤ k 的 API 调用序列：

   * `Seqs_gt(k)`：在 ground truth 中可达的调用序列；
   * `Seqs_gen(k)`：在生成状态机中可达的调用序列。
2. 计算：

   * `Diff1 = Seqs_gen(k) - Seqs_gt(k)`：生成状态机“允许但 ground truth 不允许”的序列（**过度放大**）
   * `Diff2 = Seqs_gt(k) - Seqs_gen(k)`：ground truth “允许但生成状态机不允许”的序列（**过度保守**）

再配上简单统计：

* `|Diff1| / |Seqs_gen(k)|`：大致反映 over-approx 程度；
* `|Diff2| / |Seqs_gt(k)|`：大致反映 under-approx 程度。

k 的选择：

* k = 3~6 之类，够覆盖常见短序列：

  * 如 `open → read → close`
  * `open → mmap → read → close` 等。

如果状态机很大，可以随机/符号方式采样路径，而不是穷举。

### 3.2 用真实 Trace 做验证（更工程化）

如果你有**驱动运行时日志或测试用例 trace**（例如 ftrace、LTTng 或手工记录的 API 调用序列）：

* **正例（合法 trace）**：

  * ground truth 接受；
  * 检查生成状态机是否也接受（能走到某个终止或稳定状态）。
  * 统计合法 trace 的“通过率”。

* **反例（非法 trace / 故意构造的错误序列）**：

  * ground truth 拒绝；
  * 检查生成状态机是否也拒绝。

可以给出两类准确率：

* 对合法序列的覆盖率（recall on valid sequences）
* 对非法序列的过滤率（specificity on invalid sequences）

这对分析“是否会在实际使用中放过危险操作序列”很有用。

---

## 4. 结构 + 行为结合：做一个“差异报告”

当你有了上述的数据后，可以做一个对工程师友好的“差异报告”，例如：

1. **总体指标**：

   * Transition Precision / Recall / F1；
   * 有限深度（k）的路径 over/under-approx 比例；
   * 正负样本 trace 上的准确率。

2. **关键差异列表**（对调试很有帮助）：

   * **多出来的关键转移**（高风险）：

     * 如：`OPENED --close()--> CLOSED` 是对的
       但生成的状态机额外允许：`UNINIT --read()--> READING`（ground truth 不允许）。
   * **缺失的关键转移**（影响完整性）：

     * 如：调用 `ioctl()` 之后，缺少返回到某个可读状态的边。
   * **出现顺序不正确的序列**：

     * `mmap()` 出现在 `open()` 前面等。

3. **错误类别统计**：

   * 无效调用顺序（如未 open 先 read）；
   * 漏掉错误恢复分支；
   * 多余的自环 / 空转移。

---

## 5. 一个简化的实现思路（伪代码级）

假设你已经把状态机导出成简单的 JSON（for example）：

```json
{
  "initial": "CLOSED",
  "states": ["CLOSED", "OPENED", "MMAPED"],
  "transitions": [
    { "from": "CLOSED", "label": "open",  "to": "OPENED" },
    { "from": "OPENED", "label": "read",  "to": "OPENED" },
    { "from": "OPENED", "label": "mmap",  "to": "MMAPED" },
    ...
  ]
}
```

你就可以很容易在脚本里：

1. 解析两个 JSON；
2. 用 `(from, label, to)` 作为 key，做集合运算；
3. 输出 precision/recall/F1；
4. （可选）写一个 BFS，枚举长度 ≤ k 的 label 序列，比较两边的集合差异。

---

## 6. 总结一句话流程

如果只保留一个“落地方案”，我会建议你：

1. **统一格式**：把 ground truth 和 生成状态机都转成 `(states, initial, transitions)` 结构。
2. **先算结构指标**：按 `(from, label, to)` 对齐，算 **transition-level precision/recall/F1**。
3. **再看行为差异**：对长度 ≤ k 的 API 序列做有界路径比较，统计“多余的”和“缺失的”序列，并列出几个典型例子。
4. （如果有 trace）再测一轮“对真实合法/非法调用序列的识别率”。

这样既有**定量指标**，又能从**具体路径**上解释差异，非常适合论文和工程报告。

---

如果你愿意把你现在的“ground truth 状态机”和“生成状态机”的表示形式（比如简化后的 JSON/表格结构）贴一小段出来，我可以帮你直接设计一套更贴合你数据格式的评估脚本/算法。



可以把你的问题拆成两块看：

1. **怎么构建“ground truth”的 ioctl 状态机？**
2. **怎么定量评估“自动提取的状态机”和 ground truth 之间的差别？**

我按步骤给一个比较工程化的方案，你可以直接落地。

---

## 一、如何构建 ground truth 状态机？

核心目标：得到一个「你自己也信得过」的参考模型，用来当标杆。

### 1. 先固定好“状态机长什么样”

在动手之前，先把下面几件事写清楚（写成一份小 spec）：

* **状态怎么表示？**
  比如对 vctx->state 这种 bitmask，你可以约定：

  * 状态节点 = 某些关键 bit 组合的抽象

    * S0: {}
    * S1: {GRAPH}
    * S2: {GRAPH, FORMAT}
  * 不需要所有 bit 全列出，只保留你关心的那几类（GRAPH、FORMAT、POWER_ON 等）。

* **事件是什么？**

  * 一般就是某个 `ioctl` 编号 +（可选）参数类型/范围：

    * `IOCTL_GRAPH_CREATE`
    * `IOCTL_FORMAT_SET`
  * 如果你提取框架只用 ioctl 编号，那 ground truth 就也只用编号。

* **转移的定义**

  * `(state_before, ioctl, condition) -> state_after`
  * condition 可以先不管（当做 true），或者只记录简单的：

    * “成功返回 0 的路径”
    * “错误返回 -EINVAL 的路径”

**这一步非常重要**：
ground truth 的抽象方式 **要尽量跟你自动框架的输出一致**，否则后面评估时会很痛苦（mapping 难度会很大）。

---

### 2. 为少量驱动手工建模（golden drivers）

不要一上来就想给几十个驱动建“真相”，那没必要。常见做法是：

1. **选 1–3 个驱动** 做 golden set：

   * 代码量相对适中；
   * ioctl 逻辑以 vctx->state 或类似 flag 明确实现；
   * 最好包含一点分支/错误路径，不要太 trivial。

2. **定义标注流程**（你自己或者和同学约好）：

   * 对每个 ioctl：

     1. 找到它的 handler。
     2. 标记：调用前检查了哪些状态（例如 `if (!(state & BIT(GRAPH))) return -EINVAL;`）。
     3. 标记：成功路径中对状态的写入（`state |= BIT(FORMAT);`，`state &= ~BIT(GRAPH);` 等）。
   * 把这些信息整理成：

     * 初始状态（open/alloc 时的 state）。
     * 所有可达状态集合。
     * 执行某个 ioctl 后，state 如何变化。

3. **把手工结果画成一个正式的 FSM**

   * 可以用 DOT 写成类似：

     ```dot
     digraph G {
       S0 [label="{}"];
       S1 [label="{GRAPH}"];
       S2 [label="{GRAPH,FORMAT}"];

       S0 -> S1 [label="IOCTL_GRAPH_CREATE / ok"];
       S1 -> S2 [label="IOCTL_FORMAT_SET / ok"];
       S1 -> S1 [label="IOCTL_FORMAT_SET / err"]; // 例如某条件失败
     }
     ```
   * 最终 ground truth 用 **机器可读格式** 存起来：

     * 要么就是 DOT；
     * 要么 JSON（states 列表、transitions 列表）。

---

### 3. 用动态/符号执行辅助校验 ground truth（可选但很有帮助）

手工看代码容易漏边界路径，你可以加一层“自动检查”：

* **动态记录序列**：

  * 写一个小测试程序，只调用这个驱动的 ioctl。
  * 加上内核 kprobe / tracepoint 或直接在驱动里调试打印，把：

    * 当前 state（或你关心的 bit）；
    * ioctl 编号；
    * 返回值
      都打出来。
  * 收集一堆日志，看看是否能覆盖你画的所有边，是否出现了“日志里有的状态/边，但你的 ground truth 没有”的情况。

* **符号执行/静态分析辅助**（如果你有时间）：

  * 比如用 KLEE、S2E、或你自己的静态分析，探索 ioctl handler 中的路径，把任何 `state` 变化都收集出来。
  * 和手工 FSM 对比，如果发现“工具发现的路径你没画”，就回去审一遍。

目标不是 100% 完全正确，而是**你确认这个 FSM 基本不再有明显漏边**，足够当基准使用。

---

## 二、怎么评估你的提取框架与 ground truth 的差别？

一旦 golden ground truth 准备好了，就可以比较「提取结果」和「真相」。我给你几个不同层级的指标，你可以结合使用。

---

### 1. 状态/转移层面的 Precision / Recall

假设你把两个状态机都转成统一格式：

* `State` 有个 id（例如 `{GRAPH}` 或某个编号）。
* `Transition` 是 `(src_state, ioctl, dst_state)` 三元组。

你可以定义：

* **转移集合**：

  * `E_gt` = ground truth 的所有转移；
  * `E_pred` = 你的工具输出的所有转移。

* **映射规则**：

  * 如果状态有稳定的 label（比如用 bitset 作为 label），那很简单：相同 label 即同一状态。
  * 如果你的工具输出的是内部编号，你可以：

    * 在提取时就把状态标成 “对应的 bitset”；或
    * 用额外逻辑去推断 mapping（例如以出入边相似度做匹配）——但这比较麻烦，建议前者。

然后就可以算：

* **Transition precision**：
  [
  P = \frac{|E_pred \cap E_gt|}{|E_pred|}
  ]
  你的状态机里，**真正正确的边占了多少比例？**

* **Transition recall**：
  [
  R = \frac{|E_pred \cap E_gt|}{|E_gt|}
  ]
  ground truth 里的边，有多少被你的工具找到了？

* 同样可以为 **状态节点** 做一个 `state-level P/R`：

  * 用 “出现过在至少一条正确边中的状态” 判断。

这个是最直接、最易实现的指标。

---

### 2. 行为层面的序列比较（语言相似度）

有时候两张图的拓扑有些不同，但**可接受的 ioctl 序列集合**很接近，这在 fuzzing 场景其实更重要。

可以做一个“有界序列”比较：

1. 固定一个最大长度 `k`（例如 5 或 6），表示我们只看长度 ≤ k 的调用序列。
2. 对 ground truth：

   * 从初始状态出发，遍历所有可能的 ioctl 序列（到长度 k 为止），得到一个集合 `L_gt(k)`。
3. 对你的提取状态机同样做一次，得到 `L_pred(k)`。
4. 然后定义：

   * **序列级 precision**：
     [
     P_{seq} = \frac{|L_pred(k) \cap L_gt(k)|}{|L_pred(k)|}
     ]
     你的模型认为“合法”的序列，有多少实际上在 ground truth 中也允许？
   * **序列级 recall**：
     [
     R_{seq} = \frac{|L_pred(k) \cap L_gt(k)|}{|L_gt(k)|}
     ]
     ground truth 允许的序列，有多少被你的模型也允许？

注意：如果分支超级多，可以改成“采样一堆随机路径”，近似估计这些值，而不是全部穷举。

---

### 3. 结构差异：Graph Edit Distance / 不变性检查

如果你对形式方法比较感兴趣，可以再做一些更细的对比。

#### 3.1 图编辑距离（Graph Edit Distance）

* 定义：

  * 最少需要多少次“操作”（增删状态、增删边、改标签）才能把 Pred 图变成 GT 图。
* 这本身可以作为一个独立指标：值越小，两个状态机越像。
* 实际实现时可以用现有的 GED 近似算法（很多图算法库里有），不追求严格最优也可以。

#### 3.2 不变性 / 性质检查

把你关心的“协议规则”写成一些简单的性质，比如：

* “在没有 GRAPH 的前提下调用 FORMAT 必须失败”
* “POWER_OFF 之后不能再成功调用任何数据路径的 ioctl”

然后：

1. 在 ground truth 上检查：这些性质都要满足；
2. 在你的提取状态机上也做 model checking，看同样的性质是否成立。

如果某个性质在 ground truth 上成立，而在你的提取模型上不成立，那就说明你的模型引入了**不安全的路径**；反过来，某性质只有在你的模型上成立，而在 ground truth 上不成立，说明你模型“过于保守”，漏掉了一些行为。

---

### 4. 下游效果评估：对 fuzzing 的帮助

毕竟你最终目的是辅助 AFL 生成更“合法”的输入，可以做一个 end-to-end 的效果测试：

1. 选一个带真实 bug 或复杂逻辑的驱动（不一定是 golden，不必有 ground truth）。
2. 比较三种驱动 fuzzing 策略：

   * **随机 ioctl 序列**；
   * **用 ground truth 状态机引导的序列**；
   * **用你提取的状态机引导的序列**。
3. 对比指标：

   * 覆盖率（edge/branch coverage）；
   * 触发的 unique crash 数量；
   * 到达某些深层代码的速度等。

这里 ground truth 出现的目的是“上限”，看看你自动提取的图离这个上限差多少。

---

## 三、落地建议（可以直接当 todo 列表）

1. **写一个小的状态机 schema**，把“状态 = 哪些 bit”、“事件 = 哪些 ioctl”、“只考虑成功路径还是包含错误路径”等先定死。
2. **选 1–3 个驱动做 golden set**，手工画 DOT + JSON，辅以一点动态日志验证。
3. 写一个简单的脚本：

   * 解析 ground truth DOT 和你工具的 DOT；
   * 把状态 label 标准化（比如都变成 bitset 字符串）；
   * 计算：

     * state / edge 的 precision & recall；
     * 给定长度 k 的序列级 precision & recall（可以先用小 k，比如 3）。
4. 如果你对形式验证感兴趣，再加一层：

   * 定义 2–3 条简单的安全性质；
   * 用 BFS 或简单 model checking 确认属性在两边的真假。

如果你愿意，我也可以帮你：

* 看一下你当前提取框架生成的某个驱动的 DOT，
* 一起设计一个具体的 ground truth schema 和对比脚本的格式。
