# Deep Research Agent

面向合同审查场景的多智能体应用，提供“文件上传/解析、检索、逐项审查、结果汇总、报告导出”的完整链路。

当前仓库已经包含：

- 前端工作台：上传合同与审查标准、选择检索策略、查看进度和结果
- 后端 API：任务创建、状态查询、结果读取、报告下载、历史任务查询
- 工作流引擎：6 阶段审查流程编排
- MCP 工具层：文件解析、PageIndex/LlamaIndex 检索、网页搜索、报告生成

## 核心能力

- 三种检索模式可切换
  - `llamaindex`
  - `pageindex`
  - `evidence`

- 多智能体协作
  - `Planner`
  - `Orchestrator`
  - `EvidenceCollector`
  - `Reflector`
  - `Summarizer`

- 多格式报告输出
  - `Markdown`
  - `DOCX`
  - `PDF`

- 运行日志可追踪
  - 工作流日志
  - 智能体对话日志
  - MCP 客户端日志

## 运行方式

项目支持两种运行方式：

### 1. Web 模式

用于日常联调和页面使用：

- 后端：FastAPI，默认 `http://localhost:8000`
- 前端：Vite，默认 `http://localhost:5173`
- MCP：由后端挂载在 `/mcp`

### 2. CLI 模式

用于本地开发调试：

- 直接运行 [`main.py`](./main.py)
- 通过本地脚本路径调用 MCP

## 快速开始

### 1. 安装后端依赖

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`：

```powershell
Copy-Item .env.example .env
```

至少需要配置：

```env
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_NAME=qwen-plus
```

如需网页搜索或 MinerU：

```env
SERPER_API_KEY=your_serper_api_key
MINERU_API_KEY=your_mineru_api_key
```

### 3. 启动后端

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

可访问：

- `http://localhost:8000/health`
- `http://localhost:8000/docs`
- `http://localhost:8000/mcp`

### 4. 启动前端

```powershell
cd frontend
npm install
npm run dev
```

打开：

`http://localhost:5173`

## API 概览

核心接口如下：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/upload/contract` | 上传合同文件 |
| POST | `/api/v1/upload/criteria` | 上传审查标准文件 |
| POST | `/api/v1/review/start` | 启动审查 |
| GET | `/api/v1/review/{task_id}` | 查询任务状态 |
| GET | `/api/v1/review/{task_id}/result` | 查询审查结果 |
| GET | `/api/v1/review/{task_id}/artifact/{artifact_type}` | 下载 `md/docx/pdf` |
| GET | `/api/v1/history` | 获取历史任务 |

## 输出目录

运行过程中会写入：

- `uploads/`
- `docs/reports_md/`
- `docs/reports_docx/`
- `docs/reports_pdf/`
- `logs/workflow/`
- `logs/conversations/`
- `logs/mcp/`
- `RAG_persist/`

## 项目结构

```text
deep_research_agent/
├── agents/                     # 智能体实现
├── api/                        # FastAPI 接口
├── frontend/                   # React 前端
├── main_workflow/              # 工作流编排
├── mcp_service/                # MCP 客户端与服务端
├── tools/                      # 文件解析、检索、报告生成
├── docs/                       # 输入文档和导出报告
├── uploads/                    # 上传文件
├── logs/                       # 运行日志
├── RAG_persist/                # 索引和缓存
├── project_intro/              # 项目说明
├── DEPLOYMENT.md               # 部署说明
└── main.py                     # CLI 调试入口
```

## 文档索引

- 部署说明：[`DEPLOYMENT.md`](./DEPLOYMENT.md)
- 项目概览：[`project_intro/PROJECT_OVERVIEW.md`](./project_intro/PROJECT_OVERVIEW.md)
- 架构说明：[`project_intro/ARCHITECTURE.md`](./project_intro/ARCHITECTURE.md)
- 前端说明：[`frontend/README.md`](./frontend/README.md)

## 当前限制

- 历史任务目前保存在内存，后端重启后会丢失
- 上传接口本身没有严格的后缀强校验，当前主要依赖前端限制
- 生产环境尚未接入数据库、鉴权和正式任务队列
- 解析与检索效果依赖外部模型、Serper、MinerU 等服务可用性
