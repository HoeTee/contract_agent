# Reranker 配置注意事项

本文记录当前 reranker 接入边界、配置规则和常见报错原因。

## 当前配置约定

`config.yaml` 中只保留三个字段：

```yaml
rerank:
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1/reranks"
  name: "qwen3-rerank"
  inject_instruct: false
```

`base_url` 必须填写完整的 HTTP 请求 URL。程序不会自动拼接 `/rerank`、`/reranks` 或任何厂商专用路径。

`endpoint_format` 已经移除。旧部署配置里如果还存在 `rerank.endpoint_format`，必须删除。

## 请求体

当前代码发送的是通用 rerank 请求体：

```json
{
  "model": "qwen3-rerank",
  "query": "合同审查检索问题",
  "documents": ["候选文本 1", "候选文本 2"],
  "top_n": 5
}
```

当 `rerank.inject_instruct: true` 时，请求体会额外加入：

```json
{
  "instruct": "Given a contract review query, retrieve relevant institutional policy passages."
}
```

只有目标 reranker 服务明确支持 `instruct` 字段时才开启。接入 `bge-rerank-v2-m3` 或多数内网通用 reranker 服务时，建议使用：

```yaml
inject_instruct: false
```

## 响应体

当前解析器支持两种响应结构：

```json
{
  "results": [
    {"index": 0, "relevance_score": 0.98}
  ]
}
```

或：

```json
{
  "output": {
    "results": [
      {"index": 0, "relevance_score": 0.98}
    ]
  }
}
```

每个结果项必须包含 `index`。`relevance_score` 可选；缺失时保留原始检索分数。

## DashScope 模型和 URL 边界

DashScope 的 rerank 模型不是都用同一个 URL。

`qwen3-rerank` 应使用兼容 rerank URL，例如：

```text
https://dashscope.aliyuncs.com/compatible-mode/v1/reranks
```

部分百炼工作空间或地域化部署会使用带 WorkspaceId 的 URL，例如：

```text
https://<WorkspaceId>.<region>.maas.aliyuncs.com/compatible-mode/v1/reranks
```

请以实际工作空间控制台给出的地址为准。

`gte-rerank-v2` 和 `qwen3-vl-rerank` 使用的是另一类原生 URL：

```text
https://<WorkspaceId>.<region>.maas.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank
```

如果把 `qwen3-rerank` 配到这个原生 URL，服务端会返回 HTTP `400`。这不是重试次数问题，也不是 Web/API 差异，而是模型和 URL 不匹配。

## bge-rerank-v2-m3 内网配置

如果内网服务暴露的是 `bge-rerank-v2-m3`，配置应使用内网服务实际提供的完整 URL：

```yaml
rerank:
  base_url: "http://<host>:<port>/v1/rerank"
  name: "bge-rerank-v2-m3"
  inject_instruct: false
```

如果内网服务路径是 `/reranks`，就直接把 `/reranks` 写进 `base_url`。

## 重试行为

reranker 调用复用 workflow 的模型调用配置：

```yaml
workflow:
  model_call_timeout_seconds: 60
  model_call_max_retries: 5
```

只会对临时性错误重试：

- HTTP `408`
- HTTP `409`
- HTTP `429`
- HTTP `5xx`
- 网络超时或连接失败

HTTP `400` 表示请求格式或配置错误，不会重试。日志中出现 `failed after 1 attempt(s): HTTP 400` 时，优先检查：

1. `rerank.base_url` 是否和模型匹配。
2. `rerank.name` 是否是该服务支持的模型名。
3. 目标服务是否支持当前通用请求体。
4. `inject_instruct` 是否被错误开启。

## 排障入口

出现 `reranker_call_failed` 时，先看任务事件日志：

```text
data/api/<task_id>/logs/api_events.jsonl
data/web/<tenant_id>/<task_id>/logs/api_events.jsonl
```

如果日志是 HTTP `400`，优先按“模型和 URL 是否匹配”排查。当前项目已经移除 `endpoint_format`，不要再通过该字段尝试修复 URL 或请求体问题。
