# Frontend User Journey

This document describes the Web UI flow for normal users.

## Main Flow

```text
GET /web
  -> if session is missing: render login.html
  -> if session is valid: redirect by role

POST /web/login
  -> verify tenant/user/password
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
  -> create a Web-scoped task in data/web/<tenant_id>/<task_id>/
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

## Logs

Web review tasks write event logs through the shared task-store logging helper. The log location is:

```text
data/web/<tenant_id>/<task_id>/logs/api_events.jsonl
```

Model call errors are recorded with the same event code/component pattern used by API tasks.

## Upload Rules

- Contract file is required.
- Contract file must be DOCX.
- Review criteria file is optional.
- If provided, the review criteria file must be DOCX and must pass review-criteria validation.
- If not provided, the user's default review criteria is used.

## Result Download

Successful Web reviews are added to the Web history records. Downloads resolve through history records and task output paths under `data/web/<tenant_id>/<task_id>/output/`.
