# Contract Review Agent

Contract Review Agent provides a Web UI, API endpoints, and a local CLI for DOCX contract review. It uploads contracts, validates review criteria, runs the workflow, and generates annotated DOCX output.

## Runtime Data

Runtime data uses fixed project-local paths:

```text
data/
  api/
    <task_id>/
  web/
    <tenant_id>/
      <task_id>/

user_profiles/
  users.json
```

`data_dir` and `users_file` are no longer configurable in `config.yaml`.

API and Web data are stored separately:

- API tasks: `data/api/<task_id>/`
- Web tasks: `data/web/<tenant_id>/<task_id>/`
- User accounts: `user_profiles/users.json`

## Configuration

Create `.env` from `.env.example`:

```env
LLM_API_KEY=...
EMBED_API_KEY=...
RERANK_API_KEY=...
SESSION_SECRET_KEY=replace-with-a-long-random-secret
```

MinerU has been removed. `MINERU_API_KEY`, `parser.parse_file_with_mineru`, and `mineru.api_base` are no longer used.

Reranker `base_url` must be the full request URL. The application does not append `/rerank` or `/reranks`.
`endpoint_format` only records the response compatibility mode:

```yaml
rerank:
  base_url: "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
  endpoint_format: "openai"
  name: "qwen3-rerank"
  inject_instruct: true
```

Use `inject_instruct: true` only when the reranker service accepts an `instruct` request field.

API retention settings:

```yaml
api:
  keep_input: true
  write_logs: true
  callback_file_field: "file"
```

`api.store` has been removed.

## Web Service

Start locally:

```powershell
uvicorn app:app --host 0.0.0.0 --port 5000
```

Open:

```text
http://127.0.0.1:5000
```

Web review tasks now use the shared review worker and task-store state model while keeping Web data under `data/web/`. This aligns task status, model-call errors, and event logging with the API path without mixing API and Web storage.

## API

Main async API flow:

- `POST /api/review/jobs`
- `GET /api/review/jobs/{task_id}`
- `POST /api/review/jobs/{task_id}/result`
- `POST /api/review/jobs/{task_id}/cancel`

API tasks continue to use `data/api/`.

## CLI

The CLI no longer depends on `data/` user partitions or `DEFAULT_CLI_USERNAME`.

Run with the default system criteria:

```powershell
python main.py --contract .\contract.docx
```

Run with custom review criteria:

```powershell
python main.py --contract .\contract.docx --criteria .\criteria.docx
```

Choose an output path:

```powershell
python main.py --contract .\contract.docx --criteria .\criteria.docx --output .\contract_reviewed.docx
```

If `--output` is omitted, the annotated DOCX is written to the current working directory.

## Docker

Recommended persistent mounts:

```yaml
volumes:
  - ./data:/app/data
  - ./user_profiles:/app/user_profiles
  - ./resources/review_criteria/criteria.docx:/app/resources/review_criteria/criteria.docx:ro
```

## Logs

Task event logs are written as `api_events.jsonl` inside each task's log directory when logging is enabled.

Model retry events use event names such as:

- `agent_model_call_failed`
- `embedding_call_failed`
- `reranker_call_retry`
- `reranker_call_failed`

See `docs/LOGGER_DESIGN.md` and `docs/API_REVIEW_ENDPOINT.md` for more detail.
