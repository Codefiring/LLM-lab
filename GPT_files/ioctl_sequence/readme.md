给你一份可直接跑的脚本 + 示例数据。我已把文件放好了：

* [下载脚本：ioc\_fsm\_builder.py](sandbox:/mnt/data/ioc_fsm_builder.py)
* [下载示例数据：sample\_ioctls.jsonl](sandbox:/mnt/data/sample_ioctls.jsonl)

## 怎么用

1. 本地保存上述两个文件。
2. 直接跑“启发式抽取”（无需 API）：

```bash
python ioc_fsm_builder.py --input sample_ioctls.jsonl --outdir out --projection power,driver
dot -Tsvg out/fsm.dot -o out/fsm.svg
```

生成：

* `out/fsm.dot`（Graphviz）
* `out/fsm.svg`（渲染后的状态图）
* `out/operations.json`（结构化的 pre/effects）
* `out/graph.json`（机器可读的状态图）

3. 若你有 OpenAI API Key，并想用 LLM 抽取（更准）：

```bash
export OPENAI_API_KEY=你的key
python ioc_fsm_builder.py --input sample_ioctls.jsonl --outdir out --projection power,driver --openai --model gpt-4o-mini
```

脚本会优先用 LLM；失败则自动回退到启发式。

## 脚本做了什么

* 读取 JSONL（每行：`{"name": "...", "text": "分析文本"}`）。
* 抽取 `pre` / `effects` / `error_paths`：

  * 若设置 `--openai` 且环境有 `OPENAI_API_KEY`，调用 LLM 以通用 JSON 输出；
  * 否则用内置的简易启发式，保证流水线能跑通。
* 使用内置的**小型本体/别名**做归一化（例如“上电/通电”→ `power:POWER_STATE == D0`）。
* 从初始状态做**可达性展开**，按所给 `--projection`（如 `power,driver`）生成**投影状态图**。
* 导出 Graphviz DOT 与 JSON（可接入你后续的校验/测试生成）。

需要我把 `--projection` 扩展成按 namespace 自动分图（power/init/dma/irq 四张图）或接入你自己的 `ontology.yaml / aliases.yaml` 文件吗？我可以再给你一个升级版脚本支持外部配置与更细的抽象策略。
