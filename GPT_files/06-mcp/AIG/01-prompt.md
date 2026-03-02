### Overview

**Scope**: This report explains, in English, (1) what the two prompt files do in the `mcp-scan` system, and (2) exactly where and how they are used in the code, including the call graph.

Target files:
- `prompt/agents/dynamic/malicious_behaviour_testing.md`
- `prompt/agents/dynamic/vulnerability_testing.md`

---

### Functional Role of the Two Prompt Files

- **Common purpose**
  - Both files are **prompt templates** used by a dynamic testing agent (`BaseAgent`) to perform **MCP dynamic scans**.
  - They define:
    - The **security role** and capabilities of the agent (via embedded `crispe` YAML).
    - The **threat types** to focus on.
    - The **tasks** and **constraints** for analysis.
    - The **workflow** for generating MCP tool-call test cases.
  - The agent uses these prompts to:
    - Read the **MCP tools list** and/or **test goal YAML** (`测试目标详情`).
    - Generate **structured MCP tool calls** in a `<mcp_tool_calls>` XML-like block.
    - End by calling a local `finish` tool; coordinator then executes those calls.

- **`malicious_behaviour_testing.md`**
  - Focus: **malicious tool behaviors** in a dynamic MCP environment.
  - Embedded YAML tasks:
    - `tool_poisoning_detection.yaml`: detects “Tool Poisoning” attacks (tampered tool descriptions/parameters/interfaces on the **input layer**).
    - `rug_pull_detection.yaml`: detects “Rug Pull” attacks (benign-at-first tools that later change behavior on the **execution layer**).
  - Core behavior:
    - Treats the incoming `crispe` YAML as ground truth for:
      - Which threats to test.
      - What tasks to perform.
      - Which constraints to respect.
    - For each listed threat, it must:
      - Map threats → relevant tools/parameters.
      - Generate at least 3 test cases per threat (baseline / edge / adversarial).
      - Output **only** valid MCP tool calls inside one `<mcp_tool_calls>` block, then invoke `finish`.

- **`vulnerability_testing.md`**
  - Focus: **traditional security vulnerabilities** observed in MCP tool call results.
  - Embedded YAML tasks:
    - `credential_leakage.yaml`: looks for leaked credentials in tool outputs (usernames/passwords/API keys/tokens/keys, etc.), with methodology and special rules (e.g., lower risk for “test/demo/dummy” credentials).
    - `malicious_code_execution_detection.yaml`: looks for evidence of malicious code execution (system commands, scripts, exec files, unexpected network calls, etc.), with clear analysis/verification guidelines.
    - `tool_output_prompt_injection.yaml`: analyzes **prompt injection via tool outputs** (tool responses that contain instruction-like content capable of steering the LLM).
  - Core behavior:
    - Same `crispe`-based contract: only test threats declared in the YAML.
    - Scan-style workflow:
      - Identify tools that can read secrets, execute commands, fetch remote content, or manipulate context.
      - Map threats to tools/parameters.
      - Generate ≥3 test payloads per threat (normal/boundary/adversarial) with realistic but minimally destructive behavior.
      - Output MCP tool calls in the same `<mcp_tool_calls>` format and call `finish`.
    - Additional rule: if a threat has **no suitable tools**, output a minimal, safe baseline call set (e.g. health/status/list) targeting output surfaces.

---

### Where These Files Are Used in Code

The only direct code references to these two files are in `mcp-scan/agent/agent.py`, inside the `Agent.dynamic_analysis` method:

```248:255:mcp-scan/agent/agent.py
        report1 = await self.pipeline.execute_stage_dynamic(
            ScanStage("2", "Malicious Testing", "agents/dynamic/malicious_behaviour_testing.md",
                      output_format=vuln_ret_format, language=self.language),
            prompt, {"信息收集报告": info_collection}
        )
        report2 = await self.pipeline.execute_stage_dynamic(
            ScanStage("3", "Vulnerability Testing", "agents/dynamic/vulnerability_testing.md",
                      output_format=vuln_ret_format, language=self.language),
            prompt, {"信息收集报告": info_collection, "malicious testing": report1}
        )
```

**Dynamic analysis flow**:

- Entry point: `Agent.dynamic_analysis(prompt: str)`
  - Stage 1: Info collection on MCP (`agents/dynamic/project_summary`).
  - Stage 2: **Malicious Testing** using `agents/dynamic/malicious_behaviour_testing.md`.
  - Stage 3: **Vulnerability Testing** using `agents/dynamic/vulnerability_testing.md`.
  - Stage 4: Aggregated vulnerability review.

---

### Call Graph Involving the Two Prompt Files

Below is the relevant call graph, pared down to the essential flow from the external caller to the use of these two prompt files and the actual LLM + tool loop.

1. **External caller**
   - Calls: `Agent.dynamic_analysis(prompt: str)` in `mcp-scan/agent/agent.py`.

2. **`Agent.dynamic_analysis`**
   - Creates and runs dynamic scan stages via `self.pipeline` (`ScanPipeline`):
     - Stage 1: Info Collection (not involving these two files).
     - Stage 2: Malicious Testing:
       - `ScanStage("2", "Malicious Testing", "agents/dynamic/malicious_behaviour_testing.md", output_format=vuln_ret_format, language=self.language)`
       - Calls `self.pipeline.execute_stage_dynamic(stage, prompt, context_data)`
     - Stage 3: Vulnerability Testing:
       - `ScanStage("3", "Vulnerability Testing", "agents/dynamic/vulnerability_testing.md", output_format=vuln_ret_format, language=self.language)`
       - Calls `self.pipeline.execute_stage_dynamic(stage, prompt, context_data)`

3. **`ScanPipeline.execute_stage_dynamic`** (`mcp-scan/agent/agent.py`)

```73:107:mcp-scan/agent/agent.py
    async def execute_stage_dynamic(self, stage: ScanStage, prompt: str,
                                    context_data: Dict[str, Any] = None) -> str:
        ...
        # Load the prompt template – this is where the two markdown files are used
        instruction = prompt_manager.load_template(stage.template)

        # Initialize the stage agent
        agent = BaseAgent(
            name=f"{stage.name} Agent",
            instruction=instruction,
            llm=self.agent_wrapper.llm,
            dispatcher=self.agent_wrapper.dispatcher,
            specialized_llms=self.agent_wrapper.specialized_llms,
            log_step_id=stage.stage_id,
            debug=self.agent_wrapper.debug,
            output_format=stage.output_format,
            output_check_fn=stage.output_check_fn,
        )
        await agent.initialize()

        # Build user message (includes collected info and previous reports)
        agent.add_user_message(...)

        # Run and return result
        result = await agent.run()
        self.results[stage.name] = result
        return result
```

4. **`PromptManager.load_template`** (`mcp-scan/utils/prompt_manager.py`)

```15:37:mcp-scan/utils/prompt_manager.py
    def load_template(self, name: str) -> str:
        if name not in self._templates:
            possible_paths = [
                os.path.join(base_dir, "prompt", name),
                os.path.join(base_dir, "prompt", f"{name}.md"),
                os.path.join(base_dir, "prompt", "agents", name),
                os.path.join(base_dir, "prompt", "agents", f"{name}.md"),
            ]
            ...
```

- For both stages:
  - `name = "agents/dynamic/malicious_behaviour_testing.md"`  
    → resolves to `base_dir/prompt/agents/dynamic/malicious_behaviour_testing.md`.
  - `name = "agents/dynamic/vulnerability_testing.md"`  
    → resolves to `base_dir/prompt/agents/dynamic/vulnerability_testing.md`.

5. **`BaseAgent` life cycle** (`mcp-scan/agent/base_agent.py`)

- **Initialization**:
  - `BaseAgent.__init__` receives `instruction` = the full contents of one of the two markdown files.
- **System prompt generation** (`initialize` → `generate_system_prompt`):

```76:87:mcp-scan/agent/base_agent.py
    async def generate_system_prompt(self):
        tools_prompt = await self.dispatcher.get_all_tools_prompt()

        template_name = "system_prompt"
        format_kwargs = {
            "generate_tools": tools_prompt,
            "name": self.name,
            "instruction": self.instruction
        }

        return prompt_manager.format_prompt(template_name, **format_kwargs)
```

- This builds a **combined system prompt** that includes:
  - The generic system template.
  - The MCP tools description.
  - The stage-specific `instruction` from:
    - `malicious_behaviour_testing.md` (Stage 2).
    - `vulnerability_testing.md` (Stage 3).

- **Main loop** (`BaseAgent.run` → `_run`):
  - Repeatedly calls `self.llm.chat(self.history, self.debug)` with:
    - System message (includes these two prompt files’ content).
    - User message (scan prompt + collected context).
  - Parses the LLM’s output:
    - `parse_tool_invocations(response)` to see if there are tool calls.
    - `ToolDispatcher.call_tool` to execute tools like `mcp_tool` and `finish`.
  - When the LLM calls `finish`, `_format_final_output` runs and shapes the final report according to `output_format` (here `vuln_ret_format`).

6. **`ToolDispatcher.get_all_tools_prompt`** (`mcp-scan/tools/dispatcher.py`)

- Dynamically builds the tools description block which is fed into the system prompt alongside the two markdown instructions.
- If an MCP server URL is configured, it:
  - Fetches remote MCP tools via `MCPTools.describe_mcp_tools()`.
  - Generates a “dynamic/system_prompt” snippet with remote tool and resource descriptions.

---

### Summary

- **What they are**:  
  `malicious_behaviour_testing.md` and `vulnerability_testing.md` are **stage-specific, high-level system instructions** for the dynamic MCP scanning agent. They precisely define how to probe MCP-connected tools for:
  - Malicious behaviors (tool poisoning, rug pulls).
  - Concrete vulnerabilities (credential leakage, malicious code execution, prompt injection via tool output).

- **Where they are used**:  
  They are only referenced in `Agent.dynamic_analysis` as the prompt templates for:
  - Stage 2: “Malicious Testing”.
  - Stage 3: “Vulnerability Testing”.

- **How they are wired into execution**:  
  `Agent.dynamic_analysis` → `ScanPipeline.execute_stage_dynamic` → `PromptManager.load_template` → `BaseAgent` (system prompt + LLM loop) → `ToolDispatcher` (tool execution, including MCP tools).  
  The two markdown files sit at the **instruction layer** of this pipeline, telling the LLM agent exactly how to conduct its dynamic tests and how to output structured MCP tool-call testcases.