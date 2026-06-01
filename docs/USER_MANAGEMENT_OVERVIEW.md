# 用户管理专题说明

本文说明当前项目的用户管理设计，包括普通用户前端、管理员前端、后端数据存储、审查要点管理、登录态、CLI 管理能力，以及 Docker 部署时的数据落点。

## 1. 用户角色和入口

当前系统支持两类角色：

```text
user  普通用户
admin 管理员
```

角色定义在 `web/auth.py` 的 `VALID_ROLES` 中。角色值会保存在用户账号 JSON 里。

前端入口：

```text
/login    登录页
/work     普通用户上传审核页
/history  普通用户审核历史页
/settings 普通用户设置页
/admin    管理员后台首页
/admin/users 管理员用户管理页
```

登录成功后：

- 普通用户进入 `/work`。
- 管理员进入 `/admin`。
- 管理员访问 `/work`、`/history`、`/settings` 会被重定向回 `/admin`。

## 2. 普通用户前端界面

普通用户主要使用三个页面。

### 2.1 上传审核页 `/work`

模板文件：

```text
web/templates/index.html
```

页面能力：

- 上传合同 DOCX 文件。
- 可选上传本次审查要点 DOCX 文件。
- 如果本次不上传审查要点，则使用用户目录下的默认审查要点。
- 有正在审核任务时，表单按钮会禁用并轮询刷新页面。
- 审核完成后提供下载批注合同入口。

相关后端路由主要在：

```text
web/routes.py
```

### 2.2 审核历史页 `/history`

模板文件：

```text
web/templates/history.html
```

页面展示：

- 输入文件名
- 输入文件大小
- 上传时间
- 审查要点来源
- 输出文件名
- 输出文件大小
- 输出时间
- 下载入口

历史记录来源不是扫描文件名，而是读取：

```text
data/<username>/records/review_history.json
```

历史记录由 `loggers/review_history.py` 读写。

### 2.3 用户设置页 `/settings`

模板文件：

```text
web/templates/settings.html
```

当前能力：

- 查看用户名。
- 修改显示名称 `display_name`。

显示名称写回用户账号 JSON，不会改变用户目录名。用户目录分区仍然使用 `username`。

## 3. 管理员前端界面

管理员后台入口：

```text
/admin
```

模板文件：

```text
web/templates/admin_dashboard.html
web/templates/admin_users.html
web/templates/admin_user_detail.html
```

路由文件：

```text
web/admin_routes.py
```

### 3.1 后台首页 `/admin`

展示系统摘要：

- 用户总数
- 管理员数量
- 禁用用户数量
- 成功审查数量
- 最近有审查记录的用户

数据来自 `web/admin_services.py`，它读取用户账号 JSON 和各用户的历史记录 JSON。

### 3.2 用户管理页 `/admin/users`

管理员可以：

- 创建用户
- 设置初始密码
- 设置显示名称
- 选择角色 `user` 或 `admin`
- 查看所有用户列表
- 进入用户详情页

创建用户时会同时初始化用户目录和默认审查要点。

### 3.3 用户详情页 `/admin/users/{username}`

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

删除用户有前端二次确认，绑定在：

```text
web/static/app.js
```

后端仍会做保护：

- 管理员不能禁用当前登录的自己。
- 管理员不能删除当前登录的自己。
- 管理员不能移除自己的管理员角色。

## 4. 后端账号数据

账号数据默认写在：

```text
users.json
```

实际路径由 `config.py` 中的 `USERS_FILE` 决定：

```text
USERS_FILE=<绝对路径或相对项目根目录的路径>
```

如果没有设置环境变量，默认是：

```text
<PROJECT_ROOT>/users.json
```

账号 JSON 的结构类似：

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
username         登录用户名，也是用户数据目录名
password_hash    PBKDF2 密码哈希，不保存明文密码
display_name     前端展示名称
role             user 或 admin
enabled          是否允许登录
created_at       创建时间
role_updated_at  角色更新时间
password_updated_at 密码更新时间
enabled_at       启用时间
disabled_at      禁用时间
```

禁用用户后，登录页会提示：

```text
账号已被禁用，请联系管理员。
```

这个判断在 `web/routes.py` 登录路由中完成：只有用户名存在、密码正确、但 `enabled=false` 时才显示禁用提示。用户名不存在或密码错误时仍显示用户名或密码错误。

## 5. 用户数据目录

用户数据根目录由 `config.py` 中的 `DATA_DIR` 决定：

```text
DATA_DIR=<绝对路径或相对项目根目录的路径>
```

如果没有设置环境变量，默认是：

```text
<PROJECT_ROOT>/data
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

目录初始化由：

```text
loggers/resolve_review_task_paths.py
```

中的 `initialize_user_data_dir()` 完成。

## 6. 审查要点管理

系统默认审查要点模板在：

```text
resources/review_criteria/criteria.docx
```

配置项：

```text
DEFAULT_REVIEW_CRITERIA_PATH=<PROJECT_ROOT>/resources/review_criteria/criteria.docx
```

新建用户时，系统会把默认模板复制到：

```text
data/<username>/contract_review_criteria/criteria.docx
```

普通用户上传合同时可以临时上传本次审查要点。管理员在用户详情页上传审查要点时，会覆盖该用户默认文件：

```text
data/<username>/contract_review_criteria/criteria.docx
```

审查要点上传前会做 DOCX 格式检查和内容检查。内容检查逻辑在：

```text
web/routes.py
```

核心目标是防止把明显不是审查要点的 DOCX 当成审查要点使用。

## 7. 共享用户管理服务

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

这些函数的输入主要是 `username`、`password`、`display_name`、`role`、`enabled`、`keep_data`。

输出和副作用：

- 写入或更新 `USERS_FILE`。
- 创建或删除 `DATA_DIR/<username>`。
- 抛出 `UserManagementError` 返回中文错误信息。

## 8. CLI 用户管理

CLI 文件：

```text
scripts/manage_users.py
```

查看帮助：

```powershell
python scripts/manage_users.py --help
```

### 8.1 创建普通用户

```powershell
python scripts/manage_users.py create --username user001 --password Abc123456 --display-name 张三
```

### 8.2 创建管理员

```powershell
python scripts/manage_users.py create --username admin --password Admin123456 --display-name 管理员 --role admin
```

### 8.3 修改角色

```powershell
python scripts/manage_users.py set-role --username user001 --role admin
python scripts/manage_users.py set-role --username user001 --role user
```

### 8.4 重置密码

```powershell
python scripts/manage_users.py reset-password --username user001 --password NewPass123
```

### 8.5 禁用或启用用户

```powershell
python scripts/manage_users.py disable --username user001
python scripts/manage_users.py enable --username user001
```

禁用用户不会删除账号，也不会删除用户目录。禁用后，该用户不能继续登录；如果用户已经登录，前端会通过 session 检查退出到登录页。

### 8.6 删除用户

删除账号但保留数据目录：

```powershell
python scripts/manage_users.py delete --username user001 --keep-data
```

删除账号并删除用户数据目录：

```powershell
python scripts/manage_users.py delete --username user001
```

删除目录前，后端会检查目标路径必须位于 `DATA_DIR` 内，避免误删不安全路径。

## 9. Docker 部署时的数据落点

需要区分四个位置：

```text
开发机
远端宿主机
正在运行的服务容器
临时管理容器
```

如果服务容器中配置：

```text
DATA_DIR=/app/data
USERS_FILE=/app/data/users.json
```

并且 compose 挂载：

```yaml
volumes:
  - ./data:/app/data
```

那么 Web 后台和 CLI 创建用户后，最终写到远端宿主机：

```text
./data/users.json
./data/<username>/
```

如果没有挂载 `DATA_DIR`，这些数据会写进服务容器内部文件系统，容器重建后有丢失风险。

如果要自定义新用户默认审查要点，可以挂载单个文件：

```yaml
volumes:
  - ./data:/app/data
  - ./criteria.docx:/app/resources/review_criteria/criteria.docx:ro
```

这样新建用户时复制出来的默认审查要点来自宿主机文件。

## 10. 当前边界

当前用户管理仍是单租户用户体系：

- 所有用户共享一个 `USERS_FILE`。
- 用户之间通过 `DATA_DIR/<username>` 分区。
- 还没有租户表或租户级权限模型。
- 管理员是全局管理员，不是租户管理员。

后续如果进入租户阶段，需要在账号数据中增加租户字段，并把数据目录调整为类似：

```text
data/<tenant_id>/<username>/
```
