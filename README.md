# Deep Research Agent with MCP & PageIndex

A complete 6-phase automated contract review workflow utilizing **Model Context Protocol (MCP)** and a **Multi-Agent Architecture**, combined with **PageIndex** for advanced RAG (Retrieval-Augmented Generation).

## 🌟 Key Features

1. **Multi-Agent System**
   - **Planner:** Parses and decomposes raw criteria into executable tasks.
   - **Orchestrator:** Dispatches tasks, retrieves relevant contract sections, and manages execution.
   - **Reflector:** Acts as a quality control checkpoint, evaluating sub-agent outputs and forcing revisions (up to 3 rounds) if criteria are not met.
   - **Summarizer:** Compiles all agent results into a cohesive, structured report.

2. **Model Context Protocol (MCP) Integration**
   - A standalone `mcp_server` exposes critical tools as standard functions:
     - `ingest_docx`: Parses Word/PDF/TXT files into Markdown.
     - `build_pageindex_tree`: Converts Markdown into a hierarchical PageIndex tree.
     - `pageindex_search`: Performs LLM-reasoning-based search on the tree.
     - `web_search` / `read_url`: Provides external web access via Serper API.
     - `generate_final_report`: Renders the final output into a DOCX file.
   - `MinimalMCPClient` enables seamless tool-calling over stdio.

3. **PageIndex RAG Advanced Retrieval**
   - Rather than simple chunking, the project uses **PageIndex** to retain document structure (e.g., sections, headers, logical groupings).
   - This ensures sub-agents have the exact, structured context they need without token bloat or lost context.

4. **Complete Output & Logging Ecosystem**
   - Generates both Markdown and DOCX reports.
   - Maintains full conversation logs (JSON format) and workflow execution logs (MD with Mermaid diagrams) for auditability.
   - Strict token tracking and management across all phases.

---

## 🏗 System Architecture

The workflow consists of **6 distinct phases**:

1. **Ingestion:** Parse contract and criteria documents into Markdown.
2. **Tree Building:** Convert contract Markdown into a structured PageIndex tree.
3. **Planning:** Extract specific legal criteria into structured JSON task lists.
4. **Execution & Reflection:** (Concurrent per criterion)
   - Search the PageIndex tree for relevant contract clauses.
   - Sub-agent reviews the clauses against the specific criterion.
   - Reflector agent evaluates the review. If rejected, the sub-agent refines it (loop).
5. **Summarization:** Compile all approved sub-agent reviews into a single Markdown document.
6. **Report Generation:** Save the final checklist and findings into a formal DOCX report.

_(For detailed flowcharts and diagrams, please see `project_intro/ARCHITECTURE.md`)_

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- Install dependencies (ensure you have `mcp`, `openai`, `pydantic`, `beautifulsoup4`, etc., installed).

### Configuration

Create a `.env` file in the `agent_with_mcp` directory (or use the one provided) with your preferred LLM configurations:

```env
# Example .env configuration
API_KEY=your_api_key_here
BASE_URL=https://your-llm-base-url.com/v1
LLM_NAME=qwen-plus
TEMPERATURE=0.0

# For Web Search Tool
SERPER_API_KEY=your_serper_api_key
```

### Running the Workflow

1. Navigate to the core module:

   ```bash
   cd agent_with_mcp
   ```

2. Execute the main entry point:

   ```bash
   python main.py
   ```

3. The system will start outputting logs to the console as it progresses through the 6 phases.
4. Upon completion, you will find:
   - **Formal Reports:** In `docs/reports_md/` (Markdown) and the generated DOCX path.
   - **Conversation Logs:** In `logger/conversation_logs/` (Detailed JSON traces of what every agent saw and thought).
   - **Workflow Logs:** In `logs/` (A high-level Markdown summary of the run duration, token usage, and MCP calls).

---

## 📂 Project Structure

```text
deep_research_agent/
└── agent_with_mcp/
    ├── .env                    # Central LLM & API Configuration
    ├── config.py               # Global paths and constants (Tokens, reflection limits)
    ├── main.py                 # CLI entry point
    ├── agent/                  # Base Agent class definition
    ├── agents/                 # Specialized agents (Planner, Orchestrator, Reflector, Summarizer)
    ├── mcp_service/            # MCP Client and Server implementations
    ├── main_workflow/          # The 6-Phase Pipeline orchestrator
    ├── PageIndex-main/         # PageIndex library & utils for hierarchical RAG
    ├── tools/                  # Specific Python tools (e.g., DOCX parser, Report Generator)
    ├── logger/                 # Logging utilities
    ├── docs/                   # Input contracts, criteria, and output Markdown reports
    └── logs/                   # Execution run logs
```

---

## ⚙️ Customization

- **Reflection Limit:** Modify `MAX_REFLECTION_ROUNDS` in `config.py` to change how many times the Reflector can bounce a review back to a sub-agent.
- **Token Limits:** Adjust `MAX_CONTEXT_TOKENS` and `MAX_TOOL_CALLS` in `config.py` according to your specific LLM's context window.
- **Prompts:** Agent behavior can be modified by editing the prompts found in `agents/prompts/cn_prompts.py`.
