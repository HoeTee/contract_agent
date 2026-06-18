# 项目结构

```text
deep_research_agent/
  README.md
  app.py
  main.py
  config.py
  user_profiles/
    users.json

  agents/
  main_workflow/
  mcp_service/
  tools/
  services/
    user_management.py
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
    api/
      review.py
      callbacks.py
    user/
      routes.py
    admin/
      routes.py
      services.py
    core/
      document_validation.py
      filenames.py
      review_runtime.py
      errors.py
    auth.py
    routes.py
    api_review_routes.py
    user_review_routes.py
    admin_routes.py
    admin_services.py
    templates/
    static/

  docs/
    API_REVIEW_ENDPOINT.md
    LOGGER_DESIGN.md
    USER_MANAGEMENT.md
    PROJECT_STRUCTURE.md
    DEPLOYMENT.md
    QUICK_START.md
    FRONTEND_USER_JOURNEY.md
    REVIEW_BOUNDARIES.md

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

- `web/api/review.py`：无登录、同步执行的外部 API 路由，当前提供 `POST /api/review`。
- `web/api/callbacks.py`：批注 DOCX 生成后的外部回调发送逻辑。
- `web/user/routes.py`：登录、工作台、上传审查、历史记录、下载和设置等普通用户路由。
- `web/admin/routes.py`：管理员后台路由，包括用户管理、审查要点管理和日志查看。
- `web/admin/services.py`：管理员后台展示所需的数据聚合。
- `web/core/document_validation.py`：DOCX 格式校验和审查要点内容校验。
- `web/core/filenames.py`：上传文件名清洗、批注文件展示名和任务前缀处理。
- `web/core/review_runtime.py`：审查并发控制等 Web 层共享运行时对象。
- `web/core/errors.py`：Web 层模型调用错误类型和分类函数。
- `web/auth.py`：用户读取、密码哈希、登录校验。
- `web/routes.py`、`web/api_review_routes.py`、`web/user_review_routes.py`、`web/admin_routes.py`、`web/admin_services.py`、`web/errors.py`、`web/route_helpers.py`：兼容旧 import 的薄封装，不再承载主要实现。
- `web/templates/`：HTML 模板。
- `web/static/`：CSS 和前端脚本。

## 服务模块

- `services/user_management.py`：Web 管理员后台和 `scripts/manage_users.py` 共用的用户管理服务，负责创建用户、修改角色、重置密码、启用/禁用、删除用户。
- `scripts/api_review_callback_receiver.py`：本地测试 `/api/review` 外部回调用的临时接收服务；只打印和返回字段/文件元信息，不保存回调 DOCX。

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

## 用户账号目录

`user_profiles/` 是用户账号持久化目录。默认账号文件为：

```text
user_profiles/users.json
```

该文件由程序在首次创建用户时自动生成，不应提交真实账号数据。

## 资源目录

`resources/review_criteria/criteria.docx` 是系统默认审查要点模板。创建用户目录时，程序会把它复制到 `data/<username>/contract_review_criteria/criteria.docx`。

## 文档目录

`docs/` 只用于存放 Markdown 文档，不作为程序运行时输入或输出目录。

直接 API 调用、错误类型和前端接口边界见 `docs/API_REVIEW_ENDPOINT.md`。
用户管理的完整说明见 `docs/USER_MANAGEMENT.md`。
前端用户旅程、页面状态和多标签页行为见 `docs/FRONTEND_USER_JOURNEY.md`。
合同审查边界、正文附件处理、兜底条款和外部数据限制见 `docs/REVIEW_BOUNDARIES.md`。
