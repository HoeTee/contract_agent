# Contract Review Agent

Contract Review Agent provides DOCX contract review through three entry points:

- Web UI for browser-based review.
- Async API for platform integration.
- Local CLI for one-off review runs.

The workflow reads a contract DOCX, applies review criteria, runs the agent review workflow, and generates a reviewed DOCX result with comments.

## Start Here

For local development:

```powershell
uvicorn app:app --host 0.0.0.0 --port 5000
```

Open:

```text
http://127.0.0.1:5000
```

For a quick CLI review:

```powershell
python main.py --contract .\contract.docx
```

For API usage, start with:

- `POST /api/review/jobs`
- `POST /api/review/jobs/status`
- `POST /api/review/jobs/result`

See [docs/ASYNC_REVIEW_API.md](docs/ASYNC_REVIEW_API.md) for request and response details.

## Configuration

Create `.env` from `.env.example` and provide at least:

```env
LLM_API_KEY=...
EMBED_API_KEY=...
RERANK_API_KEY=...
SESSION_SECRET_KEY=replace-with-a-long-random-secret
```

Main runtime configuration lives in [config.yaml](config.yaml). The Python loader is [config.py](config.py).

Important config areas:

- `llm`: review model endpoint and generation limits.
- `embedding`: embedding endpoint.
- `rerank`: reranker provider, endpoint, model name, and optional instruction.
- `workflow`: concurrency, retries, timeouts, and subagent tool allowlist.
- `api`: async API retention, result URL upload, metadata fields, callback, and URL download limits.
- `logging`: workflow log switch.

Reranker details are documented in [docs/RERANKER_CONFIGURATION.md](docs/RERANKER_CONFIGURATION.md).

## Data Layout

Runtime data uses fixed project-local directories:

```text
data/
  api/
    <task_id>/
  web/
    <tenant_id>/
      <task_id>/

user_profiles/
  users.json
  api_clients.json
```

API and Web task data are intentionally separated:

- API tasks: `data/api/<task_id>/`
- Web tasks: `data/web/<tenant_id>/<task_id>/`
- Web user profiles: `user_profiles/users.json`
- API client mappings: `user_profiles/api_clients.json`

Task directories contain `task.json`, input files, output files, and task-level logs when enabled.

## API

Primary async API endpoints:

- `POST /api/review/jobs`: submit a DOCX file or URL review job.
- `POST /api/review/jobs/status`: query status by JSON body.
- `GET /api/review/jobs/{task_id}`: query status by path.
- `POST /api/review/jobs/result`: return result as file or URL.
- `POST /api/review/jobs/{task_id}/result`: return result by path task id.
- `POST /api/review/jobs/{task_id}/cancel`: request cancellation.

API documentation:

- [docs/ASYNC_REVIEW_API.md](docs/ASYNC_REVIEW_API.md)
- [docs/API_REVIEW_ENDPOINT.md](docs/API_REVIEW_ENDPOINT.md)
- [docs/LOGGER_DESIGN.md](docs/LOGGER_DESIGN.md)

## Web

The Web flow uses the shared review worker and task-store model, while storing user task data under `data/web/`.

Relevant docs:

- [docs/FRONTEND_USER_JOURNEY.md](docs/FRONTEND_USER_JOURNEY.md)
- [docs/WEB_TENANT_USAGE.md](docs/WEB_TENANT_USAGE.md)
- [docs/USER_MANAGEMENT.md](docs/USER_MANAGEMENT.md)

## CLI

Use the system default review criteria:

```powershell
python main.py --contract .\contract.docx
```

Use a custom criteria file:

```powershell
python main.py --contract .\contract.docx --criteria .\criteria.docx
```

Write to an explicit output path:

```powershell
python main.py --contract .\contract.docx --criteria .\criteria.docx --output .\contract_reviewed.docx
```

## Docker

Persist runtime data outside the container:

```yaml
volumes:
  - ./data:/app/data
  - ./user_profiles:/app/user_profiles
  - ./resources/review_criteria/criteria.docx:/app/resources/review_criteria/criteria.docx:ro
```

Docker deployment and troubleshooting:

- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- [docs/DOCKER_NETWORK_TROUBLESHOOTING.md](docs/DOCKER_NETWORK_TROUBLESHOOTING.md)

## Project Docs

Architecture and workflow:

- [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)
- [docs/AGENT_WORKFLOW_ARCHITECTURE.md](docs/AGENT_WORKFLOW_ARCHITECTURE.md)
- [docs/DOCX_XML_ANCHOR_INDEXING.md](docs/DOCX_XML_ANCHOR_INDEXING.md)
- [docs/DOCX_ANNOTATION_DESIGN.md](docs/DOCX_ANNOTATION_DESIGN.md)

Operations:

- [docs/QUICK_START.md](docs/QUICK_START.md)
- [docs/LOGGER_DESIGN.md](docs/LOGGER_DESIGN.md)
- [docs/RERANKER_CONFIGURATION.md](docs/RERANKER_CONFIGURATION.md)
- [docs/REVIEW_BOUNDARIES.md](docs/REVIEW_BOUNDARIES.md)
