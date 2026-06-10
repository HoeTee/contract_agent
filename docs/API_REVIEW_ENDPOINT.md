# `/api/review` API 说明

本文说明无登录、同步执行合同审查的 API：

```text
POST /api/review
```

对应实现：

- `web/routes.py`：定义路由、接收上传、校验 DOCX、调用 workflow、返回 DOCX 或错误 JSON。
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

## `.env` 开关

```env
API_STORE=True
```

含义：

| 值 | 行为 |
| --- | --- |
| `True` | 默认行为。输入文件、输出文件和日志持久保存在 `DATA_DIR/api/<任务目录>/`。 |
| `False` | 使用系统临时目录执行本次 API；响应完成或失败后清理，不长期保存输入文件、输出文件和日志。 |

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
```

含义：

| 响应头 | 含义 |
| --- | --- |
| `X-Review-Task-Id` | 本次 API 审查任务 ID |
| `X-Review-Log-Path` | 本次 API 事件日志路径 |
| `X-Review-Criteria-Source` | 审查标准来源，值为 `default` 或 `uploaded` |

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
  -o "合同A_批注版.docx"
```

不上传审查标准时：

```bash
curl -X POST "http://127.0.0.1:5000/api/review" \
  -F "file=@/path/to/合同A.docx" \
  -o "合同A_批注版.docx"
```

此时服务端会复制系统默认 `criteria.docx` 到本次 API 任务目录。
