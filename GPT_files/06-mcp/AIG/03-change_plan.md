### 1. Where new vulnerability types fit in the current design

**Current dynamic pipeline (`Agent.dynamic_analysis`)**

- Stage 1: `Info Collection` (`agents/dynamic/project_summary`)
- Stage 2: `Malicious Testing` (`agents/dynamic/malicious_behaviour_testing.md`)
  - Focus: **Tool Poisoning, Rug Pull** (malicious/misbehaving tools).
- Stage 3: `Vulnerability Testing` (`agents/dynamic/vulnerability_testing.md`)
  - Focus: **Credential Leakage, Malicious Code Execution, Prompt Injection via Tool Output**.
- Stage 4: `Vulnerability Review` (aggregates results; generic).

**Key point**:  
Stage 3 is already designed as a **multi‑threat dynamic tester**. It reads a `crispe` YAML under `测试目标详情` and, per the template:

- Uses `crispe.threats` to know **which vulnerability types to test**.
- Uses `crispe.tasks` to know **what to do**.
- Uses `crispe.constraints` to know **how to behave**.
- Then generates MCP tool calls to exercise the MCP server.

The markdown file itself embeds some **built‑in tasks** (`credential_leakage.yaml`, `malicious_code_execution_detection.yaml`, `tool_output_prompt_injection.yaml`) as “canonical examples”.

So: **you do not need new Python stages** to add MCP Top‑25 vulnerabilities. You extend the **prompt + YAML task definitions** and, optionally, the scoring/aggregation.

---

### 2. How to conceptually map “MCP Top 25” into your system

From the Top‑25 list (Adversa’s MCP vulnerabilities), you can roughly split them:

- **Already covered / partially covered**
  - Prompt Injection → covered (Prompt Injection via Tool Output) + probably static prompts elsewhere.
  - Tool Poisoning → already in `malicious_behaviour_testing.md`.
  - Rug Pull → already in `malicious_behaviour_testing.md`.
  - Token/Credential Theft → overlaps `credential_leakage`.
  - Remote Code Execution / Command Injection → overlaps `malicious_code_execution_detection`.

- **Good candidates to add as *new* dynamic vulnerability types**
  - **Command Injection** (explicit, separate from generic “malicious code execution”).
  - **Unauthenticated / Unauthorized Access** (missing/weak authz).
  - **Path Traversal / File Containment Bypass**.
  - **Token Passthrough / Confused Deputy / OAuth proxy misuse**.
  - **MCP Configuration Poisoning** (may fit in “malicious behaviour” side).
  - **Insecure Resource Access / SSRF‑like issues** (remote fetch tools).
  - **Data Exfiltration / Privacy leaks** beyond credentials.

For each of these, ask:

1. **Is this mostly about tool behavior / registration / configuration?**  
   → belongs to `malicious_behaviour_testing.md` (Stage 2).
2. **Or is it a concrete “vulnerability class” that you can see in tool outputs / side‑effects?**  
   → belongs to `vulnerability_testing.md` (Stage 3).

You then model each vulnerability class as a **new `crispe` task** that the coordinator can select.

---

### 3. Concretely: how to add a new vulnerability type (pattern)

Using “Command Injection” as an example vulnerability for Stage 3.

#### 3.1. Extend `vulnerability_testing.md` with a new embedded YAML task

Inside `vulnerability_testing.md`, you currently have:

- `### credential_leakage.yaml`
- `### malicious_code_execution_detection.yaml`
- `### tool_output_prompt_injection.yaml`

You can **follow the exact same pattern** and add e.g.:

- `### command_injection.yaml`

Content structure (high‑level):

- `crispe.role`: security testing engineer context.
- `crispe.capabilities`: what this agent should be good at for this vuln.
- `crispe.threats`: description of “Command Injection in MCP context”.
- `crispe.tasks`: what to do with tool call results (e.g., detect patterns like `;`, `&&`, `|`, unsanitized shell arguments, etc.).
- `crispe.constraints`: how to reason, what to ignore (e.g., inputs vs outputs), and concrete analysis methodology.

You’d mirror the depth of the existing three YAML blocks: clear description + methodology + verification rules.

> Design tip:  
> For Top‑25, you can group similar items to avoid 25 separate YAMLs (e.g., “Command & Code Injection”, “Auth & Access Control”, “File/Path/FS Abuse”, “Token & Identity Misuse”) while still naming the threats with the official taxonomy inside `crispe.threats`.

#### 3.2. Decide where each new YAML lives

- **Behavior‑focused vulnerabilities** (tool poisoning, rug pull, config poisoning, token passthrough misuse):
  - Add YAML blocks under `malicious_behaviour_testing.md` (or even separate malicious‑behaviour templates if needed).
- **Result‑/effect‑focused vulnerabilities** (command injection, RCE, auth bypass, path traversal, SSRF‑like, data exfiltration):
  - Add YAML blocks under `vulnerability_testing.md`.

You’re just adding more `### xxx.yaml` sections with the same `crispe` schema.

#### 3.3. Make the coordinator send the right `测试目标详情`

The **selection mechanism** is not in the markdown; it’s in whatever component calls `dynamic_analysis` and constructs the `prompt` / `context` / `测试目标详情`.

To actually use a new vulnerability type, your orchestrator should:

- Build a `测试目标详情:` YAML that:
  - Sets the right `crispe.threats` keys (e.g., `Command Injection`, `Unauthenticated Access`, etc.), consistent with your templates.
  - Optionally reuses or customizes the text from the embedded YAML blocks.

Because both dynamic testing prompts say:

- “Treat the provided YAML task as source of truth”  
- “If a threat is NOT in the YAML, DO NOT test it.”

…adding new threats only becomes effective when the coordinator **asks for them** via `测试目标详情`.

---

### 4. Optional: adjust aggregation and scoring

Dynamic stages 2 and 3 currently:

- Output an **MCP‑threat‑oriented report** in a fixed Markdown + XML snippet format (`vuln_ret_format`).
- Stage 4 (`Vulnerability Review`) then uses a generic prompt to transform these into `<vuln>` XML and finally:
  - `VulnerabilityExtractor.extract_vulnerabilities(...)`
  - `calc_mcp_score(vuln_results)`

To fully integrate Top‑25, you *may* also want to:

1. **Normalize risk_type names**  
   - Ensure your new threat types (e.g., “Command Injection”, “Unauthenticated Access”) are consistently used in:
     - Stage 2/3 reports (`<type>` inside `<threat>`).
     - Stage 4 review prompts.
     - `VulnerabilityExtractor` and `calc_mcp_score` (if they have category‑specific logic).

2. **Adjust scoring weights**  
   - Optionally reflect Adversa’s ranking (severity, exploitability, prevalence, fix complexity) in your scoring function so Top‑ranked vulnerabilities contribute more to the MCP “score”.

Even if you don’t change code immediately, **keeping the vulnerability names identical** to the Top‑25 taxonomy in all YAML and prompts will make it much easier to wire that later.

---

### 5. Recommended incremental plan

- **Step 1 – Taxonomy design**
  - Take the Top‑25 list and group into ~5–10 **“testable via MCP dynamic stage” buckets**.
  - For each bucket, decide: Stage 2 (malicious behaviour) or Stage 3 (vulnerability).

- **Step 2 – Add YAML templates**
  - For each bucket, add a `### xxx.yaml` block under the right markdown:
    - Clear `crispe.role`, `crispe.capabilities`, `crispe.threats`, `crispe.tasks`, `crispe.constraints`.
    - Reuse and adapt the methodology style from the existing three vulnerability templates.

- **Step 3 – Update orchestrator configuration**
  - For different scan profiles (e.g., “Top‑10”, “Full Top‑25”), generate appropriate `测试目标详情` YAML that lists the desired threats.
  - Optionally add CLI/flags to select which subsets to test.

- **Step 4 – (Optional) Adjust parsing/scoring**
  - If your `VulnerabilityExtractor` / scoring depend on `risk_type` strings, extend them to recognize the new types.
  - Optionally align scoring weights with the Top‑25 ranking.

If you tell me which concrete Top‑25 entries you want to prioritize (e.g., “add Command Injection, Unauthenticated Access, Path Traversal first”), I can draft one or two full `crispe` YAML definitions tailored to your current template style so you can paste them straight into the corresponding markdown files.