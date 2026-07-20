# Reranker 配置注意事项

本文记录当前 reranker 的配置边界、请求体格式和常见报错原因。

## 配置字段

`config.yaml` 中使用以下字段：

```yaml
rerank:
  base_url: "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
  name: "qwen3-rerank"
  provider: "dashscope"
  inject_instruct: false
```

`base_url` 必须填写完整的 HTTP 请求 URL。程序不会自动拼接 `/rerank`、`/reranks` 或任何厂商路径。

`provider` 只允许两个值：

- `dashscope`：使用 DashScope 原生 rerank 请求体。
- `bge`：使用内网 BGE 或通用 rerank 请求体。

`endpoint_format` 已经移除。旧部署配置里如果还存在 `rerank.endpoint_format`，必须删除。

## DashScope 请求体

当 `rerank.provider: "dashscope"` 时，代码发送 DashScope 原生请求体：

```json
{
  "model": "qwen3-rerank",
  "input": {
    "query": "合同审查检索问题",
    "documents": ["候选文本 1", "候选文本 2"]
  },
  "parameters": {
    "return_documents": false,
    "top_n": 5
  }
}
```

DashScope 原生 URL 示例：

```text
https://<WorkspaceId>.<region>.maas.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank
```

用户从 DashScope 官方文档复制的 `qwen3-rerank` 原生 URL 示例可以使用，但必须把 `provider` 配成 `dashscope`，否则代码会按 BGE 通用 body 发送，服务端通常会返回 HTTP `400`。

DashScope 原生接口通常不需要 `instruct`。除非目标服务文档明确说明支持，否则建议：

```yaml
inject_instruct: false
```

## BGE 请求体

当 `rerank.provider: "bge"` 时，代码发送通用 rerank 请求体：

```json
{
  "model": "bge-rerank-v2-m3",
  "query": "合同审查检索问题",
  "documents": ["候选文本 1", "候选文本 2"],
  "top_n": 5
}
```

内网 BGE 配置示例：

```yaml
rerank:
  base_url: "http://<host>:<port>/v1/rerank"
  name: "bge-rerank-v2-m3"
  provider: "bge"
  inject_instruct: false
```

如果内网服务路径是 `/reranks`，就直接把完整 `/reranks` URL 写进 `base_url`。

BGE 和多数内网通用 reranker 服务不支持 `instruct` 字段，建议保持：

```yaml
inject_instruct: false
```

## 响应体

当前解析器支持两种响应结构。

通用响应：

```json
{
  "results": [
    {"index": 0, "relevance_score": 0.98}
  ]
}
```

DashScope 响应：

```json
{
  "output": {
    "results": [
      {"index": 0, "relevance_score": 0.98}
    ]
  }
}
```

每个结果项必须包含 `index`。`relevance_score` 可选，缺失时保留原始检索分数。

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
3. `rerank.name` 是否是该服务支持的模型名。
4. `inject_instruct` 是否被错误开启。

## 排障入口

出现 `reranker_call_failed` 时，先看任务事件日志：

```text
data/api/<task_id>/logs/api_events.jsonl
data/web/<tenant_id>/<task_id>/logs/api_events.jsonl
```

如果日志是 HTTP `400`，优先按 provider 和请求体格式排查，不要通过恢复 `endpoint_format` 解决。

## 本次问题复盘

这次 reranker 问题的根因不是简单的“模型和 URL 不匹配”，而是代码把所有 reranker 都按同一种通用 body 发送了。

错误判断是：看到 `qwen3-rerank` 使用 DashScope 原生 URL 后，直接认为这个 URL 不能用于该模型。用户后来贴出的 DashScope 官方示例证明，`qwen3-rerank` 可以使用原生 URL，但请求体必须是 DashScope 原生格式：

```json
{
  "model": "qwen3-rerank",
  "input": {
    "query": "查询文本",
    "documents": ["候选文本"]
  },
  "parameters": {
    "return_documents": true,
    "top_n": 5
  }
}
```

而 BGE 或内网通用 reranker 通常使用扁平格式：

```json
{
  "model": "bge-rerank-v2-m3",
  "query": "查询文本",
  "documents": ["候选文本"],
  "top_n": 5
}
```

因此以后不能只靠 `base_url` 或 `model name` 推断请求体，也不能恢复 `endpoint_format` 这类含义混乱的字段。当前明确使用 `rerank.provider` 控制 body：

- `provider: "dashscope"`：发送 DashScope 原生 body。
- `provider: "bge"`：发送 BGE/通用 body。

排查同类问题时按这个顺序看：

1. 先确认 `provider` 是否和服务类型一致。
2. 再确认 `base_url` 是否是完整请求 URL。
3. 再确认 `name` 是否是服务支持的模型名。
4. 最后看 `inject_instruct` 是否导致服务端拒绝请求。

HTTP `400` 一般是请求体或配置错误，不应期待通过重试解决。Web 和 API 都走同一条 reranker 调用链，如果两端表现不同，应优先看它们实际使用的配置文件、环境变量和任务日志是否一致。
