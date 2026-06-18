OpenCode TUI 中运行

这是推荐方案：

/mcp-scan http://127.0.0.1:3333/sse

使用：

Command → Plugin Tool → Detector Core
终端中运行真正的子命令

目前 OpenCode 文档提供的是内置 opencode agent、opencode mcp、opencode serve 等子命令，没有文档化的插件 API 可以注册新的顶层子命令，例如：

opencode mcp-scan http://127.0.0.1:3333/sse

这种需求建议提供伴生二进制：

opencode-mcp-scan http://127.0.0.1:3333/sse

或者：

mcp-detector scan http://127.0.0.1:3333/sse

OpenCode 内部使用 /mcp-scan，CI/CD 和自动化脚本使用 mcp-detector scan，两者共用同一个 detector-core，避免逻辑重复。

最终推荐结构
                          ┌─────────────────────┐
                          │ detector-core       │
                          │ MCP Top 25 检测逻辑 │
                          └──────────┬──────────┘
                                     │
                     ┌───────────────┴───────────────┐
                     │                               │
          ┌──────────▼──────────┐         ┌──────────▼──────────┐
          │ OpenCode Plugin     │         │ Standalone CLI      │
          │ 注册 mcp_scan Tool  │         │ mcp-detector scan   │
          └──────────┬──────────┘         └─────────────────────┘
                     │
          ┌──────────▼──────────┐
          │ /mcp-scan <url>     │
          │ OpenCode Command    │
          └─────────────────────┘

其中最重要的改造是：

// 不要在插件内部再次启动 OpenCode
createOpencode()

// 改为复用插件传入的 SDK client
runDetector({
  client: pluginContext.client,
})

这样既可以作为 OpenCode 原生工具运行，也能继续保留你现有的独立检测器 CLI。