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

`POST /api/review/jobs` 仍然负责保存输入文件、创建 `task.json` 并返回 `task_id`。当 `queue.enabled=true` 时，API 不再直接执行审查 workflow，而是把 `client_dir` 和 `task_id` 投递到 Celery 队列。

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
celery -A task_queue.celery_app:celery_app worker --loglevel=info --pool=solo
```

Windows 本地建议使用 `--pool=solo`。Linux 容器部署可以按资源情况选择 Celery 默认 prefork 或显式设置 worker 并发。

## 代码位置

```text
task_queue/celery_app.py       Celery app 配置
task_queue/review_tasks.py     Celery task，调用审查执行入口
task_queue/review_queue.py     API 层投递 helper
endpoints/api/review_jobs.py   提交任务后投递队列
endpoints/review/job_worker.py 审查执行入口
```

## 边界

第一阶段队列单位是一份合同审查任务：

```text
client_dir + task_id
```

本阶段不拆分 criterion/subagent，不提供模型调用级别的局部恢复，也不解决模型网关 429。它解决的是 API 进程和审查执行进程隔离，让 `/status` 在高并发审查时仍能读取任务状态。
