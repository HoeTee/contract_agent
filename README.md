# Deep Research Agent

Deep Research Agent is a contract review web service. It supports login, DOCX upload, contract review, annotated DOCX download, user-scoped storage, and task-scoped logs.

## Runtime Layout

```text
data/
  <username>/
    contract_review_criteria/
      criteria.docx
    institutional_docs/
    contracts/
    reports_docx/
    logs/

docs/
  LOGGER_DESIGN.md
  USER_MANAGEMENT.md
  PROJECT_STRUCTURE.md
  DEPLOYMENT.md
```

- `data/`: persistent user data. Mount this directory on the server.
- `docs/`: Markdown documentation only. It is not used for runtime inputs or outputs.
- `users.json`: user account config. Passwords are stored as hashes, not plaintext.

## User Management

Create a user:

```powershell
python scripts/manage_users.py create --username user001 --password Abc123456 --display-name ZhangSan
```

Reset a password:

```powershell
python scripts/manage_users.py reset-password --username user001 --password NewPass123
```

Disable a user:

```powershell
python scripts/manage_users.py disable --username user001
```

Each user needs a review criteria file:

```text
data/user001/contract_review_criteria/criteria.docx
```

## Web Service

Start locally:

```powershell
uvicorn app:app --host 0.0.0.0 --port 5000
```

Open:

```text
http://localhost:5000
```

For a step-by-step smoke test, see [docs/QUICK_START.md](docs/QUICK_START.md).

After login, the service:

1. Saves the uploaded contract to `data/<username>/contracts/`
2. Reads the contract directly from `data/<username>/contracts/`
3. Writes the annotated DOCX directly to `data/<username>/reports_docx/`
4. Writes task logs to `data/<username>/logs/<YYYY-MM-DD>/<task>/`

## CLI

The CLI uses a user partition. The default user comes from `.env`:

```env
DEFAULT_CLI_USERNAME=default
```

Run:

```powershell
python main.py --username default --contract sample.docx
```

If `--contract` is relative, it is read from:

```text
data/default/contracts/sample.docx
```

## Docker

`docker-compose.yaml` mounts:

```yaml
volumes:
  - ./data:/app/data
  - ./users.json:/app/users.json:ro
```

The container listens on `5000`. The compose file maps:

```yaml
ports:
  - "127.0.0.1:8000:5000"
```

Server-local access:

```text
http://127.0.0.1:8000
```

For external access, change the port mapping to:

```yaml
ports:
  - "8000:5000"
```

## Logs

Each review task writes logs to:

```text
data/<username>/logs/<YYYY-MM-DD>/<task>/
  workflow/
  conversations/
  mcp/
  api_events.jsonl
```

See [docs/LOGGER_DESIGN.md](docs/LOGGER_DESIGN.md).

## Required Env

Create `.env` from `.env.example` and set at least:

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

ENABLE_WORKFLOW_LOGS=False
MAX_API_CONCURRENT_REVIEWS=1
SESSION_SECRET_KEY=replace-with-a-long-random-secret
```
