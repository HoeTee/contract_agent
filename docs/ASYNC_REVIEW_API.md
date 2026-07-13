# `/api` 异步审查任务 API

本文说明普通外部客户使用的 `/api` 审查接口。当前 `/api` 只提供异步任务式调用，不再暴露同步 `POST /api/review`，也不接收 `metafields`，不做 callback。

## 身份鉴权

API client 由脚本管理：

```powershell
python scripts/manage_api_clients.py register --client-id "某某行社" --secret-key "<platform_key>"
python scripts/manage_api_clients.py list
python scripts/manage_api_clients.py list --client-id "某某行社"
python scripts/manage_api_clients.py reset-secret --client-id "某某行社" --secret-key "<new_platform_key>"
python scripts/manage_api_clients.py disable --client-id "某某行社"
python scripts/manage_api_clients.py enable --client-id "某某行社"
```

`/api` secret 来自外部平台注册 key，由脚本手动登记。明文 secret 不落盘，服务端只在 `user_profiles/api_clients.json` 保存 `secret_hash`。

## API 节点

### 提交任务

```http
POST /api/review/jobs
Content-Type: multipart/form-data
```

字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `secret_key` | string | 是 | 外部平台注册 key；本系统仅保存 hash |
| `file` | file | 是 | 待审查合同 DOCX |
| `criteria_file` | file | 否 | 本次审查标准 DOCX；不传则使用默认审查标准 |

成功响应：

```json
{
  "task_id": "20260712-144123-dccf",
  "status": "pending",
  "message": "Review job submitted."
}
```

### 查询状态

```http
GET /api/review/jobs/{task_id}
Content-Type: application/json
```

请求 JSON：

```json
{
  "secret_key": "api_xxx"
}
```

返回给调用方的是过滤后的任务视图，不暴露服务端绝对路径、日志路径或 `secret_hash`。

### 导出结果

```http
POST /api/review/jobs/{task_id}/result
Content-Type: application/json
```

请求 JSON：

```json
{
  "secret_key": "api_xxx",
  "output_path": "C:\\Users\\lenovo\\Desktop\\review_result.docx"
}
```

行为：

| 情况 | 返回 |
| --- | --- |
| `succeeded` 且 `output_path` 有效 | 服务端复制结果 DOCX 到 `output_path`，返回 JSON |
| 未传 `output_path` 或为空 | `400` |
| 任务不存在 | `404` |
| `pending` / `queued` / `running` / `failed` / `cancelled` | `409` |
| 结果源文件不存在 | `500` |

`output_path` 是服务端机器上的路径。Docker 或远端部署时必须写容器或服务器可访问的路径。

### 取消任务

```http
POST /api/review/jobs/{task_id}/cancel
Content-Type: application/json
```

请求 JSON：

```json
{
  "secret_key": "api_xxx"
}
```

行为：

| 当前状态 | 结果 |
| --- | --- |
| `pending` | 更新为 `cancelled` |
| `queued` | 更新为 `cancelled` |
| `running` | 返回 `409`，审核已经开始后不支持取消 |
| `succeeded` / `failed` / `cancelled` | 返回 `409` |

## 状态语义

| 状态 | 含义 |
| --- | --- |
| `pending` | 已提交，后台任务尚未判断并发状态 |
| `queued` | 并发已满，等待执行槽位 |
| `running` | 已获得执行槽位，正在执行 workflow |
| `succeeded` | 审核成功，结果可导出 |
| `failed` | 审核失败 |
| `cancelled` | pending 或 queued 阶段被取消 |

## 数据目录

`/api` 任务按 `client_id` 分区。真实目录名会经过安全化处理，避免 Windows 路径非法字符。

```text
data/api/clients/<client_dir>/tasks/<task_id>/
  task.json
  input/
  output/
  logs/
```

The service resolves `client_id/client_dir` from `secret_key`; `task.json` records the original `client_id` and safe `client_dir`. Internal workflow paths can remain in task storage, but ordinary `/api` responses do not expose absolute server paths.

`logs` 字段按字母顺序保存：

```json
{
  "logs": {
    "api_events_path": "data/api/clients/<client_dir>/tasks/<task_id>/logs/api_events.jsonl",
    "conversation_log_dir": "data/api/clients/<client_dir>/tasks/<task_id>/logs/conversations",
    "mcp_log_dir": "data/api/clients/<client_dir>/tasks/<task_id>/logs/mcp",
    "workflow_log_dir": "data/api/clients/<client_dir>/tasks/<task_id>/logs/workflow"
  }
}
```

当 `api.write_logs: false` 时，上述值为 `null`，且不创建对应日志目录。`output/` 始终写入；`input/` 是否保留由 `api.keep_input` 控制。

## 状态更新逻辑

```text
POST /api/review/jobs
  -> 校验 secret_key
  -> 创建 data/api/clients/<client_dir>/tasks/<task_id>/
  -> 保存上传文件
  -> 写 task.json: pending
  -> 返回 task_id
  -> 后台判断并发状态

如果并发已满
  -> task.json: queued
  -> 等待并发执行槽位

获得并发执行槽位
  -> task.json: running
  -> 开始 workflow.run()

审核成功
  -> task.json: succeeded

审核失败
  -> task.json: failed

取消任务
  -> pending: cancelled
  -> queued: cancelled
  -> running: 409
```
