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
