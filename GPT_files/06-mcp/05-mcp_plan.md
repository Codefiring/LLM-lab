MCP Vulnerability Scanning Agent System — Design Plan
我希望构建一个mcp漏洞检测multiagent框架，包含如下的一些agent

代码感知agent： 负责对mcp的源码进行全面分析并总结，获取mcp的接口列表，同时对接口功能（tool， resource， prompt）等进行分析并总结。
静态漏洞分析agent：结合每个接口的相关代码进行初步的基于静态代码的漏洞扫描。对每个接口的对所要检测的漏洞类型（一共25种，用户可自定义选择）启动subagent进行代码分析扫描，汇总扫描得到的信息（是否存在该类型的漏洞，如果测试该生成什么样的测试用例，获得什么返回值）。

动态验证agent：该agent需要完成两个功能：
1. 接口功能验证
2. 当借口验证通过，进行漏洞验证

完成动态的漏洞验证并汇总结果 需要三个sub agent：
一个服务运行 sub agent 负责根据mcp代码或者用户自定义的启动命令，在隔离的docker环境中启动mcp服务，同时可能也需要启动相关的 Oauth服务。同时监控 mcp 服务的运行状态，如果卡死需要自动进行服务的重启。

一个动态测试 sub agent 负责： 1. 接口功能验证： 通过 mcp 固定的 list_tools() list_resources() 等接口访问 MCP 服务来验证 代码感知agent 获取的接口信息。
2. 漏洞验证： 
结合静态漏洞分析agent获取的漏洞相关信息，来生成相关测试并对服务进行测试验证。通过读取测试返回值或者从 服务运行 subagent 获取mcp的执行log，来验证漏洞是否存在。
    如果启用 log打印添加 sub agent。则动态测试流程会包含两个阶段： 首先在这个sub agent 辅助下完成漏洞的验证。然后使用源代码再进行一次验证避免因为 log打印添加 sub agent 引入新漏洞。

一个log打印添加 sub agent（用户可选是否启用） 负责在必要的代码位置添加 log 打印，来辅助动态测试 sub agent 来进行更精确的漏洞测试。

报告生成 agent： 对上述几个 agent 的结果进行汇总： 1. mcp服务的概述 主要功能，接口列表等 2. 存在的漏洞汇总，以及结合验证情况的分析报告。

agent 之间存在交互  
1. 如果存在 log打印添加 sub agent： 动态测试 sub agent 通知 log打印添加 sub agent 修改代码在需要的位置添加log， log打印添加 sub agent 添加完成后 通知 服务运行 sub agent 重启服务， 重启后 通知 动态测试 sub agent 继续测试。
2. 动态测试 sub agent 如果发现 mcp 服务不可访问， 通知 服务运行 sub agent 重启服务
3. 动态测试 sub agent 如果发现 代码感知agent 获取的接口信息有问题，反馈信息给 代码感知agent 并重新进行前面的 代码感知和静态漏洞分析环节。

需要检测的漏洞类型如下：
  MCP-001  Tool Poisoning (malicious tool descriptions)
  MCP-002  Prompt Injection via Tool Responses
  MCP-003  Excessive Tool Permissions
  MCP-004  Path Traversal in File System Tools
  MCP-005  Command Injection in Shell Tools
  MCP-006  SSRF via HTTP/URL Tools
  MCP-007  Authentication Bypass
  MCP-008  Unauthorized Resource Access
  MCP-009  Sensitive Data / Secret Exposure in Outputs
  MCP-010  Insecure Deserialization of Tool Inputs
  MCP-011  Race Conditions in Stateful Tools
  MCP-012  DoS via Resource Exhaustion (no rate limiting)
  MCP-013  Cross-Context State Contamination
  MCP-014  Dynamic Tool Schema Manipulation
  MCP-015  Unvalidated / Unsanitized Input in Prompts
  MCP-016  Verbose Error Messages (path/stack trace disclosure)
  MCP-017  Hardcoded Credentials in Source
  MCP-018  Insecure Transport (missing TLS)
  MCP-019  Over-Privileged Process Execution
  MCP-020  Missing Rate Limiting on Tool Invocations
  MCP-021  Log Injection
  MCP-022  Dependency / Supply Chain Vulnerabilities
  MCP-023  Insecure Default Configuration
  MCP-024  Output Length / Truncation Bypass
  MCP-025  Cross-Tool State Pollution