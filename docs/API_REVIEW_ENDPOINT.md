# 一次性审查 API 说明

本文说明无登录、同步调用完整合同审查服务的 API：

```text
POST /api/review
```

对应实现文件：

- `web/routes.py`：定义 API 路由、处理上传、调用工作流、返回文件或错误 JSON。
- `loggers/resolve_api_review_paths.py`：集中生成本次 API 调用需要的临时目录、日志目录和输出路径。
- `main_workflow/main_workflow.py`：执行完整合同审查工作流。

这个接口的定位是“一次请求完成一次审查”：调用方上传合同，可选上传本次专用审查要点；服务端同步运行完整 workflow；成功后直接返回批注版 DOCX。

## 接口定义

路由定义在 `web/routes.py`：

```python
@router.post("/api/review")
async def api_review(
    file: UploadFile = File(...),
    criteria_file: UploadFile | None = File(None),
):
```

这里的 `File(...)` 和 `File(None)` 决定了请求必须使用 `multipart/form-data`。

- `UploadFile` 表示 FastAPI 传给函数的是上传文件对象。
- `File(...)` 表示该字段来自 multipart 文件字段，并且必填。
- `File(None)` 表示该字段来自 multipart 文件字段，但是可选。

因此调用方不是发送 JSON，而是发送 multipart 表单。

## Multipart 输入字段

### file

```text
字段名：file
是否必填：必填
类型：DOCX 文件
用途：待审查合同
```

代码：

```python
file: UploadFile = File(...)
```

如果请求中没有 `file` 字段，FastAPI 会在进入 `api_review()` 之前做参数校验，返回请求参数错误，通常是 `422`。

进入函数后，代码会先清洗上传文件名：

```python
filename = safe_upload_filename(file.filename)
```

`safe_upload_filename()` 的行为：

```python
def safe_upload_filename(filename: str | None) -> str:
    if not filename:
        return "uploaded.docx"
    return Path(filename.replace("\\", "/")).name
```

设计目的：

- 如果上传文件名为空，使用 `uploaded.docx`。
- 如果浏览器或客户端带了类似 `C:\fakepath\合同.docx` 的路径，只保留最后的文件名 `合同.docx`。
- 避免把客户端路径当成服务端路径使用。

合同文件名必须以 `.docx` 结尾：

```python
if not filename.lower().endswith(".docx"):
    raise HTTPException(
        status_code=400,
        detail="系统支持的合同文件格式是 DOCX。",
    )
```

随后合同内容会被写入本次 API 调用的临时目录：

```python
with paths.stored_contract_path.open("wb") as f:
    shutil.copyfileobj(file.file, f)
```

这里有两个文件对象：

- `file.file`：HTTP multipart 上传进来的源文件流。
- `f`：服务端临时目录中的目标文件。

`with ... as f` 只负责关闭目标文件 `f`，不会关闭上传文件对象。因此函数最后仍然会执行：

```python
await file.close()
```

### criteria_file

```text
字段名：criteria_file
是否必填：可选
类型：DOCX 文件
用途：本次审查专用审查要点
```

代码：

```python
criteria_file: UploadFile | None = File(None)
```

这个字段是可选的。没有上传时，API 使用系统默认审查要点：

```python
selected_criteria_path = Path(DEFAULT_REVIEW_CRITERIA_PATH)
criteria_source = "default"
```

如果调用方上传了 `criteria_file`，代码会走单独的上传分支：

```python
has_uploaded_criteria = bool(criteria_file and criteria_file.filename)
if has_uploaded_criteria:
    criteria_filename = safe_upload_filename(criteria_file.filename)
```

上传的审查要点也必须是 `.docx`：

```python
if not criteria_filename.lower().endswith(".docx"):
    raise HTTPException(
        status_code=400,
        detail="审查要点文件格式必须是 DOCX。",
    )
```

随后保存到本次 API 调用的临时目录：

```python
with paths.uploaded_criteria_path.open("wb") as f:
    shutil.copyfileobj(criteria_file.file, f)
```

保存后做两层校验：

```python
validate_uploaded_docx(paths.uploaded_criteria_path)
validate_review_criteria_content(paths.uploaded_criteria_path)
```

- `validate_uploaded_docx()` 校验它是否是真正可读的 Word DOCX。
- `validate_review_criteria_content()` 校验内容是否像审查要点文档，例如内容长度、关键词、编号条目等。

校验通过后，实际传给 workflow 的审查要点路径会被切换为上传文件：

```python
selected_criteria_path = paths.uploaded_criteria_path
criteria_source = "uploaded"
```

如果没有上传 `criteria_file`，代码会检查系统默认审查要点是否存在：

```python
elif not selected_criteria_path.exists():
    raise HTTPException(
        status_code=404,
        detail=f"未找到系统默认审查要点文件：{selected_criteria_path}",
    )
```

这就是为什么 `criteria_file` 有“默认文件不存在”的报错，而 `file` 没有同样逻辑：合同没有默认文件，必须由请求上传；审查要点可以不上传，但不上传时必须能找到服务器默认文件。

## 成功响应

成功时返回 `FileResponse`：

```python
return FileResponse(
    path=output_path,
    media_type=DOCX_MEDIA_TYPE,
    filename=response_filename,
    background=BackgroundTask(paths.cleanup_temp_dir),
    headers={
        "X-Review-Task-Id": paths.task_id,
        "X-Review-Log-Path": str(paths.api_events_path),
        "X-Review-Criteria-Source": criteria_source,
    },
)
```

### 响应体

响应体是生成后的批注版 DOCX 文件。

```python
path=output_path
```

`output_path` 来自 workflow 返回结果：

```python
output_path = Path(result["report_docx"])
```

`result` 是 `workflow.run()` 返回的字典，其中 `report_docx` 是最终生成的批注 DOCX 路径。

### Content-Type

```python
media_type=DOCX_MEDIA_TYPE
```

`DOCX_MEDIA_TYPE` 定义为：

```python
application/vnd.openxmlformats-officedocument.wordprocessingml.document
```

调用方可以根据这个 MIME 类型识别响应体是 Word DOCX。

### 下载文件名

```python
filename=response_filename
```

`response_filename` 由上传合同文件名生成：

```python
response_filename = build_report_display_name(filename)
```

函数：

```python
def build_report_display_name(contract_original_name: str) -> str:
    stem = Path(contract_original_name).stem or "审核结果"
    return f"{stem}_批注版.docx"
```

示例：

```text
上传文件名：合同A.docx
清洗后文件名：合同A.docx
stem：合同A
返回下载名：合同A_批注版.docx
```

如果上传文件名是：

```text
C:\fakepath\合同A.docx
```

先由 `safe_upload_filename()` 清洗为：

```text
合同A.docx
```

再生成：

```text
合同A_批注版.docx
```

### 响应头

成功响应会包含三个自定义响应头：

```text
X-Review-Task-Id
X-Review-Log-Path
X-Review-Criteria-Source
```

含义：

| 响应头 | 含义 |
| --- | --- |
| `X-Review-Task-Id` | 本次 API 审查任务 ID，用于排查日志。 |
| `X-Review-Log-Path` | 本次 API 事件日志文件路径。 |
| `X-Review-Criteria-Source` | 审查要点来源，值为 `default` 或 `uploaded`。 |

## 失败响应

失败时返回 JSON，不返回 DOCX。

### HTTPException 失败

代码：

```python
except HTTPException as exc:
    append_api_event(
        paths.api_events_path,
        "review_failed",
        status_code=exc.status_code,
        detail=exc.detail,
    )
    paths.cleanup_temp_dir()
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "task_id": paths.task_id,
            "status": "failed",
            "message": exc.detail,
            "api_events_path": str(paths.api_events_path),
        },
    )
```

这类错误主要来自明确的输入校验或资源缺失。

典型情况：

| 场景 | 状态码 | 说明 |
| --- | --- | --- |
| 合同文件名不是 `.docx` | `400` | `file` 字段存在，但文件名格式不符合要求。 |
| 上传的 `criteria_file` 不是 `.docx` | `400` | 审查要点文件名格式不符合要求。 |
| 上传文件扩展名是 `.docx`，但不是有效 Word 文件 | `400` | `validate_uploaded_docx()` 校验失败。 |
| 上传的审查要点内容不符合系统规则 | `400` | `validate_review_criteria_content()` 校验失败。 |
| 没有上传 `criteria_file`，且默认审查要点不存在 | `404` | 服务器缺少 `DEFAULT_REVIEW_CRITERIA_PATH` 指向的默认文件。 |

返回结构：

```json
{
  "task_id": "153000_abcd1234",
  "status": "failed",
  "message": "错误说明",
  "api_events_path": "data/api_logs/2026-06-10/153000_abcd1234/api_events.jsonl"
}
```

### ModelCallError 失败

代码：

```python
except Exception as exc:
    status_code = 503 if isinstance(exc, ModelCallError) else 500
    if isinstance(exc, ModelCallError):
        message = f"审核失败：{exc.user_message}"
        append_api_event(
            paths.api_events_path,
            exc.event_type,
            component=exc.component,
            error=str(exc),
        )
```

如果异常是 `ModelCallError`，API 返回 `503`。这表示外部模型类服务失败，例如超时、重试后仍失败、模型服务不可用等。

返回结构仍然是：

```json
{
  "task_id": "153000_abcd1234",
  "status": "failed",
  "message": "审核失败：模型错误说明",
  "api_events_path": "data/api_logs/2026-06-10/153000_abcd1234/api_events.jsonl"
}
```

同时会先写入模型组件级事件，再写入统一的 `review_failed` 事件，便于区分具体失败组件。

### 普通异常失败

如果不是 `HTTPException`，也不是 `ModelCallError`，API 返回 `500`：

```python
message = "审核失败，请查看任务日志。"
append_api_event(paths.api_events_path, "review_failed", error=repr(exc))
paths.cleanup_temp_dir()
```

这类错误包括 workflow 内部异常、报告生成异常、输出文件缺失等。

输出文件缺失会在这里触发：

```python
output_path = Path(result["report_docx"])
if not output_path.exists():
    raise RuntimeError("未找到输出的 DOCX 文件。")
```

## 日志设计

API 审查不写入普通用户目录，而是写入独立的 API 日志目录：

```text
data/api_logs/<YYYY-MM-DD>/<task_id>/
```

路径来自 `ResolvedApiReviewPaths.task_log_dir`：

```python
return self.data_dir / "api_logs" / self.date_str / self.task_id
```

任务目录下分为：

```text
data/api_logs/<YYYY-MM-DD>/<task_id>/
  api_events.jsonl
  workflow/
  conversations/
  mcp/
```

### api_events.jsonl

API 层使用 `append_api_event()` 追加事件。

典型事件：

| 事件名 | 触发位置 |
| --- | --- |
| `api_review_received` | 收到 API 请求。 |
| `criteria_uploaded` | 本次请求上传了审查要点。 |
| `contract_saved` | 合同已保存到临时目录。 |
| `docx_validation_passed` | 合同 DOCX 校验通过。 |
| `review_started` | workflow 即将开始。 |
| `review_completed` | workflow 完成并生成 DOCX。 |
| `review_failed` | API 或 workflow 失败。 |

`jsonl` 表示每一行是一个独立 JSON 对象，便于追加写入，也便于按任务排查。

### workflow 日志

`workflow_log_dir` 传给 `ContractReviewWorkflow`：

```python
workflow = ContractReviewWorkflow(
    server_script_path=str(MCP_SERVER_PATH),
    workflow_log_dir=str(paths.workflow_log_dir),
    conversation_log_dir=str(paths.conversation_log_dir),
    mcp_log_file=str(paths.mcp_log_dir / "mcp_client.log"),
    api_events_path=str(paths.api_events_path),
)
```

workflow 内部会记录审查阶段、token、结果摘要等信息。

### conversation 日志

API 在调用 workflow 前设置本次任务的 conversation log 目录：

```python
token = set_conversation_log_dir(paths.conversation_log_dir)
try:
    ...
finally:
    reset_conversation_log_dir(token)
```

设计目的：

- 让本次 API 调用中的 agent/model 对话日志写入本任务目录。
- 运行结束后恢复之前的上下文，避免污染其他请求。

### MCP 日志

`mcp_log_file` 指向：

```text
data/api_logs/<YYYY-MM-DD>/<task_id>/mcp/mcp_client.log
```

它用于记录 workflow 调用 MCP 工具时的客户端日志。

## 临时目录设计

API 调用需要一个临时目录，因为 workflow 和 MCP 工具都以本地文件路径为输入输出，而不是直接消费 HTTP 上传流。

临时目录由 `resolve_api_review_paths()` 创建：

```python
temp_dir = Path(tempfile.mkdtemp(prefix=f"contract_review_api_{task_id}_"))
```

临时目录通常位于系统临时目录下，目录名前缀包含本次任务 ID：

```text
contract_review_api_<task_id>_...
```

### 临时目录中的文件

本次 API 调用涉及三个主要文件路径。

#### 合同文件

```python
stored_contract_path = self.temp_dir / self.original_filename
```

它是上传合同保存后的本地路径。

#### 上传审查要点

```python
uploaded_criteria_path = self.temp_dir / "criteria.docx"
```

只有调用方上传 `criteria_file` 时才会使用这个路径。

如果没有上传审查要点，`criteria_path` 使用系统默认文件，不在临时目录。

#### 输出报告

```python
final_report_path = self.temp_dir / f"{self.task_id}_{self.safe_contract_stem}_reviewed.docx"
```

这是传给 workflow 的目标输出路径。workflow 生成的批注版 DOCX 会写到这里。

### 临时目录创建

`paths.ensure_dirs()` 会确保临时目录和日志子目录存在：

```python
def ensure_dirs(self) -> None:
    self.temp_dir.mkdir(parents=True, exist_ok=True)
    for path in (
        self.workflow_log_dir,
        self.conversation_log_dir,
        self.mcp_log_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)
```

注意：`tempfile.mkdtemp()` 已经创建了临时目录，`ensure_dirs()` 再调用 `mkdir(..., exist_ok=True)` 是幂等保障。

### 临时目录写入

合同写入：

```python
with paths.stored_contract_path.open("wb") as f:
    shutil.copyfileobj(file.file, f)
```

可选审查要点写入：

```python
with paths.uploaded_criteria_path.open("wb") as f:
    shutil.copyfileobj(criteria_file.file, f)
```

报告写入：

```python
workflow.run(
    contract_path=str(paths.stored_contract_path),
    criteria_path=str(selected_criteria_path),
    output_path=str(paths.final_report_path),
)
```

其中 `output_path` 指向 `paths.final_report_path`。

### 临时目录删除

删除函数：

```python
def cleanup_temp_dir(self) -> None:
    shutil.rmtree(self.temp_dir, ignore_errors=True)
```

成功路径：文件响应发送完成后，由后台任务删除。

```python
background=BackgroundTask(paths.cleanup_temp_dir)
```

失败路径：返回 JSON 前立即删除。

```python
paths.cleanup_temp_dir()
```

API 的 `finally` 还会关闭上传文件对象：

```python
finally:
    await file.close()
    if criteria_file:
        await criteria_file.close()
```

这里关闭的是 HTTP multipart 上传源文件，不是临时目录里的目标文件。目标文件在 `with ... open(...)` 结束时已经关闭。

### 为什么不长期保存 API 上传文件

这个 API 是无登录调用，不绑定普通用户目录。临时目录设计有几个目的：

- 隔离每次请求，避免同名合同互相覆盖。
- 避免无登录 API 污染 `data/<username>/...` 用户目录。
- 成功后调用方已经拿到 DOCX，服务端没有必要长期保存合同和报告。
- 失败时也能清理上传文件，避免磁盘堆积。
- 日志仍长期保存在 `data/api_logs/...`，便于排查。

## Workflow 嵌入方式

API 创建 workflow 对象：

```python
workflow = ContractReviewWorkflow(
    server_script_path=str(MCP_SERVER_PATH),
    workflow_log_dir=str(paths.workflow_log_dir),
    conversation_log_dir=str(paths.conversation_log_dir),
    mcp_log_file=str(paths.mcp_log_dir / "mcp_client.log"),
    api_events_path=str(paths.api_events_path),
)
```

然后定义一个内部函数：

```python
async def run_workflow():
    return await workflow.run(
        contract_path=str(paths.stored_contract_path),
        criteria_path=str(selected_criteria_path),
        output_path=str(paths.final_report_path),
    )
```

三个参数来源：

| 参数 | 来源 | 含义 |
| --- | --- | --- |
| `contract_path` | `paths.stored_contract_path` | 已保存到临时目录的上传合同路径。 |
| `criteria_path` | `selected_criteria_path` | 上传审查要点路径，或系统默认审查要点路径。 |
| `output_path` | `paths.final_report_path` | 要求 workflow 写出的批注版 DOCX 路径。 |

如果配置了并发限制，API 会通过信号量包住 workflow：

```python
if review_semaphore is None:
    result = await run_workflow()
else:
    async with review_semaphore:
        result = await run_workflow()
```

`review_semaphore` 来自 `MAX_API_CONCURRENT_REVIEWS`，用于限制同时运行的审查数量，避免模型、检索、MCP 服务被过多并发请求打满。

### workflow.run() 返回值

`ContractReviewWorkflow.run()` 返回一个字典：

```python
return {
    "report_docx": annotated_docx_path,
    "criteria_count": len(results),
    "issue_count": sum(len(result.get("issues", [])) for result in results),
    "total_tokens": total_tokens,
    "retrieval_mode": "llamaindex",
    "workflow_log": log_path,
    "results_log": results_path,
    "run_summary_log": run_summary_path,
}
```

API 只直接使用其中的 `report_docx`：

```python
output_path = Path(result["report_docx"])
```

随后检查文件是否存在：

```python
if not output_path.exists():
    raise RuntimeError("未找到输出的 DOCX 文件。")
```

如果存在，就返回给调用方下载。

### workflow 内部阶段

`workflow.run()` 内部执行完整审查流程：

1. 解析合同和审查要点。
2. 构建临时 LlamaIndex 合同索引。
3. 从审查要点中规划审查任务。
4. 执行每个审查任务，并进行反思校验。
5. 汇总审查结果。
6. 调用 MCP 工具生成批注版 DOCX。
7. 保存 workflow 日志、结果日志和 run summary。

生成 DOCX 的阶段会调用 MCP 工具：

```python
result = await self.mcp_client.call_tool(
    "generate_docx_report",
    tool_args,
)
```

工具返回 JSON 字符串，workflow 解析后取出 `docx` 路径：

```python
parsed = json.loads(result)
docx_path = parsed["docx"]
return docx_path
```

这个 `docx_path` 最终成为 API 中的 `result["report_docx"]`。

## resolve_api_review_paths 的设计理念

`resolve_api_review_paths()` 的作用不是写日志，也不是执行审查，而是集中生成路径。

输入：

```python
resolve_api_review_paths(
    original_filename=filename,
    data_dir=Path(DATA_DIR),
)
```

输出：

```python
ResolvedApiReviewPaths(
    original_filename=safe_filename,
    data_dir=data_dir,
    created_at=created_at,
    task_id=task_id,
    safe_contract_stem=stem,
    temp_dir=temp_dir,
)
```

### 为什么集中生成路径

这样设计有几个好处：

1. API 路由代码不需要到处拼字符串路径。
2. 上传文件、输出文件、日志文件的命名规则集中管理。
3. 普通用户审查路径和无登录 API 审查路径分开，避免互相污染。
4. 每次 API 调用都有独立 `task_id`，便于定位日志。
5. 临时文件和持久日志分开，清理临时目录不会误删日志。

### task_id

`task_id` 由当前时间和随机短 ID 组成：

```python
task_id = f"{created_at.strftime('%H%M%S')}_{uuid.uuid4().hex[:8]}"
```

示例：

```text
153000_abcd1234
```

这个 ID 同时用于：

- 临时目录名前缀。
- API 日志目录。
- 输出 DOCX 文件名。
- 响应头 `X-Review-Task-Id`。
- 失败 JSON 中的 `task_id`。

### safe_contract_stem

代码：

```python
safe_filename = Path(original_filename.replace("\\", "/")).name
stem = safe_path_part(Path(safe_filename).stem, "contract")
```

作用：

- 再次去掉客户端路径，只保留文件名。
- 去掉扩展名，得到合同名主体。
- 使用 `safe_path_part()` 转成适合放入服务端路径的片段。

如果文件名主体为空，就使用默认值 `contract`。

### 路径属性

`ResolvedApiReviewPaths` 用属性表达各类路径：

```python
task_log_dir
workflow_log_dir
conversation_log_dir
mcp_log_dir
api_events_path
stored_contract_path
uploaded_criteria_path
final_report_path
```

这样 API 层只需要读语义明确的属性：

```python
paths.stored_contract_path
paths.uploaded_criteria_path
paths.final_report_path
paths.api_events_path
```

而不需要关心这些路径具体如何拼接。

## 调用示例

### 只上传合同，使用默认审查要点

PowerShell：

```powershell
$form = @{
  file = Get-Item "C:\path\合同A.docx"
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
  -o "合同A_批注版.docx"
```

### 同时上传合同和本次专用审查要点

PowerShell：

```powershell
$form = @{
  file = Get-Item "C:\path\合同A.docx"
  criteria_file = Get-Item "C:\path\本次审查要点.docx"
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
  -F "criteria_file=@/path/to/本次审查要点.docx" \
  -o "合同A_批注版.docx"
```

## 和 Web 页面审查的区别

Web 页面审查接口是：

```text
POST /review
```

它需要登录用户，上传后写入用户目录，通过后台任务运行，并在 `/work` 页面展示状态。

无登录 API 审查接口是：

```text
POST /api/review
```

它不依赖登录态，不写入普通用户目录，不写历史记录；它同步等待 workflow 完成，并直接返回 DOCX 文件。持久化保留的是 `data/api_logs/...` 下的日志。

