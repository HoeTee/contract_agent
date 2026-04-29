# Deep Research Agent

面向合同审查场景的多智能体应用，提供「文件解析、检索、逐项审查、结果汇总、报告导出」的完整链路。

当前仓库包含：

- 工作流引擎：6 阶段审查流程编排
- 多智能体协作层：Planner、Orchestrator、EvidenceCollector、Reflector、Summarizer
- MCP 工具层：文件解析、PageIndex/LlamaIndex 检索、网页搜索、报告生成
- CLI 调试入口：[`main.py`](./main.py)

> 注：当前分支 (`rollback-0313-with-mineru`) 不包含前端工作台和 FastAPI Web 服务，仅提供 CLI 形态的核心后端实现。如需 Web 形态，请参考其他分支或在此基础上自行扩展。

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

当前仓库提供 CLI 模式：

- 直接运行 [`main.py`](./main.py)
- 通过本地脚本路径调用 MCP 服务（`mcp_service/mcp_server/mcp_server.py`）
- 适合本地开发、链路调试、效果验证

## 快速开始

### 1. 安装依赖

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

如需 LlamaIndex 检索模式，建议补充：

```env
EMBED_API_KEY=your_api_key_here
EMBED_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBED_NAME=text-embedding-v4

RERANK_API_KEY=your_api_key_here
RERANK_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
RERANK_NAME=qwen3-rerank
```

### 3. 准备输入文件

`main.py` 默认从以下目录读取文件：

- 合同文件目录：`docs/contracts/`
- 审查标准目录：`docs/contract_review_criteria/`

可在 [`main.py`](./main.py) 中直接修改 `doc_1` / `doc_2` / `doc_3` 与 `CRITERIA_PATH` 来指向你自己的文件。

### 4. 运行 CLI

```powershell
.\.venv\Scripts\Activate.ps1
python main.py
```

工作流会顺序执行解析、检索、审查、反思、汇总和报告导出，并将产物写入 `docs/reports_*/` 与 `logs/`。

## 输出目录

运行过程中会写入：

- `docs/contracts/`
- `docs/contract_review_criteria/`
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
├── main_workflow/              # 6 阶段工作流编排
├── mcp_service/                # MCP 客户端与服务端
├── tools/                      # 文件解析、检索、报告生成
├── RAG_persist/                # 索引和缓存
├── project_intro/              # 项目说明文档
├── config.py                   # 全局配置
├── DEPLOYMENT.md               # 部署 / 运行说明
├── main.py                     # CLI 调试入口
├── requirements.txt
└── pyproject.toml
```

## 文档索引

- 部署 / 运行说明：[`DEPLOYMENT.md`](./DEPLOYMENT.md)
- 项目概览：[`project_intro/PROJECT_OVERVIEW.md`](./project_intro/PROJECT_OVERVIEW.md)
- 架构说明：[`project_intro/ARCHITECTURE.md`](./project_intro/ARCHITECTURE.md)

## 当前限制

- 仅提供 CLI 入口，没有 Web 前端或 HTTP API
- MCP 通过本地脚本进程方式调用，未对外暴露 HTTP `/mcp` 端点
- 没有任务队列、数据库和鉴权
- 解析与检索效果依赖外部模型、Serper、MinerU 等服务可用性
