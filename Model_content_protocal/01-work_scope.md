请帮我撰写一份 Shadow mcp server detection 的 work scope 文档。

我需要在企业中实现一套 shadow mcp server 的监控系统以实时监控个人 pc 中未授权的 shadow mcp server使用。

我初步的方案如下：

基于 mcp 的特征：检测方案围绕三个方面： mcp 服务的配置文件， mcp stdio 本机实现的进程检测， 以及基于网络流量抓包识别的 mcp server 探测。

1. 先对 pc 中运行的 mcp server 进行检测。
mcp 服务的配置文件： 通过对常见mcp配置的mcp.json 文件进行扫描来获取系统中的 mcp 服务
mcp stdio 本机实现的进程检测： 在进程树中识别 mcp 服务的特征，一般是由 ai agent 进程的 subprocess 等特征
基于网络流量抓包识别： mcp 服务的数据包具有显著的特征，可以通过流量分析来识别系统中的server。 如果数据包明文传输则直接基于内容判断，如果加密了请给出一定的可行方案

2. 获取 mcp server 后

对 mcp server 进行比对，确认其是否在 management portal 中进行了注册，否则判定为shadow server

该系统应该是 client server 模式的，
个人pc端： 运行检测的client端，负责进行本地扫描和识别任务，同时上报shadow server使用
IT管理员端： 运行server， 通过 user management 监控 client的上线，获取上报的信息，及时告警和记录。

请根据这个设计帮我完成文档：

文档大纲如下：

1. Define System Boundaries and Context
1.1 Create a system context diagram
Illustrate the interactions between the system and external systems, users, and third-party services. This clarify what the system does and does not do
1.2 Define Inputs and Outputs
Clearly identify the system's data sources, output results, and interface specifications with external systems
1.3 Identify Integration Scop
Specify which systems need to be integrated (e.g. AI agent, MCP client, MCP server and LLM model, etc) and determin the integration methods（Packet  analysis, file descovery）
2. Decompose Functional and Non-functional Requirements
2.1 Functional Requirements
(Important) List core functional modules of the system, such as user management, order processing and report generation. These can be described using use case diagrams or user stories.
2.2 Non-Functional Requirements
Specify requirements related to performance, availability, security, scalability, and compliance


好，这个需求本身就**非常企业级 + 可落地**，而且你的初始设计思路是对的。我会在**不改变你核心方案的前提下**，帮你把它整理成一份**可直接进入立项 / 评审 / 安全架构评估**的 **Shadow MCP Server Detection – Work Scope 文档**。

我会注意三点：

* 用**企业安全/IT 能接受的语言**（不是研究论文）
* 明确 **“做什么 / 不做什么” 的系统边界**
* 把 **stdio / config / network** 三条检测链路说清楚，并给出**加密流量可行方案**

---

# Shadow MCP Server Detection

## Work Scope & System Definition Document

---

## 1. Define System Boundaries and Context

### 1.1 System Overview

The **Shadow MCP Server Detection System** is an enterprise security monitoring solution designed to **identify, classify, and report unauthorized MCP servers running on employee personal computers (PCs)**.

The system focuses on **local MCP server discovery and usage monitoring**, not on blocking legitimate MCP workflows by default. Policy enforcement (block / warn / allow) can be layered later.

The system follows a **Client–Server architecture**:

* **Endpoint Client (Agent)**
  Deployed on employee PCs, responsible for local detection, analysis, and reporting.

* **Management Server (Portal)**
  Operated by IT/Security teams for registration management, correlation, alerting, and auditing.

---

### 1.2 System Boundary Definition

#### In Scope

* Detection of **locally running MCP servers**, including:

  * File-based MCP configurations
  * Local stdio-based MCP implementations
  * Network-exposed MCP services
* Identification of **unauthorized (Shadow) MCP servers**
* Reporting and alerting to centralized IT systems
* Metadata-level traffic inspection (no full content exfiltration)

#### Out of Scope

* Deep inspection of LLM internal reasoning
* Blocking or modifying MCP protocol behavior by default
* Cloud-hosted MCP servers outside the endpoint device
* Non-MCP AI services (unless explicitly extended)

---

### 1.3 System Context Diagram (Textual)

```
+--------------------+          +----------------------+
|   Employee PC      |          |   Management Portal  |
|                    |  Report  |                      |
|  +--------------+  +--------> |  - MCP Registry      |
|  | MCP Detector |             |  - User Management   |
|  | (Client)     | <--------+  |  - Alerting Engine   |
|  +--------------+  Policy     |  - Audit Logs        |
|        |                               |
|        |                               |
|   +----v----+                          |
|   | AI Agent|                          |
|   | / MCP   |                          |
|   | Server  |                          |
|   +---------+                          |
+---------------------------------------+
```

---

## 2. Define Inputs and Outputs

### 2.1 Inputs

| Category    | Input Type              | Description                                             |
| ----------- | ----------------------- | ------------------------------------------------------- |
| File System | MCP configuration files | `mcp.json`, `.mcp/config`, custom MCP manifests         |
| Process     | OS process metadata     | Process tree, parent-child relationship, stdio bindings |
| Network     | Packet / flow metadata  | TCP/HTTP/WebSocket traffic, ports, TLS fingerprints     |
| Management  | MCP registry            | Authorized MCP server definitions                       |

---

### 2.2 Outputs

| Output                     | Description                                  |
| -------------------------- | -------------------------------------------- |
| Shadow MCP Detection Event | Identified unauthorized MCP server           |
| MCP Server Inventory       | List of all detected MCP servers on endpoint |
| Alert                      | Real-time notification to IT administrators  |
| Audit Log                  | Forensics-ready historical records           |

---

### 2.3 Interfaces

* **Client → Server**

  * Secure reporting API (HTTPS / mTLS)
  * Event-based push model
* **Server → Admin**

  * Web dashboard
  * SIEM / SOAR integration (optional)

---

## 3. Identify Integration Scope

### 3.1 Integrated Components

| Component  | Integration Method                     |
| ---------- | -------------------------------------- |
| AI Agent   | Process inspection / execution context |
| MCP Client | Config discovery / IPC tracing         |
| MCP Server | Network & stdio behavior analysis      |
| LLM Model  | Not directly integrated (context only) |

---

### 3.2 Detection Methods Mapping

| MCP Type         | Detection Technique                        |
| ---------------- | ------------------------------------------ |
| Config-based MCP | File discovery & parsing                   |
| stdio MCP        | Process tree & IPC pattern analysis        |
| Network MCP      | Packet inspection & traffic fingerprinting |

---

## 4. Decompose Functional Requirements

### 4.1 Functional Requirements

#### FR-1 Endpoint MCP Discovery

The client **MUST** detect MCP servers using multiple independent signals:

##### 4.1.1 MCP Configuration File Detection

* Scan for known MCP configuration patterns:

  * `mcp.json`
  * `.mcp/`
  * Tool-specific MCP manifests
* Extract:

  * Server name
  * Transport type
  * Command / binary path
* Hash and normalize configs to avoid duplication

---

##### 4.1.2 stdio-based MCP Process Detection

For stdio-based MCP servers (local-only, no port exposure):

* Monitor:

  * Subprocess spawned by AI agent processes
  * Processes with stdin/stdout pipes bound to parent
* Identify MCP traits:

  * JSON-RPC message framing
  * MCP handshake patterns
* Build **Process Ancestry Graph**

  * Agent → MCP Server subprocess

---

##### 4.1.3 Network-based MCP Detection

For network-exposed MCP servers:

**Plaintext Traffic**

* Detect:

  * MCP JSON-RPC schema patterns
  * Known MCP endpoints (`/mcp`, `/tools`, etc)

**Encrypted Traffic (TLS / WSS)**
When payload inspection is unavailable:

* TLS fingerprinting (JA3 / JA4)
* Behavioral features:

  * Long-lived bidirectional sessions
  * High-frequency request-response symmetry
* Endpoint context correlation:

  * Same process owning listening socket
* Optional:

  * Local TLS MITM (enterprise-managed devices only)

---

#### FR-2 Shadow MCP Classification

Once an MCP server is identified:

* Query Management Portal MCP Registry
* Match by:

  * Binary hash
  * Config fingerprint
  * Endpoint + protocol
* If **no match found → classify as Shadow MCP Server**

---

#### FR-3 Client Reporting

Client **MUST** report:

* MCP server metadata
* Detection method
* Confidence score
* User and device identity

---

#### FR-4 Centralized Management & Alerting

Management Portal **MUST** provide:

* Endpoint online/offline tracking
* MCP server inventory per user/device
* Real-time alerting for Shadow MCP usage
* Historical audit & export

---

## 5. Non-Functional Requirements

### 5.1 Performance

| Metric            | Requirement  |
| ----------------- | ------------ |
| CPU overhead      | < 5% average |
| Memory usage      | < 200MB      |
| Detection latency | < 10 seconds |

---

### 5.2 Availability & Reliability

* Client operates offline and syncs when online
* Server supports HA deployment
* Event delivery guarantees (at-least-once)

---

### 5.3 Security

* Mutual TLS between client and server
* Tamper-resistant client agent
* Least-privilege OS permissions
* No raw payload exfiltration by default

---

### 5.4 Scalability

* Horizontal scaling of management server
* Designed for **10k–100k endpoints**
* Stateless client reporting

---

### 5.5 Compliance & Privacy

* Minimal data collection
* Metadata-first inspection
* Configurable data retention
* Aligns with:

  * Enterprise endpoint monitoring policies
  * Data protection regulations (GDPR / local equivalents)

---

## 6. Summary

This system provides a **defense-in-depth approach** to Shadow MCP Server detection by combining:

* File-level discovery
* Process-level behavioral analysis
* Network-level traffic fingerprinting

It enables enterprises to **gain visibility, assess risk, and respond** to unauthorized MCP server usage **without disrupting legitimate AI workflows**.

---

如果你愿意，下一步我可以直接帮你做三件事之一（你选）：

1️⃣ **把这个 work scope 转成安全架构评审版（Threat Model / STRIDE）**
2️⃣ **补一份“Shadow MCP Detection Rules Playbook”（规则+日志+示例）**
3️⃣ **拆成产品级 Roadmap（MVP / Phase 2 / Phase 3）**

你这个方向，已经非常像一个**下一代 Endpoint AI Security 产品了**。
