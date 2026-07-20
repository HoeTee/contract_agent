# 前端用户旅程

本文说明普通用户在 Web 前端中的页面流转、任务状态和页面状态边界。

## 主流程

```text
GET /web
  -> 清理一次性页面提示
  -> 清理已有 auth_contexts
  -> 渲染 login.html

POST /web/login
  -> 校验租户、用户和密码
  -> 登录成功后清理一次性页面提示
  -> 创建新的 ctx
  -> 管理员进入 /web/admin
  -> 普通用户进入 /web/work

GET /web/work
  -> 从 data/web/<tenant_id>/ 读取当前用户最新 Web 任务
  -> 没有 pending/queued/running 任务时显示上传表单
  -> 有活动任务时显示当前任务状态
  -> 最新任务成功时显示下载入口

POST /web/review
  -> 校验合同 DOCX
  -> 如果上传了本次审查要点，则校验审查要点 DOCX
  -> 在 data/web/<tenant_id>/<task_id>/ 创建 task.json
  -> 派发共享 review worker
  -> 重定向回 /web/work
```

## 任务状态

Web 不再使用进程内 `review_tasks` 字典作为状态源。Web 任务存储在：

```text
data/web/<tenant_id>/<task_id>/task.json
```

Web 路由使用与 API 一致的 worker 和状态模型：

```text
pending
  -> queued
  -> running
  -> succeeded

pending/queued/running
  -> failed
```

API 和 Web 存储保持分离：

```text
data/api/<task_id>/
data/web/<tenant_id>/<task_id>/
```

`task.json` 是任务全生命周期的状态文件。Web 路由提交任务后不能用单独的 history-only 记录覆盖它；审查成功后，只能把 `/web/history` 展示所需字段合并到同一个 `task.json` 中。

## 日志

Web 审查任务通过共享 task-store 日志工具写入事件日志。日志位置：

```text
data/web/<tenant_id>/<task_id>/logs/api_events.jsonl
```

模型调用错误使用与 API 任务一致的事件码和 component。

## 登录状态

上传错误、设置错误、管理端提示等一次性页面提示保存在 session 中。进入 `/web`、进入 `/web/login`、退出登录或登录成功时，必须清理这些一次性提示，保证新登录从初始化页面状态开始。当前登录提交失败产生的登录校验错误，仍然直接渲染在 `login.html` 上。

进入 `/web` 或 `/web/login` 也会清理已有 `auth_contexts`。用户主动回到登录入口后，旧的 workbench URL 和旧 `ctx` 不能继续有效。

每次成功登录都会创建新的 `ctx`，并记录自己的 `login_created_at`。`/web/work` 不显示该登录时间之前创建的 failed 任务错误。旧 failed 任务仍保留在任务存储和历史记录中，用于审计和排障，但不能污染新登录后的工作台。

## 前端状态约束

Web UI 必须区分“持久化审计数据”和“当前页面状态”：

- 新登录必须渲染初始化的工作台。历史失败任务可以保留在 `data/web/<tenant_id>/<task_id>/task.json` 中，但不能作为当前页面错误重新出现，除非该失败任务是在当前登录上下文中创建的。
- Flash 消息是一次性页面状态。它可以跨同一工作流中的一次重定向，但进入 `/web`、进入 `/web/login`、退出登录或登录成功后必须清理。
- 回到登录入口是 reset boundary。必须让旧 `ctx` 失效，避免旧标签页在重新登录后继续渲染旧工作台状态。
- 用户开始新的登录上下文后，failed 任务属于审计记录。它可以出现在历史和日志中，但不能阻塞新上传，也不能让工作台看起来一打开就处于错误状态。
- running 类任务和历史 failed 任务不同。同一用户同一租户下如果存在 pending、queued 或 running 任务，仍应显示活动任务状态，并阻止重复提交。
- pending、queued、running 只表示当前服务进程内仍有 worker 负责该任务。服务启动时，后端会扫描遗留的 pending、queued、running，并收敛为 `failed / WORKER_INTERRUPTED`；前端只读取收敛后的 `task.json`，不再自行猜测 stale 状态。
- 不要直接根据“最新任务”推导当前 UI 报错。必须同时检查任务状态和登录上下文，否则旧 failed 任务会让后续每次登录都像失败状态。

## 上传规则

- 合同文件必传。
- 合同文件必须是 DOCX。
- 审查要点文件可选。
- 如果上传审查要点，文件必须是 DOCX，并且必须通过审查要点内容校验。
- 如果不上传审查要点，使用该用户默认审查要点。

## 结果下载

成功的 Web 审查会从 `data/web/<tenant_id>/*/task.json` 展示在历史页面中。下载时根据这些任务记录解析 `data/web/<tenant_id>/<task_id>/output/` 下的结果文件。
