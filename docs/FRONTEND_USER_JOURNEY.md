# Frontend User Journey

This document describes the Web UI flow for normal users.

## Main Flow

```text
GET /web
  -> clear transient page alerts
  -> clear existing auth contexts
  -> render login.html

POST /web/login
  -> verify tenant/user/password
  -> clear transient page alerts on successful login
  -> create ctx
  -> admin: /web/admin
  -> user: /web/work

GET /web/work
  -> read latest Web task from data/web/<tenant_id>/
  -> show upload form when no pending/queued/running task exists
  -> show current task status when a task is active
  -> show download entry when the latest task succeeded

POST /web/review
  -> validate DOCX input
  -> optionally validate uploaded review criteria DOCX
  -> create task.json in data/web/<tenant_id>/<task_id>/
  -> dispatch the shared review worker
  -> redirect to /web/work
```

## Task State

Web no longer uses an in-memory `review_tasks` dictionary as the source of truth. Web tasks are stored as task-store records under:

```text
data/web/<tenant_id>/<task_id>/task.json
```

The Web route uses the same worker/status model as API tasks:

```text
pending
  -> queued
  -> running
  -> succeeded

pending/queued/running
  -> failed
```

API and Web storage remain separate:

```text
data/api/<task_id>/
data/web/<tenant_id>/<task_id>/
```

`task.json` remains the task-state file for the full job lifecycle. The Web route does not overwrite it with a separate history-only record after submit; when a review succeeds, the display fields needed by `/web/history` are merged into the same `task.json`.

## Logs

Web review tasks write event logs through the shared task-store logging helper. The log location is:

```text
data/web/<tenant_id>/<task_id>/logs/api_events.jsonl
```

Model call errors are recorded with the same event code/component pattern used by API tasks.

## Login State

Transient page alerts such as upload errors, settings errors, and admin flash messages are session-scoped. Re-entering `/web` or `/web/login`, logging out, or logging in successfully clears those transient alerts so a new login starts from an initialized page state. Direct login validation errors still render on `login.html` for the current failed submit.

Entering `/web` or `/web/login` also clears existing `auth_contexts`. A stale workbench URL with an old `ctx` must not remain valid after the user intentionally returns to the login entry point.

Each successful login creates a new `ctx` with its own `login_created_at`. `/web/work` does not show failed-task alerts from tasks created before that login timestamp. Older failed tasks remain in task storage/history for audit and troubleshooting, but they must not pollute a freshly logged-in workbench.

## Frontend State Invariants

The Web UI must keep persisted audit data separate from current-page state:

- A fresh login must render an initialized workbench. Historical task failures may remain in `data/web/<tenant_id>/<task_id>/task.json`, but they must not reappear as current page errors unless the failed task was created in the current login context.
- Flash messages are one-shot page state. They are allowed to survive a redirect in the same workflow, but must be cleared when entering `/web`, entering `/web/login`, logging out, or completing a successful login.
- Returning to the login entry point is a reset boundary. It must invalidate old `ctx` values so stale tabs cannot keep rendering old workbench state after a re-login.
- Failed tasks are audit records after the user starts a new login context. They can be shown in history or logs, but should not block a new upload or make the workbench look like the new session is already in an error state.
- Running tasks are different from failed historical tasks. A pending, queued, or running task for the same user and tenant should still be shown and should still prevent duplicate submission.
- Do not derive current UI alerts directly from "latest task" without checking task status and login context. This is the class of bug where a stale `failed` task makes every later login look broken.

## Upload Rules

- Contract file is required.
- Contract file must be DOCX.
- Review criteria file is optional.
- If provided, the review criteria file must be DOCX and must pass review-criteria validation.
- If not provided, the user's default review criteria is used.

## Result Download

Successful Web reviews are shown in history from `data/web/<tenant_id>/*/task.json`. Downloads resolve through those task records and task output paths under `data/web/<tenant_id>/<task_id>/output/`.
