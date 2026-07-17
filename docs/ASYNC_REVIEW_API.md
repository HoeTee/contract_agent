# 异步审查 API

本文说明普通外部客户使用的 `/api` 异步合同审查接口。

系统不提供同步 `POST /api/review`。调用方先提交任务，再查询任务状态，任务成功后请求导出结果。

## 1. 鉴权与客户管理

每个 `/api` 请求都必须在 `Authorization` 请求头中传入平台分配的密钥：

```http
Authorization: <api_key>
```

服务端接受原始 key 或 `Bearer <api_key>`。平台负责该 key 的鉴权；本服务只用其 SHA-256 指纹查找本地客户映射。

管理员在本地登记平台 key 映射。`user_profiles/api_clients.json` 只保存 key 的 SHA-256 指纹，不保存明文 key。

以下管理命令应在项目根目录执行；Docker 部署时，应在挂载了与服务容器相同 `user_profiles/`、`data/` 持久化目录的临时管理容器中执行。

| 命令 | 输入 | 输出或作用 |
| --- | --- | --- |
| `register` | `--client-id`、`--api-key` | 注册一个客户映射。重复的 `client_id` 或 `api_key` 会报错。 |
| `list` | 无 | 列出全部已注册客户。 |
| `check` | `--client-id` | 显示一个客户的注册状态和任务数量。 |
| `list --client-id` | `--client-id` | 以块状格式显示该客户的全部任务。 |
| `list --client-id --compact` | `--client-id` | 以紧凑单行格式显示该客户的全部任务。 |
| `reset-api-key` | `--client-id`、`--api-key` | 替换客户的平台 key 映射。新 key 不能属于其他客户。 |
| `disable` | `--client-id` | 禁用该客户的 `/api` 调用权限。 |
| `enable` | `--client-id` | 恢复该客户的 `/api` 调用权限。 |
| `delete` | `--client-id` | 仅移除鉴权映射，已有任务数据会保留。 |

```powershell
python scripts/manage_api_clients.py register --client-id "client_a" --api-key "platform-key-for-client-a"
python scripts/manage_api_clients.py list
python scripts/manage_api_clients.py check --client-id "client_a"
python scripts/manage_api_clients.py list --client-id "client_a"
python scripts/manage_api_clients.py list --client-id "client_a" --compact
python scripts/manage_api_clients.py reset-api-key --client-id "client_a" --api-key "new-platform-key"
python scripts/manage_api_clients.py disable --client-id "client_a"
python scripts/manage_api_clients.py enable --client-id "client_a"
python scripts/manage_api_clients.py delete --client-id "client_a"
```

旧记录若只包含 `secret_hash` 或 `secret_fingerprint`，不能用于平台 key 映射。请对该 `client_id` 执行一次 `reset-api-key --api-key "<platform_api_key>"`，脚本会移除旧字段并写入 `api_key_fingerprint`。

## 2. 异步调用流程

```text
POST /api/review/jobs
  -> 返回 202 Accepted 和 task_id

GET /api/review/jobs/{task_id}
  -> 返回 pending、queued、running、succeeded、failed 或 cancelled

POST /api/review/jobs/{task_id}/result
  -> 仅 succeeded 后可导出结果
```

`POST /api/review/jobs/{task_id}/cancel` 只能取消 `pending` 或 `queued` 任务。`running` 表示任务已经进入 `workflow.run()`，该 API 不支持中止。

| 状态 | 含义 |
| --- | --- |
| `pending` | 任务已写入存储，后台任务尚未检查并发限制。 |
| `queued` | 并发已满，任务正在等待执行槽位。 |
| `running` | 已获得执行槽位，审查工作流正在运行。 |
| `succeeded` | 审查输出已生成，可导出。 |
| `failed` | 工作流失败，状态查询响应中包含 `error`。 |
| `cancelled` | 任务在开始前已取消。 |

## 3. 提交任务

```http
POST /api/review/jobs
Content-Type: multipart/form-data
Authorization: <api_key>
```

请求字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `file` | DOCX 文件 | 是 | 待审查的合同文件。 |
| `criteria_file` | DOCX 文件 | 否 | 本次审查标准；不传时使用默认审查标准。 |

PowerShell 示例：

```powershell
curl.exe -X POST "http://localhost:5000/api/review/jobs" `
  -H "Authorization: platform-key-for-client-a" `
  -F "file=@C:/Users/lenovo/Desktop/contract.docx" `
  -F "criteria_file=@C:/Users/lenovo/Desktop/criteria.docx"
```

成功响应，HTTP `202`：

```json
{
  "task_id": "20260714-143119-5ece",
  "status": "pending",
  "message": "Review job submitted."
}
```

| HTTP 状态码 | 返回场景 | 响应 |
| --- | --- | --- |
| `202` | 任务已接收。 | 任务 ID、初始状态和消息。 |
| `400` | 合同或审查标准不是有效 DOCX，或审查标准内容不符合要求。 | `{ "detail": "..." }` |
| `400` | 未传 `Authorization`，或平台 key 没有本地客户映射。 | `{ "detail": "Authorization header is required." }` 或 `{ "detail": "API key has no local client mapping." }` |
| `403` | 该客户映射已禁用。 | `{ "detail": "API client mapping is disabled." }` |
| `422` | 缺少必填的 `file` multipart 字段，或请求字段无法解析。 | FastAPI 校验详情。 |
| `500` | 客户鉴权映射格式错误或密钥匹配到多个客户。 | `{ "detail": "..." }` |

## 4. 查询任务状态

```http
GET /api/review/jobs/{task_id}
Authorization: <api_key>
```

PowerShell 示例：

```powershell
curl.exe "http://localhost:5000/api/review/jobs/20260714-143119-5ece" `
  -H "Authorization: platform-key-for-client-a"
```

成功响应，HTTP `200`：

```json
{
  "task_id": "20260714-143119-5ece",
  "status": "running",
  "created_at": "2026-07-14T14:31:19+08:00",
  "started_at": "2026-07-14T14:31:20+08:00",
  "finished_at": null,
  "message": "Contract review is running.",
  "error": null,
  "input": {
    "contract_filename": "contract.docx",
    "criteria_source": "default",
    "criteria_filename": null,
    "stored": true
  },
  "output": {
    "result_filename": "contract_批注版.docx",
    "ready": false
  },
  "logs": {
    "enabled": true
  }
}
```

| HTTP 状态码 | 返回场景 | 响应 |
| --- | --- | --- |
| `200` | 已鉴权客户拥有该任务。 | 经过过滤的任务状态，不返回服务端文件系统路径。 |
| `400` | 未传 `Authorization`，或平台 key 没有本地客户映射。 | `{ "detail": "..." }` |
| `403` | 该客户映射已禁用。 | `{ "detail": "API client mapping is disabled." }` |
| `404` | 任务 ID 不合法、不存在，或属于其他客户。 | `{ "detail": "Task not found." }` |
| `500` | 客户鉴权映射格式错误或密钥匹配到多个客户。 | `{ "detail": "..." }` |

## 5. 导出已完成结果

```http
POST /api/review/jobs/{task_id}/result
Content-Type: application/json
Authorization: <api_key>
```

请求 JSON：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `output_path` | string | 是 | 运行 API 服务的机器上的目标路径。 |

PowerShell `curl.exe` 示例：

```powershell
curl.exe -X POST "http://localhost:5000/api/review/jobs/20260714-143119-5ece/result" `
  -H "Authorization: platform-key-for-client-a" `
  -H "Content-Type: application/json" `
  -d '{\"output_path\":\"C:/Users/lenovo/Desktop/review_result.docx\"}'
```

成功响应，HTTP `200`：

```json
{
  "task_id": "20260714-143119-5ece",
  "status": "succeeded",
  "message": "Result exported.",
  "output_path": "C:\\Users\\lenovo\\Desktop\\review_result.docx"
}
```

| HTTP 状态码 | 返回场景 | 响应 |
| --- | --- | --- |
| `200` | 任务已成功，结果已复制到 `output_path`。 | 任务 ID、`succeeded`、消息和输出路径。 |
| `400` | 未传 `output_path` 或该值为空。 | `{ "task_id": "...", "status": "failed", "message": "output_path is required." }` |
| `400` | 未传 `Authorization`，或平台 key 没有本地客户映射。 | `{ "detail": "..." }` |
| `403` | 该客户映射已禁用。 | `{ "detail": "API client mapping is disabled." }` |
| `404` | 任务 ID 不合法、不存在，或属于其他客户。 | `{ "detail": "Task not found." }` |
| `409` | 任务状态不是 `succeeded`。 | `{ "detail": "Task is not finished. Current status: ..." }` |
| `422` | JSON 请求体不合法，或请求体不是 JSON 对象。 | FastAPI 校验详情。 |
| `500` | 结果源文件不存在、目标路径无法写入，或客户鉴权映射异常。 | `{ "detail": "..." }` 或 `{ "task_id": "...", "status": "failed", "message": "Failed to export result: ...", "output_path": "..." }` |

`output_path` 由 API 服务端解释，不是发送 HTTP 请求的调用方机器路径。

- 本地开发机运行服务时，它是本机文件系统路径。
- Docker 部署时，它是正在运行的服务容器内路径。要持久化导出文件，目标路径必须位于挂载到该容器的目录中。
- 远端部署时，它是远端服务进程或服务容器可访问的路径，不能直接写入调用方桌面。

## 6. 取消等待中的任务

```http
POST /api/review/jobs/{task_id}/cancel
Authorization: <api_key>
```

PowerShell 示例：

```powershell
curl.exe -X POST "http://localhost:5000/api/review/jobs/20260714-143119-5ece/cancel" `
  -H "Authorization: platform-key-for-client-a"
```

成功响应，HTTP `200`：

```json
{
  "task_id": "20260714-143119-5ece",
  "status": "cancelled",
  "message": "Review job cancelled."
}
```

| HTTP 状态码 | 返回场景 | 响应 |
| --- | --- | --- |
| `200` | 当前状态是 `pending` 或 `queued`，任务已取消。 | 任务 ID、`cancelled` 和消息。 |
| `400` | 未传 `Authorization`，或平台 key 没有本地客户映射。 | `{ "detail": "..." }` |
| `403` | 该客户映射已禁用。 | `{ "detail": "API client mapping is disabled." }` |
| `404` | 任务 ID 不合法、不存在，或属于其他客户。 | `{ "detail": "Task not found." }` |
| `409` | 任务是 `running`、`succeeded`、`failed` 或已经 `cancelled`。 | `{ "detail": "..." }`，或针对 `running` 的 JSON 消息。 |
| `500` | 客户鉴权映射格式错误或密钥匹配到多个客户。 | `{ "detail": "..." }` |

## 7. 客户数据隔离

任务按照 `task_id` 直接存储在 API 根目录：

```text
data/api/<task_id>/
  task.json
  input/
  output/
  logs/
```

调用方不提交 `client_id`。平台已认证的 `Authorization` key 仅用于本地映射；服务端根据映射得到客户身份，并按 `task.json` 中记录的 `client_dir` 校验任务归属。

例如，客户 A 拥有任务 `20260714-143119-5ece`，客户 B 使用自己的有效密钥访问该任务时，返回如下：

| 客户 B 对客户 A 任务的请求 | HTTP 状态码 | 响应 |
| --- | --- | --- |
| `GET /api/review/jobs/20260714-143119-5ece` | `404` | `{ "detail": "Task not found." }` |
| `POST /api/review/jobs/20260714-143119-5ece/result` | `404` | `{ "detail": "Task not found." }` |
| `POST /api/review/jobs/20260714-143119-5ece/cancel` | `404` | `{ "detail": "Task not found." }` |

任务不存在时也返回同一 `404`，因此客户不能通过状态码判断其他客户的任务是否存在。

任务目录不再按 `client_dir` 分区。不要手工创建或修改 `user_profiles/api_clients.json`，避免 API key 映射到错误业务身份。

## 8. 常见请求错误

| 错误请求 | 返回结果 | 正确请求 |
| --- | --- | --- |
| `POST /review/jobs/{task_id}` | `404 Not Found` | 查询状态应使用 `GET /api/review/jobs/{task_id}`。 |
| `POST /api/review/jobs/result` | `405 Method Not Allowed` | 应使用 `POST /api/review/jobs/{task_id}/result`。 |
| `POST /api/review/jobs/{task_id}/result` 请求体为 `{ "output": "..." }` | `400 output_path is required.` | 应使用 `{ "output_path": "..." }`。 |
| PowerShell `curl.exe` 发送 JSON 时丢失双引号 | `422 json_invalid` | 使用上文的 `-d '{\"output_path\":\"...\"}'` 写法。 |
