# Deep Research Agent 部署说明

## 1. 文档说明

本文档面向当前仓库的实际代码实现，覆盖以下内容：

- 本地环境准备
- 环境变量说明
- CLI 运行方式
- 输出目录与产物
- 常见故障排查

> 当前分支 (`rollback-0313-with-mineru`) 仅包含 CLI 形态的后端核心实现，不含前端工作台和 FastAPI Web 服务。本文档已据此精简，不再描述 Web 模式。

## 2. 系统组成

项目由以下核心部分组成：

1. CLI 入口：[`main.py`](./main.py)
   - 读取 `docs/contracts/` 中的合同文件与 `docs/contract_review_criteria/` 中的审查标准文件
   - 触发 `ContractReviewWorkflow` 完整链路

2. 审查工作流：`main_workflow/` + `agents/`
   - 负责合同解析、任务规划、证据检索、审查、反思、报告汇总

3. MCP 服务：`mcp_service/`
   - 通过本地脚本路径以子进程方式启动 (`mcp_service/mcp_server/mcp_server.py`)
   - 提供文件解析、检索、报告生成、网页搜索等工具

4. 工具实现：`tools/`
   - 文档解析（含 MinerU、本地 PDF/DOCX 回退）
   - 检索（PageIndex 树检索、LlamaIndex 向量检索）
   - 报告生成（Markdown / DOCX / PDF）

## 3. 环境要求

建议环境：

- Python 3.10 或以上
- `pip`

外部依赖：

- 一个 OpenAI 兼容的大模型接口（必需）
- 如需网页检索：Serper API Key
- 如需 MinerU 云解析：MinerU API Key
- 如需 LlamaIndex 检索模式：Embedding 与 Rerank 接口

建议：

- 使用独立 Python 虚拟环境 `.venv`

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
MAX_CONTEXT_TOKENS=120000
MAX_RESULT_TOKENS=4000
MAX_TOOL_CALLS=25
```

说明：

- `LLM_*` 用于 Planner、Orchestrator、Reflector、Summarizer 等智能体调用
- 如未正确配置，审查任务无法正常执行

### 4.2 检索模式配置

```env
LLAMA_INDEX=False
PAGEINDEX_SEARCH=True
```

默认策略计算规则（见 `config.py` 中的 `get_default_retrieval_mode`）：

- `LLAMA_INDEX=True`：使用 `llamaindex`
- `LLAMA_INDEX=False` 且 `PAGEINDEX_SEARCH=True`：使用 `pageindex`
- `LLAMA_INDEX=False` 且 `PAGEINDEX_SEARCH=False`：使用 `evidence`

检索策略与是否启用网页搜索均**仅由 `.env` 决定**，运行时不再支持通过函数参数覆盖。如需切换，请修改 `.env` 后重新运行。

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

### 4.5 兼容性说明

当前 `tools/document/parsers/mineru_file_parser.py` 中的 PDF LLM 清洗回退逻辑读取的是 `API_KEY` 和 `BASE_URL`。如果你希望在「无 MinerU、但使用 LLM 清洗 PDF」这一分支下工作，建议额外补一组兼容变量：

```env
API_KEY=same_as_LLM_API_KEY
BASE_URL=same_as_LLM_BASE_URL
```

如果不配置这两个兼容变量，系统仍可回退到本地 PDF 提取，只是不会走该分支。

## 5. 本地运行

### 5.1 安装依赖

在项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

可选安装（用于将项目以包的方式注册到当前环境）：

```powershell
python -m pip install -e .
```

### 5.2 准备输入文件

CLI 入口默认从以下路径读取输入：

- 合同文件：`docs/contracts/<your_contract>.docx`（或 `.pdf`）
- 审查标准：`docs/contract_review_criteria/审核要点（初稿）(2).docx`

如需替换，可直接编辑 [`main.py`](./main.py) 中的：

- `doc_1` / `doc_2` / `doc_3`
- `CRITERIA_PATH`

文件后缀目前限制为 `.pdf` 与 `.docx`（见 `main.py` 中 `contract_path` 的校验）。

### 5.3 运行 CLI

```powershell
.\.venv\Scripts\Activate.ps1
python main.py
```

CLI 会执行以下顺序：

1. 解析审查标准文件
2. 解析合同文件
3. 根据检索模式建索引或建结构树
4. Planner 拆任务 → Orchestrator 协调 → Reflector 复核
5. Summarizer 汇总
6. 生成 `md` / `docx` / `pdf` 报告

## 6. 运行产物与目录

系统运行时会写入以下目录：

- `uploads/`（如启用上传写入逻辑）
- `docs/contracts/`
- `docs/contract_review_criteria/`
- `docs/reports_md/`
- `docs/reports_docx/`
  - 若合同原文件是 `.docx`，会优先尝试在原合同上写入审查批注
- `docs/reports_pdf/`
- `logs/workflow/`
- `logs/conversations/`
- `logs/mcp/`
- `RAG_persist/`
  - PageIndex 树缓存、LlamaIndex 向量索引、manifest 文件

## 7. 常见问题

### 7.1 启动时报模型或工具错误

优先检查：

1. `.env` 中的 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_NAME` 是否正确
2. 如果使用 `llamaindex`，`EMBED_*` 和 `RERANK_*` 是否已配置
3. `requirements.txt` 是否已完整安装
4. `mcp_service/mcp_server/mcp_server.py` 是否存在且可被 Python 启动

### 7.2 PDF 解析效果差或失败

检查项：

1. 是否配置了 `MINERU_API_KEY`
2. `PARSE_FILE_WITH_MINERU` 是否为 `True`
3. 如需走 PDF 的 LLM 清洗回退，是否补充了 `API_KEY` 和 `BASE_URL`
4. 如果以上都没有，系统会退回到本地 PDF 提取，效果可能不如 MinerU

### 7.3 LlamaIndex 模式不可用

检查项：

1. 是否安装了 `llama_index` 及相关依赖
2. `EMBED_*` 是否可用
3. `RERANK_*` 是否可用
4. 查看 `logs/mcp/` 与 `logs/workflow/`

### 7.4 找不到合同或审查标准文件

检查项：

1. `docs/contracts/` 与 `docs/contract_review_criteria/` 是否存在
2. `main.py` 中的 `doc_1` / `CRITERIA_PATH` 是否与磁盘文件名完全一致
3. 文件后缀是否为 `.pdf` 或 `.docx`

## 8. 后续可扩展方向

如果未来需要恢复或新增 Web 形态，可参考的扩展方向：

- 在仓库根目录新增 `api/`，使用 FastAPI 暴露上传、审查、查询、下载、历史接口
- 在仓库根目录新增 `frontend/`，使用 React + Vite 构建工作台
- 让 MCP 通过 `Streamable HTTP` 挂载到后端的 `/mcp`，再由工作流通过 `MCP_SERVER_URL` 访问
- 引入数据库与任务队列，替代当前内存中的状态保存

这些扩展并不在当前分支的实现范围内，仅作为方向性提示。
