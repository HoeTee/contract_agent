# 部署说明

## 构建镜像

```powershell
.\protect\build.ps1 -Tag deep-research-agent:latest
```

脚本会生成一次性 32 字节 AES 密钥，通过 BuildKit secret 传入临时构建阶段，并在构建结束后删除临时密钥。正式镜像只包含原生 `/app/loader`、AES-GCM 加密的 `/app/code.bin` 和明确列出的运行资源；`docs/`、项目 `.py` 与明文项目 `.pyc` 均不会进入正式镜像。

构建后可验证保护边界：

```powershell
docker run --rm --entrypoint sh deep-research-agent:latest -c "find /app -type f -name '*.py'"
docker run --rm --entrypoint sh deep-research-agent:latest -c "find /app -type f -name '*.pyc'"
docker run --rm --entrypoint sh deep-research-agent:latest -c "test -x /app/loader && test -s /app/code.bin"
```

前两条命令应无输出，第三条命令应成功退出。第三方依赖安装在 `/usr/local/lib/python3.12/site-packages/`，其中仍可能包含公开依赖自己的 `.py` 和 `.pyc`。

如需使用固定密钥，密钥文件必须是原始 32 字节数据，并放在项目目录之外：

```powershell
.\protect\build.ps1 -Tag deep-research-agent:latest -KeyFile C:\secure\lexora-aes.key
```

## 启动服务

```powershell
docker compose up -d
```

API、Celery worker 和本地 MCP 子进程均通过 `/app/loader -m ...` 启动。loader 在内存中解密代码包，不会把项目 `.pyc` 写回容器文件系统。

## 服务器上必须准备的文件和目录

```text
.env
config.yaml
agents/prompts/cn_prompts.yaml
profiles/
data/
```

当前 `docker-compose.yaml` 会把 `.env`、`profiles/` 和 `data/` 挂载进容器：

```yaml
volumes:
  - ./.env:/app/.env:ro
  - ./config.yaml:/app/config.yaml:ro
  - ./agents/prompts/cn_prompts.yaml:/app/agents/prompts/cn_prompts.yaml:ro
  - ./profiles:/app/profiles
  - ./data:/app/data
```

Prompt YAML 在 Web 和 Celery worker 启动导入模块时读取。修改该文件后，需要重启 API 服务和所有 worker 才会生效。

`profiles/` 可以是空目录。首次创建用户时，程序会自动生成：

```text
profiles/users.json
```

`profiles/` 需要可写挂载，因为管理员后台和 CLI 会创建账号，普通用户也可以在前端修改显示名称。

用户运行数据会被挂载到容器中：

```yaml
- ./data:/app/data
```

如果从旧部署迁移，原来的 `users.json` 需要手动移动到：

```text
profiles/users.json
```

`users_file` 不再通过 `config.yaml` 配置；请将旧用户数据移动到 `profiles/users.json`。

如果要自定义新用户默认审查要点模板，可以挂载单个文件：

```yaml
- ./criteria.docx:/app/resources/criteria/criteria.docx:ro
```

不要挂载空的 `resources/criteria/` 目录覆盖容器内默认模板，除非宿主机目录中已经有 `criteria.docx`。

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

## Queue worker

如果 `queue.enabled=true`，部署时必须在 API 服务之外同时启动 Redis 和 Celery worker。Redis 不会随 `uvicorn` 自动启动；worker 也不是 API 进程的一部分。

这里的关键边界是进程隔离：API 容器负责 HTTP 请求和状态读取，worker 容器负责 workflow、MCP、LLM 调用、DOCX 生成和日志写入。`/status` 不应和审查执行任务运行在同一个 API 进程中。

Celery task、Redis broker 和 worker 进程的区别见 `docs/QUEUE_WORKER.md`。

容器内部配置应使用 Redis service 名称，不要使用 `localhost`：

```yaml
queue:
  enabled: true
  broker_url: "redis://redis:6379/0"
```

运行时至少包含：

```text
redis
api
review-worker
```
