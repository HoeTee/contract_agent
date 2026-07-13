# `/api` 审查接口说明

当前普通 `/api` 只提供异步任务接口：

```text
POST /api/review/jobs
GET  /api/review/jobs/{task_id}
POST /api/review/jobs/{task_id}/result
POST /api/review/jobs/{task_id}/cancel
```

同步 `POST /api/review` 不再注册到 `app.py`，不再作为普通外部 API 暴露。

## API 边界

`/api` 面向普通外部客户：

- 需要 `secret_key` 鉴权。
- 只做异步任务提交、查询、结果导出、取消。
- 不接收 `metafields`。
- 不 callback。
- 数据按 `client_id` 分区。

OA 集成不属于 `/api`。OA 后续应放在 `/oa`，使用独立鉴权和 callback 流程。

## API Client 管理

API client 不在 `config.yaml` 配置。使用脚本管理：

```powershell
python scripts/manage_api_clients.py register --client-id "某某行社" --secret-key "<platform_key>"
python scripts/manage_api_clients.py list
python scripts/manage_api_clients.py list --client-id "某某行社"
python scripts/manage_api_clients.py reset-secret --client-id "某某行社" --secret-key "<new_platform_key>"
python scripts/manage_api_clients.py disable --client-id "某某行社"
python scripts/manage_api_clients.py enable --client-id "某某行社"
```

数据保存位置：

```text
user_profiles/api_clients.json
```

File stores `secret_hash` and `secret_fingerprint`, not plaintext `secret_key`. `/api` secret comes from the external platform key and is registered manually by script; run `reset-secret` to replace the old hash when lost or changed.

## 请求鉴权

Submit job with `multipart/form-data`; only `secret_key` is required:

```powershell
curl.exe -X POST "http://localhost:5000/api/review/jobs" `
  -F "secret_key=api_xxx" `
  -F "file=@C:\path\contract.docx"
```

Status, result export, and cancel also use `secret_key`. It can be sent by `Authorization: Bearer <secret>`, `X-API-Key`, JSON body, or query string.

```json
{
  "secret_key": "api_xxx"
}
```

Auth failures:

| 情况 | 状态码 |
| --- | --- |
| Missing `secret_key` | `401` |
| Secret does not match an enabled client | `401` |

## 数据目录

任务目录：

```text
data/api/clients/<client_dir>/tasks/<task_id>/
  task.json
  input/
  output/
  logs/
```

`client_id` 是业务身份；`client_dir` 是由 `client_id` 生成的安全目录名。`task.json` 会记录两者：

```json
{
  "client_id": "某某行社",
  "client_dir": "某某行社",
  "task_id": "20260712-144123-dccf",
  "status": "pending"
}
```

普通 API 响应不会返回服务端绝对路径，也不会返回 `secret_hash`。

## 代码位置

- `scripts/manage_api_clients.py`：读写 `api_clients.json`，登记平台 secret hash。
- `endpoints/api/client_auth.py`：`/api` 请求鉴权。
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
