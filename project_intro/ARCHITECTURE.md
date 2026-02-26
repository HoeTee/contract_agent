# Contract Review System — Architecture & Data Flow

---

## System Architecture

```mermaid
%%{init: {'theme':'base', 'themeVariables': {'primaryColor':'#fff'}, 'flowchart':{'curve':'linear'}}}%%
graph TB
    subgraph "User Layer"
        CLI[main.py]
    end

    subgraph "Workflow Layer"
        MainWorkflow["ContractReviewWorkflow<br/>6-Phase Pipeline"]
        Logger["WorkflowLogger<br/>MD + Mermaid"]
    end

    subgraph "Agent Layer"
        Planner["Planner<br/>Criteria → Tasks"]
        Orchestrator["Orchestrator<br/>Task Dispatch"]
        SubAgents["Sub-Agents<br/>Per-Criterion Review"]
        Reflector["Reflector<br/>Quality Control"]
        Summarizer["Summarizer<br/>Report Compilation"]
    end

    subgraph "MCP Layer"
        MCPClient["MCP Client<br/>Tool Proxy"]
        MCPServer["MCP Server<br/>Tool Provider"]
    end

    subgraph "Tool Layer"
        FileParser["ingest_docx<br/>DOCX/PDF/TXT → MD"]
        TreeBuild["build_pageindex_tree<br/>MD → Tree"]
        TreeSearch["pageindex_search<br/>LLM Tree Search"]
        WebSearch["web_search<br/>Serper API"]
        ReportGen["generate_final_report<br/>DOCX Output"]
    end

    subgraph "Storage"
        Reports["docs/reports/<br/>Generated DOCX"]
        Logs["logs/<br/>Workflow MD"]
        ConvLogs["logger/conversation_logs/<br/>Agent JSON"]
    end

    CLI --> MainWorkflow
    MainWorkflow --> Logger
    MainWorkflow --> Planner
    MainWorkflow --> Orchestrator
    MainWorkflow --> Summarizer
    Orchestrator --> SubAgents
    Orchestrator --> Reflector

    Planner -.uses.-> MCPClient
    SubAgents -.uses.-> MCPClient
    MainWorkflow -.uses.-> MCPClient

    MCPClient <-->|stdio| MCPServer

    MCPServer --> FileParser
    MCPServer --> TreeBuild
    MCPServer --> TreeSearch
    MCPServer --> WebSearch
    MCPServer --> ReportGen

    ReportGen --> Reports
    Logger --> Logs
    SubAgents --> ConvLogs

    style Planner fill:#e1f5ff
    style Orchestrator fill:#e1f5ff
    style SubAgents fill:#e1f5ff
    style Reflector fill:#e1f5ff
    style Summarizer fill:#e1f5ff
    style MCPClient fill:#fff4e1
    style MCPServer fill:#fff4e1
    style TreeBuild fill:#e1ffe1
    style TreeSearch fill:#e1ffe1
```

---

## Workflow Data Flow

```mermaid
sequenceDiagram
    participant U as User
    participant W as Workflow
    participant MCP as MCP Server
    participant P as Planner
    participant O as Orchestrator
    participant S as SubAgent
    participant R as Reflector
    participant SM as Summarizer

    U->>W: python main.py

    Note over W: Phase 1: Ingestion
    W->>MCP: ingest_docx(criteria)
    W->>MCP: ingest_docx(contract)

    Note over W: Phase 2: Tree Building
    W->>MCP: build_pageindex_tree(contract_md)
    MCP-->>W: tree_json

    Note over W: Phase 3: Planning
    W->>P: design_tasks(criteria_md)
    P-->>W: criteria list (JSON)

    Note over W: Phase 4: Execute + Reflect
    W->>O: execute_criteria(criteria, tree_json)

    loop per criterion (concurrent)
        O->>MCP: pageindex_search(query, tree_json)
        MCP-->>S: relevant sections
        S->>MCP: web_search(legal query)
        MCP-->>S: search results
        S-->>R: review output

        loop max 3 rounds
            R-->>S: PASS or feedback
            S-->>R: refined output
        end
    end

    O-->>W: all results

    Note over W: Phase 5: Summarization
    W->>SM: compile_report(results)
    SM-->>W: report text

    Note over W: Phase 6: Report
    W->>MCP: generate_final_report
    MCP-->>W: DOCX path
    W-->>U: Done
```

---

## Agent Class Hierarchy

```mermaid
classDiagram
    class Agent {
        +client: AsyncOpenAI
        +name: str
        +mcp_client: MinimalMCPClient
        +tools: list
        +token_usage: dict
        +chat(message) str
        +execute() str
        +log_conversation()
    }

    class PlannerAgent {
        +design_tasks(criteria_md) dict
    }

    class OrchestratorAgent {
        +execute_criteria(list, tree_json) list
        +execute_single_criterion(dict, tree_json) dict
    }

    class ReflectorAgent {
        +review(output, criteria) dict
    }

    class SummarizerAgent {
        +compile_report(results) str
    }

    Agent <|-- PlannerAgent
    Agent <|-- ReflectorAgent
    Agent <|-- SummarizerAgent
    OrchestratorAgent ..> Agent : spawns SubAgents
    OrchestratorAgent ..> ReflectorAgent : uses
```

---

## MCP Tool Registry

```mermaid
mindmap
  root((MCP Tools))
    Document
      ingest_docx
        Parse DOCX/PDF/TXT
        Return Markdown
      generate_final_report
        Format Content
        Save DOCX
    PageIndex
      build_pageindex_tree
        MD → Tree Structure
        LLM Summaries
      pageindex_search
        LLM Reasoning Search
        Return Relevant Sections
    Web
      web_search
        Serper API
        Top 5 Results
      read_url
        Fetch Page Text
```

---

## Workflow Phases (State Diagram)

```mermaid
stateDiagram-v2
    [*] --> Ingestion
    Ingestion --> TreeBuilding: criteria_md, contract_md
    TreeBuilding --> Planning: tree_json
    Planning --> Execution: criteria_list

    state Execution {
        [*] --> PageIndexSearch
        PageIndexSearch --> SubAgentReview
        SubAgentReview --> Reflection
        Reflection --> ReflectionCheck

        state ReflectionCheck <<choice>>
        ReflectionCheck --> [*]: PASS
        ReflectionCheck --> SubAgentReview: REJECT (max 3)
    }

    Execution --> Summarization: results[]
    Summarization --> ReportGeneration: report_text
    ReportGeneration --> [*]: DOCX saved
```

---

## Configuration Flow

```mermaid
%%{init: {'theme':'base', 'flowchart':{'curve':'linear'}}}%%
graph LR
    subgraph "Config Sources"
        ENV[".env<br/>API_KEY, BASE_URL, LLM_NAME"]
        CFG["config.py<br/>PROJECT_ROOT, paths, constants"]
    end

    subgraph "Runtime"
        Settings["Settings class<br/>(Pydantic)"]
    end

    ENV --> Settings
    CFG --> Settings
    Settings --> Agents["All Agent Instances"]
    Settings --> MCPServer["MCP Server (PageIndex)"]

    style ENV fill:#fff4e1
    style CFG fill:#fff4e1
    style Settings fill:#e1f5ff
```
