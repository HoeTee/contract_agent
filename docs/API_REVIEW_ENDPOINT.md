# `/api/review` API 说明

补充：原同步接口 `POST /api/review` 保留不变；新增异步任务接口为 `POST /api/review/jobs`、`GET /api/review/jobs/{task_id}`、`GET /api/review/jobs/{task_id}/result` 和 `POST /api/review/jobs/{task_id}/cancel`。异步接口、`task.json` 字段和 `data/api/<task_id>/` 存储结构见 `docs/ASYNC_REVIEW_API.md`。

本文说明无登录、同步执行合同审查的 API：

```text
POST /api/review
```

对应实现：

- `web/api/review.py`：定义 `POST /api/review`，接收上传、校验 DOCX、调用 workflow、返回 DOCX 或错误 JSON。
- `web/api/callbacks.py`：在批注 DOCX 生成后按配置发送外部回调。
- `web/core/document_validation.py`：校验合同 DOCX 和审查要点 DOCX。
- `web/core/filenames.py`：清洗上传文件名并构造批注版 DOCX 展示文件名。
- `loggers/resolve_api_review_paths.py`：集中生成本次 API 调用的数据目录、日志目录、输入文件路径和输出文件路径。
- `main_workflow/main_workflow.py`：执行完整合同审查流程并生成批注版 DOCX。

## 直接结论

`/api/review` 不使用 `data/default`，也不写入普通用户目录。默认情况下，`API_STORE=True`，每次 API 调用会在 `data/api/` 下创建一个独立任务目录，合同、审查标准、输出批注合同和日志都保存在这个目录中。

```text
data/
  api/
    20260610-153012-a1b2/
      合同原文件名.docx
      审查标准原文件名.docx
      合同原文件名_reviewed.docx
      logs/
        api_events.jsonl
        workflow/
        conversations/
        mcp/
          mcp_client.log
```

目录名格式：

```text
YYYYMMDD-HHMMSS-xxxx
```

其中 `xxxx` 是短随机后缀，用于避免同一秒多次请求冲突。

## 接口分层

本项目目前同时存在以下 HTTP 路由类型：

| 类型 | 路由 | 用途 | 调用方 | 返回形式 |
| --- | --- | --- | --- | --- |
| 直接 API | `POST /api/review` | 无登录、同步执行合同审查 | 外部系统、脚本、集成服务 | 成功返回 DOCX；失败返回 JSON |
| 前端审查 | `POST /review` | 登录用户在 Web 页面提交审查 | 浏览器表单 | 立即 `303` 跳回 `/work`，审查在后台任务中执行 |
| 前端状态 | `GET /session/status` | 前端轮询登录状态和角色 | 浏览器 JS | JSON |
| 前端下载 | `GET /download/{filename}` | 登录用户下载自己的批注版 DOCX | 浏览器 | DOCX 或 404 |
| 前端页面 | `GET /login`、`GET /work`、`GET /settings`、`GET /history` | 页面渲染 | 浏览器 | HTML 或重定向 |
| 前端账号操作 | `POST /login`、`POST /logout`、`POST /profile/display-name` | 登录、退出、修改显示名称 | 浏览器表单 | HTML 或重定向 |
| 管理后台 | `/admin/...` | 用户、审查要点、日志查看管理 | 管理员浏览器页面 | HTML、重定向或文件下载 |

对外集成时只应使用 `POST /api/review`。`POST /review` 是 Web 前端表单接口，依赖登录态、session、用户目录和后台任务状态，不适合作为外部系统直接调用接口。

## `.env` 开关

```env
API_STORE=True
API_META_REQUIRED=False
API_META_FIELDS=templateCode,serialNo
API_CALLBACK_ENABLED=False
API_CALLBACK_URL=
API_CALLBACK_FILE_FIELD=file
DOCX_COMMENT_INCLUDE_CRITERION=False
```

含义：

| 配置 | 含义 |
| --- | --- |
| `API_STORE` | `True` 时输入文件、输出文件和日志持久保存在 `DATA_DIR/api/<任务目录>/`；`False` 时使用临时目录并在响应后清理。 |
| `API_META_REQUIRED` | 是否要求请求携带 `API_META_FIELDS` 中列出的字符串字段。 |
| `API_META_FIELDS` | 额外字符串字段名，默认 `templateCode,serialNo`。字段从 `multipart/form-data` body 中读取。 |
| `API_CALLBACK_ENABLED` | 是否在批注 DOCX 生成后主动向外部地址发送回调请求。 |
| `API_CALLBACK_URL` | 回调地址。`API_CALLBACK_ENABLED=True` 时必须配置。 |
| `API_CALLBACK_FILE_FIELD` | 回调请求里批注 DOCX 的文件字段名；未配置或为空时默认 `file`。 |
| `DOCX_COMMENT_INCLUDE_CRITERION` | 是否把每条 issue 所属审查要点追加到逐条 Word 批注末尾。它只影响 DOCX 输出内容，不是 `/api/review` 请求字段。 |

不需要额外配置 API 目录。持久化目录固定使用现有 `DATA_DIR` 下的 `api/` 子目录；目录不存在时会自动创建。

## 输入字段

请求必须使用 `multipart/form-data`。

### `file`

```text
字段名：file
是否必填：必填
类型：DOCX 文件
用途：待审查合同
```

代码入口：

```python
file: UploadFile = File(...)
```

处理链路：

1. 使用 `safe_upload_filename(file.filename)` 清洗上传文件名，只保留文件名，不信任客户端路径。
2. 校验文件名必须以 `.docx` 结尾。
3. 将上传合同写入本次 API 任务目录：

```python
with paths.stored_contract_path.open("wb") as f:
    shutil.copyfileobj(file.file, f)
```

输出位置示例：

```text
data/api/20260610-153012-a1b2/合同原文件名.docx
```

### `criteria_file`

```text
字段名：criteria_file
是否必填：可选
类型：DOCX 文件
用途：本次审查专用审查标准
```

代码入口：

```python
criteria_file: UploadFile | None = File(None)
```

如果上传了 `criteria_file`：

1. 使用 `safe_upload_filename(criteria_file.filename)` 清洗文件名。
2. 校验文件名必须以 `.docx` 结尾。
3. 将上传审查标准写入本次 API 任务目录，并保留上传文件名。
4. 校验它是可读取的 DOCX。
5. 校验内容符合审查标准文档要求。

核心代码：

```python
selected_criteria_path = paths.stored_criteria_path(criteria_filename)
with selected_criteria_path.open("wb") as f:
    shutil.copyfileobj(criteria_file.file, f)
validate_uploaded_docx(selected_criteria_path)
validate_review_criteria_content(selected_criteria_path)
criteria_source = "uploaded"
```

如果没有上传 `criteria_file`：

1. 使用系统默认审查标准 `DEFAULT_REVIEW_CRITERIA_PATH`。
2. 如果默认文件不存在，返回 `404`。
3. 将默认审查标准复制到本次 API 任务目录，文件名保持 `criteria.docx`。

核心代码：

```python
criteria_snapshot_path = paths.stored_criteria_path(selected_criteria_path.name)
shutil.copy2(selected_criteria_path, criteria_snapshot_path)
selected_criteria_path = criteria_snapshot_path
```

### 额外字符串字段

默认额外字段为：

```text
templateCode
serialNo
```

请求中仍然使用 `multipart/form-data`，字段和文件在同一个 body 中提交：

```bash
curl -X POST "http://127.0.0.1:5000/api/review" \
  -F "file=@合同A.docx" \
  -F "templateCode=TMP001" \
  -F "serialNo=SN001" \
  -o "合同A_批注版.docx"
```

如果 `API_META_REQUIRED=True`，`API_META_FIELDS` 中列出的字段必须存在且不能为空；否则返回 `400`，不会进入审查流程。

## 输出文件

workflow 输出的批注版 DOCX 会写入本次 API 任务目录：

```python
output_path=str(paths.final_report_path)
```

路径由 `ResolvedApiReviewPaths.final_report_path` 生成：

```python
return self.task_dir / f"{self.safe_contract_stem}_reviewed.docx"
```

示例：

```text
data/api/20260610-153012-a1b2/合同原文件名_reviewed.docx
```

HTTP 响应仍直接返回这个 DOCX 文件：

```python
return FileResponse(
    path=output_path,
    media_type=DOCX_MEDIA_TYPE,
    filename=response_filename,
    headers={
        "X-Review-Task-Id": paths.task_id,
        "X-Review-Log-Path": str(paths.api_events_path),
        "X-Review-Criteria-Source": criteria_source,
    },
)
```

注意：响应仍会注册后台清理任务，但只有 `API_STORE=False` 时才会删除临时目录；`API_STORE=True` 时不会删除 `data/api/<任务目录>/`。

## 日志目录

`API_STORE=True` 时，API 日志不再写入旧的 `data/api_logs/`，而是写入同一个任务目录下的 `logs/`。

```text
data/api/<任务目录>/logs/
  api_events.jsonl
  workflow/
  conversations/
  mcp/
    mcp_client.log
```

路径定义：

```python
def task_log_dir(self) -> Path:
    return self.task_dir / "logs"

def api_events_path(self) -> Path:
    return self.task_log_dir / "api_events.jsonl"
```

`api_events.jsonl` 会记录 API 层事件，例如：

| 事件 | 含义 |
| --- | --- |
| `api_review_received` | 收到 API 请求 |
| `criteria_uploaded` | 本次请求上传了审查标准 |
| `criteria_default_saved` | 本次请求使用默认审查标准并已复制到任务目录 |
| `contract_saved` | 合同已保存到任务目录 |
| `docx_validation_passed` | 合同 DOCX 校验通过 |
| `review_started` | workflow 开始运行 |
| `review_completed` | workflow 成功生成输出 DOCX |
| `review_failed` | 审查失败 |

## 路径生成规则

入口：

```python
paths = resolve_api_review_paths(
    original_filename=filename,
    data_dir=Path(DATA_DIR),
)
```

`resolve_api_review_paths()` 输出 `ResolvedApiReviewPaths`，关键属性如下：

| 属性 | 路径 |
| --- | --- |
| `task_dir` | `data/api/<任务目录>/` |
| `stored_contract_path` | `data/api/<任务目录>/<合同原文件名>.docx` |
| `stored_criteria_path(name)` | `data/api/<任务目录>/<审查标准原文件名>.docx` |
| `final_report_path` | `data/api/<任务目录>/<合同名>_reviewed.docx` |
| `task_log_dir` | `data/api/<任务目录>/logs/` |
| `api_events_path` | `data/api/<任务目录>/logs/api_events.jsonl` |
| `workflow_log_dir` | `data/api/<任务目录>/logs/workflow/` |
| `conversation_log_dir` | `data/api/<任务目录>/logs/conversations/` |
| `mcp_log_dir` | `data/api/<任务目录>/logs/mcp/` |

## Workflow 调用链路

`/api/review` 创建 `ContractReviewWorkflow`：

```python
workflow = ContractReviewWorkflow(
    server_script_path=str(MCP_SERVER_PATH),
    workflow_log_dir=str(paths.workflow_log_dir),
    conversation_log_dir=str(paths.conversation_log_dir),
    mcp_log_file=str(paths.mcp_log_dir / "mcp_client.log"),
    api_events_path=str(paths.api_events_path),
)
```

然后同步运行：

```python
result = await workflow.run(
    contract_path=str(paths.stored_contract_path),
    criteria_path=str(selected_criteria_path),
    output_path=str(paths.final_report_path),
)
```

输入和输出含义：

| 参数 | 输入 | 输出 |
| --- | --- | --- |
| `contract_path` | 已保存到 `data/api/<任务目录>/` 的合同 DOCX | workflow 读取合同内容 |
| `criteria_path` | 已保存到 `data/api/<任务目录>/` 的上传或默认审查标准 DOCX | workflow 解析审查标准 |
| `output_path` | `data/api/<任务目录>/<合同名>_reviewed.docx` | workflow 写入批注版 DOCX |

## 成功响应

成功时返回 DOCX 文件，响应头包含：

```text
X-Review-Task-Id
X-Review-Log-Path
X-Review-Criteria-Source
x-template-code
x-serial-no
```

含义：

| 响应头 | 含义 |
| --- | --- |
| `X-Review-Task-Id` | 本次 API 审查任务 ID |
| `X-Review-Log-Path` | 本次 API 事件日志路径 |
| `X-Review-Criteria-Source` | 审查标准来源，值为 `default` 或 `uploaded` |
| `x-template-code` | 请求字段 `templateCode` 的回显值；未传时为空字符串 |
| `x-serial-no` | 请求字段 `serialNo` 的回显值；未传时为空字符串 |

HTTP 响应头字段名不区分大小写。代码按小写输出额外字段响应头，便于和内网接口文档对齐。

## 批注文件回调

如果 `API_CALLBACK_ENABLED=True`，服务会在批注 DOCX 生成后、返回 `/api/review` 响应前，向 `API_CALLBACK_URL` 主动发送一次 `multipart/form-data` 请求。

回调 body 包含：

| 字段 | 来源 |
| --- | --- |
| `API_CALLBACK_FILE_FIELD` 指定的文件字段，默认 `file` | 批注后的 DOCX 文件 |
| `API_META_FIELDS` 中声明的字符串字段 | `/api/review` 请求 body 中的同名表单字段，字段名不是写死的 |

如果 `API_CALLBACK_ENABLED=True` 但没有配置 `API_CALLBACK_URL`，本次请求返回 `500`。如果回调请求发送失败或对方返回非 2xx 状态，本次请求返回 `502`。

### 本地回调接收测试

项目提供一个只用于本地测试的回调接收服务：

```powershell
uvicorn scripts.api_review_callback_receiver:app --host 127.0.0.1 --port 9001
```

`.env` 示例：

```env
API_META_REQUIRED=True
API_META_FIELDS=templateCode,serialNo
API_CALLBACK_ENABLED=True
API_CALLBACK_URL=http://127.0.0.1:9001/callback
API_CALLBACK_FILE_FIELD=file
```

调用 `/api/review`：

```powershell
curl.exe -X POST "http://localhost:5000/api/review" `
  -F "file=@C:\path\合同.docx" `
  -F "templateCode=TMP001" `
  -F "serialNo=SN001" `
  --output "C:\path\result.docx"
```

`scripts/api_review_callback_receiver.py` 会在启动终端打印收到的动态字符串字段和文件字段信息，也可以访问 `http://127.0.0.1:9001/last` 查看最近收到的记录。它只读取文件名、content type 和字节数，不会把回调里的二进制 DOCX 保存到磁盘。

## 失败响应

失败时返回 JSON，不返回 DOCX。

```json
{
  "task_id": "153012_a1b2c3d4",
  "status": "failed",
  "message": "错误信息",
  "api_events_path": "data/api/20260610-153012-a1b2/logs/api_events.jsonl"
}
```

失败时也会保留已经写入的任务目录，便于排查上传文件、审查标准和日志。

如果 `API_STORE=False`，失败返回前会清理本次临时目录，返回 JSON 中的 `api_events_path` 只表示失败发生前的临时日志路径，不保证响应后仍存在。

### 失败类型

| HTTP 状态码 | 触发条件 | `message` 来源 | 日志事件 |
| --- | --- | --- | --- |
| `400` | 合同文件名不是 `.docx` | `系统支持的合同文件格式是 DOCX。` | `review_failed` |
| `400` | 合同是旧版 `.doc`/OLE 文档 | `上传的文件是旧版 .doc/OLE 文档...` | `review_failed` |
| `400` | 合同不是有效 ZIP/DOCX 结构 | `上传的文件不是有效的 .docx 文件。` 或缺少内部文件说明 | `review_failed` |
| `400` | `criteria_file` 不是 `.docx` | `审查要点文件格式必须是 DOCX。` | `review_failed` |
| `400` | `criteria_file` 无法解析或内容不像审查标准 | 审查要点解析或校验错误文案 | `review_failed` |
| `400` | `API_META_REQUIRED=True` 且缺少 `API_META_FIELDS` 中的字段 | `缺少必填字符串字段：...` | `review_failed` |
| `404` | 未上传 `criteria_file` 且系统默认审查标准不存在 | `未找到系统默认审查要点文件：...` | `review_failed` |
| `422` | 请求不是合法 `multipart/form-data`，或缺少必填字段 `file` | FastAPI 参数校验错误 | FastAPI 在进入路由函数前返回，通常不会写入本次 `api_events.jsonl` |
| `503` | Agent、Embedding、Reranker 等模型调用失败，抛出 `ModelCallError` | `审核失败：...`，包含组件化用户可读原因 | 先写具体模型失败事件，再写 `review_failed` |
| `502` | 批注 DOCX 已生成，但回调请求发送失败或对方返回非 2xx | `批注文件回调发送失败：...` | `review_failed` |
| `500` | `API_CALLBACK_ENABLED=True` 但未配置 `API_CALLBACK_URL` | `API_CALLBACK_ENABLED=True 时必须配置 API_CALLBACK_URL。` | `review_failed` |
| `500` | workflow、DOCX 生成或其他未分类异常 | `审核失败，请查看任务日志。` | `review_failed` |

`503` 是模型或外部模型服务类失败，调用方可以结合 `X-Review-Task-Id`、返回 JSON 中的 `task_id`、`api_events_path` 和任务日志定位具体组件。`500` 表示服务内部未分类异常，应优先查看 `api_events.jsonl`、`workflow/run_summary.json`、`conversations/` 和 `mcp/` 日志。

### 直接 API 与前端错误处理差异

`POST /api/review` 的失败响应直接返回 JSON，适合脚本和外部系统读取：

```json
{
  "task_id": "20260610-153012-a1b2",
  "status": "failed",
  "message": "审核失败：Embedding 模型调用失败，请检查模型服务或网络连接。",
  "api_events_path": "data/api/20260610-153012-a1b2/logs/api_events.jsonl"
}
```

`POST /review` 是前端表单路由。它不会把错误作为 JSON 返回给浏览器脚本，而是把错误写入 session 的 `flash_error`，然后 `303` 重定向回 `/work` 页面展示。它的运行目录是 `data/<username>/...`，任务状态保存在后端内存字典 `review_tasks` 中。

## 和登录 Web 审查的区别

登录页面审查接口是：

```text
POST /review
```

它需要登录用户，写入普通用户目录：

```text
data/<username>/
  contract_review_criteria/
  contracts/
  reports_docx/
  records/
  logs/
```

无登录 API 审查接口是：

```text
POST /api/review
```

它不依赖登录态，不写入 `data/default`，不写入普通用户历史记录；它同步等待 workflow 完成。`API_STORE=True` 时，本次 API 的输入文件、输出文件和日志统一保存在：

```text
data/api/<任务目录>/
```

## 调用示例

PowerShell：

```powershell
$form = @{
  file = Get-Item "C:\path\合同A.docx"
  criteria_file = Get-Item "C:\path\本次审查标准.docx"
  templateCode = "TMP001"
  serialNo = "SN001"
}

Invoke-WebRequest `
  -Uri "http://127.0.0.1:5000/api/review" `
  -Method Post `
  -Form $form `
  -OutFile "合同A_批注版.docx"
```

curl：

```bash
curl -X POST "http://127.0.0.1:5000/api/review" \
  -F "file=@/path/to/合同A.docx" \
  -F "criteria_file=@/path/to/本次审查标准.docx" \
  -F "templateCode=TMP001" \
  -F "serialNo=SN001" \
  -o "合同A_批注版.docx"
```

不上传审查标准时：

```bash
curl -X POST "http://127.0.0.1:5000/api/review" \
  -F "file=@/path/to/合同A.docx" \
  -F "templateCode=TMP001" \
  -F "serialNo=SN001" \
  -o "合同A_批注版.docx"
```

此时服务端会复制系统默认 `criteria.docx` 到本次 API 任务目录。
