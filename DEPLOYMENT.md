# Deployment Notes

The current application is a local CLI workflow. It generates one annotated DOCX from the original contract.

## Run

```powershell
python main.py
```

## Required Configuration

Create `.env` from `.env.example` and set:

```env
LLM_API_KEY=...
LLM_BASE_URL=...
LLM_NAME=qwen-plus

EMBED_API_KEY=...
EMBED_BASE_URL=...
EMBED_NAME=text-embedding-v4

RERANK_API_KEY=...
RERANK_BASE_URL=...
RERANK_NAME=qwen3-rerank
```

## Output

- Annotated DOCX: `docs/reports_docx/`
- Workflow log: `logs/workflow/`
- Raw results: `logs/workflow/last_results.json`
- Run summary: `logs/workflow/last_run_summary.json`

## Active MCP Tools

- `ingest_file`
- `llamaindex_build_index`
- `llamaindex_search`
- `generate_docx_report`

The workflow does not call web search, PageIndex, Markdown report generation, or PDF report generation.
