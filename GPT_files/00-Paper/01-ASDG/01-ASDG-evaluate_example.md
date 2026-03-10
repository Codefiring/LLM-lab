那咱就把这件事彻底“工程化”一下 😊

你现在有「状态机 1」，我帮你再构造一份**带一点小错误的预测状态机**，这样两份图可以直接拿来做 GT vs Prediction 的评估测试。

---

## 1. Ground truth 状态机（FSM_GT）

我们直接把之前的「状态机 1」稍微规范化一下，作为 **Ground Truth**。
节点是“阶段状态”（对应枚举值），边上的 label 是操作（open/release + ioctl 名）。

### 1.1 DOT 形式（FSM_GT）

```dot
digraph NPU_Enum_Lifecycle_GT {
    rankdir=LR;
    node [shape=oval];

    // 状态
    CLOSED        [label="CLOSED (state=0)"];
    OPEN          [label="NPU_VERTEX_OPEN"];
    POWER         [label="NPU_VERTEX_POWER"];
    GRAPH         [label="NPU_VERTEX_GRAPH"];
    FORMAT        [label="NPU_VERTEX_FORMAT"];
    STREAMON      [label="NPU_VERTEX_STREAMON"];
    STREAMOFF     [label="NPU_VERTEX_STREAMOFF"];
    CLOSE         [label="NPU_VERTEX_CLOSE"];

    // 打开/关闭文件（非 ioctl）
    CLOSED    -> OPEN   [label="open: npu_vertex_open()"];                 // T1
    STREAMOFF -> CLOSE  [label="release: npu_vertex_close()"];             // T2

    // ioctl: bootup
    OPEN   -> POWER [label="ioctl: vertexioc_bootup"];                     // T3

    // ioctl: s_graph
    OPEN   -> GRAPH [label="ioctl: vertexioc_s_graph"];                    // T4
    POWER  -> GRAPH [label="ioctl: vertexioc_s_graph"];                    // T5

    // ioctl: s_format
    GRAPH  -> FORMAT [label="ioctl: vertexioc_s_format (OUT)"];            // T6

    // ioctl: streamon
    FORMAT   -> STREAMON  [label="ioctl: vertexioc_streamon"];             // T7

    // ioctl: streamoff / __force_streamoff
    STREAMON -> STREAMOFF [label="ioctl: vertexioc_streamoff"];            // T8
    STREAMON -> STREAMOFF [label="ioctl: __force_streamoff()"];            // T9

    // release: close 时，根据 done_state 收敛到 CLOSE
    STREAMON -> CLOSE  [label="release: npu_vertex_close()"];              // T10
    GRAPH    -> CLOSE  [label="release: npu_vertex_close()"];              // T11
    POWER    -> CLOSE  [label="release: npu_vertex_close()"];              // T12
    OPEN     -> CLOSE  [label="release: npu_vertex_close()"];              // T13
}
```

### 1.2 结构化表示（方便你写评估脚本）

你可以把这个 GT 状态机抽象成两张表：

**State 集合（S_GT）**

| State ID  | 语义说明                |
| --------- | ------------------- |
| CLOSED    | 文件未 open / state=0  |
| OPEN      | vctx->state 包含 OPEN |
| POWER     | 已 bootup / 上电       |
| GRAPH     | 已配置 graph/session   |
| FORMAT    | 已配置 format          |
| STREAMON  | 正在 streaming        |
| STREAMOFF | 已 streamoff         |
| CLOSE     | close 流程已执行         |

**Transition 集合（E_GT）**
（用三元组 `(src, op_label, dst)` 便于做集合比较）

| ID  | src       | op_label                        | dst       |
| --- | --------- | ------------------------------- | --------- |
| T1  | CLOSED    | open: npu_vertex_open()         | OPEN      |
| T2  | STREAMOFF | release: npu_vertex_close()     | CLOSE     |
| T3  | OPEN      | ioctl: vertexioc_bootup         | POWER     |
| T4  | OPEN      | ioctl: vertexioc_s_graph        | GRAPH     |
| T5  | POWER     | ioctl: vertexioc_s_graph        | GRAPH     |
| T6  | GRAPH     | ioctl: vertexioc_s_format (OUT) | FORMAT    |
| T7  | FORMAT    | ioctl: vertexioc_streamon       | STREAMON  |
| T8  | STREAMON  | ioctl: vertexioc_streamoff      | STREAMOFF |
| T9  | STREAMON  | ioctl: __force_streamoff()      | STREAMOFF |
| T10 | STREAMON  | release: npu_vertex_close()     | CLOSE     |
| T11 | GRAPH     | release: npu_vertex_close()     | CLOSE     |
| T12 | POWER     | release: npu_vertex_close()     | CLOSE     |
| T13 | OPEN      | release: npu_vertex_close()     | CLOSE     |

---

## 2. 预测状态机（FSM_PRED）：刻意制造一些偏差

现在构造一个“**预测结果**”版本，模拟你自动抽取框架的一些典型误差，比如：

* **漏掉** 某条边（False Negative）

  * 例如：漏掉 `POWER -> GRAPH` 这条实际合法的转移；
* **多出** 一条“看起来合理但其实不存在”的边（False Positive）

  * 例如：误认为可以直接从 `GRAPH` 状态 `streamon` 到 `STREAMON`。

其他部分保持不变，这样利于你在评估时清楚知道应该检测出哪些差异。

### 2.1 DOT 形式（FSM_PRED）

```dot
digraph NPU_Enum_Lifecycle_PRED {
    rankdir=LR;
    node [shape=oval];

    // 状态（和 GT 保持一致）
    CLOSED        [label="CLOSED (state=0)"];
    OPEN          [label="NPU_VERTEX_OPEN"];
    POWER         [label="NPU_VERTEX_POWER"];
    GRAPH         [label="NPU_VERTEX_GRAPH"];
    FORMAT        [label="NPU_VERTEX_FORMAT"];
    STREAMON      [label="NPU_VERTEX_STREAMON"];
    STREAMOFF     [label="NPU_VERTEX_STREAMOFF"];
    CLOSE         [label="NPU_VERTEX_CLOSE"];

    // 打开/关闭文件（非 ioctl）-- 与 GT 相同
    CLOSED    -> OPEN   [label="open: npu_vertex_open()"];                 // P1
    STREAMOFF -> CLOSE  [label="release: npu_vertex_close()"];             // P2

    // ioctl: bootup -- 与 GT 相同
    OPEN   -> POWER [label="ioctl: vertexioc_bootup"];                     // P3

    // ioctl: s_graph
    OPEN   -> GRAPH [label="ioctl: vertexioc_s_graph"];                    // P4
    // 注意：这里故意省略 POWER -> GRAPH 这条边（GT 有 T5）

    // ioctl: s_format -- 与 GT 相同
    GRAPH  -> FORMAT [label="ioctl: vertexioc_s_format (OUT)"];            // P5

    // ioctl: streamon
    FORMAT   -> STREAMON  [label="ioctl: vertexioc_streamon"];             // P6
    // 预测模型误判：认为 GRAPH 也能直接 streamon 到 STREAMON
    GRAPH    -> STREAMON  [label="ioctl: vertexioc_streamon (spurious)"];  // P7 (多出来的)

    // ioctl: streamoff / __force_streamoff -- 与 GT 相同
    STREAMON -> STREAMOFF [label="ioctl: vertexioc_streamoff"];            // P8
    STREAMON -> STREAMOFF [label="ioctl: __force_streamoff()"];            // P9

    // release: close -- 与 GT 相同
    STREAMON -> CLOSE  [label="release: npu_vertex_close()"];              // P10
    GRAPH    -> CLOSE  [label="release: npu_vertex_close()"];              // P11
    POWER    -> CLOSE  [label="release: npu_vertex_close()"];              // P12
    OPEN     -> CLOSE  [label="release: npu_vertex_close()"];              // P13
}
```

### 2.2 结构化表示（FSM_PRED）

**State 集合（S_PRED）**
（这里我刻意保持和 GT 完全一致，这样可以专注比较“边”的差异）

| State ID  | 语义说明 |
| --------- | ---- |
| CLOSED    | 同上   |
| OPEN      | 同上   |
| POWER     | 同上   |
| GRAPH     | 同上   |
| FORMAT    | 同上   |
| STREAMON  | 同上   |
| STREAMOFF | 同上   |
| CLOSE     | 同上   |

**Transition 集合（E_PRED）**

| ID  | src       | op_label                             | dst       |
| --- | --------- | ------------------------------------ | --------- |
| P1  | CLOSED    | open: npu_vertex_open()              | OPEN      |
| P2  | STREAMOFF | release: npu_vertex_close()          | CLOSE     |
| P3  | OPEN      | ioctl: vertexioc_bootup              | POWER     |
| P4  | OPEN      | ioctl: vertexioc_s_graph             | GRAPH     |
| P5  | GRAPH     | ioctl: vertexioc_s_format (OUT)      | FORMAT    |
| P6  | FORMAT    | ioctl: vertexioc_streamon            | STREAMON  |
| P7  | GRAPH     | ioctl: vertexioc_streamon (spurious) | STREAMON  |
| P8  | STREAMON  | ioctl: vertexioc_streamoff           | STREAMOFF |
| P9  | STREAMON  | ioctl: __force_streamoff()           | STREAMOFF |
| P10 | STREAMON  | release: npu_vertex_close()          | CLOSE     |
| P11 | GRAPH     | release: npu_vertex_close()          | CLOSE     |
| P12 | POWER     | release: npu_vertex_close()          | CLOSE     |
| P13 | OPEN      | release: npu_vertex_close()          | CLOSE     |

> 和 GT 的差别非常清晰：
>
> * **缺少**：GT 中 `T5: (POWER, s_graph, GRAPH)` 在预测里不存在 → 一个 *False Negative*；
> * **多出**：`P7: (GRAPH, streamon, STREAMON)` 在 GT 中不存在 → 一个 *False Positive*。

---

## 3. 基于这两份状态机做评估的示例思路

你可以把评估拆成两层：

### 3.1 状态级别（State-level）

这里 GT 和 PRED 的状态集合是完全一致的：

* |S_GT| = 8
* |S_PRED| = 8
* 交集 |S_GT ∩ S_PRED| = 8

所以：

* **状态召回率** = 8 / 8 = 1.0
* **状态精确率** = 8 / 8 = 1.0

这说明预测框架在“发现有哪些抽象状态”上是完美的。

如果以后你想模拟状态识别错误，就可以：

* 在 PRED 里合并两个状态（比如把 STREAMOFF 和 CLOSE 合并成一个 `STOP`）；
* 或者漏掉某个状态（比如没发现 `POWER` 这一层）。

### 3.2 转移级别（Transition-level）

我们把每条边看成一个三元组 `(src_state, op_label, dst_state)`：

* |E_GT| = 13
* |E_PRED| = 13
* 交集 |E_GT ∩ E_PRED| = 12

  * 共同的 12 条边：T1/T2/T3/T4/T6/T7/T8/T9/T10/T11/T12/T13 ↔ P1/P2/... 对应；
  * GT 独有：`T5: (POWER, s_graph, GRAPH)` → **FN = 1**
  * PRED 独有：`P7: (GRAPH, streamon, STREAMON)` → **FP = 1**

于是你可以算：

* **转移召回率 (R_edge)**
  [
  R = \frac{|E_{GT} \cap E_{PRED}|}{|E_{GT}|} = \frac{12}{13} \approx 0.923
  ]

* **转移精确率 (P_edge)**
  [
  P = \frac{|E_{GT} \cap E_{PRED}|}{|E_{PRED}|} = \frac{12}{13} \approx 0.923
  ]

* **F1-score**
  [
  F1 = \frac{2PR}{P+R} = \frac{2 \times 12/13 \times 12/13}{(12/13 + 12/13)} = \frac{12}{13} \approx 0.923
  ]

这组数字就是你后面可以用来测试、验证评估代码是否正确的“手算答案”。

### 3.3 扩展：你后面可以再加的评估维度

有了这对“玩具例子”之后，你可以逐步增加评估复杂度：

1. **带前置条件的边**

   * 比如边上不仅有 `ioctl_name`，还有 “需要有哪些状态位被 set / 未被 set”；
   * 评估时就比较 `(src_state, op, dst_state, precondition)` 四元组。

2. **路径级别评估**

   * 枚举从 CLOSED 到 CLOSE 的所有长度 ≤ k 的路径；
   * 比较 GT 和 PRED 的路径集合交集/差集，衡量“行为层面”的偏差。

3. **加权指标**
    
   * 某些边很重要（例如 `FORMAT -> STREAMON`），可以给它更高权重；
   * 计算加权精确率/召回率，看模型在关键转移上的表现。

---

如果你愿意，下一步我可以：

* 按你现在这个 FSM_GT / FSM_PRED 的格式，帮你设计一套**JSON/CSV schema**，直接用脚本读入并算 P/R/F1；
* 或者扩展一版，**把 `vctx->state` 的 bit 条件也编码进去**，做“带谓词的状态机”的评估。
