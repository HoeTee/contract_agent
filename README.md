# Deep Research Agent

This project runs a local contract review workflow and outputs one annotated DOCX based on the original contract.

## Current Workflow

`python main.py` runs the review pipeline:

1. Parse the contract and review criteria files.
2. Build a temporary LlamaIndex index for the current contract.
3. Use `Planner` to extract review criteria.
4. Use `Orchestrator` to retrieve contract context and run review agents.
5. Use `Reflector` to validate each review result.
6. Use `Summarizer` to create a short overall comment.
7. Write Word comments back into a copy of the original DOCX.

The workflow does not generate Markdown or PDF reports. It only generates an annotated DOCX.

## Main Entry

```powershell
python main.py
```

## Important Output

- Annotated DOCX: `docs/reports_docx/`
- Raw criterion results: `logs/workflow/last_results.json`
- Compact run summary: `logs/workflow/last_run_summary.json`
- Workflow log: `logs/workflow/`

## Active Components

- `main.py`: local CLI entry.
- `main_workflow/main_workflow.py`: workflow orchestration.
- `agents/planner.py`: review criteria extraction.
- `agents/orchestrator.py`: retrieval and sub-agent execution.
- `agents/reflector.py`: review quality validation.
- `agents/summarizer.py`: short summary comment generation.
- `mcp_service/`: MCP client/server.
- `tools/document/`: file parsing, DOCX cleaning, annotated DOCX generation.
- `tools/retrieval/llamaindex/`: temporary contract retrieval.

## MCP Tools Used By The Workflow

- `ingest_file`
- `llamaindex_build_index`
- `llamaindex_search`
- `generate_docx_report`

`generate_markdown_report` and `generate_pdf_report` may exist as standalone MCP tools, but the main workflow does not call them.
