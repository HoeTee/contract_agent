# Contract Review Multi-Agent System — Project Overview

## Purpose
AI-powered contract review system using multi-agent architecture with **PageIndex** (tree-based RAG) for document retrieval. The system decomposes criteria into specialized tasks, delegates them to expert agents with web search capability, and synthesizes professional legal review reports.

---

## Architecture

```
┌─────────────────────┐         ┌──────────────────────┐
│   Main Workflow     │◄────────┤   MCP Client         │
│   (6-Phase Flow)    │         │   (Tool Proxy)       │
└─────────────────────┘         └──────────────────────┘
         │                                │ stdio
         │                                ▼
         │                       ┌──────────────────────┐
         │                       │   MCP Server         │
         │                       │   (Tool Provider)    │
         │                       └──────────────────────┘
         │                                │
         ▼                                ▼
┌─────────────────────┐         ┌──────────────────────┐
│   Agent Swarm       │         │  Tools               │
│   - Planner         │         │  - ingest_docx       │
│   - Orchestrator    │         │  - build_pageindex_tree│
│   - Sub-Agents      │         │  - pageindex_search   │
│   - Reflector       │         │  - web_search         │
│   - Summarizer      │         │  - generate_report    │
└─────────────────────┘         └──────────────────────┘
```

---

## Workflow (6 Phases)

| Phase | Component | Action |
|-------|-----------|--------|
| 1. Ingestion | MCP:`ingest_docx` | Parse contract + criteria DOCX → markdown |
| 2. Tree Building | MCP:`build_pageindex_tree` | Build PageIndex tree from contract markdown |
| 3. Planning | `PlannerAgent` | Structure criteria into tasks with check-points |
| 4. Execute + Reflect | `OrchestratorAgent` → `SubAgent` + `Reflector` | Per-criterion: pageindex_search → sub-agent review → reflection loop (max 3 rounds) |
| 5. Summarize | `SummarizerAgent` | Compile all results into report text |
| 6. Report | MCP:`generate_final_report` | Generate timestamped DOCX in `docs/reports/` |

---

## Components

### 1. Config ([config.py](file:///c:/Users/18014/agent_self_practice/agent_with_mcp/config.py))
Central configuration: `PROJECT_ROOT`, paths, `MAX_REFLECTION_ROUNDS`, `MAX_TOOL_CALLS`.

### 2. Agent Framework ([agent/agent.py](file:///c:/Users/18014/agent_self_practice/agent_with_mcp/agent/agent.py))
Base class with LLM chat, tool calling, context management, token tracking, conversation logging.

### 3. Agents ([agents/](file:///c:/Users/18014/agent_self_practice/agent_with_mcp/agents))

| Agent | File | Role |
|-------|------|------|
| **Planner** | `planner.py` | Parses criteria → structured JSON tasks |
| **Orchestrator** | `orchestrator.py` | Dispatches sub-agents per criterion, runs reflection loop |
| **SubAgent** | (ephemeral) | Reviews contract against one criterion, uses `web_search` + `pageindex_search` |
| **Reflector** | `reflector.py` | Quality control — PASS/REJECT with feedback |
| **Summarizer** | `summarizer.py` | Compiles results into final report (no MCP) |

### 4. MCP Server ([mcp_server.py](file:///c:/Users/18014/agent_self_practice/agent_with_mcp/mcp_service/mcp_server/mcp_server.py))
6 tools: `web_search`, `read_url`, `ingest_docx`, `build_pageindex_tree`, `pageindex_search`, `generate_final_report`.

### 5. Workflow Logger ([workflow_logger.py](file:///c:/Users/18014/agent_self_practice/agent_with_mcp/workflow_logger.py))
Records every step → `logs/workflow_*.md` with Mermaid diagram + per-step detail blocks.

---

## Directory Structure
```
agent_with_mcp/
├── main.py                       # Entry point
├── config.py                     # Central config
├── workflow_logger.py            # MD+Mermaid logging
├── agent/
│   └── agent.py                  # Base Agent class
├── agents/
│   ├── planner.py                # Criteria → tasks
│   ├── orchestrator.py           # Task dispatch + reflection
│   ├── reflector.py              # Quality control
│   ├── summarizer.py             # Report compilation
│   └── prompts/cn_prompts.py     # All Chinese prompts
├── mcp_service/
│   ├── mcp_client/mcp_minimal.py # MCP client wrapper
│   └── mcp_server/mcp_server.py  # Tool registry
├── main_workflow/
│   └── main_workflow.py          # 6-phase orchestration
├── tools/
│   └── document_tools.py         # FileParser + ReportGenerator
├── PageIndex-main/               # Tree-based RAG library
├── docs/
│   ├── contracts/                # Input contracts
│   ├── contract_review_criteria/ # Review criteria docs
│   └── reports/                  # Generated DOCX reports
├── logs/                         # Workflow logs (MD)
└── logger/conversation_logs/     # Agent conversation logs (JSON)
```

---

## Environment

**`.env`** (in parent directory):
```env
API_KEY=sk-...          # QWEN-compatible API key
BASE_URL=https://...    # LLM endpoint
LLM_NAME=qwen-plus     # Model name
SERPER_API_KEY=...      # For web search
```

**Key constants** (in `config.py`):
- `MAX_REFLECTION_ROUNDS = 3`
- `MAX_TOOL_CALLS = 10`
- `MAX_CONTEXT_TOKENS = 100000`

---

## Usage
```bash
cd agent_with_mcp
python main.py
```

**Output:**
1. Console progress for all 6 phases
2. Report saved to `docs/reports/独立审查报告_<name>_<timestamp>.docx`
3. Workflow log in `logs/workflow_<timestamp>.md`
4. Agent conversation logs in `logger/conversation_logs/`
