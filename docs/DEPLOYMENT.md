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
config.yaml
user_profiles/
data/
```

当前 `docker-compose.yaml` 会把 `.env`、`user_profiles/` 和 `data/` 挂载进容器：

```yaml
volumes:
  - ./.env:/app/.env:ro
  - ./config.yaml:/app/config.yaml:ro
  - ./user_profiles:/app/user_profiles
  - ./data:/app/data
```

`user_profiles/` 可以是空目录。首次创建用户时，程序会自动生成：

```text
user_profiles/users.json
```

`user_profiles/` 需要可写挂载，因为管理员后台和 CLI 会创建账号，普通用户也可以在前端修改显示名称。

用户运行数据会被挂载到容器中：

```yaml
- ./data:/app/data
```

如果从旧部署迁移，原来的 `users.json` 需要手动移动到：

```text
user_profiles/users.json
```

也可以在 `config.yaml` 中设置 `storage.users_file` 临时兼容旧路径，但新部署推荐使用 `user_profiles/` 目录挂载。

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
