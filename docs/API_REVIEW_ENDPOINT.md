# `/api` 审查接口说明

当前普通 `/api` 只提供异步任务接口：

```text
POST /api/review/jobs
GET  /api/review/jobs/{task_id}
POST /api/review/jobs/{task_id}/result
POST /api/review/jobs/{task_id}/cancel
```

普通外部 API 不提供同步 `POST /api/review`；OA 专用同步接口为 `POST /oa/review`。

## API 边界

`/api` 面向普通外部客户：

- 平台负责 `Authorization` key 鉴权；服务仅用该 key 映射 `client_id/client_dir`。
- 只做异步任务提交、查询、结果下载、取消。
- 不接收 `metafields`。
- 不 callback。
- 数据按 `client_id` 分区。

OA 集成不属于 `/api`。OA 后续应放在 `/oa`，使用独立鉴权和 callback 流程。

## API Client 管理

API client 不在 `config.yaml` 配置。使用脚本管理：

```powershell
python scripts/manage_api_clients.py register --client-id "client_a" --secret-key "<platform_key>"
python scripts/manage_api_clients.py list
python scripts/manage_api_clients.py check --client-id "client_a"
python scripts/manage_api_clients.py list --client-id "client_a"
python scripts/manage_api_clients.py list --client-id "client_a" --compact
python scripts/manage_api_clients.py reset-api-key --client-id "client_a" --api-key "<new_platform_key>"
python scripts/manage_api_clients.py disable --client-id "client_a"
python scripts/manage_api_clients.py enable --client-id "client_a"
python scripts/manage_api_clients.py delete --client-id "client_a"
```

`list` shows registered clients. `check --client-id` shows one client detail. `list --client-id` shows tasks under that client in block format; add `--compact` for one-line rows with truncated filenames. `delete --client-id` removes only the auth mapping and keeps task data.

数据保存位置：

```text
user_profiles/api_clients.json
```

File stores `api_key_fingerprint`, not a plaintext platform key. The platform key is used only to resolve the local client mapping; run `reset-api-key` when the platform key changes.

## 请求鉴权

Submit jobs with `multipart/form-data`; the platform key must be passed through `Authorization`:

```powershell
curl.exe -X POST "http://localhost:5000/api/review/jobs" `
  -H "Authorization: <platform_api_key>" `
  -F "file=@C:\path\contract.docx"
```

Status, result download, and cancel use the same `Authorization` header. Body, form, query string, and `X-API-Key` are not used for API key mapping.

Auth failures:

| 情况 | 状态码 |
| --- | --- |
| Missing `Authorization` | `400` |
| Platform key has no local client mapping | `400` |
| Client mapping is disabled | `403` |

## 数据目录

任务目录：

```text
data/api/<task_id>/
  task.json
  input/
  output/
  logs/
```

`client_id` 是业务身份；`client_dir` 为兼容既有 client 配置继续记录在 `task.json` 中，但不再参与目录分区。`task.json` 会记录两者：

```json
{
  "client_id": "某某行社",
  "client_dir": "某某行社",
  "task_id": "20260712-144123-dccf",
  "status": "pending"
}
```

普通 API 响应不会返回服务端绝对路径，也不会返回 `api_key_fingerprint`。

## 代码位置

- `scripts/manage_api_clients.py`：读写 `api_clients.json`，登记平台 key 指纹映射。
- `endpoints/api/client_mapping.py`：根据平台 `Authorization` key 映射 `/api` 客户目录。
- `endpoints/api/review_jobs.py`：异步任务 API 路由。
- `endpoints/review/task_store.py`：按 client 分区的 task 存储。
- `endpoints/review/job_worker.py`：异步审查 worker。
- `endpoints/review/response.py`：过滤对外响应。

## 存储开关

`config.yaml` 中仍保留运行时存储开关：

```yaml
api:
  keep_input: true
  write_logs: true
```

- `output/` 始终写入。
- `input/` 是否保留由 `api.keep_input` 控制。
- `logs/` 是否写入由 `api.write_logs` 控制。
