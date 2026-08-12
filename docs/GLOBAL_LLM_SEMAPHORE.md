# 全局 LLM 并发控制

本文说明 Redis 全局 LLM semaphore 的设计。该机制用于控制所有容器、所有 worker、所有 agent 的 LLM HTTP 请求总并发。

## 解决的问题

Celery worker 数量和 workflow 内部并发会叠加模型请求压力：

```text
worker 容器数 * 每个 worker 的 --concurrency * 单任务内部 criterion 并发
```

这些配置只能粗略控制任务推进宽度，不能严格保证同一时刻发往模型网关的 HTTP 请求数。多个 worker 容器之间也不会共享 Python 进程内的 `asyncio.Semaphore`。

全局 LLM semaphore 的目标是：

```text
任意时刻，全项目最多 N 个 LLM HTTP 请求正在执行。
```

## 控制范围

当前埋点在统一 LLM 调用入口：

```text
agents/base_agent.py
  Agent.execute()
    self.client.chat.completions.create(...)
```

因此以下 agent 调用都会受控：

```text
Planner
SubAgent
Reflector
Summarizer
```

不在当前控制范围内：

```text
embedding
reranker
MCP 工具内部的非 LLM 操作
```

如果后续需要严格控制 embedding 或 reranker，需要在它们各自的统一 HTTP 调用入口增加独立 semaphore。

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
llm:
  global_semaphore_enabled: true
  max_global_concurrent_requests: 10
  global_semaphore_redis_url: "redis://redis:6379/2"
  global_semaphore_key: "contract_agent:llm:semaphore"
  global_semaphore_wait_timeout_seconds: 600
  global_semaphore_lease_seconds: 600
  global_semaphore_poll_interval_seconds: 0.2
```

字段含义：

```text
global_semaphore_enabled
  是否启用全局 LLM 并发控制。

max_global_concurrent_requests
  全项目同时执行中的 LLM HTTP 请求上限。

global_semaphore_redis_url
  semaphore 使用的 Redis 地址。Docker Compose 内应使用 redis 服务名。

global_semaphore_key
  Redis key 名称。

global_semaphore_wait_timeout_seconds
  等待令牌的最长时间。

global_semaphore_lease_seconds
  令牌租约时间。用于防止进程崩溃后令牌永久占用。

global_semaphore_poll_interval_seconds
  令牌满时的重试等待间隔。
```

## 与其他并发配置的关系

该配置不会替代 Celery 或 workflow 并发配置。

```text
全局 LLM semaphore
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
llm.max_global_concurrent_requests=10
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
