# Reranker 配置注意事项

本文记录当前 reranker 的配置边界、请求体格式和常见报错原因。

## 配置字段

`config.yaml` 中使用以下字段：

```yaml
rerank:
  base_url: "https://<WorkspaceId>.<region>.maas.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
  name: "qwen3-rerank"
  provider: "dashscope"
  inject_instruct: false
```

`base_url` 必须填写完整的 HTTP 请求 URL。程序不会自动拼接 `/rerank`、`/reranks` 或任何厂商路径。

`provider` 只允许两个值：

- `dashscope`：使用 DashScope 原生 rerank HTTP API。
- `tei`：使用 Hugging Face Text Embeddings Inference 的 `/rerank` HTTP API。

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

用户从 DashScope 官方文档复制的 `qwen3-rerank` 原生 URL 示例可以使用，但必须把 `provider` 配成 `dashscope`。

DashScope 原生接口通常不需要 `instruct`。除非目标服务文档明确说明支持，否则建议：

```yaml
inject_instruct: false
```

## TEI 请求体

`bge-reranker-v2-m3` 是 BAAI 发布的模型，不是 HTTP API 协议。BAAI/FlagEmbedding 官方给的是本地 Python 推理用法，并没有规定统一的在线 HTTP body。

如果该模型由 Hugging Face Text Embeddings Inference 部署，则应使用 TEI 官方 `/rerank` 请求体：

```json
{
  "query": "合同审查检索问题",
  "texts": ["候选文本 1", "候选文本 2"],
  "raw_scores": false
}
```

TEI 配置示例：

```yaml
rerank:
  base_url: "http://<host>:<port>/rerank"
  name: "BAAI/bge-reranker-v2-m3"
  provider: "tei"
  inject_instruct: false
```

注意：

- `name` 仅用于记录模型名；TEI `/rerank` 请求体不会发送 `model` 字段。
- `rerank_top_n` 不会发送给 TEI；代码会拿到 TEI 排序结果后在本地截取前 `top_n`。
- TEI 官方请求体使用 `texts`，不是 `documents`。
- TEI 官方请求体不包含 `instruct`，建议保持 `inject_instruct: false`。

## 响应体

当前解析器支持三种响应结构。

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

带 `results` 包装的响应：

```json
{
  "results": [
    {"index": 0, "relevance_score": 0.98}
  ]
}
```

TEI 响应通常是数组：

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
4. `inject_instruct` 是否被错误开启。

## 排障入口

出现 `reranker_call_failed` 时，先看任务事件日志：

```text
data/api/<task_id>/logs/api_events.jsonl
data/web/<tenant_id>/<task_id>/logs/api_events.jsonl
```

如果日志是 HTTP `400`，优先按 provider 和请求体格式排查，不要通过恢复 `endpoint_format` 解决。

## 本次问题复盘

这次 reranker 问题暴露出两个错误假设。

第一，不能仅凭 `qwen3-rerank` 和 DashScope 原生 URL 就判断模型与 URL 不匹配。用户贴出的 DashScope 官方示例证明，`qwen3-rerank` 可以走 DashScope 原生 URL，但请求体必须是 DashScope 原生格式。

第二，不能把 `bge-reranker-v2-m3` 当成 HTTP API 协议。BGE 是 BAAI 发布的模型，HTTP body 由部署服务决定。如果内网使用 TEI 部署 BGE，就必须按 TEI 官方 `/rerank` 格式发送 `query/texts/raw_scores`。

因此当前只保留已知协议：

- `provider: "dashscope"`：发送 DashScope 原生 body。
- `provider: "tei"`：发送 Hugging Face TEI body。

如果后续内网服务不是 TEI，也不是 DashScope，必须先拿到该服务自己的接口文档，再增加新的 provider；不能预设一个所谓“通用格式”。
