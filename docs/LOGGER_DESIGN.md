# Logger Design

Logger code lives in `loggers/`. The module `resolve_review_task_paths.py` resolves task IDs and file paths; the other logger modules only write logs.

## Task Directory

Each review task writes logs to:

```text
data/<username>/logs/<YYYY-MM-DD>/<HHMMSS_shortid_contractname>/
```

The task directory is split by log source:

```text
workflow/
conversations/
mcp/
api_events.jsonl
```

## Path Resolution

Module:

```text
loggers/resolve_review_task_paths.py
```

Purpose:

```text
Resolve the task ID and all input, output, and log paths for one review task.
```

It resolves:

```text
stored_contract_path
final_report_path
criteria_path
task_log_dir
workflow_log_dir
conversation_log_dir
mcp_log_dir
api_events_path
```

## Workflow Logs

Module:

```text
loggers/workflow_logger.py
```

Files:

```text
workflow/workflow_YYYYMMDD_HHMMSS.md
workflow/results.json
workflow/run_summary.json
```

## Agent Conversation Logs

Module:

```text
loggers/agent_logger.py
```

Files:

```text
conversations/Planner_*.json
conversations/SubAgent_C1_*.json
conversations/Reflector_*.json
conversations/Summarizer_*.json
```

## MCP Logs

Module:

```text
loggers/mcp_logger.py
```

File:

```text
mcp/mcp_client.log
```

## API Events

Module:

```text
loggers/api_event_logger.py
```

File:

```text
api_events.jsonl
```

`jsonl` is one JSON object per line. It is used for append-only API events such as upload, validation, review start, review completion, and failure.
