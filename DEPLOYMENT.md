# Deep Research Agent 部署说明

## 1. 文档说明

本文档面向当前仓库的实际代码实现，覆盖以下内容：

- 本地开发部署
- 生产环境部署建议
- 环境变量说明
- API 与前端联调方式
- 常见故障排查

当前项目同时支持两种运行方式：

- Web 方式：`FastAPI + React`，适合日常使用和联调
- CLI 方式：直接运行 [`main.py`](./main.py)，适合本地调试工作流

## 2. 系统组成

项目由 4 个核心部分组成：

1. 前端：`frontend/`
   - 技术栈：React 18 + TypeScript + Vite
   - 本地开发默认地址：`http://localhost:5173`

2. 后端 API：`api/`
   - 技术栈：FastAPI
   - 默认地址：`http://localhost:8000`

3. 审查工作流：`main_workflow/` + `agents/`
   - 负责合同解析、任务规划、证据检索、审查、反思、报告汇总

4. MCP 服务：`mcp_service/`
   - 在 Web 模式下通过 `Streamable HTTP` 挂载到后端的 `/mcp`
   - 在 CLI 模式下由 [`main.py`](./main.py) 以本地脚本方式调用

## 3. 部署前要求

建议环境：

- Python 3.10 或以上
- Node.js 18 或以上
- `pip`
- `npm`

外部依赖：

- 一个 OpenAI 兼容的大模型接口
- 如需网页检索：Serper API Key
- 如需 MinerU 云解析：MinerU API Key

建议：

- 使用独立 Python 虚拟环境 `.venv`
- 前后端分开进程运行
- 生产环境通过反向代理统一入口

## 4. 环境变量

复制 `.env.example` 为 `.env`：

```powershell
Copy-Item .env.example .env
```

最常用配置如下。

### 4.1 必填配置

```env
# 主 LLM
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_NAME=qwen-plus

# 工作流数值配置
TEMPERATURE=0.0
TOP_P=0.01
SEED=42
MAX_REFLECTION_ROUNDS=3
```

说明：

- `LLM_*` 用于 Planner、Orchestrator、Reflector、Summarizer 等智能体调用
- 如果未正确配置，审查任务无法正常执行

### 4.2 检索模式配置

```env
# 默认检索策略
LLAMA_INDEX=False
PAGEINDEX_SEARCH=True
```

默认策略计算规则：

- `LLAMA_INDEX=True`：默认使用 `llamaindex`
- `LLAMA_INDEX=False` 且 `PAGEINDEX_SEARCH=True`：默认使用 `pageindex`
- `LLAMA_INDEX=False` 且 `PAGEINDEX_SEARCH=False`：默认使用 `evidence`

重要说明：

- `.env` 只决定“默认检索模式”
- 当前前端会显式提交 `retrieval_mode`
- 只要请求体里传了 `retrieval_mode`，就会覆盖 `.env` 默认值

### 4.3 LlamaIndex 相关配置

当你需要使用 `llamaindex` 模式时，建议同时配置：

```env
EMBED_API_KEY=your_api_key_here
EMBED_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBED_NAME=text-embedding-v4

RERANK_API_KEY=your_api_key_here
RERANK_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
RERANK_NAME=qwen3-rerank
```

说明：

- `EMBED_*` 用于向量化
- `RERANK_*` 用于重排，未配置时仍可运行，但召回质量可能下降

### 4.4 文件解析与外部搜索配置

```env
ENABLE_MCP_WEB_TOOLS=True
SERPER_API_KEY=your_api_key_here

PARSE_FILE_WITH_MINERU=True
MINERU_API_BASE=https://mineru.net
MINERU_API_KEY=your_api_key_here
```

说明：

- `ENABLE_MCP_WEB_TOOLS=True` 时，会注册 `web_search` 和 `read_url`
- `PARSE_FILE_WITH_MINERU=True` 时，解析链路优先走 MinerU
- 没有 `MINERU_API_KEY` 时，系统会回退到本地解析或 PDF 清洗回退逻辑

### 4.5 MCP 地址配置

```env
MCP_SERVER_URL=http://localhost:8000/mcp
```

说明：

- Web 模式下，后端工作流通过该地址访问 MCP 服务
- 当前代码里 MCP 路由实际挂载在 `/mcp`
- 如果后端端口、域名、容器地址发生变化，需要同步修改此变量

### 4.6 兼容性说明

当前 `tools/document/parsers/mineru_file_parser.py` 中的 PDF LLM 清洗回退逻辑读取的是 `API_KEY` 和 `BASE_URL`。如果你希望在“无 MinerU、但使用 LLM 清洗 PDF”这一分支下工作，建议额外补一组兼容变量：

```env
API_KEY=same_as_LLM_API_KEY
BASE_URL=same_as_LLM_BASE_URL
```

如果不配置这两个兼容变量，系统仍可回退到本地 PDF 提取，只是不会走该分支。

## 5. 本地开发部署

### 5.1 安装 Python 依赖

在项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

可选安装：

```powershell
python -m pip install -e .
```

### 5.2 启动后端

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

启动后可访问：

- 健康检查：`http://localhost:8000/health`
- Swagger：`http://localhost:8000/docs`
- MCP：`http://localhost:8000/mcp`

说明：

- 当前 Web 工作流使用 HTTP 方式访问 MCP，而不是再额外拉起一个独立脚本进程
- 因此部署时最关键的是 API 服务本身能稳定提供 `/mcp`

### 5.3 安装并启动前端

```powershell
cd frontend
npm install
npm run dev
```

默认访问地址：

`http://localhost:5173`

### 前端如何访问后端

本地开发默认有两种方式：

1. 推荐方式：不设置 `VITE_API_URL`
   - 依赖 Vite 代理将 `/api` 转发到 `http://localhost:8000`

2. 显式指定方式：在 `frontend/.env` 中写入

```env
VITE_API_URL=http://localhost:8000
```

### 5.4 本地联调顺序

建议按以下顺序启动：

1. 启动后端 `uvicorn`
2. 访问 `http://localhost:8000/health`
3. 启动前端 `npm run dev`
4. 在浏览器打开 `http://localhost:5173`

## 6. 生产环境部署建议

推荐拆成两个部署单元：

1. 后端 API 服务
2. 前端静态资源

### 6.1 后端部署

生产环境不建议使用 `--reload`：

```powershell
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

建议配合进程守护工具使用，例如：

- Linux：`systemd`、`supervisor`
- Windows：`NSSM`、任务计划程序、服务化脚本

关键点：

- `MCP_SERVER_URL` 必须指向当前后端可访问的 `/mcp`
- 后端需要能写入 `uploads/`、`docs/reports_*`、`logs/`、`RAG_persist/`

### 6.2 前端部署

在 `frontend/` 目录执行：

```powershell
npm ci
npm run build
```

构建产物位于：

`frontend/build`

你可以将该目录交给 Nginx、Caddy、静态文件服务器或对象存储/CDN 托管。

### 6.3 反向代理示例（Nginx）

如果你希望用户通过一个统一域名访问前后端，可参考以下配置：

```nginx
server {
    listen 80;
    server_name review.example.com;

    root /srv/deep_research_agent/frontend/build;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /health {
        proxy_pass http://127.0.0.1:8000;
    }

    location /docs {
        proxy_pass http://127.0.0.1:8000;
    }

    location /openapi.json {
        proxy_pass http://127.0.0.1:8000;
    }

    location /redoc {
        proxy_pass http://127.0.0.1:8000;
    }

    location /mcp {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

如果前端和后端分域名部署，则需要：

- 前端构建时配置正确的 `VITE_API_URL`
- 后端把 `MCP_SERVER_URL` 指向自己的实际可访问地址

## 7. API 说明

### 7.1 健康与文档

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 健康检查 |
| GET | `/docs` | Swagger UI |
| GET | `/redoc` | ReDoc |

### 7.2 上传接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/upload/contract` | 上传合同文件 |
| POST | `/api/v1/upload/criteria` | 上传审查标准文件 |

说明：

- 后端当前会直接保存上传文件
- 前端 UI 目前限制为 `.pdf`、`.docx`
- 后端上传接口本身没有做严格后缀强校验

### 7.3 审查任务接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/review/start` | 启动审查任务 |
| GET | `/api/v1/review/{task_id}` | 查询任务状态 |
| GET | `/api/v1/review/{task_id}/result` | 查询审查结果 |
| GET | `/api/v1/review/{task_id}/artifact/{artifact_type}` | 下载报告产物 |

其中 `artifact_type` 支持：

- `md`
- `docx`
- `pdf`

### 7.4 历史接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/history` | 获取历史任务列表 |
| GET | `/api/v1/history/{task_id}` | 获取单个历史任务 |

### 7.5 启动审查示例

```powershell
curl -X POST http://localhost:8000/api/v1/review/start `
  -H "Content-Type: application/json" `
  -d '{
    "contract_path": "C:/path/to/contract.docx",
    "criteria_path": "C:/path/to/criteria.docx",
    "retrieval_mode": "pageindex"
  }'
```

`retrieval_mode` 可选值：

- `llamaindex`
- `pageindex`
- `evidence`

如果不传该字段，后端会按 `.env` 中的检索开关推导默认模式。

### 7.6 任务阶段说明

`stage` 可能出现以下值：

- `queued`
- `ingesting`
- `building_index`
- `building_tree`
- `planning`
- `reviewing`
- `summarizing`
- `generating_report`
- `completed`
- `failed`

`status` 可能出现以下值：

- `pending`
- `processing`
- `completed`
- `failed`

## 8. 运行产物与目录

系统运行时会写入以下目录：

- `uploads/`
  - 上传的合同与审查标准文件

- `docs/reports_md/`
  - Markdown 报告

- `docs/reports_docx/`
  - DOCX 报告
  - 若合同原文件是 `.docx`，会优先尝试在原合同上写入审查批注

- `docs/reports_pdf/`
  - PDF 报告

- `logs/workflow/`
  - 工作流日志

- `logs/conversations/`
  - 智能体对话日志

- `logs/mcp/`
  - MCP 客户端日志

- `RAG_persist/`
  - PageIndex 树缓存、LlamaIndex 向量索引、manifest 文件

## 9. 常见问题

### 9.1 后端能启动，但发起审查时报模型或工具错误

优先检查：

1. `.env` 中的 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_NAME` 是否正确
2. 如果使用 `llamaindex`，`EMBED_*` 和 `RERANK_*` 是否已配置
3. `MCP_SERVER_URL` 是否仍然指向正确的 `/mcp`
4. `requirements.txt` 是否已完整安装

### 9.2 前端无法访问后端

检查项：

1. `http://localhost:8000/health` 是否可访问
2. 开发环境下是否误配了 `VITE_API_URL`
3. `frontend/vite.config.ts` 里的 `/api` 代理是否仍指向 `http://localhost:8000`

### 9.3 PDF 解析效果差或失败

检查项：

1. 是否配置了 `MINERU_API_KEY`
2. `PARSE_FILE_WITH_MINERU` 是否为 `True`
3. 如需走 PDF 的 LLM 清洗回退，是否补充了 `API_KEY` 和 `BASE_URL`
4. 如果以上都没有，系统会退回到本地 PDF 提取，效果可能不如 MinerU

### 9.4 LlamaIndex 模式不可用

检查项：

1. 是否安装了 `llama_index` 及相关依赖
2. `EMBED_*` 是否可用
3. `RERANK_*` 是否可用
4. 查看后端启动日志和 `logs/mcp/`

### 9.5 历史任务为什么会丢失

当前历史任务保存在内存中的 [`api/services/task_store.py`](./api/services/task_store.py)。后端重启后，历史列表会清空。这是当前实现限制，不是部署问题。

## 10. CLI 运行方式

如果你只想本地跑完整工作流，不经过 Web 前后端，可直接执行：

```powershell
.\.venv\Scripts\Activate.ps1
python main.py
```

说明：

- 该模式会读取 `main.py` 里写死的示例文件名和标准文件路径
- 如果本地没有这些示例文件，需要先修改 `main.py` 中的文件名或路径
- 该模式通过本地脚本路径调用 MCP，而不是通过 `http://localhost:8000/mcp`
- 更适合开发者排查工作流，不适合作为正式部署入口
