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

当前 `docker-compose.yaml` 会把 `.env`、`users.json` 和 `data/` 挂载进容器：

```yaml
volumes:
  - ./.env:/app/.env:ro
  - ./users.json:/app/users.json
  - ./data:/app/data
```

`users.json` 会被挂载到容器中：

```yaml
- ./users.json:/app/users.json
```

`users.json` 需要可写挂载，因为前端支持用户修改显示名称。

用户运行数据会被挂载到容器中：

```yaml
- ./data:/app/data
```

如果希望账号 JSON 也放入统一数据挂载目录，可以把 `.env` 中的 `USERS_FILE` 设置为 `/app/data/users.json`，并相应移除单独的 `users.json` 挂载。当前仓库默认 compose 仍使用 `/app/users.json`。

如果要自定义新用户默认审查要点模板，可以挂载单个文件：

```yaml
- ./criteria.docx:/app/resources/review_criteria/criteria.docx:ro
```

不要挂载空的 `resources/review_criteria/` 目录覆盖容器内默认模板，除非宿主机目录中已经有 `criteria.docx`。

## 端口说明

当前 compose 命令让容器内部服务监听：

```text
0.0.0.0:8000
```

`docker-compose.yaml` 中的端口映射决定外部如何访问。例如：

```yaml
ports:
  - "0.0.0.0:5000:8000"
```

表示允许通过服务器 5000 端口访问：

```text
http://服务器IP:5000
```

如果只允许服务器本机访问，需要改为：

```yaml
ports:
  - "127.0.0.1:5000:8000"
```

然后访问：

```text
http://127.0.0.1:5000
```

## 健康检查

```text
http://127.0.0.1:5000/health
```

容器内部健康检查访问的是 `http://127.0.0.1:8000/health`，这是容器内端口，不是宿主机端口。
