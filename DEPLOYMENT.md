# 合同审查系统部署说明

## 概览

当前系统分为 3 层：

- 前端：React + TypeScript + Vite，默认地址 `http://localhost:5173`
- 后端：FastAPI，默认地址 `http://localhost:8000`
- 审查工作流：由 FastAPI 后台任务触发，串联 MCP tools、PageIndex / LlamaIndex 检索和多智能体流程

当前前端主界面支持的主流程：

1. 上传合同文件
2. 上传审查标准文件
3. 选择本次任务的检索策略
4. 启动审查任务
5. 轮询任务状态与阶段进度
6. 左侧查看文档预览，右侧查看审查结论
7. 查看并下载 `md`、`docx`、`pdf` 报告产物

补充说明：

- 前端“检索策略”按钮会把本次任务的 `retrieval_mode` 提交给后端。
- 后端 `.env` 中的 `LLAMA_INDEX` / `PAGEINDEX_SEARCH` 只用于计算默认检索模式；仅在请求没有显式传入 `retrieval_mode` 时生效。
- 前端可能看到两种 Phase 2 状态：
  - `building_index`：LlamaIndex 向量索引构建
  - `building_tree`：PageIndex 结构树构建

当前上传限制说明：

- 浏览器前端 UI 当前只允许选择 `.pdf` 和 `.docx`
- PDF 可以直接预览
- DOCX 会在服务端先清洗修订和批注，再进入解析流程
- 后端上传接口尚未同步做同样的强校验，因此当前限制仍主要由 UI 控制

## 环境要求

- Node.js 18+
- Python 3.10+
- `pip`
- 建议使用 Python 虚拟环境 `.venv`

## 后端部署

### 1. 创建并激活虚拟环境

推荐在项目根目录执行：

```powershell
cd C:\Users\18014\agent_self_practice\deep_research_agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

激活后先确认当前解释器：

```powershell
python -c "import sys; print(sys.executable)"
```

预期输出应指向：

```text
C:\Users\18014\agent_self_practice\deep_research_agent\.venv\Scripts\python.exe
```

### 2. 安装依赖

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. 配置环境变量

将 `.env.example` 复制为 `.env`，至少补齐以下配置：

```env
# LLM
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_NAME=qwen-plus

# EMBEDDING MODEL
EMBED_API_KEY=your_api_key_here
EMBED_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBED_NAME=text-embedding-v4

# QWEN RERANKING MODEL
RERANK_API_KEY=your_api_key_here
RERANK_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
RERANK_NAME=qwen3-rerank

# NUMERIC CONFIGS
TEMPERATURE=0.0
TOP_P=0.01
SEED=42
MAX_REFLECTION_ROUNDS=3

# RETRIEVAL MODE
LLAMA_INDEX=False
PAGEINDEX_SEARCH=True

# BOOL CONFIGS
ENABLE_MCP_WEB_TOOLS=True
PARSE_FILE_WITH_MINERU=True

# SERPER
SERPER_API_KEY=your_api_key_here

# MINERU
MINERU_API_BASE=https://mineru.net
MINERU_API_KEY=your_api_key_here
```

说明：

- 主链路模型使用 `LLM_API_KEY` / `LLM_BASE_URL`。
- `EMBED_*` 与 `RERANK_*` 在 `llamaindex` 模式下更重要；若与主模型一致，可先沿用同一供应商配置。
- 不再使用单独的 `RETRIEVAL_MODE` 环境变量；默认模式由 `LLAMA_INDEX` 与 `PAGEINDEX_SEARCH` 组合决定。
- 默认模式规则如下：
  - `LLAMA_INDEX=true`：使用 `LlamaIndex RAG (MCP)`
  - `LLAMA_INDEX=false` 且 `PAGEINDEX_SEARCH=true`：使用 `PageIndex tree search (MCP)`
  - `LLAMA_INDEX=false` 且 `PAGEINDEX_SEARCH=false`：使用 `EvidenceCollector agent`
- `POST /api/v1/review/start` 现在支持可选字段 `retrieval_mode`，传入后会覆盖本次任务的默认模式。
- MCP server 会始终注册 `llamaindex_build_index` / `llamaindex_search` 工具，但只有真正选择 `llamaindex` 时才会加载对应依赖。

### 4. 启动后端

启动虚拟环境：
```
.venv\Scripts\Activate.ps1
```

首次联调建议先不要带 `--reload`：

```powershell
python -m uvicorn api.main:app --port 8000
```

确认稳定后再使用：

```powershell
python -m uvicorn api.main:app --reload --port 8000
```

可用地址：

- 健康检查：`http://localhost:8000/health`
- Swagger UI：`http://localhost:8000/docs`

重要说明：

- 推荐始终使用 `python -m uvicorn ...`，不要直接使用裸命令 `uvicorn ...`
- 当前 MCP server 是由后端进程通过 `sys.executable` 拉起的
- 如果你用系统 `uvicorn` 启动 API，但项目依赖装在 `.venv`，就可能出现“API 能启动，但 review 任务里 MCP 连接失败”的情况

### 5. 验证后端

```powershell
curl http://localhost:8000/health
```

预期返回：

```json
{"status":"healthy"}
```

## 前端部署

### 1. 安装依赖

```powershell
cd C:\Users\18014\agent_self_practice\deep_research_agent\frontend
npm install
```

### 2. 配置 `VITE_API_URL`

本地开发推荐直接使用 Vite dev proxy，不显式设置 `VITE_API_URL`。

如果需要显式指定后端地址，可在 `frontend/.env` 中写入：

```env
VITE_API_URL=http://localhost:8000
```

### 3. 启动前端

```powershell
npm run dev
```

默认访问地址：

```text
http://localhost:5173
```

### 4. 生产构建

```powershell
npm run build
```

当前构建产物目录：

```text
frontend/build
```

## 联调启动

使用两个终端。

### 终端 1：启动后端

```powershell
cd C:\Users\18014\agent_self_practice\deep_research_agent
.\.venv\Scripts\Activate.ps1
python -m uvicorn api.main:app --port 8000
```

如需热重载：

```powershell
python -m uvicorn api.main:app --reload --port 8000
```

### 终端 2：启动前端

```powershell
cd C:\Users\18014\agent_self_practice\deep_research_agent\frontend
npm run dev
```

然后打开：

```text
http://localhost:5173
```

## API 说明

### 基础接口

| Method | Path | 说明 |
| --- | --- | --- |
| GET | `/health` | 健康检查 |
| GET | `/docs` | Swagger UI |

### 上传接口

| Method | Path | 说明 |
| --- | --- | --- |
| POST | `/api/v1/upload/contract` | 上传合同文件，前端 UI 当前只允许 `.pdf` / `.docx` |
| POST | `/api/v1/upload/criteria` | 上传审查标准文件，前端 UI 当前只允许 `.pdf` / `.docx` |

### 审查任务接口

| Method | Path | 说明 |
| --- | --- | --- |
| POST | `/api/v1/review/start` | 创建审查任务 |
| GET | `/api/v1/review/{task_id}` | 查询任务状态和阶段 |
| GET | `/api/v1/review/{task_id}/result` | 查询结构化审查结果 |
| GET | `/api/v1/review/{task_id}/artifact/{artifact_type}` | 下载 `md`、`docx`、`pdf` 报告 |

### 审查任务请求体补充

`POST /api/v1/review/start` 支持可选字段 `retrieval_mode`：

- `llamaindex`
- `pageindex`
- `evidence`

未传时回退到后端 `.env` 默认模式。

任务状态接口、结果接口、历史接口都会返回 `retrieval_mode`，表示本次任务实际执行的检索模式。

### 历史记录接口

| Method | Path | 说明 |
| --- | --- | --- |
| GET | `/api/v1/history` | 获取历史任务列表 |
| GET | `/api/v1/history/{task_id}` | 获取单个历史任务 |

## 任务状态模型

任务阶段 `stage`：

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

任务状态 `status`：

- `pending`
- `processing`
- `completed`
- `failed`

前端会在 `status=processing` 时轮询：

```text
GET /api/v1/review/{task_id}
```

## 常用调用示例

### 1. 上传合同

```powershell
curl -X POST http://localhost:8000/api/v1/upload/contract `
  -F "file=@contract.docx"
```

### 2. 上传审查标准

```powershell
curl -X POST http://localhost:8000/api/v1/upload/criteria `
  -F "file=@criteria.docx"
```

### 3. 启动审查

```powershell
curl -X POST http://localhost:8000/api/v1/review/start `
  -H "Content-Type: application/json" `
  -d '{
    "contract_path": "C:/path/to/contract.docx",
    "criteria_path": "C:/path/to/criteria.docx",
    "retrieval_mode": "pageindex"
  }'
```

返回示例：

```json
{
  "task_id": "9fce2d3e-0b4f-4c7c-9d0a-4a0f5dcf62d3",
  "status": "processing",
  "created_at": "2026-03-27T19:00:00",
  "contract_name": "contract.docx",
  "retrieval_mode": "pageindex",
  "stage": "queued",
  "progress_message": "Task created",
  "error": null
}
```

### 4. 查询任务状态

```powershell
curl http://localhost:8000/api/v1/review/9fce2d3e-0b4f-4c7c-9d0a-4a0f5dcf62d3
```

### 5. 查询完成结果

```powershell
curl http://localhost:8000/api/v1/review/9fce2d3e-0b4f-4c7c-9d0a-4a0f5dcf62d3/result
```

### 6. 下载报告

```powershell
curl -L http://localhost:8000/api/v1/review/9fce2d3e-0b4f-4c7c-9d0a-4a0f5dcf62d3/artifact/pdf -o review-report.pdf
```

## 运行时输出目录

系统运行时会生成以下目录：

- `uploads/`：上传的合同和标准文件
- `docs/reports_md/`：Markdown 报告
- `docs/reports_docx/`：DOCX 报告
- `docs/reports_pdf/`：PDF 报告
- `logs/workflow/`：工作流日志
- `logs/conversations/`：智能体对话日志
- `RAG_persist/`：PageIndex / LlamaIndex 的运行期缓存和索引目录

## 当前限制

- 历史任务当前仍使用内存存储，后端重启后历史会丢失
- `.env` 只决定默认检索模式；前端或 API 请求可以通过 `retrieval_mode` 覆盖本次任务的执行策略
- 若选择 `llamaindex`，仍需确保对应依赖、embedding、rerank 与模型配置可用
- 上传入口当前主要面向 `.pdf` / `.docx`
- 报告下载只有在任务完成且产物存在时可用

## 故障排查

### 后端能启动，但发起审查时报 `Connection closed`

优先检查：

1. 当前解释器是否来自 `.venv`

```powershell
python -c "import sys; print(sys.executable)"
```

2. 后端是否通过下面的命令启动：

```powershell
python -m uvicorn api.main:app --port 8000
```

而不是：

```powershell
uvicorn api.main:app --port 8000
```

3. 若开启了 `--reload`，先切回不带 `--reload` 的命令排查
4. 若本次选择的是 `llamaindex`，确认当前环境可以导入对应包：

```powershell
python -c "import llama_index.embeddings.openai_like; print('ok')"
```

5. 再检查 `python -m pip install -r requirements.txt` 是否是在同一个虚拟环境里执行的

### 前端连不上后端

检查：

1. 后端是否已启动：`curl http://localhost:8000/health`
2. `VITE_API_URL` 是否指向正确后端
3. Vite dev proxy 是否仍然把 `/api` 转发到 `http://localhost:8000`

### 前端构建失败

运行：

```powershell
cd C:\Users\18014\agent_self_practice\deep_research_agent\frontend
npm run build
```

若失败，优先检查 Node 版本和依赖安装状态。

### 后端启动失败

检查：

1. Python 版本：`python --version`
2. 当前解释器路径是否为 `.venv\Scripts\python.exe`
3. 依赖是否已安装：`python -m pip install -r requirements.txt`
4. `.env` 是否存在且 `LLM_API_KEY` / `LLM_BASE_URL` 已正确配置

### 审查任务失败

检查：

1. 本次请求是否显式传入 `retrieval_mode`
2. 若未传，再检查 `.env` 中的 `LLAMA_INDEX` / `PAGEINDEX_SEARCH` 是否符合预期
3. MCP tools 是否能被正常拉起
4. 若选择 `llamaindex`，对应依赖与模型配置是否可用
5. 上传后的文件路径是否存在
6. 后端日志以及 `logs/workflow/` 输出

### 检索模式补充排查

1. 前端按钮会直接提交 `retrieval_mode`，不会修改后端 `.env`
2. 若请求未传 `retrieval_mode`，后端才会回退到 `.env` 的默认组合
3. 若选择 `llamaindex`，确认 MCP 已暴露 `llamaindex_build_index` / `llamaindex_search`
4. 若接口报 `LlamaIndex index build failed` 或 `Error in LlamaIndex search`，优先检查 LlamaIndex 依赖和相关模型配置
