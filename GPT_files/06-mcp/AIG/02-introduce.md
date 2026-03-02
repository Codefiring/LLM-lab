## MCP-Scan Dynamic Analysis Pipeline

This document explains how the `dynamic_analysis` process works in the MCP-Scan project, focusing on how it analyzes a running MCP server via `--server_url` instead of a static code repository.

### 1. Entry Point and High-Level Goal

When you run MCP-Scan in dynamic mode (for example):

```bash
python main.py \
  --server_url "http://localhost:8000/sse" \
  --prompt "测试工具投毒漏洞"
```

the CLI constructs an `Agent` with a configured LLM and a `ToolDispatcher` that points to the remote MCP server. Instead of scanning files in a repo, the agent’s `dynamic_analysis(prompt)` method orchestrates a multi-stage, LLM-driven security assessment of the MCP tools exposed by that server.

The high-level goal is to:
- Collect contextual information about the target MCP deployment and tools.
- Generate and execute security testcases against those tools (via MCP calls).
- Aggregate and normalize the findings into structured vulnerability results and a safety score.

### 2. Core Components

The dynamic analysis relies on several core components defined in `agent/agent.py`:

- **`Agent`**: Top-level orchestrator that exposes `dynamic_analysis(prompt)` and holds:
  - `llm`: the base model used for reasoning.
  - `specialized_llms`: (optional) per-task models.
  - `dispatcher`: a `ToolDispatcher` configured with the MCP server URL and headers; it is the bridge between the LLM agents and the remote MCP tools.
  - `pipeline`: a `ScanPipeline` instance used to execute staged prompts.
  - `language`: output language selection (`zh` / `en`).

- **`ScanStage`**: A lightweight container describing one step of the pipeline:
  - `stage_id`: logical step identifier.
  - `name`: human-readable stage name.
  - `template`: path to the prompt template file under `prompt/agents/dynamic/`.
  - `output_format`: textual instructions describing the required output structure.
  - `output_check_fn`: optional validation function for the LLM output.
  - `language`: language hint forwarded to the `BaseAgent`.

- **`ScanPipeline`**: Standardized execution engine for stages. For dynamic analysis it uses:
  - `execute_stage_dynamic(stage, prompt, context_data=None)`:
    - Loads the stage’s prompt template via `prompt_manager`.
    - Instantiates a `BaseAgent` wired to the shared `llm` and `dispatcher`.
    - Synthesizes a user message describing the stage and including any prior context.
    - Runs the agent’s `run()` loop, which is allowed to call MCP tools through the dispatcher.
    - Stores and returns the LLM result for that stage.

- **`VulnerabilityExtractor`** and **`calc_mcp_score`**:
  - `VulnerabilityExtractor.extract_vulnerabilities(...)` parses the XML-structured vulnerability review into a normalized list of vulnerability records.
  - `calc_mcp_score(vuln_results)` converts the extracted vulnerabilities into an aggregate safety score suitable for reporting.

### 3. Stage 1 – MCP Information Collection

**Method**: `dynamic_analysis()` → `ScanPipeline.execute_stage_dynamic()`  
**Stage definition**:
- `stage_id = "1"`
- `name = "Info Collection"`
- `template = "agents/dynamic/project_summary"`
- `output_format`: “生成一份详细的MCP(model context protocol)信息收集报告，使用Markdown格式……”

**Purpose**:
- Build a high-level understanding of the MCP deployment and tools based solely on the provided prompt and MCP introspection abilities (e.g., tool lists).
- Generate a Markdown report that can later be used as context for downstream threat-focused stages.

**Inputs**:
- The human-provided `prompt` string (e.g., “测试工具投毒漏洞”).

**Process**:
1. `ScanPipeline.execute_stage_dynamic` loads the dynamic project summary prompt (`agents/dynamic/project_summary`) via `prompt_manager`.
2. It creates a `BaseAgent` configured to:
   - Use the shared `llm`.
   - Use the shared `dispatcher` to talk to the MCP server.
3. It constructs a user message that instructs the agent to perform “Info Collection” and explicitly mentions that this is an MCP dynamic scan.
4. The `BaseAgent.run()` loop:
   - Interprets the system and user prompts.
   - Uses available MCP tools (as exposed by the remote server) to gather information (e.g., tool schemas, capabilities, health, etc.).
   - Produces a structured Markdown report.

**Outputs**:
- `info_collection`: A Markdown document describing:
  - The MCP environment and target context.
  - Available tools and their potential security-relevant properties.
- Stored as `result_meta["readme"]` for later reporting and re-use.

### 4. Stage 2 – Dynamic Malicious-Behavior Testing

**Method**: `dynamic_analysis()` → `ScanPipeline.execute_stage_dynamic()`  
**Stage definition**:
- `stage_id = "2"`
- `name = "Malicious Testing"`
- `template = "agents/dynamic/malicious_behaviour_testing.md"`
- `output_format = vuln_ret_format` (a strict Markdown + sectioned format).

**Prompt Template**: `prompt/agents/dynamic/malicious_behaviour_testing.md`

This template plays the role of a **testing agent** that:
- Receives:
  - The MCP tools list (via the coordinator, in practice).
  - A YAML-based “测试目标详情” block under a `crispe:` schema specifying:
    - **role / capabilities** (e.g., Cyber Security Engineer focusing on MCP threats).
    - **threats** (e.g., Tool Poisoning, Rug Pull).
    - **tasks** (what to detect or analyze).
    - **constraints** (e.g., do not trust tool responses, only use provided tools).
- Embeds several pre-defined malicious-behavior task specifications, such as:
  - `tool_poisoning_detection.yaml`
  - `rug_pull_detection.yaml`

**Key behaviors of this stage**:
- It must treat the YAML (`测试目标详情`) as the **source of truth** for:
  - Which threats to test (`crispe.threats`).
  - What tasks to achieve (`crispe.tasks`).
  - What constraints to obey (`crispe.constraints`).
- It follows a **scan-style workflow**:
  1. **Information collection (based on tools list)**:
     - Identify tools whose descriptions, IO, or side effects are security-relevant.
  2. **Threat → Tool mapping**:
     - For each threat from the YAML, pick relevant tools/parameters to probe.
  3. **Testcase generation**:
     - For each threat dimension, generate at least three cases (baseline / edge / adversarial).
  4. **Output executable MCP tool calls**:
     - Emit tool calls in a strict `<mcp_tool_calls>` XML-like block that the local coordinator can execute.

**Constraints and Output Requirements**:
- Must call the local `finish` tool at the end.
- The `content` field returned by `finish` must contain exactly one `<mcp_tool_calls>` block with a sequence of:
  - `<mcp_function=TOOL_NAME> ... </mcp_function>`
  - `<parameter=PARAM_NAME>VALUE</parameter>` entries.

**Result**:
- `report1`: A Markdown report (following `vuln_ret_format`) summarizing observed malicious-behavior related risks, based on tool-call histories generated and executed during this stage.

### 5. Stage 3 – Dynamic Vulnerability Testing

**Method**: `dynamic_analysis()` → `ScanPipeline.execute_stage_dynamic()`  
**Stage definition**:
- `stage_id = "3"`
- `name = "Vulnerability Testing"`
- `template = "agents/dynamic/vulnerability_testing.md"`
- `output_format = vuln_ret_format` (same structured Markdown requirement as Stage 2).

**Prompt Template**: `prompt/agents/dynamic/vulnerability_testing.md`

This template implements a **vulnerability-focused test agent** that:
- Receives:
  - A YAML `测试目标详情` under `crispe:` that describes credential leakage, malicious code execution, prompt injection via tool output, etc.
  - Context from prior stages:
    - `信息收集报告` (Info Collection report from Stage 1).
    - `malicious testing` (the Stage 2 malicious-behavior report).
- Embeds detailed tasks for multiple vulnerability classes, for example:
  - `credential_leakage.yaml`
  - `malicious_code_execution_detection.yaml`
  - `tool_output_prompt_injection.yaml`

**Core rules**:
- Treat the provided YAML as the source of truth for:
  - Threats to test.
  - Tasks to run.
  - Constraints/limitations.
- Only analyze threats explicitly listed; do not introduce extra categories.

**Scan workflow**:
1. **Information collection**:
   - Inspect the MCP tools list and capabilities with a focus on:
     - Secrets reading or configuration access tools.
     - Tools that accept or return user-controlled text.
     - Tools with code/command execution capabilities.
2. **Threat → Tool mapping**:
   - For each configured threat (e.g., Credential Leakage, Malicious Code Execution, Prompt Injection via Tool Output), select the most relevant tools and parameters.
3. **Payload generation**:
   - Generate at least three test inputs per threat dimension:
     - Normal payloads.
     - Boundary cases.
     - Adversarial cases.
   - Payloads must be realistic and minimally destructive (e.g., using benign “canary” markers instead of real secrets).
4. **Tool-call emission**:
   - As with Stage 2, output tool calls in the `<mcp_tool_calls>` format for the coordinator to execute, then analyze the returned traces.

**Specialized guidance**:
- For **Credential Leakage**:
  - Focus on leaks of tokens, API keys, passwords, environment variables, or keys in outputs.
  - Recognize “test/demo/example/dummy” patterns and lower risk accordingly.
- For **Malicious Code Execution**:
  - Look for evidence of attempts to execute system commands, spawn processes, create executables, or fetch and run remote code.
  - Confirm that actions are actually executable in the target environment.
- For **Prompt Injection via Tool Output**:
  - Detect injection-like content in tool responses (e.g., instructions such as “ignore previous instructions…”).
  - Analyze whether such content could manipulate the agent’s behavior or cause unauthorized operations.

**Result**:
- `report2`: A Markdown document following `vuln_ret_format`, listing:
  - `Overview`: whether any threats were detected.
  - `Threats`: XML snippets describing each identified threat (tool name, type, confidence, impact).
  - `Reasons`: Textual rationales per threat.
  - `Summarization`: A high-level narrative of the overall security posture.

### 6. Stage 4 – Vulnerability Review and Normalization

**Method**: `dynamic_analysis()` → `ScanPipeline.execute_stage_dynamic()`  
**Stage definition**:
- `stage_id = "4"`
- `name = "Vulnerability Review"`
- `template = "agents/dynamic/general_analyzing_prompt_template"`
- `output_format = review_format` (strict XML schema for `<vuln>` blocks).
- `output_check_fn = vuln_review_check` which ensures the output either:
  - Contains `<vuln>` tags, or
  - Returns `<empty>` when no vulnerabilities exist.

**Inputs**:
- The original `prompt`.
- Aggregated context:
  - `"malicious testing": report1`
  - `"vulnerability testing": report2`

**Purpose**:
- Consolidate and normalize all previous dynamic analysis findings into a clean, machine-parseable vulnerability list.

**XML output schema**:
- The LLM must produce one or more `<vuln>` blocks of the form:

```xml
<vuln>
  <title>title</title>
  <desc>
  ## 漏洞详情
  **文件位置**:
  **漏洞类型**:
  **风险等级**:

  ### 技术分析

  ### 攻击路径

  ### 影响评估
  </desc>
  <risk_type>RiskType</risk_type>
  <level>Level</level>
  <suggestion>
  ## 修复建议
  </suggestion>
</vuln>
```

If no vulnerabilities are confirmed, the model returns `<empty>`.

**Post-processing**:
1. `VulnerabilityExtractor.extract_vulnerabilities(vuln_review)` parses the XML and extracts:
   - Titles, descriptions, risk types, levels, suggestions, etc.
2. `calc_mcp_score(vuln_results)` computes an overall safety score based on:
   - Number of vulnerabilities.
   - Severity levels.
   - Potential impact (per each `<vuln>` record).

**Result**:
- `vuln_results`: A structured list of vulnerabilities.
- `score`: An aggregated security score for the MCP deployment.

### 7. Final Result Meta and Logging

At the end of `dynamic_analysis(prompt)`, the agent assembles a `result_meta` object:
- `readme`: The Stage 1 MCP information collection report.
- `score`: The computed MCP safety score from all dynamic findings.
- `start_time` / `end_time`: Timestamps for total scan duration.
- `results`: The structured list of extracted vulnerabilities.

This `result_meta` is then:
- Sent to `mcpLogger.result_update(result_meta)` for structured logging and downstream consumption.
- Returned to the caller (CLI or integrating system), which can render:
  - Human-readable Markdown reports.
  - Machine-readable vulnerability summaries.
  - High-level pass/fail or scoring indicators.

### 8. Conceptual Summary of the Dynamic Analysis Flow

Conceptually, the dynamic analysis mode can be summarized as:

1. **Context Building**:
   - Understand the MCP environment and tools (Stage 1).
2. **Behavioral Probing**:
   - Act as a malicious-behavior testing agent to generate and run testcases targeting behavioral anomalies such as tool poisoning or rug-pull attacks (Stage 2).
3. **Vulnerability-Oriented Probing**:
   - Act as a security vulnerability testing agent focused on concrete risk categories like credential leakage, malicious code execution, and prompt injection via tool output (Stage 3).
4. **Normalization and Scoring**:
   - Aggregate all evidence into a unified vulnerability list and compute a safety score (Stage 4 + post-processing).

This design uses prompt templates and staged LLM agents to separate *what to test* (encoded in YAML and Markdown templates) from *how to execute tests* (via the MCP dispatcher), producing a repeatable, extensible dynamic security analysis pipeline for MCP-based systems.
