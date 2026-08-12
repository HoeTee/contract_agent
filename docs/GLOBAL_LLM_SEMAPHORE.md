# 全局模型并发控制

本文说明 Redis 全局模型 semaphore 的设计。该机制用于控制所有容器、所有 worker、所有模型 HTTP 请求总并发。

## 解决的问题

Celery worker 数量和 workflow 内部并发会叠加模型请求压力：

```text
worker 容器数 * 每个 worker 的 --concurrency * 单任务内部 criterion 并发
```

这些配置只能粗略控制任务推进宽度，不能严格保证同一时刻发往模型网关的 HTTP 请求数。多个 worker 容器之间也不会共享 Python 进程内的 `asyncio.Semaphore`。

全局模型 semaphore 的目标是：

```text
任意时刻，全项目最多 N 个指定类型的模型 HTTP 请求正在执行。
```

## 控制范围

当前埋点分为三类：

```text
LLM:
  agents/base_agent.py
    Agent.execute()
      self.client.chat.completions.create(...)

Embedding:
  tools/retrieval/llamaindex/limited_embedding.py
    SemaphoreOpenAILikeEmbedding

Reranker:
  tools/retrieval/llamaindex/qwen_reranker.py
    QwenRerankPostprocessor._request_json_with_retries()
```

因此以下调用都会受控：

```text
Planner
SubAgent
Reflector
Summarizer
embedding
reranker
```

MCP 工具内部的非模型操作不在控制范围内。

## Redis 令牌含义

Redis 中维护一个有过期时间的令牌集合。一次 LLM 请求开始前：

```text
1. 删除已过期令牌
2. 检查当前令牌数是否小于上限
3. 小于上限则写入当前请求令牌
4. 请求结束后删除自己的令牌
```

如果令牌已满，请求会等待；等待超过配置时间后，当前模型调用失败，并记录到 trace。

## 配置

```yaml
model_semaphore:
  llm:
    enabled: true
    max_concurrent_requests: 10
    redis_url: "redis://redis:6379/2"
    key: "contract_agent:model:llm:semaphore"
    wait_timeout_seconds: 600
    lease_seconds: 600
    poll_interval_seconds: 0.2
  embedding:
    enabled: true
    max_concurrent_requests: 5
    redis_url: "redis://redis:6379/2"
    key: "contract_agent:model:embedding:semaphore"
    wait_timeout_seconds: 600
    lease_seconds: 600
    poll_interval_seconds: 0.2
  reranker:
    enabled: true
    max_concurrent_requests: 5
    redis_url: "redis://redis:6379/2"
    key: "contract_agent:model:reranker:semaphore"
    wait_timeout_seconds: 600
    lease_seconds: 600
    poll_interval_seconds: 0.2
```

字段含义：

```text
enabled
  是否启用全局 LLM 并发控制。

max_concurrent_requests
  全项目同时执行中的该类型模型 HTTP 请求上限。

redis_url
  semaphore 使用的 Redis 地址。Docker Compose 内应使用 redis 服务名。

key
  Redis key 名称。

wait_timeout_seconds
  等待令牌的最长时间。

lease_seconds
  令牌租约时间。用于防止进程崩溃后令牌永久占用。

poll_interval_seconds
  令牌满时的重试等待间隔。
```

## 与其他并发配置的关系

该配置不会替代 Celery 或 workflow 并发配置。

```text
全局模型 semaphore
  控制模型 HTTP 请求硬上限。

Celery worker 数量 / --concurrency
  控制同时执行多少份合同任务。

workflow.max_orchestrator_concurrency
  控制单份合同内部同时推进多少个 criterion。
```

推荐先保守配置：

```text
至少 3 个 worker 容器
每个 worker --concurrency=1
workflow.max_orchestrator_concurrency=3
model_semaphore.llm.max_concurrent_requests=10
model_semaphore.embedding.max_concurrent_requests=5
model_semaphore.reranker.max_concurrent_requests=5
```

这样即使任务推进较宽，也会在模型调用入口被全局限流，避免瞬间打爆模型网关。

## Trace 记录

启用后，每个 `llm.*` span 会记录：

```text
llm_global_semaphore_key
llm_global_semaphore_wait_seconds
llm_global_semaphore_max_requests
```

这些字段用于判断模型调用是在直接执行，还是在等待全局令牌。

embedding 和 reranker 当前通过 `events.log` 记录 `model_semaphore_acquired` 事件。
