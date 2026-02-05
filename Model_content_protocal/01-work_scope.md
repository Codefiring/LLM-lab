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



明白 👍
下面我将**严格、逐条、不扩展、不跳级**，**完全按照你给定的大纲结构**来重写这份 **Shadow MCP Server Detection – Work Scope 文档**。
内容会保持**企业可实施性 + 技术可审计性**，但**不引入任何额外章节或顺序调整**。

---

# Shadow MCP Server Detection

## Work Scope Document

---

## 1. Define System Boundaries and Context

### 1.1 Create a System Context Diagram

The Shadow MCP Server Detection System is designed to operate within an enterprise-managed endpoint environment to detect unauthorized MCP servers running on personal PCs.

The system consists of two core components:

* **Endpoint Client (Detection Agent)**:
  Installed on employee PCs, responsible for local detection of MCP servers through file scanning, process inspection, and network traffic analysis.

* **Central Management Server (Management Portal)**:
  Operated by IT administrators, responsible for MCP server registration management, client monitoring, alerting, and audit logging.

**External entities interacting with the system include:**

* Employees (end users)
* AI agents running on endpoints
* MCP clients and MCP servers
* Enterprise identity and access management systems (optional)
* Security monitoring systems (SIEM/SOAR, optional)

The system **does not** modify MCP behavior, interfere with LLM inference, or block traffic by default. Its primary responsibility is **visibility, identification, and reporting** of Shadow MCP servers.

---

### 1.2 Define Inputs and Outputs

#### Inputs

The system consumes the following inputs:

1. **File System Inputs**

   * MCP configuration files such as `mcp.json`
   * MCP-related directories (e.g. `.mcp/`)
   * Tool- or framework-specific MCP manifests

2. **Process and Runtime Inputs**

   * Operating system process lists
   * Process parent–child relationships
   * Standard input/output (stdio) pipe bindings
   * Command-line arguments and execution paths

3. **Network Inputs**

   * Network packet metadata
   * Flow-level information (source/destination, ports, protocol)
   * TLS handshake metadata for encrypted traffic

4. **Management Inputs**

   * Authorized MCP server registry maintained in the management portal
   * User and device identity information

---

#### Outputs

The system produces the following outputs:

1. **Detected MCP Server Records**

   * Metadata describing each detected MCP server instance
   * Detection method(s) used
   * Confidence level

2. **Shadow MCP Classification Results**

   * Determination of whether a detected MCP server is registered or unregistered

3. **Alerts and Notifications**

   * Real-time alerts to IT administrators for Shadow MCP server usage

4. **Audit and Reporting Data**

   * Historical logs for investigation and compliance purposes

---

### 1.3 Identify Integration Scope

This system integrates with the following components and technologies:

#### Integrated Systems

* AI agents running on employee PCs
* MCP clients invoking MCP servers
* MCP servers implemented via stdio or network interfaces
* Enterprise management and monitoring infrastructure

#### Integration Methods

* **File Discovery**
  Used to identify MCP configuration files and local MCP definitions.

* **Process Inspection**
  Used to detect stdio-based MCP server implementations through process trees and IPC characteristics.

* **Packet / Flow Analysis**
  Used to identify network-based MCP servers via protocol behavior and traffic patterns.

No direct integration with LLM model internals is required.

---

## 2. Decompose Functional and Non-functional Requirements

### 2.1 Functional Requirements

The system shall provide the following core functional capabilities.

---

#### FR-1 MCP Server Detection on Endpoint PCs

The endpoint client shall detect MCP servers using three complementary techniques.

**FR-1.1 MCP Configuration File Detection**

* Scan local file systems for known MCP configuration patterns (e.g. `mcp.json`)
* Parse configuration content to extract MCP server definitions
* Record server metadata such as command, transport type, and execution context

---

**FR-1.2 stdio-based MCP Process Detection**

* Monitor running processes and process trees
* Identify MCP servers implemented as subprocesses of AI agents
* Detect stdio-based communication patterns consistent with MCP usage
* Correlate parent AI agent processes with child MCP server processes

---

**FR-1.3 Network-based MCP Server Detection**

* Monitor local network activity to identify MCP server behavior
* For plaintext traffic:

  * Inspect payloads for MCP protocol and JSON-RPC characteristics
* For encrypted traffic:

  * Use flow-based analysis (connection duration, request/response symmetry)
  * Correlate network sockets with owning processes
  * Leverage TLS handshake metadata and fingerprinting where available

---

#### FR-2 MCP Server Registration Verification

* For each detected MCP server, the client or server shall verify registration status against the management portal
* Matching may be based on:

  * Configuration fingerprint
  * Binary hash
  * Endpoint and protocol characteristics
* MCP servers not found in the registry shall be classified as **Shadow MCP Servers**

---

#### FR-3 Client Reporting and Telemetry

* Endpoint clients shall securely report detection results to the management server
* Reports shall include:

  * MCP server metadata
  * Detection method
  * Timestamp
  * User and device identity

---

#### FR-4 Centralized Monitoring and Alerting

The management server shall:

* Maintain a real-time view of connected clients
* Aggregate MCP server detection data
* Trigger alerts upon detection of Shadow MCP servers
* Provide audit logs and historical reports for administrators

---

### 2.2 Non-Functional Requirements

#### Performance

* Endpoint detection shall operate with minimal CPU and memory overhead
* Detection activities shall not noticeably impact user workflows

---

#### Availability

* Endpoint clients shall continue operating during temporary network outages
* Management server shall support high availability deployment models

---

#### Security

* All client–server communication shall be encrypted
* Endpoint agents shall follow least-privilege principles
* Detection mechanisms shall minimize exposure of sensitive user data

---

#### Scalability

* The system shall support enterprise-scale deployments (thousands to tens of thousands of endpoints)
* Management server components shall be horizontally scalable

---

#### Compliance and Privacy

* Data collection shall be limited to what is necessary for MCP detection
* Raw content inspection shall be minimized or avoided where possible
* Audit logs shall support compliance and internal security reviews

---

如果你需要，下一步我可以在**不破坏这个大纲结构**的前提下，继续帮你做：

* ✅ **把每个 FR 拆成可实现的技术子任务（工程视角）**
* ✅ **补一份 detection coverage matrix（config / stdio / network × 明文 / 加密）**
* ✅ **改写成可直接用于安全评审或招标的正式英文版本**

你可以直接告诉我：**“下一步做哪一个”**。


好的，下面我将**严格保持原有结构与语义**，把 **Client / Server 模块总结表**完整、专业地**转成英文**，语言风格对齐 **enterprise security / architecture / work scope 文档**，可直接用于 **设计说明、评审材料或招标文档**。

---

# Shadow MCP Server Detection

## Client / Server Module Breakdown

---

## Client Side – Endpoint Detection Agent Modules

| Module Name                   | Description                                                                                                                                                                                                                                                                                                                                           |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| MCP Config Scanner            | Scans the local file system for MCP-related configuration files (such as `mcp.json`, `.mcp/` directories, or tool-specific MCP manifests). It parses MCP server definitions to extract execution commands, transport types, and paths. This module focuses on static discovery only and does not execute or modify any configuration.                 |
| Process & stdio Detector      | Monitors operating system processes and process trees to identify MCP servers implemented as subprocesses of AI agents. It analyzes stdin/stdout communication patterns to detect stdio-based MCP servers, addressing the visibility gap of local MCP services that do not expose network ports.                                                      |
| Network Traffic Analyzer      | Observes local network activity to identify MCP server behavior. For plaintext traffic, it detects MCP/JSON-RPC protocol characteristics. For encrypted traffic, it relies on behavioral features such as connection patterns, traffic symmetry, timing characteristics, and TLS metadata, without depending on specific ports or payload inspection. |
| MCP Signal Correlator         | Correlates and deduplicates signals collected from configuration scanning, process inspection, and network analysis to construct a unified view of detected MCP server instances. This module improves detection accuracy and reduces false positives caused by single-signal analysis.                                                               |
| Shadow MCP Classifier         | Performs preliminary classification of detected MCP servers by comparing correlated MCP metadata against known authorized identifiers. It assigns a Shadow MCP indication and confidence score, while final authorization decisions are performed by the server-side components.                                                                      |
| Client Telemetry Reporter     | Securely reports MCP detection results, runtime observations, and client status to the Management Server using protected communication channels (e.g., HTTPS or mutual TLS). This module focuses on reliable and auditable data transmission and does not enforce blocking actions.                                                                   |
| Client Policy Receiver        | Receives detection policies, rule updates, and configuration parameters (such as scan frequency and enabled detection methods) from the Management Server and applies them locally. This module supports centralized control without embedding enforcement logic.                                                                                     |
| Client Self-Protection Module | Provides basic self-protection capabilities for the endpoint agent, including integrity validation, runtime health monitoring, and resistance against unauthorized termination or tampering, ensuring continuous detection availability.                                                                                                              |

---

## Server Side – Management Portal Modules

| Module Name                | Description                                                                                                                                                                                                                                                    |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| MCP Registry               | Maintains a centralized registry of **authorized MCP servers**, including server identifiers, configuration fingerprints, binary hashes, and approved execution environments. This module serves as the authoritative reference for Shadow MCP classification. |
| Client & User Management   | Manages registered endpoint clients and associated user identities, tracking online status, agent versions, and device associations to correlate MCP detection events with specific users and endpoints.                                                       |
| Detection Intake API       | Provides secure APIs to receive MCP detection events and telemetry data from endpoint clients. This module performs authentication, validation, and normalization of incoming data but does not execute complex decision logic.                                |
| Shadow MCP Decision Engine | Analyzes reported MCP server data by matching it against the MCP Registry and applying classification logic across multiple attributes (configuration, behavior, provenance) to determine Shadow MCP status and risk level.                                    |
| Alerting Engine            | Generates alerts based on Shadow MCP detection results and enterprise security policies, and delivers notifications to IT administrators or integrated alerting systems such as email, messaging platforms, or SIEM tools.                                     |
| Audit & Forensics Log      | Stores MCP detection records, classification outcomes, and alert history for long-term auditing, compliance verification, and forensic investigations.                                                                                                         |
| Policy & Rule Management   | Manages detection rules, classification policies, and threshold configurations, and distributes updates to endpoint clients, enabling continuous evolution of detection logic without frequent client redeployment.                                            |
| Reporting & Dashboard      | Provides visual dashboards and analytical views of MCP server distribution, Shadow MCP trends, and user/device risk profiles to support ongoing monitoring and operational decision-making.                                                                    |
| Integration Adapter        | Enables integration with existing enterprise security and IT systems (such as EDR, SIEM, SOAR, or asset management platforms), ensuring Shadow MCP detection results are incorporated into the broader security operations workflow.                           |

---

### One-sentence executive summary (optional, very useful in docs)

> **The client focuses on discovery and observation across configuration, process, and network layers, while the server performs centralized authorization, classification, alerting, and governance of Shadow MCP servers.**

---

如果你接下来需要，我可以继续帮你：

* 🔹 **把这些模块映射到具体实现技术（Windows / macOS / Linux）**
* 🔹 **拆分为 MVP / Phase-2 / Phase-3 交付范围**
* 🔹 **为每个模块补充 Threat → Control 映射表**

你只需要说一句：**“next step: XXX”**
