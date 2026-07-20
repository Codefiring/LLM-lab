# 可能,而且相当契合。下面是分析。

## 为什么契合
这个项目的核心其实已经是"声明式工作流"——25 条漏洞定义 + 每条一份 Markdown prompt spec(带 front-matter)+ 确定性验证器。Skills 本质上也是"Markdown + front-matter + 按需加载的指令包"。所以**漏洞知识层**几乎可以一对一映射成 skill。

## 三层,转化难度不同

**1. Prompt specs → skills(容易、自然)**
那 25 份 `prompts/vulnerabilities/MCP-0NN-*.md` 已经是 front-matter + 结构化章节,和 skill 文件格式几乎同构。把每条漏洞做成一个 skill(描述里写"何时适用"),让 agent 按需加载、生成探测计划,是最顺的部分。

**2. 编排/工具/扫描命令 → 留作代码**
`/mcp-scan` 的真正价值在于**确定性、安全护栏的执行引擎**:URL 策略门、limits/p-limit、EvidenceStore 脱敏、callback 服务器、并发 burst、always-close client。这些是 TypeScript 逻辑,不是"指令"。Skill 是给 agent 读的提示,**无法替代**这套确定性管道——尤其"验证器永远不调用 LLM""agent 不能自证 confirmed"这类安全不变量,只有代码能保证。强行用 skill 让 LLM 来判定 confirmed,会直接破坏整个项目最核心的设计原则(假阳性防护、证据驱动)。

**3. 验证器 → 必须留作代码**
确定性、纯函数、读脱敏证据、正则/指纹匹配——这是项目的安全地基,绝不能交给 LLM 推断。

## 现实的混合形态(最合理)
- **保留**执行引擎 + 验证器为代码(可以仍包成 OpenCode 插件/工具,或一个 CLI)。
- **把漏洞知识做成 skills**:每条漏洞一个 skill,封装"何时适用 + 如何安全探测 + 远程化建议"。一个总的 `mcp-security-scan` skill 负责编排叙事,并在需要确定性步骤时**调用那个工具**(skill 调工具,而不是 skill 取代工具)。

## 结论
- **整体替换成纯 skills:不建议**——会丢掉确定性、安全护栏和"agent 不能自证"这条核心不变量,假阳性会回潮(这恰恰是项目里每次终审都在防的失败模式)。
- **把知识层 + 编排叙事做成 skills、执行+验证留代码的混合:很合适**,而且工作量集中在"换包装",因为 prompt specs 已经是 skill 形态。

一句话:**漏洞知识与编排适合 skills;确定性执行与验证必须留代码。** 最佳形态是 skills 调用工具,而非取代工具。





“Active testing was skipped” 是报告里对一个 **`skipped` 结论**的 limitations 文案，来源只有两类：`unmetPreconditions`（前置条件未满足）或 **取消/超时**。结合 MCP-026 的定义（`executionMode: active`、`riskLevel: controlled`、`defaultProfiles: ["full"]`、**没有 `requires`**），可能原因和对策如下：

## 最可能的原因
1. **Profile 没选对（最常见）**
   MCP-026 的 `defaultProfiles` 只有 `full`。用 `discovery` / `standard` / `targeted` 跑时它根本不在启用集里；`discovery` 更是完全不做 active 测试。
   → 用 `--profile full`，或不管 profile 直接显式选它：`--vuln MCP-026`（显式选择会强制把它放进启用集）。

2. **没有可用的 agent / LLM 运行时**
   active 模式要靠 OpenCode agent 生成测试计划（`selectApplicability`→`generateTestPlan`）。若没配置 LLM（`OPENCODE_SERVER_URL` / `opencode.json` 插件配置）那条主动流水线就跑不起来。
   → 确认 agent 运行时已就绪。

3. **扫描被取消 / 超时**
   abort、整体超时或连接中断会把剩余漏洞标成 skipped（“Scan cancelled before this vulnerability finished.”）。
   → 提高 `--request-timeout` / `--connect-timeout`，别中途取消。

4. **调用预算被耗尽**
   若 `--max-requests` 或 `--max-calls-per-vulnerability` 为 0 / 过小，轮到 MCP-026 时已无预算。
   → 调大这两个上限。

## 注意：对 MCP-026 而言不是这些
- **`requires` 前置**：MCP-026 没有 `requires`，所以不是缺 callback/auth/source 之类导致的 skip。
- **`--allow-intrusive`**：MCP-026 是 `controlled` 不是 `intrusive`，**不需要**这个 flag（除非 agent 把某个测试用例自标为 intrusive，那也只会让单个用例被拒，结果是 not_detected，不是 skipped）。
- **目标无 tool/prompt**：MCP-026 适用接口是 `tool` 和 `prompt`；若目标一个都不暴露，applicability 会返回无候选，那显示的是 **`not_applicable`**（不是 skipped），但仍值得检查目标确实有可测接口。

## 强制开始检测的最小做法
```
--profile full --vuln MCP-026 \
--max-calls-per-vulnerability <足够大> --request-timeout <足够大>
```
并确保：① 不是 discovery profile；② agent/LLM 运行时已配置；③ 目标至少暴露一个 tool 或 prompt。

最稳妥的是 **显式 `--vuln MCP-026` + `--profile full`**——这样既绕过 profile 过滤，又走 active 流水线。（具体 flag 拼写以当前 `scan-request` schema / CLI 为准，我无法在此读取确认。）


是的，基本上**继承自 OpenCode 宿主的配置**，扫描器自身并不单独配置 LLM 厂商/模型/密钥。

根据本项目的结构：

- 插件入口拿到 OpenCode 的 `PluginInput`（`client`、`directory`），用 `createOpencodeAgentRuntime(client, { directory })`（在 `src/adapters/opencode/opencode-agent-runtime.ts`）构建 agent 运行时。
- 这个运行时是基于 `@opencode-ai/sdk` / `@opencode-ai/plugin` 的 **client** 去开 worker 会话、发提示词的。也就是说，真正决定用哪个模型、哪个 provider、用什么 API key 的，是**承载这个插件的 OpenCode CLI/server 实例**——扫描器只是借用它的会话 API，模型选择落在 OpenCode 那边的配置里（`opencode.json` / OpenCode 的 provider & model 设置）。
- 项目里给了 `opencode.json.example`，是用来把插件挂进 OpenCode 的配置；它管的是“插件如何被加载”，而不是替你单独指定 LLM 厂商。
- 离线 E2E 用的是**确定性 fake agent runtime**（不打真模型）；只有 live 测试才需要真 LLM，并通过环境变量门控：`MCP_SCAN_AGENT_LIVE=1`、`OPENCODE_SERVER_URL=…`（指向一个已配置好模型的 OpenCode server）。换句话说，live 路径下模型同样来自那个 OpenCode server 的配置。

需要注意的一点（我无法在此读文件确认的部分）：worker 会话被设计成 **deny-all 工具、无递归**，并把服务器内容当作 `untrustedServerData`，但**“用哪个模型”本身不在扫描器里硬编码**——所以如果你想换模型/厂商，应该在 OpenCode 这一侧（它的配置或启动该 server 的方式）去改，而不是在扫描器代码里找 LLM 配置项。

如果你需要确认具体是“读取本机 OpenCode CLI 当前配置”还是“连到 `OPENCODE_SERVER_URL` 指定的远端 server”，要看 `createOpencodeAgentRuntime` 实际是如何拿到 client 的——这点我没有在上下文里看到确切实现细节，无法替你断定。


是的，基本上**继承自 OpenCode 宿主的配置**，扫描器自身并不单独配置 LLM 厂商/模型/密钥。

根据本项目的结构：

- 插件入口拿到 OpenCode 的 `PluginInput`（`client`、`directory`），用 `createOpencodeAgentRuntime(client, { directory })`（在 `src/adapters/opencode/opencode-agent-runtime.ts`）构建 agent 运行时。
- 这个运行时是基于 `@opencode-ai/sdk` / `@opencode-ai/plugin` 的 **client** 去开 worker 会话、发提示词的。也就是说，真正决定用哪个模型、哪个 provider、用什么 API key 的，是**承载这个插件的 OpenCode CLI/server 实例**——扫描器只是借用它的会话 API，模型选择落在 OpenCode 那边的配置里（`opencode.json` / OpenCode 的 provider & model 设置）。
- 项目里给了 `opencode.json.example`，是用来把插件挂进 OpenCode 的配置；它管的是“插件如何被加载”，而不是替你单独指定 LLM 厂商。
- 离线 E2E 用的是**确定性 fake agent runtime**（不打真模型）；只有 live 测试才需要真 LLM，并通过环境变量门控：`MCP_SCAN_AGENT_LIVE=1`、`OPENCODE_SERVER_URL=…`（指向一个已配置好模型的 OpenCode server）。换句话说，live 路径下模型同样来自那个 OpenCode server 的配置。

需要注意的一点（我无法在此读文件确认的部分）：worker 会话被设计成 **deny-all 工具、无递归**，并把服务器内容当作 `untrustedServerData`，但**“用哪个模型”本身不在扫描器里硬编码**——所以如果你想换模型/厂商，应该在 OpenCode 这一侧（它的配置或启动该 server 的方式）去改，而不是在扫描器代码里找 LLM 配置项。

如果你需要确认具体是“读取本机 OpenCode CLI 当前配置”还是“连到 `OPENCODE_SERVER_URL` 指定的远端 server”，要看 `createOpencodeAgentRuntime` 实际是如何拿到 client 的——这点我没有在上下文里看到确切实现细节，无法替你断定。




在本项目里，`skipped` 的具体原因是被写进 finding 的 **`reason` 字段**的（不是只显示笼统的 limitations 文案）。从代码里能确定有这么几条 reason 文本：

- 前置条件未满足：`"Preconditions not met: <missing>."`（例如 `callbackUrl`、`source path`、`secondary identity`、`authentication`、`log access path`）
- 取消/中断：`"Scan cancelled before this vulnerability finished."`

报告里那句 `"Active testing was skipped (unmet preconditions or cancellation)."` 是 `limitationsFor()` 给 `skipped` 状态加的通用注脚；真正区分原因要看 **reason**。

## 怎么看到它

1. **JSON 报告（最直接）**
   用 `--output json`（或看 `outputs/<scan-id>/` 目录里写出的 JSON / `report.json`）。每条 finding 都有 `status`、`reasonSummary`/`reason`、`matchedRules`、`evidenceRefs` 等字段——看 MCP-026 那条的 `reason`，就能区分到底是“Preconditions not met: …”还是“Scan cancelled …”。

2. **Markdown 报告**
   Detected 表只列 confirmed/suspected，所以 skipped 的不在那张表里；要看 **“## Findings”** 区每条 finding 的明细（`findingDetail` 会输出 Status、Reason、Limitations）。skipped 的 reason 行就在这里。

3. **执行证据**
   `outputs/<scan-id>/` 下的 executions 记录（`executions.jsonl`）能进一步看是否真的有调用发生、是被 policy 拒绝还是根本没起跑。

## 对 MCP-026 的判断捷径

MCP-026 **没有 `requires`**，所以理论上不会因为前置条件缺失而 skip——如果它的 reason 是 “Preconditions not met”，那说明触发的是它定义里确实存在的某个 `requires`（值得核对定义）；如果 reason 是 “Scan cancelled …”，那就是取消/超时/连接中断导致的。

> 注意：如果目标根本没有可测的 tool/prompt，结果会是 **`not_applicable`**（reason 类似 “Agent applicability selection found no candidate target.”），而不是 `skipped`——两者 reason 文案不同，可据此区分。

最省事的办法就是直接打开 `outputs/<scan-id>/` 的 JSON 报告，读 MCP-026 那条的 `reason` 字段。


你的 reason 是 **“Scan cancelled before this vulnerability finished.”**(取消/中断,不是前置条件问题)。这条只在一个地方产生:运行 MCP-026 期间检测到 abort 信号——而 abort 几乎总是来自**超时**(整体扫描超时,或该漏洞的 per-vuln 超时),或外部取消。

## 为什么是它
- MCP-026 是 active 模式,要走 `selectApplicability → generateTestPlan → 执行 → validate → analyzeExecution`,其中有**多次 LLM 调用**;只要这整条链没在超时窗口内跑完,就会被取消并标成这句 reason。
- 注意它**不是**前置条件(那会是 “Preconditions not met: …”),也不是不适用(那会是 not_applicable)。所以 MCP-026 本身配置没问题,卡点在“没跑完就被掐了”。

## 最可能的根因(按概率)
1. **per-vuln 超时太小**:MCP-026 定义里的 `limits.timeoutMs` 给这个漏洞的时间窗口,被 LLM 往返耗尽。
2. **整体 request/connect 超时太小**:`--request-timeout` / `--connect-timeout` 不够,LLM 生成测试计划慢就超时。
3. **LLM 运行时慢或不可用**:agent 调用本身耗时过长(模型慢、网络慢、OpenCode server 响应慢),导致每一步都顶到超时。
4. **外部取消**:进程/会话被中途 abort(手动取消、上层超时、连接断开)。

## 怎么让它跑完
- **调大超时**:把 `--request-timeout`、`--connect-timeout` 显著调大;如果是 per-vuln `limits.timeoutMs` 太紧,需要在 MCP-026 定义里放宽。
- **缩小本次范围**:只跑这一个 —— `--profile full --vuln MCP-026`,减少前面漏洞抢占整体时间预算/触发整体超时。
- **确认 LLM 运行时正常**:OpenCode 的模型/`OPENCODE_SERVER_URL` 可用且响应不慢(慢模型是 active 类最常见的超时来源)。
- **别中途取消**,并确保连接稳定。

## 怎么进一步确认是哪种超时
看 `outputs/<scan-id>/` 里的 `executions.jsonl` 和 `events.jsonl`:如果 MCP-026 几乎没有执行记录、且时间戳贴着某个超时阈值,基本就是超时;若能看到 cancel 事件的来源,可区分是 per-vuln 超时还是整体取消。

简言之:**这是超时/取消,不是配置缺失;优先调大超时(尤其 per-vuln `timeoutMs` 和 `--request-timeout`)并单独 `--vuln MCP-026` 重跑。**





这两个是**环境变量**,在启动测试/扫描的 shell 里设置即可。

## 含义
- `OPENCODE_SERVER_URL` —— 指向一个已配置好模型的 OpenCode server 的 base URL(agent 通过它开 worker 会话、发提示词)。
- `MCP_SCAN_AGENT_LIVE=1` —— 门控开关,置为 `1` 才会启用走真实 LLM 的 live 测试(否则相关 `describe.runIf(...)` 直接 skip)。

## 设置方式

**临时(单条命令)**
```bash
MCP_SCAN_AGENT_LIVE=1 OPENCODE_SERVER_URL=http://127.0.0.1:4096 \
  NO_PROXY=localhost,127.0.0.1 pnpm vitest run tests/live
```

**当前 shell 会话内 export**
```bash
export OPENCODE_SERVER_URL=http://127.0.0.1:4096
export MCP_SCAN_AGENT_LIVE=1
# 之后再跑
NO_PROXY=localhost,127.0.0.1 pnpm vitest run tests/live
```

> 上面的 URL 只是示例。`http://127.0.0.1:4096` 是 OpenCode server 常见的本地端口,但**你必须填你实际启动的 OpenCode server 的地址/端口**。

## 关键前提
- 你得先**真的有一个在跑的 OpenCode server**,并且它那边已经配好了 provider/模型/API key(如前面所说,模型配置在 OpenCode 一侧,不在扫描器里)。仅仅 export 这两个变量、但没有实际 server 在监听,live 测试连上就会失败。
- 确认 server 在监听后再设这两个变量。验证可达性可以用类似 `curl "$OPENCODE_SERVER_URL"`(具体健康检查路径取决于 OpenCode 的 API)。

## 注意(基于本仓库的门控逻辑)
- live agent 测试的条件是 `MCP_SCAN_AGENT_LIVE === "1" && !!OPENCODE_SERVER_URL` —— **两个都要满足**,缺一个就 skip。
- 另外还有一个 `MCP_SCAN_LIVE=1`,那是门控“连真实 MCP fixture server(如 127.0.0.1:8090)”那批 live 测试的,和 LLM 的这两个是分开的——如果你要跑需要真实 MCP 目标的用例,可能也要一起设。

如何**启动**那个 OpenCode server、以及它具体读哪个端口/配置文件,取决于你的 OpenCode CLI 安装方式,这部分我无法从当前上下文替你确定。



可以——而且对**插件正常运行路径**来说,本来就是复用的;只有 `tests/live/` 那批 vitest 是个例外才需要单独的 server URL。区分两种场景:

## 1. 插件实际运行(已经在复用)
当 `/mcp-scan` 在 OpenCode CLI 里跑时,插件入口拿到的是 OpenCode 注入的 `PluginInput.client`,然后用 `createOpencodeAgentRuntime(input.client, { directory })` 构建 agent。这个 `client` 就是**宿主 OpenCode 进程自己的 SDK client**——所以插件本身**已经在复用当前 CLI 的会话/模型,不需要你额外起 server,也不读 `OPENCODE_SERVER_URL`**。

## 2. `tests/live/` 测试(才需要 URL)
那批 live 测试是**独立的 vitest 进程**,不在 OpenCode CLI 内,手里没有现成的 `client`,所以它们用 `createOpencodeClient({ baseUrl: process.env.OPENCODE_SERVER_URL })` 自己连一个 server,因此才需要你提供地址。这是测试 harness 的限制,不是插件运行时的限制。

## 怎么“复用而不单独启动”

- **如果你的目的是真正用扫描器**:直接在 OpenCode 里跑 `/mcp-scan`,根本不用碰 `OPENCODE_SERVER_URL`——它已经复用 CLI 的 LLM 了。前面那些超时/skip 的排查,应该在这个真实运行路径里看,而不是去跑 live 测试。

- **如果你的目的是跑 `tests/live/` 这批用例**:它们必须有一个可连的 HTTP 端点。可行的复用方式有两类(具体取决于 OpenCode 版本,我无法在此确认):
  1. OpenCode 通常可以**以 server 模式运行**(暴露一个本地 HTTP API 端点)。如果你日常用的那个 CLI 实例已经监听某个端口,把 `OPENCODE_SERVER_URL` 指向**它的地址**即可——这就是“复用同一个、不另起一个”。
  2. 如果当前 CLI 没有以可连端点的方式跑,那 vitest 进程就拿不到 client,只能要么让 CLI 暴露端点、要么单独起一个。

- **第三条路(改造测试)**:把 live 测试改成接受外部注入的 `client`/runtime(就像离线 E2E 里 `deps.createAgentRuntime` 那样可替换),让它能复用一个已有 client 而不是必须自己 `createOpencodeClient(baseUrl)`。但这是改测试代码,不是配置层面的事。

**一句话**:插件真实运行时**已经复用** OpenCode CLI 的 LLM,无需单独 server;需要单独 URL 的只有脱离 CLI 的 `tests/live/`,而它本质上只是需要一个可连的 OpenCode HTTP 端点——把它指向你已在运行的那个实例就算复用,否则才需要单独起一个。

(注:OpenCode 具体如何暴露/复用 HTTP 端点属于 OpenCode CLI 本身的能力,这部分我无法从上下文确认,建议以你所用 OpenCode 版本的文档为准。)







这段 log 把原因讲得很清楚了:

## 发生了什么
1. worker 会话用 **`model=default`** 创建(没指定具体模型)。
2. `targeted` profile + 显式 `--vuln MCP-026`,只启用了它 1 个 —— 这部分正常。
3. MCP-026 的 **per-vuln 超时预算 = 12000ms(12 秒)**。
4. 第一步 `selectApplicability` 的 LLM 调用:发出 22315 字符的提示词,**耗时 32286ms(约 32 秒)才返回 ok**。
5. 虽然这次调用本身"成功"了,但它已经**远超 12 秒预算**;预算超时信号早已触发,于是下一步检查时漏洞被标成 **`Scan cancelled before this vulnerability finished.`**

## 根因(确定)
**不是配置缺失,而是 LLM 调用太慢导致 per-vuln 超时**。仅 applicability 一步就花了 32s,而整个漏洞的预算只有 12s。这里还印证了那条 Note:**prompt 调用没有 per-call deadline**——所以这次 32s 的调用没有被中途打断,等它返回时早已超预算,因此即便"ok"也救不回来。

## 为什么这么慢
- `model=default`:用的是 OpenCode 那边的默认模型,可能很慢/排队/走远端。
- 提示词很大(22k 字符),进一步拖慢首个 token 与整体生成。

## 怎么解决(按有效性)
1. **调大 per-vuln 超时预算**(最直接):12000ms 对 active 类 + 慢模型明显不够。MCP-026 定义里的 `limits.timeoutMs` 需要放大到能覆盖多次 LLM 往返(selectApplicability 之后还有 generateTestPlan、analyzeExecution,每步都可能几十秒)。按你看到的 32s/步,预算至少要往 90–120s 量级走才稳。
2. **换更快的模型**:`model=default` 慢是核心;在 OpenCode 一侧配置一个更快的模型(单步从 ~32s 降到几秒),12s 预算就可能够用了。
3. **(代码层改进,非配置)** 把该模型调用的 signal/超时透传给 `client.session.prompt`,让超时能真正中途打断——目前它不打断,只能等返回,所以你才会看到"32s→ok 但仍被取消"这种浪费。

## 一句话结论
MCP-026 被跳过 = **`selectApplicability` 这步 LLM 用了 32s,超过了 12s 的 per-vuln 预算**。把 MCP-026 的 `timeoutMs` 调大到能容纳多次慢调用,或换更快的模型即可;光靠 `--request-timeout` 那类整体超时改不动这个 per-vuln 预算。



简短结论:取决于 **profile**。

## 默认行为(非 full)
对每个漏洞,agent 的 `selectApplicability` 会返回多个候选接口,但运行器**只测第一个候选**(`candidateTargets[0]`)。所以 4 个 tool 时,默认只测 agent 选中的那一个最相关的,不是全部。

## 如何让它全部测试
用 **`--profile full`**。在之前实现的 `full-interfaces-scan-mode`(已合并)里:
- `full` profile 会**对每个漏洞 fan-out 到所有适用的候选接口**(tools / resources / resource_templates / prompts),而不是只测第一个;
- 即对 4 个 tool 会逐个生成测试计划并执行;
- 受同一个 per-vuln `LimitTracker`(`maxCallsPerVulnerability`)预算约束 —— 预算在所有目标间**共享**,不会按目标翻倍;
- 每条 finding 的 reason 会标注实际覆盖了多少个接口(如 `exercised 3/4 candidate interfaces`)。

## 注意几点
1. **只有 `full` 走 fan-out**;`standard` / `targeted` / `intrusive` / `discovery` 仍是单候选(或不测)。
2. **预算要够**:fan-out 共享 `--max-calls-per-vulnerability` 预算,4 个 tool 想都测到,得把它调大,否则后面的 tool 会因预算耗尽被 policy 拒绝(reason 里会显示 `exercised 2/4` 这种不足覆盖)。
3. **per-vuln 超时也要够**:每个候选都要一次 `generateTestPlan` + 执行(各自的 LLM 往返),`full` 比单候选慢得多、贵得多;结合你之前遇到的 12s 预算/32s 慢调用问题,`full` 下 per-vuln `timeoutMs` 需要放得更大,否则会在 fan-out 中途超时被取消。
4. **`concurrent` / `multi_session` / `protocol` / passive 等专门模式不参与 fan-out**,保持各自的单目标/无目标机制。

一句话:**加 `--profile full` 即可对所有适用接口全测**,同时记得把 `--max-calls-per-vulnerability` 和 per-vuln 超时预算调大以容纳多接口的多次 LLM 调用。




根据本对话中已建立的报告渲染逻辑,简短回答:**取决于报告区块**。

## Markdown 报告里
- **Detected/Summary 表**:只列状态为 **`confirmed` / `suspected`** 的 finding(即真正检测到有问题的)。`not_detected`、`inconclusive`、`skipped`、`not_applicable` 不进这张表。
- **Findings 明细区**:会逐条输出 finding 的 Status、Reason、Limitations 等,这里能看到非 confirmed 的条目(比如被跳过/未发现的)。

## 关于"接口粒度"
注意报告是**按漏洞类型(per-vulnerability)**组织的,不是"每个被测接口一行"。也就是说:
- 一条 finding 对应一个漏洞(如 MCP-026),不是对应单个 tool。
- 在 `full` profile 的 fan-out 模式下,一个漏洞可能测了多个接口(如 4 个 tool),但结果**聚合成该漏洞的一条 finding**;实际覆盖了多少个接口是写在该 finding 的 **reason 注记**里的(如 `exercised 3/4 candidate interfaces`),而**不是**每个有问题的接口单独成一条。
- finding 里通常会带 `affectedInterface` / 触发证据(matchedRules、evidence 引用),指向具体是哪个接口/规则命中,但仍挂在这一条漏洞 finding 下。

## 完整数据在 JSON
- `--output json`(`outputs/<scan-id>/report.json`)包含**所有** finding(不只 confirmed),字段最全。
- `outputs/<scan-id>/executions.jsonl` 是**逐次执行**的(已脱敏)证据记录,这一层才是真正"每个接口/每次调用"粒度的明细——想看"具体哪个接口被测、命中了什么",这里最细。

**一句话**:被确认有漏洞的会进 Markdown 的检测表,但报告是按漏洞类型聚合的;"哪些接口被测/命中"以注记+证据形式体现,真正的逐接口逐调用明细要看 JSON 报告和 `executions.jsonl`。

(注:以上基于本对话中已讨论的渲染规则;具体字段以当前 report-builder / renderer 源码为准,我无法在此读取确认。)



能，但要分清“被检测覆盖”和“有专门验证器”两层。

## 适用的验证器
在已实现的 25 个里，明确把 `resource_template` 列入适用接口的是 **MCP-013 资源投毒（Resource Poisoning，passive）**。它在能力快照上遍历 `resources` 和 `resourceTemplates` 的 name/description，扫 `DIRECTIVE_PATTERNS`，命中即 confirmed。所以**资源模板的元数据投毒是能被检测的**。

> 注意：本对话早先讨论的是一个新的 15 类精简目录（其中 MCP-013 = Resource Poisoning），与“现有 25 类目录”里漏洞编号含义不同。无论哪套，针对资源模板的检测能力都落在“资源投毒”这一类上。

## 覆盖范围与限制
1. **passive（快照层）能测**：模板的 name、description 里的隐藏指令/外泄祈使句会被 MCP-013 类的验证器命中——这部分确定可用。
2. **active（实际 read 模板内容）较弱**：大多数 active 验证器（路径穿越、命令注入、密钥泄露等）的适用接口是 `tool`/`resource`，**模板实例化后的读取**不一定在它们的 `applicableInterfaces` 里；要让某个 active 漏洞真正对模板发起调用，得确认该漏洞定义把 `resource_template` 列进 `applicableInterfaces`，否则 applicability 不会把模板选为候选。
3. **fan-out（full profile）**：full 模式会对**所有适用接口**展开，包括 resource_template——但前提仍是“该漏洞的 applicableInterfaces 包含 resource_template”，且预算/超时够用。
4. **执行路径**：对模板的读取走 `read_resource`（按 `uriTemplate`/实例化 URI），证据进 `executionRecords`，再交确定性验证器判定。

## 一句话
**资源模板的元数据类漏洞（投毒）现在能检测**（由资源投毒验证器覆盖）；至于“穿越/注入/泄露”等 active 类是否对模板生效，取决于对应漏洞定义是否把 `resource_template` 写进 `applicableInterfaces`，没写就只会停在快照层而不会主动 read 模板。具体以当前 `definitions.ts` 里各漏洞的 `applicableInterfaces` 为准。




是的，目前所有 validator 都是**确定性、规则判定、不调用 LLM** 的——这是本项目刻意的核心架构原则：agent（LLM）只负责“生成探测用例 + 给出建议性分析”，**无权把结论提升为 confirmed**，最终判定永远来自基于证据的确定性规则（反射护栏、指纹/密钥/指令正则、out-of-band 回调命中等）。

## 把判定改成 LLM 是否可行
技术上可行，但要分清它**带来什么**、**牺牲什么**。

### 可能提升的“可扩展性”
- **新增漏洞更快**：写一个判定提示词即可，省去手写正则/证据规则；语义类、上下文相关的漏洞（细微逻辑滥用、模糊的授权问题）更容易表达。
- **泛化更好**：能命中规则没枚举到的变体（新的注入花样、改写过的指令）。

### 但会牺牲项目当前的关键属性
1. **确定性 / 可复现**：规则判定对同一证据永远同一结论，报告 diff 稳定；LLM 判定有随机性、跨运行不一致。
2. **可审计性**：现在每条 confirmed 都能指到具体 matchedRules + 证据；LLM “我觉得是漏洞”难以举证、易假阳/假阴。
3. **安全边界**：当前设计明确**不让 LLM 自证漏洞**，正是为了防止被测服务器的恶意内容（提示词注入）操纵判定结果——讽刺的是，这个扫描器本身就在检测 prompt injection/tool poisoning，如果判定器吃服务器返回内容又信它，等于把判定器暴露给它要检测的攻击面。
4. **成本/延迟**：你已经遇到 per-vuln 超时问题（32s 一次调用 / 12s 预算）；再把判定也变成 LLM 调用会成倍放大慢和贵。

## 更稳妥的折中（推荐方向）
不要用 LLM **替换**确定性判定，而是**分层**：
- 保留确定性 validator 作为 **confirmed 的唯一来源**（硬证据）。
- 把 LLM 判定作为**第二信号**，只能产出 `suspected`/建议，喂给现有的 verdict 引擎——这其实正贴合当前已有的 `suspected` 状态和“agent advisory 分析不能单独 confirm”的设计。
- 这样既拿到 LLM 的泛化/可扩展性，又不破坏确定性、可审计、抗注入的核心保证。

**一句话**：改成 LLM 判定确实能让“加新漏洞”更省事、覆盖更泛，但会牺牲本项目刻意保留的确定性、可审计性和抗提示词注入边界；更好的做法是让 LLM 只贡献 `suspected` 级别的辅助信号，confirmed 仍由确定性证据规则把关。



这是因为在**执行证据层**，`ExecutionRecord.target.type` 的枚举里**没有** `resource_template` —— 它只有 `tool / resource / prompt / transport`。

所以当对一个资源模板发起实际读取（`read_resource`，用实例化后的 URI）时，那条执行记录只能把 `target.type` 记成 **`resource`**，无法记成 `resource_template`。报告若从执行记录去推断接口类型，就会把模板显示成 `resource`。

对比一下两条路径：

- **快照 / 定义 / 报告覆盖表层**：区分是干净的。`resourceTemplates` 是独立数组（键 `uriTemplate`），`InterfaceKind` 有独立的 `resource_template` 值，`applicableInterfaces` 和报告里的 `type` 也都能写 `resource_template`。
- **active 执行证据层**：不对称。执行记录的 `target.type` 不含 `resource_template`，模板被实例化成具体 URI 去 read，于是落成 `resource`；模板的正确归属主要靠 **passive 路径的 matchedRules `template:` token**（会归一化到 `resource_template`），而不是靠执行记录的 type。

**根因一句话**：`target.type` 枚举缺 `resource_template`，模板在被真正调用时降级记成了 `resource`。

如果要让它在报告里正确显示为 `resource_template`，需要（这属于需要改代码的方向，不是配置）：在 `ExecutionRecord.target.type` 枚举里加入 `resource_template`，并让执行模板读取时写入该类型，同时报告的接口归属逻辑据此区分——否则 active 证据这一层就会继续把模板归为 `resource`。




下面按「部署 → 启动 → POST 测试 → LLM 配置」四段讲,重点说清 LLM 这块的**当前真实状态**。

## 1. 部署

```bash
# 拉取代码后安装依赖(新增了 hono / @hono/node-server / tsx)
pnpm install
# 校验
pnpm typecheck && pnpm test
```

服务是纯 TS + ESM,`pnpm serve` 会用 `tsx` 直接运行 `src/service/server.ts`,无独立构建步骤。生产环境建议:绑定内网接口、前面挂 TLS/反代,不要公网暴露。

## 2. 启动

通过环境变量配置(完整列表见 `docs/http-service.md`):

```bash
export MCP_SCAN_API_KEY=devsecret          # 必填,否则拒绝启动
export MCP_SCAN_HOST=127.0.0.1             # 默认
export MCP_SCAN_PORT=8787                  # 默认
export MCP_SCAN_TARGET_ALLOWLIST=mcp.internal  # 失败关闭:不配则所有扫描都 403
# 可选安全开关(只能服务端配,请求体传了会被忽略):
# export MCP_SCAN_ALLOW_INSECURE_HTTP=true      # 允许 http:// 目标
# export MCP_SCAN_ALLOW_PRIVATE_NETWORK=true    # 允许内网/环回目标
# export MCP_SCAN_ALLOW_INTRUSIVE=true          # 允许 intrusive profile
pnpm serve
# → [mcp-scan-service] listening on http://127.0.0.1:8787
```

## 3. POST 测试

```bash
# 健康检查(免鉴权)
curl -s http://127.0.0.1:8787/healthz     # {"status":"ok"}

# discovery 扫描(零 LLM,可直接跑)
curl -s -X POST http://127.0.0.1:8787/scan \
  -H 'authorization: Bearer devsecret' \
  -H 'content-type: application/json' \
  -d '{"targetUrl":"https://mcp.internal/mcp","profile":"discovery"}'
```

响应码语义:`401` 无/错 token,`403` 目标不在 allowlist 或未开 intrusive,`413` body 过大,`429` 并发满,`503` 主动扫描但没配 LLM 运行时,`502/504` 连目标失败。

## 4. LLM 配置 —— 关键点

**当前默认的 `server.ts` 并没有接入 LLM 运行时**。这是本次实现里刻意留的边界(deferred follow-up)。它带来的直接后果是:

- `profile: "discovery"` 以及被动/协议类校验 → **不需要 LLM,直接可跑**。
- `profile: "standard" / "full" / "intrusive"` 等**主动检测** → 会返回 **`503`**(“Active scanning is not available: no agent runtime is configured”)。

原因:主动检测由 `AgentRuntime` 接口驱动,而目前唯一的实现是 `createOpencodeAgentRuntime()`(绑定 OpenCode 会话)。架构上已经预留了注入点——`createApp(config, deps)` 的 `deps.createAgentRuntime?`(类型 `AgentRuntimeFactory`),但默认 bootstrap 里**故意没有传**,所以是空的。

要启用带 LLM 的主动扫描,需要在 `src/service/server.ts` 里给 `createApp` 的 deps 补上 `createAgentRuntime`,由服务端持有 LLM/OpenCode 凭据。大致形态:

```ts
const app = createApp(config, {
  resolve: /* dns lookup */,
  createClient: () => new McpSdkV1Client(),
  createAgentRuntime: async (dir, log, opts) => {
    const client = createOpencodeClient(/* OpenCode server URL, 服务端持有 */);
    return createOpencodeAgentRuntime(client, {
      directory: dir, log,
      llmCallTimeoutMs: opts?.llmCallTimeoutMs,
      llmMaxAttempts: opts?.llmMaxAttempts,
    });
  },
});
```

配好后:LLM 端点/密钥全部只在服务端,请求体里**不接受**任何 LLM 凭据字段(会被 zod 丢弃),同样的 `POST /scan` 换成 `profile: "standard"` 即可跑主动检测。

需要提醒的是:上面这段 OpenCode 客户端的**确切构造方式**(`createOpencodeClient` 需要的 server URL / 参数)要以 `src/adapters/opencode/opencode-agent-runtime.ts` 里的实现为准——把它接进 `server.ts` 本身是一个尚未完成的后续改动,不是当前已交付能力。

一句话总结:**现在开箱即用的是 discovery/被动扫描;主动(LLM)扫描需要你在 `server.ts` 里补一个服务端持有凭据的 `createAgentRuntime` 工厂,否则返回 503。**






下面是一个带 OAuth 的 `POST /scan` 请求例子。核心原则:**请求体里绝不放 token/client_secret,只放一个服务端环境变量的名字**(`authEnv`),真实凭据由服务端持有。

## 1. 服务端启动时注入 OAuth 配置

```bash
export MCP_SCAN_API_KEY=devsecret
export MCP_SCAN_TARGET_ALLOWLIST=mcp.internal
# 目标 MCP server 的 OAuth(client_credentials)配置,值是 JSON
export TARGET_OAUTH='{"tokenUrl":"https://idp.internal/oauth/token","clientId":"my-client","clientSecret":"my-secret","scopes":["mcp:read","mcp:write"]}'
pnpm serve
```

## 2. 发起请求(只引用变量名)

```bash
curl -s -X POST http://127.0.0.1:8787/scan \
  -H 'authorization: Bearer devsecret' \
  -H 'content-type: application/json' \
  -d '{
        "targetUrl": "https://mcp.internal/mcp",
        "profile": "discovery",
        "authEnv": "TARGET_OAUTH"
      }'
```

服务会读取 `TARGET_OAUTH` 环境变量 → 走 client_credentials 换取 access token → 以 `Authorization: Bearer <token>` 连接目标。

## 需要注意

- **两层鉴权别混淆**:`authorization: Bearer devsecret` 是给**扫描服务本身**的(= `MCP_SCAN_API_KEY`);`authEnv` 引用的才是连**目标 MCP server** 的 OAuth。
- 需要第二身份(如未授权访问类检测)时,再配一个环境变量并加 `"secondaryAuthEnv": "另一个变量名"`。
- `TARGET_OAUTH` 里的**确切字段名**(`tokenUrl`/`clientId`/`clientSecret`/`scopes` 等)以 `src/adapters/mcp/auth-provider.ts` 中 `parseAuthEnv` 的 schema 为准——上面是示意值,请对照该文件确认键名。
- 被引用的环境变量必须在服务端进程里已存在,否则会报 `authentication_required`。
- 上例用的是 `discovery`(零 LLM,可直接验证 OAuth 是否正确送达)。若要用 `profile: "standard"` 等主动扫描,还需服务端配置好 `createAgentRuntime`,否则返回 `503`。

验证 OAuth 是否真正生效,最直接的办法是让 allowlist 内的被测 MCP server 记录它收到的 `Authorization` 头。