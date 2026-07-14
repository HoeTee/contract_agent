# Asynchronous Review API

This document describes the external asynchronous contract review API under `/api`.

The API has no synchronous `POST /api/review` endpoint. A caller submits a task, then queries the task until it succeeds, and finally asks the service to export the result.

## 1. Authentication and Client Management

Every `/api` request must carry the platform-provided key in the `Authorization` header:

```http
Authorization: <secret_key>
```

`Bearer <secret_key>` and `X-API-Key: <secret_key>` are also accepted by the service. The examples below use `Authorization`.

The administrator registers platform keys locally. The key is stored only as a password hash and fingerprint in `user_profiles/api_clients.json`; plaintext keys are not stored.

Run the commands from the project root, or from a temporary management container that mounts the same persistent `user_profiles/` and `data/` directories as the service container.

| Command | Input | Output / Effect |
| --- | --- | --- |
| `register` | `--client-id`, `--secret-key` | Registers one client. Duplicate `client_id` or `secret_key` returns an error. |
| `list` | None | Lists all registered clients. |
| `check` | `--client-id` | Shows one client's registration state and task count. |
| `list --client-id` | `--client-id` | Shows that client's tasks in block format. |
| `list --client-id --compact` | `--client-id` | Shows that client's tasks in compact rows. |
| `reset-secret` | `--client-id`, `--secret-key` | Replaces the client key hash. The new key must not belong to another client. |
| `disable` | `--client-id` | Makes the client key unable to call `/api`. |
| `enable` | `--client-id` | Restores the client's `/api` access. |
| `delete` | `--client-id` | Removes the authentication mapping only. Existing task data is retained. |

```powershell
python scripts/manage_api_clients.py register --client-id "client_a" --secret-key "platform-key-for-client-a"
python scripts/manage_api_clients.py list
python scripts/manage_api_clients.py check --client-id "client_a"
python scripts/manage_api_clients.py list --client-id "client_a"
python scripts/manage_api_clients.py list --client-id "client_a" --compact
python scripts/manage_api_clients.py reset-secret --client-id "client_a" --secret-key "new-platform-key"
python scripts/manage_api_clients.py disable --client-id "client_a"
python scripts/manage_api_clients.py enable --client-id "client_a"
python scripts/manage_api_clients.py delete --client-id "client_a"
```

## 2. Asynchronous Calling Sequence

```text
POST /api/review/jobs
  -> 202 Accepted with task_id

GET /api/review/jobs/{task_id}
  -> pending, queued, running, succeeded, failed, or cancelled

POST /api/review/jobs/{task_id}/result
  -> only after status is succeeded
```

`POST /api/review/jobs/{task_id}/cancel` can cancel only `pending` or `queued` tasks. A `running` task has already entered `workflow.run()` and cannot be stopped by this API.

Task statuses:

| Status | Meaning |
| --- | --- |
| `pending` | The task was stored and the background worker has not yet checked the concurrency limit. |
| `queued` | The concurrency limit is full; the task waits for an execution slot. |
| `running` | The worker acquired a slot and is running the review workflow. |
| `succeeded` | The review output exists and can be exported. |
| `failed` | The workflow failed. The status response contains `error`. |
| `cancelled` | The task was cancelled before it started. |

## 3. Submit a Task

```http
POST /api/review/jobs
Content-Type: multipart/form-data
Authorization: <secret_key>
```

Request fields:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `file` | DOCX file | Yes | Contract document to review. |
| `criteria_file` | DOCX file | No | Review criteria document. The default criteria are used when omitted. |

PowerShell example:

```powershell
curl.exe -X POST "http://localhost:5000/api/review/jobs" `
  -H "Authorization: platform-key-for-client-a" `
  -F "file=@C:/Users/lenovo/Desktop/contract.docx" `
  -F "criteria_file=@C:/Users/lenovo/Desktop/criteria.docx"
```

Successful response, HTTP `202`:

```json
{
  "task_id": "20260714-143119-5ece",
  "status": "pending",
  "message": "Review job submitted."
}
```

| HTTP status | When returned | Response |
| --- | --- | --- |
| `202` | Task accepted. | The task ID, initial status, and message. |
| `400` | Contract or criteria is not a valid DOCX, or criteria content is invalid. | `{ "detail": "..." }` |
| `401` | Authorization key is absent, invalid, or belongs to a disabled client. | `{ "detail": "secret_key is required." }` or `{ "detail": "Invalid API client credentials." }` |
| `422` | Required multipart field `file` is absent or request fields cannot be parsed. | FastAPI validation detail. |
| `500` | API client mapping is malformed or ambiguous. | `{ "detail": "..." }` |

## 4. Query Task Status

```http
GET /api/review/jobs/{task_id}
Authorization: <secret_key>
```

PowerShell example:

```powershell
curl.exe "http://localhost:5000/api/review/jobs/20260714-143119-5ece" `
  -H "Authorization: platform-key-for-client-a"
```

Successful response, HTTP `200`:

```json
{
  "task_id": "20260714-143119-5ece",
  "status": "running",
  "created_at": "2026-07-14T14:31:19+08:00",
  "started_at": "2026-07-14T14:31:20+08:00",
  "finished_at": null,
  "message": "Contract review is running.",
  "error": null,
  "input": {
    "contract_filename": "contract.docx",
    "criteria_source": "default",
    "criteria_filename": null,
    "stored": true
  },
  "output": {
    "result_filename": "contract_批注版.docx",
    "ready": false
  },
  "logs": {
    "enabled": true
  }
}
```

| HTTP status | When returned | Response |
| --- | --- | --- |
| `200` | The authenticated client owns the task. | Filtered task status; no server filesystem paths are exposed. |
| `401` | Authorization fails. | `{ "detail": "..." }` |
| `404` | The task ID is invalid, does not exist, or belongs to another client. | `{ "detail": "Task not found." }` |
| `500` | API client mapping is malformed or ambiguous. | `{ "detail": "..." }` |

## 5. Export a Completed Result

```http
POST /api/review/jobs/{task_id}/result
Content-Type: application/json
Authorization: <secret_key>
```

Request JSON:

| Field | Type | Required | Description |
| --- | --- | --- |
| `output_path` | string | Yes | Destination path on the machine running the API service. |

PowerShell `curl.exe` example:

```powershell
curl.exe -X POST "http://localhost:5000/api/review/jobs/20260714-143119-5ece/result" `
  -H "Authorization: platform-key-for-client-a" `
  -H "Content-Type: application/json" `
  -d '{\"output_path\":\"C:/Users/lenovo/Desktop/review_result.docx\"}'
```

Successful response, HTTP `200`:

```json
{
  "task_id": "20260714-143119-5ece",
  "status": "succeeded",
  "message": "Result exported.",
  "output_path": "C:\\Users\\lenovo\\Desktop\\review_result.docx"
}
```

| HTTP status | When returned | Response |
| --- | --- | --- |
| `200` | Task succeeded and the result was copied to `output_path`. | Task ID, `succeeded`, message, output path. |
| `400` | `output_path` is absent or blank. | `{ "task_id": "...", "status": "failed", "message": "output_path is required." }` |
| `401` | Authorization fails. | `{ "detail": "..." }` |
| `404` | Task ID is invalid, missing, or belongs to another client. | `{ "detail": "Task not found." }` |
| `409` | Task status is not `succeeded`. | `{ "detail": "Task is not finished. Current status: ..." }` |
| `422` | JSON body is malformed or is not a JSON object. | FastAPI validation detail. |
| `500` | Result source file is absent, export path cannot be written, or client mapping is invalid. | `{ "detail": "..." }` or `{ "task_id": "...", "status": "failed", "message": "Failed to export result: ...", "output_path": "..." }` |

`output_path` is evaluated by the API service, not by the machine that sent the HTTP request.

- On a local development machine, it is a local filesystem path.
- In Docker, it is a path inside the running service container. To persist exports, the destination must be under a directory mounted into that container.
- On a remote host, it is a path reachable by the remote service process or container. It cannot directly write to the caller's desktop.

## 6. Cancel a Waiting Task

```http
POST /api/review/jobs/{task_id}/cancel
Authorization: <secret_key>
```

PowerShell example:

```powershell
curl.exe -X POST "http://localhost:5000/api/review/jobs/20260714-143119-5ece/cancel" `
  -H "Authorization: platform-key-for-client-a"
```

Successful response, HTTP `200`:

```json
{
  "task_id": "20260714-143119-5ece",
  "status": "cancelled",
  "message": "Review job cancelled."
}
```

| HTTP status | When returned | Response |
| --- | --- | --- |
| `200` | Current status is `pending` or `queued`; the task is cancelled. | Task ID, `cancelled`, and message. |
| `401` | Authorization fails. | `{ "detail": "..." }` |
| `404` | Task ID is invalid, missing, or belongs to another client. | `{ "detail": "Task not found." }` |
| `409` | Task is `running`, `succeeded`, `failed`, or already `cancelled`. | `{ "detail": "..." }` or a JSON message for `running`. |
| `500` | API client mapping is malformed or ambiguous. | `{ "detail": "..." }` |

## 7. Client Data Isolation

API task data is partitioned by the `client_dir` resolved from the authenticated client key:

```text
data/api/clients/<client_dir>/tasks/<task_id>/
  task.json
  input/
  output/
  logs/
```

The caller does not submit `client_id` in an API request. The server identifies the client from its key, then reads tasks only below that client's `client_dir`.

For example, assume client A owns task `20260714-143119-5ece` and client B sends a valid key. Client B receives the following responses:

| Request made by client B for client A's task | HTTP status | Response |
| --- | --- | --- |
| `GET /api/review/jobs/20260714-143119-5ece` | `404` | `{ "detail": "Task not found." }` |
| `POST /api/review/jobs/20260714-143119-5ece/result` | `404` | `{ "detail": "Task not found." }` |
| `POST /api/review/jobs/20260714-143119-5ece/cancel` | `404` | `{ "detail": "Task not found." }` |

The same `404` is returned for a nonexistent task ID. This prevents a client from using status codes to determine whether another client's task exists.

The isolation depends on each API client record using an exclusive `client_dir`. Do not manually create or edit `user_profiles/api_clients.json` records that share a `client_dir`.

## 8. Common Route Errors

| Incorrect request | Result | Correct request |
| --- | --- | --- |
| `POST /review/jobs/{task_id}` | `404 Not Found` | `GET /api/review/jobs/{task_id}` for status. |
| `POST /api/review/jobs/result` | `405 Method Not Allowed` | `POST /api/review/jobs/{task_id}/result`. |
| `POST /api/review/jobs/{task_id}/result` with `{ "output": "..." }` | `400 output_path is required.` | Use `{ "output_path": "..." }`. |
| PowerShell `curl.exe` JSON loses double quotes | `422 json_invalid` | Use the escaped `-d '{\"output_path\":\"...\"}'` form shown above. |
