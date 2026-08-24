# 异步审查 API 调用指南

## 调用顺序

```text
POST /api/review/jobs
  -> 获取 task_id
  -> POST /api/review/jobs/status 查询任务状态
  -> status=succeeded
  -> POST /api/review/jobs/result 下载 DOCX
```

状态为 `pending`、`queued` 或 `running` 时继续查询。状态为 `failed` 或 `cancelled` 时停止查询。

## 1. 提交任务

```http
POST /api/review/jobs
Authorization: <api_key>
Content-Type: multipart/form-data
```

请求字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `file` | DOCX 文件 | 待审查合同。 |
| `templateCode` | 字符串 | 业务模板编号。 |
| `serialNo` | 字符串 | 业务流水号。 |

```powershell
curl.exe -X POST "http://localhost:5000/api/review/jobs" `
  -H "Authorization: <api_key>" `
  -F "file=@C:/path/contract.docx" `
  -F "templateCode=template_001" `
  -F "serialNo=serial_001"
```

成功响应为 HTTP `202`：

```json
{
  "task_id": "20260824-120000-abcd",
  "status": "pending",
  "message": "Review job submitted."
}
```

## 2. 查询任务状态

```http
POST /api/review/jobs/status
Authorization: <api_key>
Content-Type: application/json
```

```json
{
  "task_id": "20260824-120000-abcd"
}
```

```powershell
curl.exe -X POST "http://localhost:5000/api/review/jobs/status" `
  -H "Authorization: <api_key>" `
  -H "Content-Type: application/json" `
  -d '{ "task_id": "20260824-120000-abcd" }'
```

成功响应中的 `status` 为 `succeeded` 后调用结果接口：

```json
{
  "task_id": "20260824-120000-abcd",
  "status": "succeeded",
  "meta_fields": {
    "templateCode": "template_001",
    "serialNo": "serial_001"
  },
  "output": {
    "result_filename": "【已AI审查】contract.docx",
    "ready": true
  }
}
```

## 3. 下载结果

```http
POST /api/review/jobs/result
Authorization: <api_key>
Content-Type: application/json
```

```json
{
  "task_id": "20260824-120000-abcd",
  "output_type": "file"
}
```

```powershell
curl.exe -X POST "http://localhost:5000/api/review/jobs/result" `
  -H "Authorization: <api_key>" `
  -H "Content-Type: application/json" `
  -d '{ "task_id": "20260824-120000-abcd", "output_type": "file" }' `
  -o "review_result.docx"
```

成功响应为 HTTP `200`，响应体是 DOCX 文件流，调用方通过 `-o` 指定本地保存路径。
