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