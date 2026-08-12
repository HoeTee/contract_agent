# 快速启动

本文用于验证服务是否能端到端跑通。

## 1. 安装依赖

```powershell
pip install -r requirements.txt
```

## 2. 创建测试用户

```powershell
python scripts/manage_users.py create --username testuser --password Test123456 --display-name TestUser
```

创建用户时会自动初始化用户目录，并从 `resources/criteria/criteria.docx` 复制默认审查要点。

如果用户已经存在，可以重置密码：

```powershell
python scripts/manage_users.py reset-password --username testuser --password Test123456
```

## 3. 确认审查要点

默认审查要点应已经存在于：

```text
data/testuser/criteria/criteria.docx
```

如果要临时使用其他审查要点，可以在 `/work` 页面上传合同的同时上传本次审查要点；如果要修改该用户默认审查要点，可以用管理员后台进入用户详情页上传覆盖。

## 4. 创建管理员用户

```powershell
python scripts/manage_users.py create --username admin --password Admin123456 --display-name 管理员 --role admin
```

如果管理员已经存在，可以重置密码：

```powershell
python scripts/manage_users.py reset-password --username admin --password Admin123456
```

## 5. 启动 Web 服务

如果 `config.yaml` 中 `queue.enabled=true`，先启动 Redis。Redis 是独立服务，不会随 `uvicorn` 自动启动。

```powershell
redis-server
```

```powershell
uvicorn app:app --host 0.0.0.0 --port 5000
```

另开一个终端启动审查 worker：

```powershell
celery -A task_queue.celery_app:celery_app worker --loglevel=info --pool=solo
```

Windows 本地建议使用 `--pool=solo`。如果 `queue.enabled=false`，可以不启动 Redis 和 Celery worker，API 会回退到进程内后台任务。

本机浏览器访问：

```text
http://127.0.0.1:5000
```

登录信息：

```text
username: testuser
password: Test123456
```

管理员后台：

```text
http://127.0.0.1:5000/admin
```

## 6. 上传合同

在页面中上传真实 `.docx` 合同文件。

审查成功后，服务会写入：

```text
data/testuser/contracts/
data/testuser/reports_docx/
data/testuser/records/review_history.json
data/testuser/logs/
```

页面会显示批注版 DOCX 的下载链接。

前端完整用户旅程、页面状态和多标签页行为见 `docs/FRONTEND_USER_JOURNEY.md`。

## 7. 使用 curl 测试

先保存登录 cookie：

```powershell
$loginPage = Invoke-WebRequest -Uri http://127.0.0.1:5000/login -SessionVariable webSession
$loginToken = [regex]::Match($loginPage.Content, 'name="login_token" type="hidden" value="([^"]+)"').Groups[1].Value
```

登录：

```powershell
$loginResponse = Invoke-WebRequest `
  -Uri http://127.0.0.1:5000/login `
  -Method Post `
  -WebSession $webSession `
  -Body @{
    username = "testuser"
    password = "Test123456"
    login_token = $loginToken
  }
$ctx = [regex]::Match($loginResponse.Headers.Location, 'ctx=([^&]+)').Groups[1].Value
```

上传合同并触发审查：

```powershell
$form = @{
  file = Get-Item "data/testuser/contracts/合同文件名.docx"
}
Invoke-WebRequest `
  -Uri "http://127.0.0.1:5000/review?ctx=$ctx" `
  -Method Post `
  -WebSession $webSession `
  -Form $form
```

`$webSession` 是 PowerShell 用来模拟浏览器保存登录态的临时对象，正常 Web 运行时浏览器会自动保存和发送 cookie。

## 8. Docker 冒烟测试

确认服务器上存在：

```text
.env
config.yaml
profiles/
data/
```

`profiles/` 和 `data/` 都可以是空目录。首次创建用户时，程序会自动生成 `profiles/users.json`。

构建并启动：

```powershell
docker build -t deep-research-agent:latest .
docker compose up -d
```

当前 compose 映射：

```text
http://<server-ip>:5000
```

如果只允许服务器本机访问，修改 `docker-compose.yaml`：

```yaml
ports:
  - "127.0.0.1:5000:8000"
```

然后访问：

```text
http://127.0.0.1:5000
```

## 9. 预期输出

上传合同：

```text
data/testuser/contracts/<task_prefix>_<original_filename>.docx
```

批注结果：

```text
data/testuser/reports_docx/<task_prefix>_【已AI审查】<contract_name>.docx
```

任务日志：

```text
data/testuser/logs/<YYYY-MM-DD>/<task>/
```

历史索引：

```text
data/testuser/records/review_history.json
```
