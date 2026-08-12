# API 批量审查测试

该目录是独立的 API 跑批测试项目。脚本通过 `/api/review/jobs` 提交任务，轮询 `/api/review/jobs/status`，任务成功后从 `/api/review/jobs/result` 下载 DOCX 结果。

## 准备

在项目根目录启动 API 服务：

```powershell
python app.py
```

确认 API key 已注册：

```powershell
python scripts/manage_api_clients.py register --client-id "client_a" --api-key "platform-key-for-client-a"
```

在本目录安装依赖：

```powershell
cd tests\api_batch_runner
pip install -r requirements.txt
copy .env.example .env
```

编辑 `.env`，至少填写 `BASE_URL`、`API_KEY` 和 `CONCURRENCY`。

## 运行

将待审查 DOCX 放入 `cases/`，然后执行：

```powershell
python batch_review_cases.py
```

## 配置

| 配置 | 含义 |
| --- | --- |
| `BASE_URL` | API 服务地址，例如 `http://localhost:5000`。 |
| `API_KEY` | `Authorization` 请求头的完整值。 |
| `CONCURRENCY` | 跑批客户端同时处理的文件数量。 |
| `POLL_INTERVAL_SECONDS` | 每隔多少秒查询一次任务状态。 |
| `TASK_TIMEOUT_SECONDS` | 单个文件最多等待多少秒；超时只影响脚本等待，不会取消服务端任务。 |
| `HTTP_TIMEOUT_SECONDS` | 单次 HTTP 请求最多等待多少秒；适用于提交、状态查询和结果下载。 |
| `HTTP_CONNECT_TIMEOUT_SECONDS` | 单次 HTTP 连接建立最多等待多少秒。 |
| `CASES_DIR` | 输入 DOCX 目录。 |
| `OUTPUT_DIR` | 输出 DOCX 目录。 |
| `LOG_DIR` | 每次跑批的日志根目录。 |
| `OVERWRITE` | 输出文件已存在时是否覆盖。 |

## 输出与日志

结果 DOCX 默认写入 `outputs/`。每次运行生成独立日志目录：

```text
logs/
  run_YYYYMMDD_HHMMSS/
    batch_summary.json
    batch_summary.csv
    tasks/
      <task_id>/
        task.json
```

`elapsed` 是跑批脚本视角的墙钟时间，从提交 API 成功到结果下载并写入本地完成，不代表服务端 workflow 内部阶段耗时。
