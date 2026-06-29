要新增一个漏洞类型（比如 MCP-026），需要按这条流水线 **discover → definition → prompt → validator → 接线 → 测试 → OpenSpec** 改动以下地方：

## 1. 漏洞定义（必改）
`src/vulnerabilities/definitions.ts` —— 新增一条 `VulnerabilityDefinition`：
- `id`、`name`、`category`、`severity`
- `applicableInterfaces`（tool/resource/resource_template/prompt/server/transport）
- `executionMode`（passive/static/active/concurrent/multi_session/protocol）
- `riskLevel`、`defaultProfiles`
- `promptPath`（指向下面的规范文件）
- `validatorId`（指向下面的验证器）
- `requires`（前置条件：callbackUrl/source/secondaryIdentity/authentication/logAccess…）
- `limits`（maxCalls/timeoutMs/concurrency/maxPayloadBytes）

类型本身在 `src/vulnerabilities/definition.ts`，只有用到新字段时才动它。

## 2. 提示词规范（必改）
在 `promptPath` 指向的位置新建 Markdown 规范文件，按现有 25 个规范的结构写：`# Vulnerability Definition`、`# Security Impact`、`# Non-Applicability Rules`、`# Remediation Requirements`，以及 agent steering 部分。由 `src/vulnerabilities/prompt-loader.ts` 加载。

## 3. 验证器（必改）
- 新建 `src/validators/mcp-026.ts`，实现 `VulnerabilityValidator`（`id` + `validate(input): RuleValidationResult`），保持**确定性、基于证据、不调用 LLM**，带反射/假阳性防护。
- 在**验证器注册表**（收集所有 validator、按 `validatorId` 映射的那个 index/registry 文件）里登记它。

## 4. 编排/能力接线（条件性）
仅当新漏洞用到现有没有的机制时：
- 新的 `executionMode` → 在 `src/orchestrator/vulnerability-runner.ts` 的模式分支里处理。
- 新的证据来源/前置能力 → 扩展 `VulnRunnerDeps` 和 `ValidatorInput`（如 callbackHits/secondaryRecords/authProbe/stateMarker/logContent 之类），并在 orchestrator 里 provision/teardown。
- 新的运行参数 → `src/schemas/scan-request.ts` 加字段 + CLI flag。
- 普通的 active/passive 漏洞通常**不用动**这一层。

## 5. 测试（必改）
- 新验证器的单元测试。
- `tests/unit/definitions.test.ts` 里关于数量/形状的守卫断言（25→26）。
- 提示词守卫测试（`docs.test.ts` / `mvp-prompts.test.ts`）对应章节断言。
- 可选：E2E 夹具（一个会触发该验证器的 MCP fixture server）。

## 6. OpenSpec（按本项目工作流）
`/opsx:propose` 新建 change → 给 `vulnerability-registry` / `vulnerability-validation` capability 加 `### Requirement` + 场景 → 实现 → `/opsx:archive` 折进基线。

## 一般**不用**改的
报告渲染（report-builder/markdown-renderer 是通用的）、风险评分（由 `severity` 自动驱动）、redaction、策略引擎——除非引入了全新的类别或证据类型。

最小路径（一个普通 active 工具类漏洞）：**定义 + 规范文件 + 验证器并注册 + 测试**，四处即可；编排层和 scan-request 都不用动。