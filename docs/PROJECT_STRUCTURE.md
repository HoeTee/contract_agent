# 项目结构

本文描述当前主要目录职责。普通 `/api`、浏览器 `/web`、后续 OA `/oa` 应保持边界清楚。

## 入口

- `app.py`：FastAPI 服务入口，注册 `/api`、`/web` 路由和静态文件。
- `main.py`：本地 CLI 审查入口。
- `config.py`：集中读取系统配置、路径和环境变量。API client 身份不在这里配置。

## HTTP Endpoints

- `endpoints/api/client_auth.py`: authenticates ordinary `/api` requests by `secret_key`, then resolves `client_id/client_dir` from `api_clients.json`.
- `endpoints/api/review_jobs.py`：普通 `/api` 异步任务 API，提供提交、查询、结果导出、取消任务节点。
- `endpoints/api/review.py`：旧同步 API 文件，当前不再注册到 `app.py`，不作为普通外部 API 暴露。
- `endpoints/web/user_routes.py`：浏览器普通用户页面和表单路由，URL 以 `/web` 开头。
- `endpoints/web/admin_routes.py`：管理端页面和表单路由，URL 以 `/web/admin` 开头。
- `endpoints/web/admin_services.py`：管理端展示所需的数据聚合。
- `endpoints/runtime/`：HTTP 层运行时支撑，包括认证、DOCX 校验、文件名、JSON 响应、错误类型和并发控制。

## Review Support

- `endpoints/review/task_store.py`：读写 `/api` task 数据，路径为 `data/api/clients/<client_dir>/tasks/<task_id>/`。
- `endpoints/review/job_worker.py`：执行异步审查后台任务。
- `endpoints/review/response.py`：构造对外 API 响应，避免暴露服务端路径和 secret hash。
- `endpoints/review/meta.py`：旧 meta fields helper；普通 `/api` 当前不再使用。
- `endpoints/review/callbacks.py`：旧 callback helper；普通 `/api` 异步主流程不依赖 callback。

## Services And Scripts

- `scripts/manage_users.py`：Web 用户管理脚本。
- `endpoints/web/user_management.py`：`/web` 管理端使用的用户管理逻辑。
- `scripts/manage_api_clients.py`：`/api` client 管理脚本，支持 register/list/check/reset-secret/enable/disable/delete。
- `scripts/api_review_callback_receiver.py`：本地测试 callback 的临时接收服务；普通 `/api` 异步主流程不依赖 callback。

## Identity Files

```text
user_profiles/
  users.json          # /web 用户，由 scripts/manage_users.py 管理
  api_clients.json    # /api 客户，由 scripts/manage_api_clients.py 管理
```

`api_clients.json` stores `client_id`, `enabled`, `secret_hash`, and `secret_fingerprint`. Plaintext `secret_key` is never written to disk; `/api` secret comes from the external platform key and is registered manually by script.

## Data Directories

当前 `/web` 数据目录仍沿用既有结构，后续租户化时再单独调整。

普通 `/api` 数据目录：

```text
data/api/clients/<client_dir>/tasks/<task_id>/
  task.json
  input/
  output/
  logs/
```

`client_id` 是业务身份，`client_dir` 是由 `client_id` 生成的安全目录名。`task.json` 同时记录两者。

## API Boundary

普通 `/api`：

- 只做异步任务。
- 需要 `secret_key` 鉴权。
- 按 `client_id` 分区存储。
- 不接收 `metafields`。
- 不 callback。

浏览器 `/web`：

- 依赖 session/cookie。
- 面向页面、表单、历史记录和下载。
- 后续租户管理员、超级管理员改造不在本次范围内。

OA `/oa`：

- 后续单独新增。
- 应使用独立鉴权和 callback 逻辑。
