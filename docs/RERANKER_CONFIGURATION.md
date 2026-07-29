# Reranker Configuration

本文记录当前 reranker 的配置边界、三种 provider 的请求体格式和排障入口。

## 配置字段

`config.yaml` 使用以下字段：

```yaml
rerank:
  provider: "higress_qwen"
  base_url: "http://higress.llmgateway.dev.qa.zrub.com/v1/rerank"
  name: "Qwen3-Reranker-8B"
  instruct: "Given a contract review query, retrieve relevant institutional policy passages."

retrieval:
  rerank_top_n: 5
```

字段说明：

- `rerank.provider`：只允许 `higress_qwen`、`bge`、`dashscope_qwen`。
- `rerank.base_url`：完整 HTTP 请求 URL，程序不会自动拼接路径。
- `rerank.name`：模型名。`higress_qwen` 和 `dashscope_qwen` 必填；`bge` 不发送该字段。
- `rerank.instruct`：可选指令。仅 `higress_qwen` 和 `dashscope_qwen` 在非空时发送；`bge` 不发送。
- `retrieval.rerank_top_n`：三种 provider 都会作为 `top_n` 发送。

## Higress Qwen

配置示例：

```yaml
rerank:
  provider: "higress_qwen"
  base_url: "http://higress.llmgateway.dev.qa.zrub.com/v1/rerank"
  name: "Qwen3-Reranker-8B"
  instruct: "Given a contract review query, retrieve relevant institutional policy passages."
```

请求头：

```http
Authorization: Bearer <RERANK_API_KEY>
Content-Type: application/json
```

请求体：

```json
{
  "model": "Qwen3-Reranker-8B",
  "query": "合同审查检索问题",
  "documents": ["候选文本1", "候选文本2"],
  "top_n": 5,
  "instruct": "Given a contract review query, retrieve relevant institutional policy passages."
}
```

## BGE

配置示例：

```yaml
rerank:
  provider: "bge"
  base_url: "http://<host>:<port>/rerank"
  name: ""
  instruct: ""
```

请求头：

```http
Content-Type: application/json
```

请求体：

```json
{
  "query": "合同审查检索问题",
  "documents": ["候选文本1", "候选文本2"],
  "top_n": 5
}
```

`bge` 后端模型固定，不发送 `model`，也不发送 `instruct`。

## DashScope Qwen

配置示例：

```yaml
rerank:
  provider: "dashscope_qwen"
  base_url: "https://<WORKSPACE_ID>.cn-beijing.maas.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
  name: "qwen3-rerank"
  instruct: "Given a contract review query, retrieve relevant institutional policy passages."
```

请求头：

```http
Authorization: Bearer <RERANK_API_KEY>
Content-Type: application/json
```

请求体：

```json
{
  "model": "qwen3-rerank",
  "input": {
    "query": "合同审查检索问题",
    "documents": ["候选文本1", "候选文本2"]
  },
  "parameters": {
    "return_documents": false,
    "top_n": 5
  },
  "instruct": "Given a contract review query, retrieve relevant institutional policy passages."
}
```

## 响应体

当前解析器支持三种结果结构：

```json
{
  "output": {
    "results": [
      {"index": 0, "relevance_score": 0.98}
    ]
  }
}
```

```json
{
  "results": [
    {"index": 0, "relevance_score": 0.98}
  ]
}
```

```json
[
  {"index": 0, "score": 0.98}
]
```

每个结果项必须包含 `index`。分数字段支持 `relevance_score` 或 `score`，缺失时保留原始检索分数。

## 重试行为

reranker 调用复用 workflow 的模型调用配置：

```yaml
workflow:
  model_call_timeout_seconds: 60
  model_call_max_retries: 5
```

只会对临时错误重试：

- HTTP `408`
- HTTP `409`
- HTTP `429`
- HTTP `5xx`
- 网络超时或连接失败

HTTP `400` 表示请求格式、模型名、URL 或 provider 配置错误，不会重试。日志中出现 `failed after 1 attempt(s): HTTP 400` 时，优先检查：

1. `rerank.provider` 是否选对。
2. `rerank.base_url` 是否是目标服务真实完整 URL。
3. `rerank.name` 是否是实际部署的模型名。
4. `rerank.instruct` 是否被目标服务支持。

## 排障入口

出现 `reranker_call_failed` 时，先看任务事件日志：

```text
data/api/<task_id>/logs/api_events.jsonl
data/web/<tenant_id>/<task_id>/logs/api_events.jsonl
```

如果日志是 HTTP `400`，优先按 provider 和请求体格式排查，不要通过恢复旧的 `endpoint_format`、`tei` 或 `dashscope` provider 名称解决。
