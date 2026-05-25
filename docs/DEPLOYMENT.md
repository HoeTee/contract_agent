# 部署说明

## 构建镜像

```powershell
docker build -t deep-research-agent:latest .
```

## 启动服务

```powershell
docker compose up -d
```

## 服务器上必须准备的文件和目录

```text
.env
users.json
data/
```

`users.json` 会被挂载到容器中：

```yaml
- ./users.json:/app/users.json:ro
```

用户运行数据会被挂载到容器中：

```yaml
- ./data:/app/data
```

## 端口说明

容器内部服务监听：

```text
0.0.0.0:5000
```

`docker-compose.yaml` 中的端口映射决定外部如何访问。例如：

```yaml
ports:
  - "127.0.0.1:8000:5000"
```

表示只允许服务器本机通过下面地址访问：

```text
http://127.0.0.1:8000
```

如果需要让其他机器访问服务器 IP，需要改为：

```yaml
ports:
  - "8000:5000"
```

然后访问：

```text
http://服务器IP:8000
```

## 健康检查

```text
http://127.0.0.1:8000/health
```
