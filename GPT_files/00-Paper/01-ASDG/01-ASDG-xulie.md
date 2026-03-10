下面我根据你的需求，把“**序列级（行为级）状态机评估方法**”整体设计成一份**完整、可落地、可度量、适用于 fuzzing 的评估方案**。
内容分为你要求的三个部分：

1. **序列级评估方法介绍（原理 + 定义）**
2. **结合你的 NPU 状态机 GT / PRED 例子构造一个可运行的评估流程**
3. **说明此方案能评估哪些方面、能从结果中读出什么意义**

---

# **1. 序列级评估方法：核心思想 + 形式化定义**

状态机的节点差一点、边少一点，都可能导致 fuzzing 不能覆盖某些路径，但光看拓扑差距很难判断“行为上的差异到底大不大”。
所以引入 **语言相似度 (Language Similarity)** 的方式，将每一条 “从初始状态出发、长度 ≤ k 的 ioctl 序列” 视为状态机语言的一部分，并比较两个状态机所生成的语言的差异。

## **1.1 基本思想**

对于一个状态机 ( M = (S, s_0, \Sigma, \delta) )：

* ( S )：状态集合
* ( s_0 )：初始状态
* ( \Sigma )：操作集合（这里是 ioctl 名）
* ( \delta : S \times \Sigma \to S )：状态转移

我们定义：

### **有界行为语言（Bounded Behavior Language）**

给定一个长度上界 ( k )（如 5、6、8），定义状态机允许的所有调用序列集合：

[
L(M, k) = {, \sigma_1\sigma_2...\sigma_n \mid n \le k, \exists,\text{路径从 } s_0 \text{ 出发按序执行 } \sigma_i \text{ 且合法},}
]

这是 fuzzing 最关注的量：
**某个序列的 ioctl 调用是否合法？是否能走通？**

## **1.2 语言级 Precision / Recall**

给定：

* Ground Truth（人工状态机）: ( M_{gt} )
* Predicted（自动抽取状态机）: ( M_{pred} )

构造语言：

[
L_{gt}(k) = L(M_{gt}, k)
]
[
L_{pred}(k) = L(M_{pred}, k)
]

然后定义：

### **序列级 Precision**

[
P_{seq} = \frac{|L_{gt}(k) \cap L_{pred}(k)|}{|L_{pred}(k)|}
]

代表：

**模型认为“合法”的序列，有多少是真的合法？**

→ FP 序列越多，Precision 越低。

---

### **序列级 Recall**

[
R_{seq} = \frac{|L_{gt}(k) \cap L_{pred}(k)|}{|L_{gt}(k)|}
]

代表：

**真实合法的序列，有多少被预测状态机捕获？**

→ FN 序列越多，Recall 越低。

---

### **F1 (可选)**

[
F1 = \frac{2 P_{seq} R_{seq}}{P_{seq} + R_{seq}}
]

可以作为一个总体语言相似度指标。

---

## **1.3 为何要限定 k（有界语言）？**

因为：

* ioctl 很多，状态机可能有环（如 STREAMON → STREAMOFF → STREAMON）
* 不限制长度会产生无限语言

但 fuzzing 常常关注：

* 2~6 步的局部行为
* 较短的路径覆盖更多漏洞

所以限定 ( k = 5 ) 或 6 是实际可行的。

---

# **2. 利用你的 GT / PRED NPU 状态机构造评估流程**

我们现在用前面定义的 FSM_GT 与 FSM_PRED。

---

## **2.1 设定最大序列长度 k**

可以从 k = 4 或 k = 5 开始。

例如 k=4：

```
(open), (open → s_graph), (open → bootup → s_graph), ...
```

---

## **2.2 构造 L_gt(k)**

以 GT 状态机为例，长度 ≤4 的可能序列包含：

### **合法示例（节选）**

```
1. open
2. open → vertexioc_bootup
3. open → vertexioc_s_graph
4. open → vertexioc_bootup → vertexioc_s_graph
5. open → vertexioc_bootup → vertexioc_s_graph → vertexioc_s_format
6. open → vertexioc_s_graph → vertexioc_s_format
7. open → ... → streamon
8. open → ... → streamon → streamoff
```

特别注意：
**POWER → s_graph** 在 GT 中合法，因此路径：

```
open → bootup → s_graph → ...
```

必须包含在 L_gt(k) 中。

---

## **2.3 构造 L_pred(k)**

由于预测状态机缺少以下转移：

* `POWER → GRAPH`

因此：

```
open → bootup → s_graph
```

在预测状态机中是非法的，无法生成。

同时预测状态机多了一条：

* `GRAPH → streamon`（假阳性）

所以它会包含一些 GT 没有的序列：

```
open → s_graph → streamon
open → bootup → s_graph → streamon
```

这些属于 FP 序列。

---

## **2.4 求交集 + Precision / Recall**

我们举一个长度 k=4 的实例化演示。

### **GT 中有（合法）**

* `open → bootup → s_graph`
* `open → bootup → s_graph → s_format`

### **Pred 中没有（FN）**

因为 Pred 不允许 `POWER → GRAPH`

所以 Recall 下降。

---

### **Pred 多出来（FP）**

* `open → s_graph → streamon`
* `open → bootup → s_graph → streamon`

GT 中没有此行为 → Precision 降低

---

## **2.5 结果示例（假设规模化后）**

假设统计后结果如下（示例数据）：

| 指标          | 数值                    |
| ----------- | --------------------- |
| |L_gt(5)|   | 120                   |
| |L_pred(5)| | 140                   |
| 交集          | 115                   |
| Precision   | 115 / 140 = **0.821** |
| Recall      | 115 / 120 = **0.958** |
| F1          | 0.884                 |

解释：

* Recall 高 → PRED 基本覆盖了 GT 的“大多数可行序列”
* Precision 较低 → PRED 多认为一些非法序列是合法的

这正符合我们设计的错误：

* 漏掉合法边（降低 Recall）
* 多出非法边（降低 Precision）

---

# **3. 这个评估方案能评估什么？能反映什么？**

序列级评估的优势在于：

---

## **3.1 检查“行为正确性”而不是图形拓扑**

两个状态机看起来节点/边可能很像，但：

* 能生成的操作序列是否一样？
* 某些序列是否在预测模型上走不通？
* 某些错误序列是否被预测模型错误接受？

语言比较可以直接量化这些差异。

---

## **3.2 衡量状态机对 fuzzing“输入空间”的限制能力**

一个状态机用于 fuzzing 的价值在于：

* 限制不合法输入
* 同时允许尽可能多的合法路径被覆盖

序列级指标告诉你：

### Precision 低 → 状态机不够约束

→ fuzzing 会产生大量无效路径，浪费执行机会。

### Recall 低 → 状态机过于保守

→ fuzzing 会 miss 合法路径，覆盖率损失。

---

## **3.3 更贴合 fuzzing 的真实行为**

fuzzing 不关心状态图的拓扑长什么样，而关心：

* "open → bootup → s_graph → streamon 是否能执行？"
* "streamon → format 是否会报错？"

序列级评估直接刻画这种实际行为能力。

---

## **3.4 能定位“行为偏差”的来源**

例如：

* Recall 降低 → 检查哪些序列走不通 → 找到缺失的转移
* Precision 降低 → 检查多出的序列 → 找到错误的转移

对于建模工具的 debugging 非常有参考价值。

---

## **3.5 适用于扩展至“加权行为评估”**

你可以给某些序列定义：

* “关键序列”
* “高价值路径”
* “安全敏感路径”

并在 Precision/Recall 中设权重。

---

# **总结：为何这个方案是完美的状态机评估方式？**

✔ 能评估**行为层面**是否一致，而不是结构一致
✔ 与 fuzzing 完美契合（fuzzer 生成的是 ioctl 序列）
✔ 允许使用 sampling 避免组合爆炸
✔ 可以量化假阳性、假阴性
✔ 结果易解释，可作为优化状态机抽取算法的反馈

---

如果你愿意，我可以继续帮你：

### ✅ 写出一个 Python / Rust 的序列枚举器

### ✅ 写出自动计算 Precision/Recall 的脚本

### ✅ 生成全部长度 ≤5 的 NPU GT / PRED 序列例子

### ✅ 给出可视化热力图（Showing mismatch regions）

你希望我继续输出哪一步？
