下面给你一份可直接复制的「高质量提示词模板」，帮你把那 126 个 ioctl 的“前置条件/状态变化”推理成 **Graphviz DOT** 时序依赖图（只输出 DOT）。我把关键约束都写进 prompt 里，能最大限度避免跑题与冗长思考暴露。

---

# 提示词（直接复制用）

你是一名系统软件分析助手。
我将提供一份列表，其中每一项包含一个内核驱动 **ioctl** 的名称和一段分析文本；分析文本描述了：

* “正确执行需要什么状态要求（前置条件）”
* “执行后会对驱动状态造成什么影响（状态添加/清除/状态机迁移）”。

## 任务

基于这份列表，**在内部完成推理**：抽取统一的“状态谓词（state predicates）”、为每个 ioctl 识别其前置条件与效果，并据此建立 **ioctl 之间的可执行时序依赖关系**（A → B 表示执行 A 会产生/满足 B 的必要状态，从而使 B 成为可执行的下一步）。
最终 **只输出 Graphviz DOT** 源码，绘制一个有向图表示 ioctl 的可执行顺序与分支/回路；**不要输出任何解释或中间步骤**。

## 规则

1. 将分析文本中的自然语言前置条件与效果，归一化为布尔状态或枚举状态（例如 `OPEN`, `CONFIGURED`, `RUNNING`, `MODE=DMA` 等）。同义词要合并为同一谓词；否定条件用 `!STATE` 表示。
2. 生成边的原则：

   * 如果 `ioctl X` 的效果 **新增/设置** 了 `ioctl Y` 的前置条件中至少一个“此前未满足的必要状态”，则连边 `X -> Y`，并在边上用 `label` 简记“被满足的关键状态”。
   * 多前置条件：当且仅当 X 的效果能使 Y 所需的**至少一个**必备状态从“不满足”变为“满足”时，才连边（不是所有条件都由 X 一次满足）。
   * 若某 ioctl 会**清除**某状态，从而阻断另一 ioctl 的可执行性，也可连边并以 `label="clears STATE"` 标注阻断关系，用 `style=dashed` 表示“冲突/重置”边。
3. 初始状态：从文本可推断的“默认/上电”状态（如 `!OPEN`, `IDLE` 等）用一个虚拟节点 `INIT` 表示；凡是在初始状态即可执行的 ioctl，从 `INIT` 连边过去。
4. 允许环路（如 `START -> STOP -> START`）。
5. **只输出 DOT**，不包含解释文字、不包含代码块围栏；图设置如下：

   * `digraph IOCTL { rankdir=LR; splines=true; overlap=false; node [shape=box, style=rounded]; }`
   * 将阶段性强的 ioctl（例如 init/config/run/teardown）尝试按层级 `rank` 对齐；无法判断时不强行设定。
   * 对“重置/清除”关系使用 `style=dashed, color=gray`。
6. 如发现同名 ioctl 的分析相互矛盾，保守处理：以“多数描述一致的方向”为主，少数相反描述忽略。

## 输出格式（必须严格遵守）

* 只输出一段 **合法的 Graphviz DOT**，不加任何多余文本。
* 节点名使用 ioctl 的原始名称（必要时替换空白为 `_`）。
* 示例节点与边格式：

  * `INIT -> IOCTL_OPEN [label="!OPEN"];`
  * `IOCTL_OPEN -> IOCTL_CONFIG [label="+OPEN"];`
  * `IOCTL_STOP -> IOCTL_CLOSE [label="clears RUNNING", style=dashed];`

## 输入

下面是列表，数组中每一项包含 `name` 与 `analysis` 两个字段（UTF-8 文本）：

```
[在这里粘贴你的 126 项 JSON 或表格化文本]
```

---

## 可选增强（按需附在提示尾部）

* **状态词表提示**（若你已提前整理出常见状态名）：
  “常见状态词请优先对齐到：`OPEN, CONFIGURED, RUNNING, RESET, POWERED, MODE=PIO|DMA, BUF_ALLOCATED, LOCK_HELD, IRQ_ENABLED ...`”
* **强约束**（避免幻觉）：
  “若无法从文本中确定依赖关系，宁缺勿滥，不要创建该边。”
* **规模提示**（提高一致性）：
  “共有 126 个 ioctl，请一次性处理完整集合，避免丢失节点。”

---

## 小示例（理解用，不必放进你的实际请求）

输入（简化）：

```
[
  {"name":"IOCTL_OPEN","analysis":"需要设备未打开；执行后设置 OPEN"},
  {"name":"IOCTL_CONFIG","analysis":"需要 OPEN；执行后设置 CONFIGURED"},
  {"name":"IOCTL_START","analysis":"需要 OPEN 且 CONFIGURED；执行后设置 RUNNING"},
  {"name":"IOCTL_STOP","analysis":"需要 RUNNING；执行后清除 RUNNING"},
  {"name":"IOCTL_CLOSE","analysis":"需要 OPEN 且 !RUNNING；执行后清除 OPEN 与 CONFIGURED"}
]
```

期望输出（DOT 片段）：

```
digraph IOCTL {
  rankdir=LR; splines=true; overlap=false;
  node [shape=box, style=rounded];

  INIT -> IOCTL_OPEN [label="!OPEN"];
  IOCTL_OPEN -> IOCTL_CONFIG [label="+OPEN"];
  IOCTL_CONFIG -> IOCTL_START [label="+CONFIGURED"];
  IOCTL_START -> IOCTL_STOP [label="+RUNNING"];
  IOCTL_STOP -> IOCTL_START [label="clears RUNNING", style=dashed];
  IOCTL_STOP -> IOCTL_CLOSE [label="clears RUNNING", style=dashed];
  IOCTL_OPEN -> IOCTL_CLOSE [label="+OPEN"];
}
```

---

## 实操小贴士

* 若 126 条放不下上下文：先让模型\*\*仅做“状态抽取与规范化”\*\*输出成精简 JSON（按 ioctl → `{requires:[], adds:[], clears:[]}`），随后用同一模型或下一次请求喂入该 JSON 让它生成 DOT。
* 让采样更稳定：温度设低（如 `temperature=0~0.3`），并固定随机种子（若平台支持）。
* 评审图可读性：边的 `label` 控制在 1–3 个关键状态，避免过长。

需要的话，把你的 126 项列表贴上来，我可以按这个模板帮你一次性生成 DOT。
