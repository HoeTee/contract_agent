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

user_profiles/
  users.json

docs/
  API_REVIEW_ENDPOINT.md
  LOGGER_DESIGN.md
  USER_MANAGEMENT.md
  PROJECT_STRUCTURE.md
  DEPLOYMENT.md
  QUICK_START.md
  FRONTEND_USER_JOURNEY.md
  REVIEW_BOUNDARIES.md
```

- `data/`：运行时持久化数据目录。部署到服务器时应挂载这个目录。
- `user_profiles/`：用户账号数据目录。首次创建用户时会自动生成 `users.json`。
- `resources/review_criteria/criteria.docx`：系统默认审查要点模板，新建用户时会复制到用户目录。
- `docs/`：只存放 Markdown 文档，不作为程序输入或输出目录。
- `user_profiles/users.json`：用户账号配置文件。密码只保存哈希值，不保存明文。

## 用户管理

创建用户：

```powershell
python scripts/manage_users.py create --username user001 --password Abc123456 --display-name ZhangSan
```

创建管理员：

```powershell
python scripts/manage_users.py create --username admin --password Admin123456 --display-name 管理员 --role admin
```

调整角色：

```powershell
python scripts/manage_users.py set-role --username user001 --role admin
python scripts/manage_users.py set-role --username user001 --role user
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

管理员登录后进入：

```text
http://127.0.0.1:5000/admin
```

管理员后台支持创建用户、修改角色、重置密码、启用/禁用、删除用户，以及管理用户默认审查要点。

完整冒烟测试见 [docs/QUICK_START.md](docs/QUICK_START.md)，直接 API 说明见 [docs/API_REVIEW_ENDPOINT.md](docs/API_REVIEW_ENDPOINT.md)，用户管理细节见 [docs/USER_MANAGEMENT.md](docs/USER_MANAGEMENT.md)，前端用户旅程见 [docs/FRONTEND_USER_JOURNEY.md](docs/FRONTEND_USER_JOURNEY.md)，审查边界见 [docs/REVIEW_BOUNDARIES.md](docs/REVIEW_BOUNDARIES.md)。

主要 Web 代码入口：

- `web/api/review.py`：外部同步审查 API。
- `web/user/routes.py`：普通用户登录后工作台、上传、下载和历史页面。
- `web/admin/routes.py`：管理员后台路由。
- `web/core/`：DOCX 校验、文件名处理、错误类型和共享运行时对象。

用户登录后，服务会：

1. 将上传合同保存到 `data/<username>/contracts/`
2. 如果本次上传了审查要点，则先校验 DOCX 内容是否包含编号审查要点，通过后使用本次上传的 DOCX；否则使用 `data/<username>/contract_review_criteria/criteria.docx`
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
  - ./user_profiles:/app/user_profiles
  # 可选：自定义新用户默认审查要点模板
  # - ./resources/review_criteria/criteria.docx:/app/resources/review_criteria/criteria.docx:ro
```

`user_profiles/` 可以是空目录。程序首次创建用户时会自动写入 `user_profiles/users.json`。

当前 compose 中容器内部 Uvicorn 监听 `8000`，宿主机端口映射为：

```yaml
ports:
  - "0.0.0.0:5000:8000"
```

访问：

```text
http://服务器IP:5000
```

如果只允许服务器本机访问，可以改成：

```yaml
ports:
  - "127.0.0.1:5000:8000"
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
EMBED_API_KEY=...
RERANK_API_KEY=...
MINERU_API_KEY=...
SESSION_SECRET_KEY=replace-with-a-long-random-secret
```
