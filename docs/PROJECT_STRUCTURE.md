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

## HTTP endpoints 目录

- `endpoints/api/review.py`：无 Cookie 同步 API，提供 `POST /api/review`。
- `endpoints/api/review_jobs.py`：无 Cookie 异步任务 API，提供提交、查询、下载、取消任务节点。
- `endpoints/api/support/task_store.py`：读写 `data/api/<task_id>/task.json`，并统一处理 input/output/logs 路径与写入策略。
- `endpoints/api/support/review_meta.py`：解析直接 API 的 meta fields，并生成响应 header。
- `endpoints/api/support/review_job_worker.py`：执行异步审核后台任务。
- `endpoints/api/support/callbacks.py`：同步 API 的 callback helper；异步主流程不依赖 callback。
- `endpoints/web/user_routes.py`：前端用户页面和表单路由，URL 统一以 `/web` 开头。
- `endpoints/web/admin_routes.py`：管理端页面和表单路由，URL 统一以 `/web/admin` 开头。
- `endpoints/web/admin_services.py`：管理端展示所需的数据聚合。
- `endpoints/runtime/`：endpoints 层运行时支撑，包括认证、DOCX 校验、文件名、错误类型和并发控制。

## Frontend 目录

- `frontend/templates/`：HTML 模板。
- `frontend/static/`：CSS 和前端脚本。

异步 API 的详细设计见 `docs/ASYNC_REVIEW_API.md`。

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
