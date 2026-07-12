# 异步 `/api/review` 任务 API

本文说明无 Cookie、直接调用的异步合同审查 API。异步设计用于避免 HTTP 长请求超时：提交任务后立即返回 `task_id`，后台继续审核，调用方后续查询状态并导出结果。

## 代码目录

```text
endpoints/
  api/
    review.py       # 同步 POST /api/review
    review_jobs.py  # 异步任务 API 路由
  review/
    task_store.py   # task.json、任务目录、input/output/logs 写入策略
    response.py     # 对外 API 响应过滤，避免暴露服务端路径
    meta.py         # meta fields 解析
    job_worker.py   # 异步审核后台任务
    callbacks.py    # 同步 API callback helper
```

## API 节点

### 提交任务

```http
POST /api/review/jobs
Content-Type: multipart/form-data
```

字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `file` | file | 是 | 待审查合同 DOCX |
| `criteria_file` | file | 否 | 本次审查标准 DOCX；不传则使用默认审查标准 |
| `templateCode` | string | 取决于配置 | 普通 `/api` 可接收的扩展字段 |
| `serialNo` | string | 取决于配置 | 普通 `/api` 可接收的扩展字段 |

成功响应：

```json
{
  "task_id": "20260712-144123-dccf",
  "status": "queued",
  "message": "Review job submitted."
}
```

### 查询状态

```http
GET /api/review/jobs/{task_id}
```

返回给普通 `/api` 调用方的是过滤后的任务视图，不暴露服务端绝对路径、日志路径或 `meta_fields`。

示例：

```json
{
  "task_id": "20260712-144123-dccf",
  "status": "running",
  "created_at": "2026-07-12T14:41:23+08:00",
  "started_at": "2026-07-12T14:42:01+08:00",
  "finished_at": null,
  "message": "Contract review is running.",
  "error": null,
  "input": {
    "contract_filename": "合同.docx",
    "criteria_source": "uploaded",
    "criteria_filename": "审查标准.docx",
    "stored": true
  },
  "output": {
    "result_filename": "合同_批注版.docx",
    "ready": false
  },
  "logs": {
    "enabled": true
  }
}
```

状态语义：

| 状态 | 含义 |
| --- | --- |
| `queued` | 已提交，等待并发执行槽位 |
| `running` | 已获得执行槽位，正在执行 workflow |
| `succeeded` | 审核成功，结果可导出 |
| `failed` | 审核失败 |
| `cancelled` | queued 阶段被取消 |

### 导出结果

```http
POST /api/review/jobs/{task_id}/result
Content-Type: application/json
```

请求 JSON：

```json
{
  "output_path": "C:\\Users\\lenovo\\Desktop\\review_result.docx"
}
```

行为：

| 情况 | 返回 |
| --- | --- |
| `succeeded` 且 `output_path` 有效 | 服务端复制结果 DOCX 到 `output_path`，返回 JSON |
| 未传 `output_path` 或为空 | `400` |
| 任务不存在 | `404` |
| `queued` / `running` / `failed` / `cancelled` | `409` |
| 结果源文件不存在 | `500` |

成功响应：

```json
{
  "task_id": "20260712-144123-dccf",
  "status": "succeeded",
  "message": "Result exported.",
  "output_path": "C:\\Users\\lenovo\\Desktop\\review_result.docx"
}
```

curl 示例：

```powershell
curl.exe -X POST "http://localhost:5000/api/review/jobs/20260712-144123-dccf/result" `
  -H "Content-Type: application/json" `
  -d "{\"output_path\":\"C:\\Users\\lenovo\\Desktop\\review_result.docx\"}"
```

注意：`output_path` 是服务端机器上的路径。当前本机运行服务时可以写本机路径；Docker 或远端部署时必须写容器或服务器可访问的路径。

### 取消任务

```http
POST /api/review/jobs/{task_id}/cancel
```

行为：

| 当前状态 | 结果 |
| --- | --- |
| `queued` | 更新为 `cancelled` |
| `running` | 返回 `409`，审核已经开始后不支持取消 |
| `succeeded` / `failed` / `cancelled` | 返回 `409` |

## task.json

内部 `task.json` 存放在：

```text
data/api/<task_id>/task.json
```

内部数据允许保留 workflow 需要的服务端路径，但这些路径不会直接返回给普通 `/api` 调用方。

`task.json` 不再保存：

```text
status_url
result_url
cancel_url
```

`logs` 字段按字母顺序保存：

```json
{
  "logs": {
    "api_events_path": "data/api/<task_id>/logs/api_events.jsonl",
    "conversation_log_dir": "data/api/<task_id>/logs/conversations",
    "mcp_log_dir": "data/api/<task_id>/logs/mcp",
    "workflow_log_dir": "data/api/<task_id>/logs/workflow"
  }
}
```

当 `api.write_logs: false` 时，上述值为 `null`，且不创建对应日志目录。

## 状态更新逻辑

```text
POST /api/review/jobs
  -> 创建 data/api/<task_id>/
  -> 保存上传文件
  -> 写 task.json: queued
  -> 返回 task_id
  -> 后台等待并发执行槽位

获得并发执行槽位
  -> task.json: running
  -> 开始 workflow.run()

审核成功
  -> task.json: succeeded

审核失败
  -> task.json: failed

取消任务
  -> queued: cancelled
  -> running: 409
```
