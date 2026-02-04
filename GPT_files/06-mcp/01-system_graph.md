flowchart LR
  %% =======================
  %% Users
  %% =======================
  subgraph U[System Users]
    SOC[SecOps / SOC Analyst]
    IT[IT / Endpoint Admin]
    DEV[Developers / App Owners]
  end

  %% =======================
  %% Enterprise Environment
  %% =======================
  subgraph E[Enterprise Environment]
    subgraph END[Endpoints (Employee Devices)]
      APP[Apps / IDE / Agent Hosts]
      MCPCLI[MCP Clients (tools/agents)]
      LOCALAGENT[Local Security Agent\n(MCP Interceptor + Policy Enforcer)]
    end

    subgraph NET[Network & Edge]
      TAP[Traffic Source\n(SPAN/TAP/Proxy/WFP/NetExt)]
      FW[NGFW / Secure Web Gateway]
    end

    subgraph SUT[MCP Traffic Detection System (IDS/IPS-like)]
      DET[Detection & Correlation Engine\n(Signature + Behavior + Anomaly)]
      POL[Policy / Allowlist Engine\n(Approved MCP Servers)]
      RESP[Response Orchestrator\n(Block / Quarantine / Notify)]
      ASSET[Asset & Identity Mapper\n(User/Device/App mapping)]
      UI[Analyst Console / Portal]
      LOG[Telemetry Store\n(Flows + Events + Evidence)]
    end
  end

  %% =======================
  %% 3rd Party Systems / Services
  %% =======================
  subgraph T[3rd Party Systems / Services]
    SIEM[SIEM / SOAR]
    EDR[EDR Platform]
    TI[Threat Intelligence Feeds]
    IDP[IdP / IAM (SSO)\n(Azure AD/Okta)]
    ITSM[Ticketing / ITSM\n(ServiceNow/Jira)]
    CLOUD[Cloud Security / Logs\n(CloudTrail/Defender/Config)]
    DNS[DNS / Domain Reputation]
    CMDB[CMDB / Asset Inventory]
  end

  %% =======================
  %% Flows
  %% =======================
  APP --> MCPCLI
  MCPCLI -->|MCP over HTTP/JSON-RPC\nStdio/StreamableHTTP| LOCALAGENT

  LOCALAGENT -->|Allow/Block decision| RESP
  LOCALAGENT -->|Flow metadata + content hints| TAP
  TAP --> DET
  FW -->|Netflow/Proxy logs| DET

  POL <--> DET
  ASSET <--> DET
  LOG <--> DET
  RESP -->|Block connection / kill process\nhost firewall/WFP/NetExt| LOCALAGENT
  RESP -->|Push rules / indicators| FW
  UI <--> LOG
  UI <--> DET

  %% Users interactions
  SOC --> UI
  IT --> UI
  DEV --> UI

  %% Integrations
  DET -->|Alerts/Incidents| SIEM
  SIEM -->|Playbooks| RESP
  RESP -->|Open/Update ticket| ITSM
  DET -->|IOC queries / enrichment| TI
  DET -->|Domain / URL lookup| DNS
  ASSET -->|User auth context| IDP
  ASSET -->|Inventory sync| CMDB
  DET -->|Endpoint verdict / process tree| EDR
  DET -->|Cloud findings / exposures| CLOUD
