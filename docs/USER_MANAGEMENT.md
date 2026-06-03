# 用户管理

本文是项目用户管理专题文档，覆盖普通用户界面、管理员界面、后端数据、审查要点、CLI 和 Docker 部署落点。前端完整用户旅程、页面状态和多标签页行为见 `docs/FRONTEND_USER_JOURNEY.md`。

## 角色和入口

当前系统支持两类角色：

```text
user  普通用户
admin 管理员
```

角色定义在 `web/auth.py` 的 `VALID_ROLES` 中，实际值保存在用户账号 JSON 里。

前端入口：

```text
/login        登录页
/work         普通用户上传审核页
/history      普通用户审核历史页
/settings     普通用户设置页
/admin        管理员后台首页
/admin/users  管理员用户管理页
```

登录成功后：

- 普通用户进入 `/work`。
- 管理员进入 `/admin`。
- 管理员访问 `/work`、`/history`、`/settings` 会被重定向回 `/admin`。

## 普通用户前端

普通用户界面由 `web/routes.py` 提供路由，由 `web/templates/` 下的模板渲染。

### `/work`

模板：

```text
web/templates/index.html
```

能力：

- 上传合同 DOCX。
- 可选上传本次审查要点 DOCX。
- 如果本次不上传审查要点，则使用 `data/<username>/contract_review_criteria/criteria.docx`。
- 审核中会禁用提交按钮并定时刷新任务状态。
- 审核完成后提供批注版 DOCX 下载入口。

### `/history`

模板：

```text
web/templates/history.html
```

展示字段：

- 输入文件名
- 输入文件大小
- 上传时间
- 审查要点来源
- 输出文件名
- 输出文件大小
- 输出时间
- 下载入口

历史记录不是扫描目录生成，而是读取：

```text
data/<username>/records/review_history.json
```

读写逻辑在：

```text
loggers/review_history.py
```

### `/settings`

模板：

```text
web/templates/settings.html
```

当前能力：

- 查看用户名。
- 修改显示名称 `display_name`。

显示名称写回账号 JSON，不改变用户目录名。用户目录分区始终使用 `username`。

## 管理员前端

管理员后台路由在：

```text
web/admin_routes.py
```

后台数据聚合在：

```text
web/admin_services.py
```

模板：

```text
web/templates/admin_dashboard.html
web/templates/admin_users.html
web/templates/admin_user_detail.html
```

### `/admin`

展示运行摘要：

- 用户总数
- 管理员数量
- 禁用用户数量
- 成功审查数量
- 最近有审查记录的用户

这些数据来自账号 JSON 和各用户的 `records/review_history.json`。

### `/admin/users`

管理员可以：

- 创建用户
- 设置初始密码
- 设置显示名称
- 设置角色 `user` 或 `admin`
- 查看全部用户
- 进入用户详情页

创建用户时会同时初始化用户数据目录，并复制系统默认审查要点。

### `/admin/users/{username}`

管理员可以：

- 修改用户角色
- 重置用户密码
- 启用用户
- 禁用用户
- 删除用户
- 删除用户时选择是否保留用户数据目录
- 下载用户默认审查要点
- 上传覆盖用户默认审查要点
- 恢复系统默认审查要点
- 查看该用户审核历史
- 查看该用户日志目录和 API 事件

删除用户有前端二次确认，逻辑在：

```text
web/static/app.js
```

后端保护：

- 管理员不能禁用当前登录的自己。
- 管理员不能删除当前登录的自己。
- 管理员不能移除自己的管理员角色。

## 后端账号数据

账号数据路径由 `config.py` 中的 `USERS_FILE` 决定。

默认值：

```text
<PROJECT_ROOT>/user_profiles/users.json
```

可以通过环境变量覆盖：

```env
USERS_FILE=/app/user_profiles/users.json
```

账号 JSON 结构：

```json
{
  "users": [
    {
      "username": "user001",
      "password_hash": "pbkdf2_sha256$...",
      "display_name": "张三",
      "role": "user",
      "enabled": true,
      "created_at": "2026-06-01 12:00:00"
    }
  ]
}
```

字段说明：

```text
username             登录用户名，也是用户数据目录名
password_hash        PBKDF2 密码哈希，不保存明文密码
display_name         前端展示名称
role                 user 或 admin
enabled              是否允许登录
created_at           创建时间
role_updated_at      角色更新时间
password_updated_at  密码更新时间
enabled_at           启用时间
disabled_at          禁用时间
```

禁用用户后，登录页会显示：

```text
账号已被禁用，请联系管理员。
```

只有用户名存在、密码正确、但 `enabled=false` 时才显示禁用提示。用户名不存在或密码错误时显示用户名或密码错误。

## 用户数据目录

用户数据根目录由 `config.py` 中的 `DATA_DIR` 决定。

默认值：

```text
<PROJECT_ROOT>/data
```

可以通过环境变量覆盖：

```env
DATA_DIR=/app/data
```

创建用户后会生成：

```text
data/<username>/
  contract_review_criteria/
    criteria.docx
  institutional_docs/
  contracts/
  reports_docx/
  records/
    review_history.json
  logs/
```

目录初始化逻辑在：

```text
loggers/resolve_review_task_paths.py
```

## 审查要点

系统默认审查要点模板：

```text
resources/review_criteria/criteria.docx
```

新建用户时，程序会复制它到：

```text
data/<username>/contract_review_criteria/criteria.docx
```

普通用户在 `/work` 上传的审查要点只用于本次任务。管理员在用户详情页上传的审查要点会覆盖该用户默认文件：

```text
data/<username>/contract_review_criteria/criteria.docx
```

审查要点上传前会做 DOCX 格式检查和内容检查。内容检查逻辑在 `web/routes.py`，目标是拒绝明显不是审查要点的 DOCX。

## 共享用户管理服务

CLI 和管理员 Web 页面共用同一套用户管理逻辑：

```text
services/user_management.py
```

主要函数：

```text
create_user_account()   创建用户并初始化用户目录
set_user_role()         修改用户角色
reset_user_password()   重置密码
set_user_enabled()      启用或禁用用户
delete_user_account()   删除用户账号，可选删除用户目录
```

这些函数会写入或更新 `USERS_FILE`，并按需要创建或删除 `DATA_DIR/<username>`。

## CLI

CLI 文件：

```text
scripts/manage_users.py
```

查看帮助：

```powershell
python scripts/manage_users.py --help
```

创建普通用户：

```powershell
python scripts/manage_users.py create --username user001 --password Abc123456 --display-name 张三
```

创建管理员：

```powershell
python scripts/manage_users.py create --username admin --password Admin123456 --display-name 管理员 --role admin
```

修改角色：

```powershell
python scripts/manage_users.py set-role --username user001 --role admin
python scripts/manage_users.py set-role --username user001 --role user
```

重置密码：

```powershell
python scripts/manage_users.py reset-password --username user001 --password NewPass123
```

禁用或启用用户：

```powershell
python scripts/manage_users.py disable --username user001
python scripts/manage_users.py enable --username user001
```

删除账号但保留用户数据目录：

```powershell
python scripts/manage_users.py delete --username user001 --keep-data
```

删除账号并删除用户数据目录：

```powershell
python scripts/manage_users.py delete --username user001
```

删除目录前，后端会检查目标路径必须位于 `DATA_DIR` 内，避免误删不安全路径。

## 登录态与 Session

Web 界面使用带签名的 session cookie 保持用户身份。

`app.py` 中启用 `SessionMiddleware`：

```python
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    session_cookie="contract_review_session",
    max_age=None,
)
```

登录成功后，`web/routes.py` 会写入：

```python
request.session["username"] = user["username"]
request.session["display_name"] = user.get("display_name") or user["username"]
request.session["role"] = normalize_role(user.get("role"))
```

文件存储和下载使用的用户名必须来自 session，不应来自用户提交的表单字段。

## Docker 部署落点

需要区分开发机、远端宿主机、正在运行的服务容器和临时管理容器。

当前仓库默认 `.env.example` 配置：

```env
DATA_DIR=data
USERS_FILE=user_profiles/users.json
```

当前 `docker-compose.yaml` 挂载后，容器内实际等价于：

```text
DATA_DIR=/app/data
USERS_FILE=/app/user_profiles/users.json
```

compose 挂载：

```yaml
volumes:
  - ./user_profiles:/app/user_profiles
  - ./data:/app/data
```

此时 Web 后台和 CLI 创建用户后，最终写到远端宿主机：

```text
./user_profiles/users.json
./data/<username>/
```

如果没有挂载 `DATA_DIR`，这些数据会写进服务容器内部文件系统，容器重建后有丢失风险。

如果从旧部署迁移，原来的 `users.json` 需要手动移动到：

```text
user_profiles/users.json
```

如果希望账号 JSON 放入统一数据挂载目录，可以设置：

```env
DATA_DIR=/app/data
USERS_FILE=/app/data/users.json
```

并把 compose 调整为只挂载总数据目录：

```yaml
volumes:
  - ./data:/app/data
```

如果要自定义新用户默认审查要点，可以挂载单个文件：

```yaml
volumes:
  - ./data:/app/data
  - ./criteria.docx:/app/resources/review_criteria/criteria.docx:ro
```

这样新建用户时复制出来的默认审查要点来自宿主机文件。

## 当前边界

当前用户管理仍是单租户用户体系：

- 所有用户共享一个 `USERS_FILE`。
- 用户之间通过 `DATA_DIR/<username>` 分区。
- 管理员是全局管理员，不是租户管理员。
- 还没有租户表或租户级权限模型。

后续进入租户阶段时，需要把账号数据和目录结构扩展为租户分区，例如：

```text
data/<tenant_id>/<username>/
```
