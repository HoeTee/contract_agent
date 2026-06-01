# 项目结构

```text
deep_research_agent/
  README.md
  app.py
  main.py
  config.py
  users.example.json
  users.json

  agents/
  main_workflow/
  mcp_service/
  tools/
  scripts/
    manage_users.py

  resources/
    review_criteria/
      criteria.docx

  loggers/
    resolve_review_task_paths.py
    workflow_logger.py
    agent_logger.py
    mcp_logger.py
    api_event_logger.py
    review_history.py

  web/
    admin_routes.py
    admin_services.py
    auth.py
    routes.py
    templates/
    static/

  docs/
    LOGGER_DESIGN.md
    USER_MANAGEMENT.md
    PROJECT_STRUCTURE.md
    DEPLOYMENT.md
    QUICK_START.md

  data/
    <username>/
      contract_review_criteria/
      institutional_docs/
      contracts/
      reports_docx/
      records/
      logs/
```

## 入口文件

- `app.py`：FastAPI Web 服务入口，负责创建应用、启用 session middleware、挂载静态文件和注册路由。
- `main.py`：本地 CLI 审查入口，按用户分区读取合同和审查要点。
- `config.py`：集中读取项目路径和环境变量，包括系统默认审查要点路径。

## Web 目录

- `web/routes.py`：登录、工作台、上传审查、历史记录、下载等 Web 路由。
- `web/auth.py`：用户读取、密码哈希、登录校验。
- `web/templates/`：HTML 模板。
- `web/static/`：CSS 和前端脚本。

## 数据目录

`data/` 是运行时持久化目录，按用户名分区：

```text
data/<username>/
  contract_review_criteria/
  institutional_docs/
  contracts/
  reports_docx/
  records/
  logs/
```

- `contract_review_criteria/`：该用户的默认审查要点，默认文件名为 `criteria.docx`。
- `institutional_docs/`：该用户的制度文档预留目录。
- `contracts/`：上传合同原件。
- `reports_docx/`：批注版合同输出。
- `records/`：跨任务结构化记录，当前存放 `review_history.json`，用于历史记录页面。
- `logs/`：审查任务日志。

## 资源目录

`resources/review_criteria/criteria.docx` 是系统默认审查要点模板。创建用户目录时，程序会把它复制到 `data/<username>/contract_review_criteria/criteria.docx`。

## 文档目录

`docs/` 只用于存放 Markdown 文档，不作为程序运行时输入或输出目录。
