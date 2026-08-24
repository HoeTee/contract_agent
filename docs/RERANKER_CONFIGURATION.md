# Reranker Configuration

本文说明 reranker 的配置边界、provider 推断规则和三种请求体风格。

## 配置字段

`config.yaml` 中不再配置 `rerank.provider`。程序会根据 `rerank.name` 或请求体中的 `reranker_model_name`，在 `rerank.provider_model_names` 中查找对应 provider。

```yaml
rerank:
  base_url: "http://higress.llmgateway.dev.qa.zrub.com/v1/rerank"
  name: "Qwen3-Reranker-8B"
  instruct: "Given a contract review query, retrieve relevant institutional policy passages."
  provider_model_names:
    higress_qwen:
      - "Qwen3-Reranker-8B"
    bge:
      - "bge-reranker-v2-m3"
    dashscope_qwen:
      - "qwen3-rerank"
      - "gte-rerank-v2"

retrieval:
  llamaindex:
    rerank_top_n: 5
```

字段说明：

- `rerank.base_url`：完整 HTTP 请求 URL，程序不会自动拼接路径。
- `rerank.name`：默认 reranker 模型名。
- `rerank.instruct`：可选指令。仅 `higress_qwen` 和 `dashscope_qwen` 在非空时发送；`bge` 不发送。
- `rerank.provider_model_names`：provider 到模型名列表的映射。模型名不能同时出现在多个 provider 下。
- `retrieval.llamaindex.rerank_top_n`：LlamaIndex 检索下，三种 provider 都会作为 `top_n` 发送。

如果开启 `api.require_request_model_config: true`，API 请求体里的 `reranker_model_name` 也会通过同一份 `provider_model_names` 映射推断 provider。

## Higress Qwen

配置示例：

```yaml
rerank:
  base_url: "http://higress.llmgateway.dev.qa.zrub.com/v1/rerank"
  name: "Qwen3-Reranker-8B"
  instruct: "Given a contract review query, retrieve relevant institutional policy passages."
  provider_model_names:
    higress_qwen:
      - "Qwen3-Reranker-8B"
```

请求体：

```json
{
  "model": "Qwen3-Reranker-8B",
  "query": "合同审查检索问题",
  "documents": ["候选文本", "候选文本"],
  "top_n": 5,
  "instruct": "Given a contract review query, retrieve relevant institutional policy passages."
}
```

## BGE

配置示例：

```yaml
rerank:
  base_url: "http://<host>:<port>/rerank"
  name: "bge-reranker-v2-m3"
  instruct: ""
  provider_model_names:
    bge:
      - "bge-reranker-v2-m3"
```

请求体：

```json
{
  "query": "合同审查检索问题",
  "documents": ["候选文本", "候选文本"],
  "top_n": 5
}
```

`bge` 风格不发送 `model`，也不发送 `instruct`。

## DashScope Qwen

配置示例：

```yaml
rerank:
  base_url: "https://<WORKSPACE_ID>.cn-beijing.maas.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
  name: "qwen3-rerank"
  instruct: "Given a contract review query, retrieve relevant institutional policy passages."
  provider_model_names:
    dashscope_qwen:
      - "qwen3-rerank"
      - "gte-rerank-v2"
```

请求体：

```json
{
  "model": "qwen3-rerank",
  "input": {
    "query": "合同审查检索问题",
    "documents": ["候选文本", "候选文本"]
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

每个结果项必须包含 `index`。分数字段支持 `relevance_score` 或 `score`。

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

HTTP `400` 表示请求格式、模型名、URL 或 provider 映射错误，不会重试。日志中出现 `failed after 1 attempt(s): HTTP 400` 时，优先检查：

1. `rerank.provider_model_names` 是否包含当前 `rerank.name` 或请求体 `reranker_model_name`。
2. `rerank.base_url` 是否是目标服务真实完整 URL。
3. `rerank.name` 是否是实际部署的模型名。
4. `rerank.instruct` 是否被目标服务支持。
