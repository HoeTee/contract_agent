# Reranker Configuration Notes

This document records the current reranker integration boundary and common deployment pitfalls.

## Current Contract

The reranker is configured by:

```yaml
rerank:
  base_url: "http://your-reranker-host/v1/rerank"
  name: "bge-rerank-v2-m3"
  inject_instruct: false
```

`base_url` must be the complete HTTP request URL. The application does not append `/rerank`, `/reranks`, or any provider-specific path.

There is no `endpoint_format` setting. If an old deployment config still contains `rerank.endpoint_format`, remove it.

## Request Body

The current implementation sends this generic request body:

```json
{
  "model": "bge-rerank-v2-m3",
  "query": "contract review query",
  "documents": ["passage 1", "passage 2"],
  "top_n": 5
}
```

When `rerank.inject_instruct: true`, the body also includes:

```json
{
  "instruct": "Given a contract review query, retrieve relevant institutional policy passages."
}
```

Only enable `inject_instruct` when the target reranker service explicitly accepts an `instruct` field. For `bge-rerank-v2-m3` and most internal reranker services, use:

```yaml
inject_instruct: false
```

## Response Body

The parser accepts either of these response shapes:

```json
{
  "results": [
    {"index": 0, "relevance_score": 0.98}
  ]
}
```

or:

```json
{
  "output": {
    "results": [
      {"index": 0, "relevance_score": 0.98}
    ]
  }
}
```

Each result item must include `index`. `relevance_score` is optional; when it is missing, the original retrieval score is preserved.

## DashScope Boundary

The current code does not contain a DashScope-specific reranker branch. If `base_url` points to a DashScope native rerank endpoint such as:

```text
https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank
```

the request may fail with HTTP 400 if DashScope expects a provider-specific request body. In that case, either:

- use an internal/OpenAI-compatible reranker endpoint that accepts the generic body above, or
- add a dedicated DashScope adapter in code.

Do not try to fix a DashScope native-body mismatch with `endpoint_format`; that setting has been removed and no longer exists.

## Retry Behavior

Reranker calls reuse workflow retry settings:

```yaml
workflow:
  model_call_timeout_seconds: 60
  model_call_max_retries: 5
```

Retries are only attempted for transient failures:

- HTTP `408`
- HTTP `409`
- HTTP `429`
- HTTP `5xx`
- network timeout or connection failure

HTTP `400` is treated as a request-format/configuration error and is not retried. A log message such as `failed after 1 attempt(s): HTTP 400` usually means the request URL, model name, request body, or `inject_instruct` setting is incompatible with the target reranker service.

## Recommended Internal BGE Setup

For an internal service exposing `bge-rerank-v2-m3`, use the exact endpoint provided by that service:

```yaml
rerank:
  base_url: "http://<host>:<port>/v1/rerank"
  name: "bge-rerank-v2-m3"
  inject_instruct: false
```

If the internal service exposes `/reranks` instead of `/rerank`, put `/reranks` directly in `base_url`.

## Troubleshooting Checklist

When `reranker_call_failed` appears:

1. Check `data/api/<task_id>/logs/api_events.jsonl` or `data/web/<tenant_id>/<task_id>/logs/api_events.jsonl`.
2. Confirm the error status.
3. For HTTP `400`, verify `base_url`, `name`, request-body compatibility, and `inject_instruct`.
4. For HTTP `429` or `5xx`, check retry events and the upstream reranker service health.
5. For timeout errors, increase `workflow.model_call_timeout_seconds` only after confirming the service is reachable.

