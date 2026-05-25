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

如果用户已经存在，可以重置密码：

```powershell
python scripts/manage_users.py reset-password --username testuser --password Test123456
```

## 3. 放置审查要点

将审查要点 DOCX 放到：

```text
data/testuser/contract_review_criteria/criteria.docx
```

文件名必须是：

```text
criteria.docx
```

## 4. 启动 Web 服务

```powershell
uvicorn app:app --host 0.0.0.0 --port 5000
```

本机浏览器访问：

```text
http://127.0.0.1:5000
```

登录信息：

```text
username: testuser
password: Test123456
```

## 5. 上传合同

在页面中上传真实 `.docx` 合同文件。

审查成功后，服务会写入：

```text
data/testuser/contracts/
data/testuser/reports_docx/
data/testuser/logs/
```

页面会显示批注版 DOCX 的下载链接。

## 6. 使用 curl 测试

先保存登录 cookie：

```powershell
curl.exe -i -c cookies.txt http://127.0.0.1:5000/
```

登录：

```powershell
curl.exe -i -c cookies.txt -b cookies.txt `
  -X POST http://127.0.0.1:5000/login `
  -d "username=testuser" `
  -d "password=Test123456"
```

上传合同并触发审查：

```powershell
curl.exe -i -b cookies.txt `
  -F "file=@data/testuser/contracts/合同文件名.docx" `
  http://127.0.0.1:5000/review
```

`cookies.txt` 是 curl 用来模拟浏览器保存登录态的临时文件，正常 Web 运行时不会由程序生成这个文件。

## 7. Docker 冒烟测试

确认服务器上存在：

```text
.env
users.json
data/
```

构建并启动：

```powershell
docker build -t deep-research-agent:latest .
docker compose up -d
```

当前 compose 映射：

```text
http://127.0.0.1:8000
```

如果需要通过服务器 IP 对外访问，修改 `docker-compose.yaml`：

```yaml
ports:
  - "8000:5000"
```

然后访问：

```text
http://<server-ip>:8000
```

## 8. 预期输出

上传合同：

```text
data/testuser/contracts/<task_prefix>_<original_filename>.docx
```

批注结果：

```text
data/testuser/reports_docx/<task_prefix>_<contract_name>_批注版.docx
```

任务日志：

```text
data/testuser/logs/<YYYY-MM-DD>/<task>/
```
