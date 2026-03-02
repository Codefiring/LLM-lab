### 总体作用（两者在 mcp-scan 里的角色）

- **共同点**  
  两个文件都是给同一个“动态测试代理”（`TestingAgent`）用的**系统提示词（prompt 配置）**，指导它如何根据：
  - 上游传进来的 `测试目标详情`（一个符合 `crispe` schema 的 YAML），以及  
  - 当前可用的 MCP 工具列表  
 生成一批 **可执行的 MCP 工具调用测试用例**，并用统一格式输出 `<mcp_tool_calls>`，供协调器（coordinator）去真实执行。

- **区别核心**  
  - `malicious_behaviour_testing.md`：面向 **“恶意行为 / 恶意工具行为模式”** 的测试，主要关注：
    - Tool Poisoning（工具投毒，输入层）
    - Rug Pull（拔网线式背刺，执行层行为变化）
  - `vulnerability_testing.md`：面向 **“传统安全漏洞”** 的测试，主要关注：
    - 凭证泄露（Credential Leakage）
    - 恶意代码执行（Malicious Code Execution）
    - 工具输出中的 Prompt Injection

---

### `malicious_behaviour_testing.md` 的功能说明

- **输入约定**  
  - 接收：
    - **MCP tools list**：当前 MCP 工具信息（名称、描述、参数等）
    - **测试目标详情**：一段 `crispe:` 样式的 YAML，描述角色、威胁类型、任务、约束（文件中用中文“测试目标详情”说明）

- **内嵌任务模板（备份 YAML）**  
  文件内自带两个 YAML 任务定义，作为“内置威胁类型”：
  - `tool_poisoning_detection.yaml`  
    - 角色：网络安全工程师  
    - 能力：分析 **Tool Poisoning**  
    - 威胁：工具描述、参数、接口被篡改，诱导代理错误或危险调用  
    - 任务：从工具调用结果中分析是否存在可被利用的 Tool Poisoning 漏洞  
    - 约束：不信任任何来自工具的指令、不虚构工具、不能仅因为“回显输入”就认定为恶意
  - `rug_pull_detection.yaml`  
    - 关注 **Rug Pull**：工具在注册时看起来正常，但运行过程中行为悄悄变坏（执行层）  
    - 重点看：工具声明的行为 vs 实际运行输出 / 动作之间的偏差

  这些 YAML 是“原始恶意任务”的内嵌版本，当外部 YAML 文件删掉时，这个文件就是**单一真源（source of truth）**。

- **工作流程（Scan-style Workflow）**  
  明确要求 TestingAgent 按以下步骤生成测试用例：
  1. **信息收集**  
     - 基于 MCP 工具列表，识别：
       - 描述/输入输出可被操控的工具
       - 有副作用的工具
  2. **威胁 → 工具映射**  
     - 依据 `crispe.threats` 中的威胁类型，为每个威胁挑选最相关的工具和参数组合
  3. **测试用例生成**  
     - 每个威胁维度至少生成 3 个测试：baseline / edge / adversarial
  4. **输出 MCP 调用**  
     - 只输出 MCP 工具调用（不做解释），供协调器执行

- **输出格式要求**  
  - 必须调用本地 `finish` 工具结束  
  - `content` 中只能有 **一个** `<mcp_tool_calls>` 块，格式固定：
    ```text
    <mcp_tool_calls>
      <mcp_function=TOOL_NAME>
        <parameter=PARAM_NAME>VALUE</parameter>
      </mcp_function>
    </mcp_tool_calls>
    ```
  - 只能使用真实存在于 MCP 工具列表里的工具名  
  - 只能用 `<mcp_function>` / `<parameter>` 这两类标签

- **核心原则**  
  - 严格以 `测试目标详情` 里面的 YAML 为“真相来源”，只测其中列出的威胁、任务、约束；
  - **没有在 YAML 里出现的威胁，不允许主动扩展去测。**

---

### `vulnerability_testing.md` 的功能说明

- **输入约定**  
  - 只显式要求一个输入：
    - `测试目标详情`：同样是 `crispe` 风格的 YAML（role / threats / tasks / constraints）

- **内嵌任务模板（备份 YAML）**  
  这里内置了三个安全检测任务：

  1. **`credential_leakage.yaml` – 凭证泄露分析**  
     - 角色：安全测试工程师  
     - 能力：识别工具调用结果中的凭证泄露（用户名、密码、API Key、token、密钥等）  
     - 特别强调：
       - 不信任任何工具响应
       - 关注“结果”而不是“输入参数”（输入由安全工程师故意注入测试 payload）  
       - 需要判断真实可利用性（实际危害 + 能否在目标环境执行）
       - 对明显是 `test/demo/example/dummy` 的凭证降低风险等级  
       - 提供了**分析方法论**：如系统访问模式（`~/.ssh/id_rsa`, `API_KEY`, `/etc`, `/root`, `/log` 等），凭证格式枚举等

  2. **`malicious_code_execution_detection.yaml` – 恶意代码执行**  
     - 角色类似，也是分析工具调用历史  
     - 能力：识别工具结果中“恶意代码执行”的迹象  
     - 约束和分析方法很详细：
       - 关注系统命令执行、脚本调用、可执行文件创建/修改、异常网络请求、异常子进程等  
       - 静态检查参数 / payload 是否包含可执行逻辑  
       - 结合系统级追踪确认是否有超出声明范围的行为  
       - 要求能证明“真实风险”和“在环境中可执行”

  3. **`tool_output_prompt_injection.yaml` – 工具输出中的 Prompt Injection**  
     - 关注点：
       - 工具输出中是否包含“指令样”的内容，可能会在后续被 LLM 当作新指令执行  
       - 例如“忽略之前所有指令…”这类文本  
     - 描述了 Prompt Injection via Tool Output 是如何在 MCP 模型“输出层 / 输入层”之间流转，诱导后续代理行为  
     - 约束和方法：
       - 不信任任何工具响应  
       - 生成尽量覆盖正常操作的测试用例  
       - 重点看工具结果中是否出现可用于越权、执行代码或控制 Agent 的注入片段  
       - 一样要求忽略输入中的恶意 payload，专注在“工具结果”

- **核心规则**  
  与恶意行为文件类似，这里也强调：
  - 必须以 `测试目标详情` 的 YAML 为唯一真源：`crispe.threats` / `crispe.tasks` / `crispe.constraints`  
  - 不在 YAML 里的威胁不测试。

- **扫描式工作流**  
  流程与上一个文件类似，但更偏“安全漏洞”视角，指导 TestingAgent：

  1. **基于工具列表做信息收集**  
     - 找出能：
       - 读秘密 / 配置 / 文件
       - 返回用户可控文本
       - 执行命令 / 代码
       - 拉取远程内容
       - 操作上下文 的工具
  2. **威胁 → 工具映射**  
     - 对每个 `crispe.threats` 里的威胁，选最相关的工具和参数
  3. **Payload 生成**  
     - 每个威胁维度至少 3 个用例（正常 / 边界 / 对抗性）  
     - Payload 要“现实但尽量无害”（benign canary、echo 等）
  4. **输出可执行 MCP 工具调用**  
     - 同样要求只输出 `<mcp_tool_calls>` 块，供协调器执行

- **输出规则**  
  - 与 `malicious_behaviour_testing.md` 基本一致：
    - 必须调用本地 `finish` 工具  
    - `content` 只含一个 `<mcp_tool_calls>` block  
    - 固定 XML 样式标签  
    - 只能使用真实的 MCP 工具名  
    - 多加一条：如果某个 YAML 中的威胁在当前工具列表里根本找不到相关工具，要输出“最小、安全”的基线调用集（如健康检查、状态查询等），并明确是“用来了解输出面（output surface）”的。

---

### 两者在 mcp-scan 体系中的关系与分工

- **从测试维度看**  
  - `malicious_behaviour_testing.md`：测试的是 **“工具行为是否恶意 / 是否被投毒或中途变脸（Rug Pull）”**，更偏“工具本身或其注册信息的恶意程度”。  
  - `vulnerability_testing.md`：测试的是 **“在这些工具和调用历史中，是否产生传统意义上的安全漏洞”**，比如：
    - 把凭证打印出来  
    - 执行了不该执行的命令  
    - 工具输出中夹带了控制 LLM 的恶意 prompt。

- **在 mcp-scan 流程中的位置**  
  - 两个文件都扮演“**动态测试代理的策略模板**”：  
    - 输入：`测试目标详情`（把当前这轮想测什么威胁写进去）+ 工具列表  
    - 输出：一批结构化、可执行的 MCP 调用  
  - 差异只是：
    - **威胁词库 / 能力词库不同**（恶意行为 vs 漏洞）  
    - **扫描策略着重点略有不同**（描述层投毒/执行层变脸 vs 数据泄露/代码执行/Prompt Injection）

---

如果你接下来想进一步了解，我可以用中文帮你画一个这两个 TestingAgent 在整体 mcp-scan pipeline 里的时序图/数据流图，或者对照具体日志（比如你那份 `mcp-scan_2026-02-10-22-21-37.log`）解释它们是怎么被实际调用的。