# 合同审查 Agent

本项目提供合同 DOCX 审查的 Web 前端、异步 API 和本地 CLI。系统会读取合同、校验审查要点、运行审查工作流，并生成带批注的 DOCX 结果文件。

## 运行数据

运行数据使用项目内固定路径：

```text
data/
  api/
    <task_id>/
  web/
    <tenant_id>/
      <task_id>/

user_profiles/
  users.json
```

`data_dir` 和 `users_file` 不再通过 `config.yaml` 配置。

API 和 Web 数据分区独立：

- API 任务：`data/api/<task_id>/`
- Web 任务：`data/web/<tenant_id>/<task_id>/`
- 用户配置：`user_profiles/users.json`

Web 审查任务中，`data/web/<tenant_id>/<task_id>/task.json` 是提交、运行状态、结果展示和历史记录的唯一任务状态文件。提交后不能用 history-only 记录覆盖它；任务成功后只能把历史展示字段合并进原有任务记录。

前端页面状态约束，包括“重新登录后不能显示旧失败任务错误”，见 `docs/FRONTEND_USER_JOURNEY.md`。

## 配置

从 `.env.example` 创建 `.env`：

```env
LLM_API_KEY=...
EMBED_API_KEY=...
RERANK_API_KEY=...
SESSION_SECRET_KEY=replace-with-a-long-random-secret
```

MinerU 已移除。`MINERU_API_KEY`、`parser.parse_file_with_mineru` 和 `mineru.api_base` 不再使用。

reranker 的 `base_url` 必须是完整请求 URL。程序不会自动拼接 `/rerank` 或 `/reranks`，也不存在 `endpoint_format` 配置。

`qwen3-rerank` 示例：

```yaml
rerank:
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1/reranks"
  name: "qwen3-rerank"
  inject_instruct: true
```

只有目标 reranker 服务支持 `instruct` 字段时，才设置 `inject_instruct: true`。

reranker 的厂商边界和排障说明见 `docs/RERANKER_CONFIGURATION.md`。

API 留存配置：

```yaml
api:
  keep_input: true
  write_logs: true
  callback_file_field: "file"
```

`api.store` 已移除。

## Web 服务

本地启动：

```powershell
uvicorn app:app --host 0.0.0.0 --port 5000
```

浏览器访问：

```text
http://127.0.0.1:5000
```

Web 审查任务使用共享 review worker 和 task-store 状态模型，但数据仍保存在 `data/web/`。这样 Web 与 API 的任务状态、模型调用错误和事件日志保持一致，同时不混用两边的数据目录。

## API

主要异步 API 流程：

- `POST /api/review/jobs`
- `GET /api/review/jobs/{task_id}`
- `POST /api/review/jobs/{task_id}/result`
- `POST /api/review/jobs/{task_id}/cancel`

API 任务保存在 `data/api/`。

## CLI

CLI 不再依赖 `data/` 用户分区，也不再使用 `DEFAULT_CLI_USERNAME`。

使用系统默认审查要点：

```powershell
python main.py --contract .\contract.docx
```

使用自定义审查要点：

```powershell
python main.py --contract .\contract.docx --criteria .\criteria.docx
```

指定输出路径：

```powershell
python main.py --contract .\contract.docx --criteria .\criteria.docx --output .\contract_reviewed.docx
```

如果不传 `--output`，带批注的 DOCX 会写入当前命令执行目录。

## Docker

建议持久化挂载：

```yaml
volumes:
  - ./data:/app/data
  - ./user_profiles:/app/user_profiles
  - ./resources/review_criteria/criteria.docx:/app/resources/review_criteria/criteria.docx:ro
```

## 日志

开启日志时，任务事件日志写入每个任务目录下的 `api_events.jsonl`。

模型重试和失败事件包括：

- `agent_model_call_failed`
- `embedding_call_failed`
- `reranker_call_retry`
- `reranker_call_failed`

更多说明见 `docs/LOGGER_DESIGN.md` 和 `docs/API_REVIEW_ENDPOINT.md`。
