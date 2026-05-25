# 用户管理

用户账号存储在项目根目录的 `users.json` 中。

密码不保存明文。服务只保存 PBKDF2 密码哈希。如果用户忘记密码，管理员只能重置为一个新密码，不能从哈希中找回原密码。

## 创建用户

```powershell
python scripts/manage_users.py create --username user001 --password Abc123456 --display-name ZhangSan
```

脚本会创建：

```text
data/user001/
  contract_review_criteria/
  institutional_docs/
  contracts/
  reports_docx/
  logs/
```

如果用户名已经存在，脚本会报错并退出，不会覆盖原用户。

## 重置密码

```powershell
python scripts/manage_users.py reset-password --username user001 --password NewPass123
```

## 禁用或启用用户

```powershell
python scripts/manage_users.py disable --username user001
python scripts/manage_users.py enable --username user001
```

## 登录态与 Session

Web 界面使用带签名的 session cookie 在多次请求之间保持用户身份。

`app.py` 中启用 `SessionMiddleware`：

```python
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    session_cookie="contract_review_session",
    max_age=None,
)
```

`POST /login` 登录成功后，`web/routes.py` 会把认证通过的用户写入 session：

```python
request.session["username"] = user["username"]
request.session["display_name"] = user.get("display_name") or user["username"]
```

`SessionMiddleware` 会将这份 session 数据签名后写入浏览器的 `contract_review_session` cookie。之后浏览器访问 `/work`、`/review`、`/history`、`/download/...` 时会自动携带这个 cookie。服务端再从 cookie 还原 `request.session`，并读取：

```python
username = request.session.get("username")
```

这个 `username` 是可信的用户分区依据，用于：

```text
data/<username>/contracts/
data/<username>/reports_docx/
data/<username>/logs/
data/<username>/contract_review_criteria/criteria.docx
```

所有用户使用相同的 cookie 名 `contract_review_session`，但每个浏览器会话中的 cookie 值不同。因此多个用户同时登录不会共享同一份 session。每个请求都会从自己携带的签名 cookie 还原出自己的 `request.session`。

不要把上传或下载表单里用户可控的 `username` 当成文件访问依据。存储和下载使用的用户名必须来自 `request.session`。

## 审查要点

每个用户都需要一个审查要点文件：

```text
data/<username>/contract_review_criteria/criteria.docx
```

## 制度文档

如果后续启用制度文档检索，每个用户的制度文档应放在：

```text
data/<username>/institutional_docs/
```
