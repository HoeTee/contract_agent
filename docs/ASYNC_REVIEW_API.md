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
  -> 仅 succeeded 后可下载结果 DOCX
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

该接口按 `Content-Type` 分流，且只支持以下两种请求体：

- `multipart/form-data`：上传二进制 DOCX 文件，只接受 `file` / `criteria_file`。
- `application/json`：通过 URL 下载 DOCX，只接受 `file_url` / `criteria_file_url`。

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

JSON URL 输入示例：

```powershell
curl.exe -X POST "http://localhost:5000/api/review/jobs" `
  -H "Authorization: platform-key-for-client-a" `
  -H "Content-Type: application/json" `
  -d '{ "file_url": "https://example.com/contract.docx", "criteria_file_url": "https://example.com/criteria.docx" }'
```

`application/json` 只支持 URL 输入：`file_url` 必填，`criteria_file_url` 可选。URL 文件会先下载到任务 `input/` 目录，再执行与本地上传一致的 DOCX 校验。

成功响应，HTTP `202`：

```json
{
  "task_id": "20260714-143119-5ece",
  "status": "pending",
  "message": "Review job submitted."
}
```

提交期错误响应。如果请求已通过 API client 解析并生成 `task_id`，但文件输入、URL 下载或 DOCX 校验失败，接口返回标准失败结构：

```json
{
  "task_id": "20260714-143119-5ece",
  "status": "failed",
  "message": "Contract file URL download failed.",
  "error": {
    "code": "CONTRACT_URL_DOWNLOAD_FAILED",
    "message": "Contract file URL download failed.",
    "http_status": null
  }
}
```

鉴权失败发生在 `task_id` 生成前，因此仍返回 FastAPI 错误结构。

| HTTP 状态码 | 返回场景 | 响应 |
| --- | --- | --- |
| `202` | 任务已接收。 | 任务 ID、初始状态和消息。 |
| `400` | 已生成 `task_id` 后，合同或审查标准不是有效 DOCX，URL 输入字段无效，或审查标准内容不符合要求。 | `{ "task_id": "...", "status": "failed", "message": "...", "error": {...} }` |
| `415` | 已生成 `task_id` 后，请求 `Content-Type` 不受支持。 | `{ "task_id": "...", "status": "failed", "message": "Unsupported Content-Type.", "error": {...} }` |
| `502` | 已生成 `task_id` 后，合同 URL 或审查标准 URL 下载失败。 | `{ "task_id": "...", "status": "failed", "message": "...", "error": {...} }` |
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

## 5. 下载已完成结果

```http
POST /api/review/jobs/{task_id}/result
Authorization: <api_key>
```

该接口支持两种输出方式：

- `output_type=file`：直接返回结果 DOCX 文件流。
- `output_type=url`：将结果 DOCX 上传到配置的附件接口，并返回上传后的 URL。

不传请求体时，使用 `api.result_output_default`。默认配置为 `file`，兼容已有调用方。

请求文件输出：

```json
{
  "output_type": "file"
}
```

请求 URL 输出：

```json
{
  "output_type": "url"
}
```

PowerShell `curl.exe` 示例：

```powershell
curl.exe -X POST "http://localhost:5000/api/review/jobs/20260714-143119-5ece/result" `
  -H "Authorization: platform-key-for-client-a" `
  -o "C:\Users\lenovo\Desktop\review_result.docx"
```

Python `requests` 示例：

```python
import requests

url = "http://localhost:5000/api/review/jobs/20260714-143119-5ece/result"
headers = {"Authorization": "platform-key-for-client-a"}
output_file = r"C:\Users\lenovo\Desktop\review_result.docx"

response = requests.post(url, headers=headers, stream=True)
response.raise_for_status()

with open(output_file, "wb") as f:
    for chunk in response.iter_content(chunk_size=1024 * 1024):
        if chunk:
            f.write(chunk)
```

URL 输出示例：

```powershell
curl.exe -X POST "http://localhost:5000/api/review/jobs/20260714-143119-5ece/result" `
  -H "Authorization: platform-key-for-client-a" `
  -H "Content-Type: application/json" `
  -d '{ "output_type": "url" }'
```

成功响应，HTTP `200`：

```json
{
  "task_id": "20260714-143119-5ece",
  "status": "succeeded",
  "output_type": "url",
  "filename": "contract_reviewed.docx",
  "url": "https://example.com/contract_reviewed.docx"
}
```

URL 输出依赖以下配置：

```yaml
api:
  keep_output: true
  result_output_default: "file"
  result_upload_enabled: false
  result_upload_domain: "http://64.202.33.42:30843"
  result_upload_path: "/openapi/agentar/v1/attachment/batchUploadAttachmentFile.json"
  result_upload_authorization: ""
  result_upload_timeout_seconds: 60
```

上传请求等价于：

```bash
curl -X POST "http://64.202.33.42:30843/openapi/agentar/v1/attachment/batchUploadAttachmentFile.json" \
  -H "Authorization: <result_upload_authorization>" \
  -F "files=@/path/to/reviewed.docx;type=application/vnd.openxmlformats-officedocument.wordprocessingml.document"
```

`keep_output=false` 只在 URL 输出上传成功后清理本地结果文件；文件流输出不能在响应发送前删除本地结果文件。

上传成功后，服务会从上传接口 JSON 响应中的常见 URL 字段解析结果地址，例如 `url`、`fileUrl`、`downloadUrl` 以及它们在 `data` 或 `data[0]` 下的形式；如果解析不到 URL，接口返回 `502`。

| HTTP 状态码 | 返回场景 | 响应 |
| --- | --- | --- |
| `200` | 任务已成功，请求 `file` 输出。 | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` 响应体。 |
| `200` | 任务已成功，请求 `url` 输出。 | `{ "task_id": "...", "status": "succeeded", "output_type": "url", "url": "..." }` |
| `400` | `output_type` 非 `file` / `url`，或 URL 输出未启用。 | `{ "detail": "..." }` |
| `400` | 未传 `Authorization`，或平台 key 没有本地客户映射。 | `{ "detail": "..." }` |
| `403` | 该客户映射已禁用。 | `{ "detail": "API client mapping is disabled." }` |
| `404` | 任务 ID 不合法、不存在，或属于其他客户。 | `{ "detail": "Task not found." }` |
| `409` | 任务状态不是 `succeeded`。 | `{ "detail": "Task is not finished. Current status: ..." }` |
| `500` | 服务端结果源文件不存在，或客户鉴权映射异常。 | `{ "detail": "..." }` |
| `502` | URL 输出上传失败，或上传响应中无法解析 URL。 | `{ "detail": "Result file URL upload failed." }` |

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
| `POST /api/review/jobs/{task_id}/result` 传 `output_path` | 仍返回文件流，不会写入该路径。 | 使用 `curl.exe -o` 或客户端代码保存响应体。 |
| PowerShell `curl.exe` 未使用 `-o` | 文件内容输出到终端。 | 使用上文的 `-o "C:\...\review_result.docx"` 写法。 |
