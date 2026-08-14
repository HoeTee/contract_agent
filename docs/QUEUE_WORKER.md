# 审查任务队列架构

本文说明普通 `/api/review/jobs` 的队列执行层。外部 API 路径和请求体保持不变，变化只发生在服务内部执行方式。

## 结构

```text
API service
  POST /api/review/jobs
  POST /api/review/jobs/status
  POST /api/review/jobs/result

Task queue
  Redis broker

Worker service
  Celery worker
  run_async_review_job(client_dir, task_id)

Shared storage
  data/api/<task_id>/
```

## 进程隔离

这个队列层的核心目的不是单纯限制并发，而是把 API 进程和审查执行进程分开。

旧结构中，`/api/review/jobs` 会在 uvicorn 所在的 API 进程内用 `asyncio.create_task(...)` 启动审查任务。此时 `/status` 请求和 workflow、MCP、LLM 调用、DOCX 生成、日志写入都共享同一个 Python 进程、同一个事件循环、同一组线程池和同一份进程资源。即使 `/status` 逻辑只是读取 `task.json`，它也需要等待 API 进程获得调度机会。

队列结构中：

```text
API process
  /api/review/jobs
  /api/review/jobs/status
  /api/review/jobs/result

Worker process
  workflow.run()
  MCP
  LLM calls
  DOCX generation
  task logs
```

worker 忙于审查时，API 进程仍然可以处理 `/status`。这就是本阶段引入 Celery 的主要价值。Celery 的并发控制只是附带能力；真正解决的是 HTTP 状态查询和重型审查任务不再抢同一个 API 进程。

## Celery 概念边界

Celery 不是单独一个“队列进程”。本项目里需要区分三个概念：

```text
Task
  任务类型，定义一类任务如何执行。
  代码位置：queue/review_tasks.py
  当前任务名：review.run_job

Broker
  队列消息存储，本项目使用 Redis。
  代码配置：queue.broker_url
  当前消息内容：client_dir + task_id

Worker
  独立执行进程，连接 broker，消费 task 并执行对应 Python 函数。
  启动方式：celery -A queue.celery_app:celery_app worker ...
```

`@celery_app.task(name="review.run_job")` 定义的是任务类型，不是 worker：

```python
@celery_app.task(name="review.run_job")
def run_review_job_task(client_dir: str, task_id: str) -> dict[str, str]:
    ...
```

API 调用 `.delay(...)` 时，只是向 Redis broker 写入一条待执行消息：

```python
run_review_job_task.delay(client_dir, task_id)
```

真正执行这条消息的是 worker 进程。Docker Compose 中的 `review-worker` service 才是 worker 的部署形态：

```yaml
review-worker:
  command: ["celery", "-A", "queue.celery_app:celery_app", "worker", "--loglevel=info", "--concurrency=3"]
```

如果只启动 Redis 而不启动 worker，任务会留在队列里，不会执行。如果只启动 worker 而没有 Redis，worker 无法连接 broker，也无法取任务。

worker 并发由启动命令控制：

```text
--concurrency=3
```

表示一个 worker 容器内部最多同时执行 3 个 `review.run_job`。如果部署多个 worker 容器，总合同任务并发约等于：

```text
worker 容器数量 * 每个 worker 的 --concurrency
```

这个并发只控制“整份合同审查任务”的并发，不控制单份合同内部 subagent/criterion 并发。单份合同内部并发仍由 `workflow.max_orchestrator_concurrency` 控制。

第二阶段的 criterion 级恢复、SubAgent/Reflector 执行边界、以及为什么业务输入输出不写入 Redis broker，见 `docs/CRITERION_RECOVERY.md`。

`POST /api/review/jobs` 仍然负责校验请求头和请求体、保存输入文件、创建 `task.json` 并返回 `task_id`。只有合法提交才进入任务生命周期；请求协议错误、JSON 格式错误或提交字段缺失不应创建 `task_id`、任务目录或 `task.json`。

当 `queue.enabled=true` 时，API 不再直接执行审查 workflow，而是把 `client_dir` 和 `task_id` 投递到 Celery 队列。API 投递成功后，任务初始状态仍是 `pending`；`queued` 不是“已经写入 Celery broker”的同义词。

状态语义由 worker 执行阶段决定：

| 状态 | 写入位置 | 含义 |
| --- | --- | --- |
| `pending` | API 提交阶段 | 合法任务已写入存储并投递，worker 尚未进入执行资源判断。 |
| `queued` | worker 执行入口 | worker 已接手任务，但执行槽位已满，正在等待。 |
| `running` | worker 获得执行槽位后 | 审查 workflow 已开始运行。 |

因此 API 层不能因为 `queue.enabled=true` 就直接把新任务标记为 `queued`。如果没有实际等待执行槽位，状态应保持 `pending`，直到 worker 将其推进到 `running` 或真正等待时标记为 `queued`。

`POST /api/review/jobs/status` 仍然只读取 `data/api/<task_id>/task.json`。它不等待模型调用、MCP、DOCX 生成或日志写入。

## 配置

```yaml
queue:
  enabled: true
  broker_url: "redis://localhost:6379/0"
```

- `enabled=true`：`/api/review/jobs` 提交后投递到 Celery。
- `enabled=false`：回退到旧行为，在 API 进程内 `asyncio.create_task(...)` 执行审查。
- `broker_url`：Celery broker 地址，API 投递任务、worker 消费任务都使用它。

Redis 是独立服务，不会随 `uvicorn` 自动启动。本机默认地址是 `redis://localhost:6379/...`。Docker Compose 内部应使用 service 名称，例如 `redis://redis:6379/0`。

## 启动

本地需要三个进程：

```powershell
redis-server
uvicorn app:app --host 0.0.0.0 --port 5000
celery -A queue.celery_app:celery_app worker --loglevel=info --pool=solo
```

Windows 本地建议使用 `--pool=solo`。Linux 容器部署可以按资源情况选择 Celery 默认 prefork 或显式设置 worker 并发。

## 代码位置

```text
queue/celery_app.py       Celery app 配置
queue/review_tasks.py     Celery task，调用审查执行入口
queue/review_queue.py     API 层投递 helper
endpoints/api/review_jobs.py   提交任务后投递队列
endpoints/review/job_worker.py 审查执行入口
```

## 边界

第一阶段队列单位是一份合同审查任务：

```text
client_dir + task_id
```

本阶段不拆分 criterion/subagent，不提供模型调用级别的局部恢复，也不解决模型网关 429。它解决的是 API 进程和审查执行进程隔离，让 `/status` 在高并发审查时仍能读取任务状态。
