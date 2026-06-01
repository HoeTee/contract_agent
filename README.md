# Deep Research Agent

Deep Research Agent 是一个合同智能审查 Web 服务，支持用户登录、DOCX 合同上传、合同审查、批注版 DOCX 下载、按用户分区存储，以及按任务分区记录日志。

## 运行目录

```text
data/
  <username>/
    contract_review_criteria/
      criteria.docx
    institutional_docs/
    contracts/
    reports_docx/
    records/
      review_history.json
    logs/

docs/
  LOGGER_DESIGN.md
  USER_MANAGEMENT.md
  PROJECT_STRUCTURE.md
  DEPLOYMENT.md
  QUICK_START.md
```

- `data/`：运行时持久化数据目录。部署到服务器时应挂载这个目录。
- `resources/review_criteria/criteria.docx`：系统默认审查要点模板，新建用户时会复制到用户目录。
- `docs/`：只存放 Markdown 文档，不作为程序输入或输出目录。
- `users.json`：用户账号配置文件。密码只保存哈希值，不保存明文。

## 用户管理

创建用户：

```powershell
python scripts/manage_users.py create --username user001 --password Abc123456 --display-name ZhangSan
```

重置密码：

```powershell
python scripts/manage_users.py reset-password --username user001 --password NewPass123
```

禁用用户：

```powershell
python scripts/manage_users.py disable --username user001
```

创建用户时会自动生成用户目录，并从系统默认模板复制审查要点：

```text
data/user001/contract_review_criteria/criteria.docx
```

## Web 服务

本地启动：

```powershell
uvicorn app:app --host 0.0.0.0 --port 5000
```

本机浏览器访问：

```text
http://127.0.0.1:5000
```

完整冒烟测试见 [docs/QUICK_START.md](docs/QUICK_START.md)。

用户登录后，服务会：

1. 将上传合同保存到 `data/<username>/contracts/`
2. 如果本次上传了审查要点，则使用本次上传的 DOCX；否则使用 `data/<username>/contract_review_criteria/criteria.docx`
3. 直接从 `data/<username>/contracts/` 读取合同
4. 将批注版 DOCX 写入 `data/<username>/reports_docx/`
5. 将成功审查的历史索引写入 `data/<username>/records/review_history.json`
6. 将任务日志写入 `data/<username>/logs/<YYYY-MM-DD>/<task>/`

## CLI

CLI 也按用户分区运行。默认用户来自 `.env`：

```env
DEFAULT_CLI_USERNAME=default
```

运行示例：

```powershell
python main.py --username default --contract sample.docx
```

如果 `--contract` 是相对路径，程序会从下面的位置读取：

```text
data/default/contracts/sample.docx
```

## Docker

`docker-compose.yaml` 挂载：

```yaml
volumes:
  - ./data:/app/data
  - ./users.json:/app/users.json:ro
  # 可选：自定义新用户默认审查要点模板
  # - ./resources/review_criteria/criteria.docx:/app/resources/review_criteria/criteria.docx:ro
```

容器内部监听 `5000`。当前 compose 映射：

```yaml
ports:
  - "127.0.0.1:8000:5000"
```

服务器本机访问：

```text
http://127.0.0.1:8000
```

如果要允许外部机器访问，改成：

```yaml
ports:
  - "8000:5000"
```

然后访问：

```text
http://服务器IP:8000
```

## 日志

每个审查任务的日志目录：

```text
data/<username>/logs/<YYYY-MM-DD>/<task>/
  workflow/
  conversations/
  mcp/
  api_events.jsonl
```

日志设计见 [docs/LOGGER_DESIGN.md](docs/LOGGER_DESIGN.md)。

## 必要环境变量

从 `.env.example` 创建 `.env`，至少配置：

```env
LLM_API_KEY=...
LLM_BASE_URL=...
LLM_NAME=qwen-plus

EMBED_API_KEY=...
EMBED_BASE_URL=...
EMBED_NAME=text-embedding-v4

RERANK_API_KEY=...
RERANK_BASE_URL=...
RERANK_NAME=qwen3-rerank

ENABLE_WORKFLOW_LOGS=False
MAX_API_CONCURRENT_REVIEWS=1
SESSION_SECRET_KEY=replace-with-a-long-random-secret
```
