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

- 需要 `client_id + secret_key` 鉴权。
- 可选校验来源 IP 是否在该 client 的 `allowed_ips` 中。
- 只做异步任务提交、查询、结果导出、取消。
- 不接收 `metafields`。
- 不 callback。
- 数据按 `client_id` 分区。

OA 集成不属于 `/api`。OA 后续应放在 `/oa`，使用独立鉴权和 callback 流程。

## API Client 管理

API client 不在 `config.yaml` 配置。使用脚本管理：

```powershell
python scripts/manage_api_clients.py create --client-id "某某行社" --allowed-ip "127.0.0.1"
python scripts/manage_api_clients.py list
python scripts/manage_api_clients.py list --client-id "某某行社"
python scripts/manage_api_clients.py reset-secret --client-id "某某行社"
python scripts/manage_api_clients.py set-ips --client-id "某某行社" --allowed-ip "127.0.0.1"
python scripts/manage_api_clients.py disable --client-id "某某行社"
python scripts/manage_api_clients.py enable --client-id "某某行社"
```

数据保存位置：

```text
user_profiles/api_clients.json
```

文件保存 `secret_hash`，不保存明文 `secret_key`。`create` 和 `reset-secret` 会在终端打印明文 secret 一次：

```text
Store this secret securely. It is shown only once. If lost, reset it.
```

丢失 secret 时无法反推，只能运行 `reset-secret` 覆盖旧 hash 并生成新 secret。

## 请求鉴权

提交任务使用 `multipart/form-data`：

```powershell
curl.exe -X POST "http://localhost:5000/api/review/jobs" `
  -F "client_id=某某行社" `
  -F "secret_key=api_xxx" `
  -F "file=@C:\path\合同.docx"
```

查询、导出、取消使用 JSON body 传鉴权字段：

```json
{
  "client_id": "某某行社",
  "secret_key": "api_xxx"
}
```

鉴权失败：

| 情况 | 状态码 |
| --- | --- |
| 缺少 `client_id` 或 `secret_key` | `401` |
| `client_id` 不存在、禁用或 secret 错误 | `401` |
| 来源 IP 不在 `allowed_ips` | `403` |

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

- `scripts/manage_api_clients.py`：API client 管理脚本。
- `services/api_client_management.py`：读写 `api_clients.json`，生成 secret，保存和验证 hash。
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
