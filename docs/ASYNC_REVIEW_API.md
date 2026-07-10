# 异步 `/api/review` 任务 API 说明

本文说明无 Cookie、直接调用的异步合同审查 API。原同步接口 `POST /api/review` 保留不变，并已与异步接口统一使用 `data/api/<task_id>/`、`task.json`、`input/`、`output/` 和 `logs/` 存储结构。

## 代码目录

```text
endpoints/
  api/
    review.py          # 同步 POST /api/review
    review_jobs.py     # 异步任务 API
    task_store.py      # data/api/<task_id>/task.json 读写
    callbacks.py       # 旧 callback helper，异步主流程不依赖
  web/
    user_routes.py     # /web 开头的前端用户路由
    admin_routes.py    # /web/admin 开头的管理端路由
```

边界：

- `/api/...`：外部系统或脚本直接调用，不依赖登录态和 Cookie。
- `/web/...`：浏览器前端和管理端使用，依赖 session/cookie。

## API 节点

### 提交任务

```http
POST /api/review/jobs
Content-Type: multipart/form-data
```

入参：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `file` | file | 是 | 待审核合同 DOCX |
| `criteria_file` | file | 否 | 本次审查标准 DOCX；不传则使用默认审查标准 |
| `templateCode` | string | 取决于配置 | `API_META_FIELDS` 中声明的业务字段 |
| `serialNo` | string | 取决于配置 | `API_META_FIELDS` 中声明的业务字段 |

成功响应：

```http
202 Accepted
```

```json
{
  "task_id": "20260710-153012-a1b2",
  "status": "queued",
  "message": "审核任务已提交",
  "status_url": "/api/review/jobs/20260710-153012-a1b2",
  "result_url": "/api/review/jobs/20260710-153012-a1b2/result",
  "cancel_url": "/api/review/jobs/20260710-153012-a1b2/cancel"
}
```

### 查询状态

```http
GET /api/review/jobs/{task_id}
```

返回 `task.json` 中的任务状态。核心状态包括：

```text
queued
running
succeeded
failed
cancelling
cancelled
```

### 下载结果

```http
GET /api/review/jobs/{task_id}/result
```

行为：

- `succeeded`：返回批注后的 DOCX。
- `queued`、`running`、`cancelling`：返回 `409`。
- `failed`、`cancelled`：返回 `409`。
- 任务不存在：返回 `404`。

### 取消任务

```http
POST /api/review/jobs/{task_id}/cancel
```

行为：

- `queued`：直接更新为 `cancelled`。
- `running`：更新为 `cancelling`，后台任务在检查点停止后更新为 `cancelled`。
- `succeeded`、`failed`、`cancelled`：返回 `409`。

当前取消是协作式取消，不是强制杀进程。如果 workflow 正在等待模型或外部工具调用，任务会在当前调用返回后的检查点处理取消。

## task.json

每个异步任务的数据存放在：

```text
data/api/<task_id>/task.json
```

同目录保存输入、输出和日志：

```text
data/api/<task_id>/
  task.json
  input/
    contract.docx
    criteria.docx
  output/
    reviewed.docx
  logs/
    api_events.jsonl
    workflow/
    conversations/
    mcp/
```

示例字段：

```json
{
  "task_id": "20260710-153012-a1b2",
  "status": "queued",
  "status_url": "/api/review/jobs/20260710-153012-a1b2",
  "result_url": "/api/review/jobs/20260710-153012-a1b2/result",
  "cancel_url": "/api/review/jobs/20260710-153012-a1b2/cancel",
  "created_at": "2026-07-10T10:00:00+08:00",
  "started_at": null,
  "finished_at": null,
  "message": "审核任务已提交",
  "error": null,
  "input": {
    "contract_filename": "合同.docx",
    "contract_path": "data/api/20260710-153012-a1b2/input/合同.docx",
    "criteria_source": "default",
    "criteria_filename": null,
    "criteria_path": "resources/review_criteria/criteria.docx"
  },
  "output": {
    "result_filename": "合同_reviewed.docx",
    "result_path": "data/api/20260710-153012-a1b2/output/合同_reviewed.docx"
  },
  "meta_fields": {
    "templateCode": "TMP001",
    "serialNo": "SN001"
  },
  "cancel": {
    "requested": false,
    "requested_at": null,
    "cancelled_at": null
  }
}
```

## 状态更新逻辑

```text
POST /api/review/jobs
  -> 创建 data/api/<task_id>/
  -> 保存上传文件
  -> 写 task.json: queued
  -> 返回 task_id
  -> 后台继续执行审核

后台任务开始
  -> task.json: running

后台任务成功
  -> task.json: succeeded

后台任务失败
  -> task.json: failed

取消任务
  -> queued: cancelled
  -> running: cancelling -> cancelled
```

异步设计解决的是 HTTP 请求超时和状态可查询问题，不会让实际审核耗时变短。
