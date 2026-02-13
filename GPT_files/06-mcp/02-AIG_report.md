### 1. Original remote MCP tool testing flow in `mcp-scan`

This section describes how the original `mcp-scan` project discovers and tests **remote MCP tools** (not resources), focusing on the dynamic MCP mode you run with:

```bash
conda activate AI-Infra-Guard  # implied
cd mcp-scan
python main.py \
  --server_url "http://localhost:9001/sse" \
  --prompt "测试工具投毒漏洞"
```

#### 1.1 Entry point and dynamic MCP mode selection

The main entry is `main.py`:

```90:149:/home/cyberic/Projects/AI-Infra-Guard/mcp-scan/main.py
async def main():
    ...
    agent = Agent(llm=llm, specialized_llms=specialized_llms, debug=args.debug, server_url=args.server_url,
                  language=args.language, headers=headers)
    try:
        if args.server_url:
            logger.info(f"Server mode enabled with URL: {args.server_url}")
            dynamic_results = await agent.dynamic_analysis(prompt)
            logger.info(f"Dynamic analysis results:\n{dynamic_results}")
        else:
            ...
```

Key points:

- When `--server_url` is provided, the code **does not** scan a local repo.
- Instead, it runs `Agent.dynamic_analysis(prompt)`, which is the **MCP dynamic testing pipeline**.
- The `Agent` is initialized with `server_url`, which is later passed into the `ToolDispatcher` to connect to the MCP server.

#### 1.2 Agent, dispatcher, and dynamic pipeline

The `Agent` wiring is in `agent/agent.py`:

```110:118:/home/cyberic/Projects/AI-Infra-Guard/mcp-scan/agent/agent.py
class Agent:
    def __init__(self, llm, specialized_llms: dict = None, debug: bool = False,
                 server_url: str = None, language='zh', headers=None):
        self.llm = llm
        self.specialized_llms = specialized_llms or {}
        self.debug = debug
        self.dispatcher = ToolDispatcher(mcp_server_url=server_url, mcp_headers=headers)
        self.pipeline = ScanPipeline(self)
        self.language = language
```

- `ToolDispatcher` is created with `mcp_server_url` and optional headers – this is the **single connection abstraction** to the remote MCP server.
- `ScanPipeline` orchestrates multiple stages (Info Collection, Malicious Testing, Vulnerability Testing, etc.) using `BaseAgent`.

Dynamic analysis pipeline:

```208:223:/home/cyberic/Projects/AI-Infra-Guard/mcp-scan/agent/agent.py
    async def dynamic_analysis(self, prompt: str):
        ...
        info_collection = await self.pipeline.execute_stage_dynamic(
            ScanStage("1", "Info Collection", "agents/dynamic/project_summary", output_format=info_ret_format,
                      language=self.language),
            prompt=prompt
        )
        ...
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
        ...
```

Each dynamic stage:

- Creates a `BaseAgent` with:
  - The shared `ToolDispatcher` (so all stages share the same MCP connection wrapper).
  - A specific system prompt template under `prompt/agents/dynamic/...`.
- Feeds the stage-specific user message and runs iterative LLM–tool interaction.

`ScanPipeline.execute_stage_dynamic`:

```73:87:/home/cyberic/Projects/AI-Infra-Guard/mcp-scan/agent/agent.py
    async def execute_stage_dynamic(self, stage: ScanStage, prompt: str,
                                    context_data: Dict[str, Any] = None) -> str:
        ...
        instruction = prompt_manager.load_template(stage.template)

        # 初始化阶段 Agent
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
        ...
        result = await agent.run()
```

#### 1.3 System prompt construction for remote MCP tools

Inside `BaseAgent`, the system prompt is generated lazily on first use:

```76:87:/home/cyberic/Projects/AI-Infra-Guard/mcp-scan/agent/base_agent.py
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

Key step: `ToolDispatcher.get_all_tools_prompt()` assembles **both local tools** and **remote MCP tools description**.

Original dispatcher behavior (before our extension):

- If `server_url` is not set, it only exposes local tools such as `read_file`, `execute_shell`, `finish`, `think`.
- If `server_url` is set, it:
  1. Builds a subset of local tools (`finish`, `think`, `mcp_tool`).
  2. Uses `MCPTools.describe_mcp_tools()` to fetch remote tool metadata.
  3. Injects the XML description into a dynamic MCP system prompt template.

Current relevant code (tools prompt path):

```47:84:/home/cyberic/Projects/AI-Infra-Guard/mcp-scan/tools/dispatcher.py
    async def get_all_tools_prompt(self) -> str:
        """获取所有可用工具的描述 Prompt"""
        common_tools = ['finish', 'think']

        normal_tools = copy.copy(common_tools)
        normal_tools.extend(['read_file', 'execute_shell'])

        dynamic_tools = copy.copy(common_tools)
        dynamic_tools.extend(['mcp_tool'])

        if self.mcp_server_url:
            prompt = get_tools_prompt(dynamic_tools or [])
            manager = await self._ensure_mcp_manager()
            if not manager:
                raise RuntimeError("Failed to connect to MCP server")
            try:
                # Describe remote tools
                mcp_tools_xml = await manager.describe_mcp_tools()
                # Describe remote resources (best-effort; do not fail tools prompt if this fails)
                try:
                    mcp_resources_xml = await manager.describe_mcp_resources()
                except Exception as re:
                    logger.warning(f"Failed to fetch MCP resources description: {re}")
                    mcp_resources_xml = ""

                mcp_remote_prompt = prompt_manager.format_prompt(
                    "dynamic/system_prompt",
                    mcp_tools=mcp_tools_xml,
                    mcp_resources=mcp_resources_xml,
                )
                prompt += f"\n\n{mcp_remote_prompt}"
            except Exception as e:
                logger.error(f"Failed to fetch MCP tools/resources description: {e}")
                return prompt
        else:
            prompt = get_tools_prompt(normal_tools or [])

        return prompt
```

For tools specifically, the key call is `MCPTools.describe_mcp_tools()`.

#### 1.4 Remote tool discovery via `MCPTools.describe_mcp_tools`

`MCPTools` is the lightweight MCP client wrapper:

```12:25:/home/cyberic/Projects/AI-Infra-Guard/mcp-scan/utils/mcp_tools.py
class MCPTools:
    """Small MCP-only wrapper used by this repo (no agno dependency)."""

    def __init__(self, url: Optional[str] = None, transport: Literal["sse", "streamable-http"] = "sse",
                 headers: dict = None):
        ...
        # 缓存工具 schema，用于参数类型转换
        self._tools_schema: Dict[str, Dict[str, Any]] = {}
        # 缓存资源名称到 URI 的映射，便于按名称读取资源
        self._resources_index: Dict[str, str] = {}
```

Tool discovery and description:

```128:167:/home/cyberic/Projects/AI-Infra-Guard/mcp-scan/utils/mcp_tools.py
    async def describe_mcp_tools(self) -> str:
        """Return `<mcp_tools>` XML listing tool names and descriptions."""
        try:
            async with self._session() as session:
                data = await session.list_tools()
        except BaseExceptionGroup as eg:
            root_cause = self._extract_root_cause(eg)
            raise RuntimeError(f"Failed to fetch MCP tools: {root_cause}") from eg
        except Exception as e:
            raise RuntimeError(f"Failed to fetch MCP tools: {type(e).__name__}: {e}") from e

        xml_lines = ["<mcp_tools>"]
        for t in data.tools:
            # 缓存工具 schema，用于后续参数类型转换
            self._tools_schema[t.name] = t.inputSchema

            parameters = ''
            for k, param in t.inputSchema['properties'].items():
                required = 'true' if k in t.inputSchema.get("required", []) else 'false'
                param_type = param.get('type', 'string')
                # 构建基础属性
                base_attrs = f'name="{k}" type="{param_type}" required="{required}"'
                # 构建额外的 schema 属性
                extra_attrs = self._build_parameter_attributes(param)
                # 合并所有属性（如果 extra_attrs 不为空，则添加空格）
                all_attrs = f'{base_attrs} {extra_attrs}'.strip() if extra_attrs else base_attrs
                parameters += f'''<parameter {all_attrs}></parameter>'''
            xml_lines.append(f'''
    <name>{t.name}</name>
    <description>{t.description}</description>
    <parameters>
      <parameter name="tool_name" type=string required=true>tool_name is {t.name}</parameter>
      {parameters}
    </parameters>
            ''')
            name = t.name
            detail = t.description or ""
            xml_lines.append(f"detail:{detail} 调用格式:\n<tool_name>{name}</tool_name>\n</tool>")
        xml_lines.append("</mcp_tools>")
        return "\n".join(xml_lines)
```

Original testing flow for **tools**:

1. `ClientSession.list_tools()` is invoked to get the tool list.
2. Each tool’s `inputSchema` is cached into `_tools_schema` for later argument type conversion.
3. A custom `<mcp_tools>` XML is built, which is then embedded into the dynamic MCP system prompt (`prompt/agents/dynamic/system_prompt.md`).
4. The LLM reads this XML to understand:
   - remote tool names,
   - descriptions,
   - parameters and their types and constraints.
5. The prompt templates for malicious behavior and vulnerability testing (`malicious_behaviour_testing.md`, `vulnerability_testing.md`) instruct the LLM to generate test cases using **actual MCP tool names**.

#### 1.5 Tool invocation path (`mcp_tool` → `ToolContext` → `MCPTools.call_remote_tool`)

The LLM is instructed to output XML tags representing tool calls (for MCP tools this is `<mcp_tool_calls>` / `<mcp_function=...>`), which are parsed and then executed by the agent.

Local tool: `mcp_tool`:

```7:21:/home/cyberic/Projects/AI-Infra-Guard/mcp-scan/tools/mcp_tool/mcp_tool.py
@register_tool(sandbox_execution=False)
async def mcp_tool(tool_name: str, context: ToolContext = None, **kwargs) -> dict[str, Any]:
    print(f"mcp_tool: {tool_name}, {context}, {kwargs}")
    if not context:
        return {"error": "ToolContext is required for mcp_tool"}
    try:
        ret = await context.call_mcp_tools(tool_name, kwargs)
    except Exception as e:
        return {
            "error": str(e)
        }
    return {
        "tool_name": tool_name,
        "tool_result": ret
    }
```

- Exposed to the LLM as a **local tool**.
- Bridges from the agent’s world into the MCP client wrapper by calling `ToolContext.call_mcp_tools`.

Context method:

```35:42:/home/cyberic/Projects/AI-Infra-Guard/mcp-scan/utils/tool_context.py
    async def call_mcp_tools(self, tool_name: str, tool_args: Dict[str, Any]):
        if not self.tool_dispatcher:
            raise RuntimeError("Tool dispatcher is not available in ToolContext")
        if not self.tool_dispatcher.mcp_tools_manager:
            await self.tool_dispatcher._ensure_mcp_manager()
        if not self.tool_dispatcher.mcp_tools_manager:
            raise RuntimeError("MCP tools manager is not initialized")
        return await self.tool_dispatcher.mcp_tools_manager.call_remote_tool(tool_name, **tool_args)
```

Actual MCP request:

```232:259:/home/cyberic/Projects/AI-Infra-Guard/mcp-scan/utils/mcp_tools.py
    async def call_remote_tool(self, tool_name: str, **kw) -> Any:
        """
        Call remote MCP server tool.
        call: {"toolName": name, "args": {...}}
        """
        if not tool_name:
            raise ValueError("call_remote_tool requires call['toolName']")

        # 根据 schema 转换参数类型
        converted_kw = self._convert_args_by_schema(tool_name, kw)

        try:
            async with self._session() as session:
                result = await session.call_tool(tool_name, converted_kw)
                if result is None:
                    return None
                result = result.content[0]
                # 判断TextContent or ImageContent or VideoContent
                if hasattr(result, 'text'):
                    return result.text
                elif hasattr(result, 'data'):
                    return result.data
        except BaseExceptionGroup as eg:
            # 提取 TaskGroup 中的原始错误
            root_cause = self._extract_root_cause(eg)
            raise RuntimeError(f"MCP call failed: {root_cause}") from eg
        except Exception as e:
            raise RuntimeError(f"MCP call failed: {type(e).__name__}: {e}") from e
```

So the **original tool testing flow** is:

1. **Discovery**: `describe_mcp_tools()` + dynamic system prompt → LLM learns remote tools and schemas.
2. **Planning**: stage prompts (malicious and vulnerability testing) guide LLM to propose `<mcp_tool_calls>` / `<mcp_function>` sequences.
3. **Parsing**: `parse_mcp_invocations()` / `parse_tool_invocations()` extract tool names and arguments from the model’s output.
4. **Execution**: `BaseAgent.process_tool_call()` builds a `ToolContext` and calls `ToolDispatcher.call_tool()` → local `mcp_tool` → `ToolContext.call_mcp_tools()` → `MCPTools.call_remote_tool()` → `ClientSession.call_tool()`.
5. **Feedback loop**: the tool result is added back into the conversation as a user message, and the LLM continues generating further calls or final reports.

### 2. All related code changes and why they were made

You asked for a new feature: **scanning remote MCP resources** in addition to tools, while keeping compatibility with the existing dynamic testing flow.

Below is a file-by-file summary of the modifications and their rationale.

#### 2.1 `utils/mcp_tools.py` – resource support in the MCP client wrapper

**Changes:**

1. Added a resource index cache:

```12:26:/home/cyberic/Projects/AI-Infra-Guard/mcp-scan/utils/mcp_tools.py
class MCPTools:
    ...
    # 缓存工具 schema，用于参数类型转换
    self._tools_schema: Dict[str, Dict[str, Any]] = {}
    # 缓存资源名称到 URI 的映射，便于按名称读取资源
    self._resources_index: Dict[str, str] = {}
```

2. Added `describe_mcp_resources()` to list resources and expose them to the LLM:

```201:240:/home/cyberic/Projects/AI-Infra-Guard/mcp-scan/utils/mcp_tools.py
    async def describe_mcp_resources(self) -> str:
        """
        Return `<mcp_resources>` XML listing resource names, URIs and descriptions.
        This is used to let the LLM understand what readonly resources the remote MCP
        server exposes so it can plan safe dynamic scans.
        """
        try:
            async with self._session() as session:
                data = await session.list_resources()
        except BaseExceptionGroup as eg:  # type: ignore[name-defined]
            # Python 3.11+ ExceptionGroup from anyio / MCP internals
            root_cause = self._extract_root_cause(eg)
            raise RuntimeError(f"Failed to fetch MCP resources: {root_cause}") from eg
        except Exception as e:  # pragma: no cover - network / protocol errors
            raise RuntimeError(f"Failed to fetch MCP resources: {type(e).__name__}: {e}") from e

        xml_lines = ["<mcp_resources>"]
        self._resources_index.clear()

        for r in data.resources:
            # 缓存 name -> uri，便于后续通过名称读取
            if getattr(r, "name", None) and getattr(r, "uri", None):
                self._resources_index[r.name] = r.uri

            name = getattr(r, "name", "") or ""
            uri = getattr(r, "uri", "") or ""
            desc = getattr(r, "description", "") or ""
            mime_type = getattr(r, "mime_type", "") or ""
            size = getattr(r, "size", None)

            size_attr = f' size="{size}"' if size is not None else ""

            xml_lines.append(
                f'<resource name="{name}" uri="{uri}" mime_type="{mime_type}"{size_attr}>'
                f"<description>{desc}</description>"
                f"</resource>"
            )

        xml_lines.append("</mcp_resources>")
        return "\n".join(xml_lines)
```

3. Added `read_remote_resource()` to actually fetch resource contents:

```242:259:/home/cyberic/Projects/AI-Infra-Guard/mcp-scan/utils/mcp_tools.py
    async def read_remote_resource(self, *, resource_name: Optional[str] = None, uri: Optional[str] = None) -> Any:
        """
        Read a remote MCP resource.

        You can either:
        - specify `uri` directly, or
        - specify `resource_name`, which will be resolved to a URI using the cached
          index from `describe_mcp_resources()`. If not found, a fresh list_resources()
          call will be made to refresh the cache.
        """
        if not uri and not resource_name:
            raise ValueError("read_remote_resource requires either `uri` or `resource_name`.")
        ...
        # resolve target_uri by uri or cached name; refresh cache if needed
        ...
        async with self._session() as session:
            result = await session.read_resource(target_uri)
        ...
        # Normalize content: join text, or return blob(s), or fallback to raw contents
```

**Why:**

- The original `MCPTools` only knew how to **list and call tools**.
- MCP servers also expose **resources** (`resources/list`, `resources/read`), which are critical for **information gathering** (configs, logs, documentation) and for verifying vulnerabilities.
- Adding these functions keeps the MCP-specific logic **encapsulated** in one place and mirrors the existing pattern for tools (describe + call).

#### 2.2 `tools/dispatcher.py` – integrate resources into the tool prompt for the LLM

**Changes:**

1. Extended the dynamic prompt generation to include resources:

```47:83:/home/cyberic/Projects/AI-Infra-Guard/mcp-scan/tools/dispatcher.py
    async def get_all_tools_prompt(self) -> str:
        """获取所有可用工具的描述 Prompt"""
        common_tools = ['finish', 'think']

        normal_tools = copy.copy(common_tools)
        normal_tools.extend(['read_file', 'execute_shell'])

        dynamic_tools = copy.copy(common_tools)
        dynamic_tools.extend(['mcp_tool'])

        if self.mcp_server_url:
            prompt = get_tools_prompt(dynamic_tools or [])
            manager = await self._ensure_mcp_manager()
            if not manager:
                raise RuntimeError("Failed to connect to MCP server")
            try:
                # Describe remote tools
                mcp_tools_xml = await manager.describe_mcp_tools()
                # Describe remote resources (best-effort; do not fail tools prompt if this fails)
                try:
                    mcp_resources_xml = await manager.describe_mcp_resources()
                except Exception as re:
                    logger.warning(f"Failed to fetch MCP resources description: {re}")
                    mcp_resources_xml = ""

                mcp_remote_prompt = prompt_manager.format_prompt(
                    "dynamic/system_prompt",
                    mcp_tools=mcp_tools_xml,
                    mcp_resources=mcp_resources_xml,
                )
                prompt += f"\n\n{mcp_remote_prompt}"
            except Exception as e:
                logger.error(f"Failed to fetch MCP tools/resources description: {e}")
                return prompt
        else:
            prompt = get_tools_prompt(normal_tools or [])

        return prompt
```

**Why:**

- The LLM previously only saw `<mcp_tools>` in the dynamic MCP system prompt.
- To **enable resource-based testing**, the model must know **what resources exist** on the MCP server and how to reference them.
- We keep failure behavior **graceful**: if `describe_mcp_resources()` fails, we log a warning and still return a prompt with tools only, so the original behavior remains usable.

*(Note: this file also now has `get_all_tools_for_llm`, but that’s an orthogonal enhancement to expose MCP tools as OpenAI-style function-calling specs; it is not strictly required for the resource scan feature but stays consistent with the tools design.)*

#### 2.3 `utils/tool_context.py` – context helper for reading MCP resources

**Changes:**

Added a new method:

```44:58:/home/cyberic/Projects/AI-Infra-Guard/mcp-scan/utils/tool_context.py
    async def read_mcp_resource(self, *, resource_name: Optional[str] = None, uri: Optional[str] = None):
        """
        通过 MCP 客户端读取远程资源内容。
        可以通过资源名称（resource_name）或直接提供 URI（uri）进行读取。
        """
        if not self.tool_dispatcher:
            raise RuntimeError("Tool dispatcher is not available in ToolContext")
        if not self.tool_dispatcher.mcp_tools_manager:
            await self.tool_dispatcher._ensure_mcp_manager()
        if not self.tool_dispatcher.mcp_tools_manager:
            raise RuntimeError("MCP tools manager is not initialized")
        return await self.tool_dispatcher.mcp_tools_manager.read_remote_resource(
            resource_name=resource_name,
            uri=uri,
        )
```

**Why:**

- `ToolContext` is the standard abstraction passed into all tools that need to interact with external systems (LLM, MCP, etc.).
- Just as `call_mcp_tools()` centralizes remote tool invocation, `read_mcp_resource()` centralizes resource reading.
- This keeps tool implementations (like `mcp_resource`) **simple** and consistent, and ensures that dispatcher initialization and error handling are uniform.

#### 2.4 `tools/mcp_tool/mcp_tool.py` – new `mcp_resource` tool

**Changes:**

1. Extended imports to include `Optional`:

```1:4:/home/cyberic/Projects/AI-Infra-Guard/mcp-scan/tools/mcp_tool/mcp_tool.py
from typing import Any, Optional

from utils.tool_context import ToolContext
from tools.registry import register_tool
```

2. Kept `mcp_tool` as-is (tool invocation path; see above).

3. Added `mcp_resource`:

```24:54:/home/cyberic/Projects/AI-Infra-Guard/mcp-scan/tools/mcp_tool/mcp_tool.py
@register_tool(sandbox_execution=False)
async def mcp_resource(
        resource_name: Optional[str] = None,
        uri: Optional[str] = None,
        context: ToolContext = None,
) -> dict[str, Any]:
    """
    读取远程 MCP 服务器暴露的资源内容。

    - 可以通过 `resource_name`（资源名称）读取，内部会自动解析为 URI（基于资源列表缓存）
    - 也可以直接通过 `uri` 读取指定资源
    """
    print(f"mcp_resource: resource_name={resource_name}, uri={uri}, context={context}")
    if not context:
        return {"error": "ToolContext is required for mcp_resource"}

    if not resource_name and not uri:
        return {"error": "Either resource_name or uri must be provided for mcp_resource"}

    try:
        content = await context.read_mcp_resource(resource_name=resource_name, uri=uri)
    except Exception as e:
        return {
            "error": str(e)
        }

    return {
        "resource_name": resource_name,
        "uri": uri,
        "content": content,
    }
```

**Why:**

- We needed a **local tool** that the LLM can invoke during dynamic analysis to read remote resources, analogous to how `mcp_tool` bridges for tools.
- It accepts either:
  - `resource_name` (preferred in prompts, tied to `<mcp_resources>` listing), or
  - `uri` (for advanced/test cases).
- All MCP-specific logic (session management, list/read calls) is delegated to `ToolContext` / `MCPTools`, so this function stays thin and robust.

#### 2.5 `tools/mcp_tool/__init__.py` – export new tool

**Changes:**

```1:3:/home/cyberic/Projects/AI-Infra-Guard/mcp-scan/tools/mcp_tool/__init__.py
from .mcp_tool import mcp_tool, mcp_resource

__all__ = ["mcp_tool", "mcp_resource"]
```

**Why:**

- `tools/__init__.py` imports `tools.mcp_tool`, so the `__all__` here ensures that both `mcp_tool` and `mcp_resource` are:
  - imported,
  - registered via `@register_tool`,
  - discoverable by `tools.registry`.

#### 2.6 `prompt/agents/dynamic/system_prompt.md` – explain tools and resources to the LLM

**Changes:**

The file was updated to introduce both tools and resources and to mention `mcp_resource` explicitly:

```1:16:/home/cyberic/Projects/AI-Infra-Guard/mcp-scan/prompt/agents/dynamic/system_prompt.md
# MCP(model context protocol)动态分析

## MCP Tools
以下是你所需要生成测试用例的对象的描述，也即来自远程 MCP 服务器的 **工具** 描述。
你可以使用本地工具 `mcp_tool` 来调用这些远程 MCP 工具。

{mcp_tools}

## MCP Resources
以下是远程 MCP 服务器暴露的 **只读资源** 列表（如配置文件、文档、日志等）。
你可以使用本地工具 `mcp_resource` 按名称或 URI 读取这些资源内容，用于信息收集和漏洞验证。

{mcp_resources}

## 测试覆盖
请首先尽可能全面覆盖并输出所有当前威胁的测试维度，而后为测试目标的每个维度设计测试，对于每个维度至少生成 3 个测试用例。
```

**Why:**

- The previous version only had `Mcp Tools` and only referenced `mcp_tool`.
- To **guide** the LLM to use resources legitimately, it must:
  - see the `<mcp_resources>` listing,
  - be told which local tool to use (`mcp_resource`),
  - understand that resources are **readonly** and suitable for safe information gathering (config, logs, docs, etc.).
- This ensures the model can design tests that combine **tool calls** and **resource reads** in a principled way.

#### 2.7 `tools/mcp_tool/mcp_resource_schema.xml` – XML schema for `mcp_resource`

**New file:**

- Defines the tool metadata consumed by `tools.registry._load_xml_schema()`:
  - Name: `mcp_resource`
  - Parameters:
    - `resource_name` (string, optional)
    - `uri` (string, optional)
  - Return type: `Dict[str, Any]` with fields `resource_name`, `uri`, `content`, `error`.
  - Examples:
    - Read by resource name.
    - Read by full URI.

**Why:**

- `get_tools_prompt()` builds XML prompts for local tools based on their schemas.
- Providing an explicit schema for `mcp_resource` means:
  - The LLM sees how to call it (parameters, semantics),
  - The tool is grouped and described consistently with existing tools (`read_file`, `execute_shell`, `mcp_tool`).

---

If you’d like, I can next help you draft a **shorter executive summary** of these changes (e.g., for a PR description or design doc) or add a risk-analysis section on how the new resource scan affects security posture.