# 合同审查系统部署说明

## 概览

当前系统分为 3 层：

- 前端：React + TypeScript + Vite，默认地址 `http://localhost:5173`
- 后端：FastAPI，默认地址 `http://localhost:8000`
- 审查工作流：由 FastAPI 后台任务触发，串联 MCP tools、PageIndex 和多智能体流程

当前前端主界面已经围绕真实合同审查任务流重做：

1. 上传合同文件
2. 上传审查标准文件
3. 启动审查任务
4. 轮询任务状态与阶段进度
5. 左侧查看文档预览，右侧查看审查结论
6. 在右侧切换查看 `Markdown` 报告
7. 下载 `md`、`docx`、`pdf` 报告产物

当前上传限制说明：

- 浏览器前端 UI 目前只允许选择 `.pdf` 和 `.docx`
- PDF 可以直接预览
- DOCX 会在服务端先清洗修订和批注，再进入解析流程
- 后端上传接口目前还没有同步做同样的强校验，因此当前限制仍然主要是 UI 侧限制

## 环境要求

- Node.js 18+
- Python 3.10+
- `pip`
- 建议使用 Python 虚拟环境

## 后端部署

### 1. 安装依赖

```bash
cd deep_research_agent
pip install -r requirements.txt
```

### 2. 配置环境变量

将 `.env.example` 复制为 `.env`，至少补齐以下配置：

```env
API_KEY=your_api_key_here
BASE_URL=https://your-llm-base-url.com/compatible-mode/v1
LLM_NAME=qwen-plus
TEMPERATURE=0.0
TOP_P=0.01
SEED=42
PAGEINDEX_SEARCH=False
EMBED_NAME=text-embedding-v4
SERPER_API_KEY=your_serper_api_key_here
```

说明：

- `API_KEY`、`BASE_URL`、`LLM_NAME` 用于模型调用
- `SERPER_API_KEY` 用于 web search
- `PAGEINDEX_SEARCH=True` 使用 PageIndex search
- `PAGEINDEX_SEARCH=False` 使用 Evidence Collector 模式

### 3. 启动后端

```bash
uvicorn api.main:app --reload --port 8000
```

可用地址：

- 健康检查：`http://localhost:8000/health`
- Swagger UI：`http://localhost:8000/docs`

### 4. 验证后端

```bash
curl http://localhost:8000/health
```

预期返回：

```json
{"status":"healthy"}
```

## 前端部署

### 1. 安装依赖

```bash
cd deep_research_agent/frontend
npm install
```

### 2. 配置 `VITE_API_URL`

本地开发有两种方式：

- 推荐：不设置 `VITE_API_URL`，直接使用 Vite dev proxy，把 `/api` 转发到 `http://localhost:8000`
- 可选：在 `frontend/.env` 中显式指定后端地址

```env
VITE_API_URL=http://localhost:8000
```

### 3. 启动前端

```bash
npm run dev
```

默认访问地址：

`http://localhost:5173`

### 4. 生产构建

```bash
npm run build
```

当前构建产物目录：

`frontend/build`

## 联调启动

使用两个终端。

### 终端 1：启动后端

```bash
cd deep_research_agent
uvicorn api.main:app --reload --port 8000
```

### 终端 2：启动前端

```bash
cd deep_research_agent/frontend
npm run dev
```

然后打开：

`http://localhost:5173`

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

### 历史记录接口

| Method | Path | 说明 |
| --- | --- | --- |
| GET | `/api/v1/history` | 获取历史任务列表 |
| GET | `/api/v1/history/{task_id}` | 获取单个历史任务 |

## 任务状态模型

任务阶段 `stage`：

- `queued`
- `ingesting`
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

`GET /api/v1/review/{task_id}`

## 常用调用示例

### 1. 上传合同

```bash
curl -X POST http://localhost:8000/api/v1/upload/contract \
  -F "file=@contract.docx"
```

### 2. 上传审查标准

```bash
curl -X POST http://localhost:8000/api/v1/upload/criteria \
  -F "file=@criteria.docx"
```

### 3. 启动审查

```bash
curl -X POST http://localhost:8000/api/v1/review/start \
  -H "Content-Type: application/json" \
  -d '{
    "contract_path": "C:/path/to/contract.docx",
    "criteria_path": "C:/path/to/criteria.docx"
  }'
```

返回示例：

```json
{
  "task_id": "9fce2d3e-0b4f-4c7c-9d0a-4a0f5dcf62d3",
  "status": "processing",
  "created_at": "2026-03-24T10:00:00",
  "contract_name": "contract.docx",
  "stage": "queued",
  "progress_message": "Task created",
  "error": null
}
```

### 4. 查询任务状态

```bash
curl http://localhost:8000/api/v1/review/9fce2d3e-0b4f-4c7c-9d0a-4a0f5dcf62d3
```

### 5. 查询完成结果

```bash
curl http://localhost:8000/api/v1/review/9fce2d3e-0b4f-4c7c-9d0a-4a0f5dcf62d3/result
```

### 6. 下载报告

```bash
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

## 当前限制

- 历史任务目前使用内存存储，后端重启后会丢失
- 前端当前只允许在浏览器中选择 PDF 和 DOCX
- PDF 支持直接预览，DOCX 通过服务端解析
- 后端上传接口尚未同步强制限制文件类型
- 只有任务成功完成且产物文件存在时，报告下载才可用

## 故障排查

### 前端连不上后端

检查：

1. 后端是否启动：`curl http://localhost:8000/health`
2. `VITE_API_URL` 是否指向正确后端
3. Vite dev proxy 是否仍然转发到 `http://localhost:8000`

### 前端构建失败

运行：

```bash
cd deep_research_agent/frontend
npm run build
```

当前主审查路径应当可以成功构建。如果本地失败，先检查 Node 版本和依赖安装状态。

### 后端启动失败

检查：

1. Python 版本：`python --version`
2. 依赖是否安装：`pip install -r requirements.txt`
3. `.env` 是否存在且模型配置有效

### 审查任务失败

检查：

1. `.env` 中的模型和搜索配置
2. MCP tools 是否可调用
3. 上传后的文件路径是否存在
4. 后端日志以及 `logs/workflow/` 输出
