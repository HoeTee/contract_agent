# Deep Research Agent — 基于 MCP 与 PageIndex 的多智能体合同审查系统

一套完整的 6 阶段自动化合同审查工作流，融合 **Model Context Protocol (MCP)** 与**多智能体架构**，结合 **PageIndex** 实现高级 RAG（检索增强生成）。

## 🌟 核心特性

### 1. 多智能体协作系统

- **Planner** — 解析审查标准，分解为可执行的结构化任务
- **Orchestrator** — 调度子智能体，检索合同相关章节，管理执行流程
- **Evidence Collector** — 逐章节提取与审查标准相关的文本片段（可选模式）
- **Reflector** — 质量控制关卡，评估子智能体输出，不合格则返回修订（最多 3 轮）
- **Summarizer** — 汇总所有智能体审查结果，生成结构化最终报告

### 2. Model Context Protocol (MCP) 集成

MCP Server 将关键功能暴露为标准工具函数：

- `ingest_docx` — 解析 Word/PDF/TXT 文件为 Markdown
- `build_pageindex_tree` — 将 Markdown 转为层级 PageIndex 树
- `pageindex_search` — 基于 LLM 推理的树结构搜索
- `web_search` / `read_url` — 通过 Serper API 提供外部网络访问
- `generate_final_report` — 渲染最终审查报告并保存为 MD, DOCX, PDF 格式

`MinimalMCPClient` 通过 stdio 实现无缝工具调用。

### 3. PageIndex RAG 高级检索

区别于简单分块策略，本项目使用 **PageIndex** 保留文档结构（章节、标题、逻辑分组），确保子智能体获取精确的结构化上下文，避免 Token 浪费和上下文丢失。

### 4. 完整的输出与日志体系

- 同时生成 Markdown、DOCX 和 PDF 三种格式的合法报告，自动归档至独立文件夹
- 完整的对话日志（JSON 格式）和工作流执行日志（MD + Mermaid 序列图），便于审计追踪
- 全流程 Token 用量追踪与管理

---

## 🏗 系统架构

工作流包含 **6 个阶段**：

1. **文件解析** — 解析合同和审查标准文档为 Markdown
2. **构建文档树** — 将合同 Markdown 转为结构化 PageIndex 树
3. **任务规划** — 将审查标准提取为结构化 JSON 任务列表
4. **执行与反思**（逐条并发执行）
   - 通过 PageIndex 树搜索合同相关条款（或通过 Evidence Collector 逐章节提取证据）
   - 子智能体审查条款是否符合审查标准
   - 反思智能体评估审查结果，不通过则要求修订（循环）
5. **报告汇总** — 将所有审查结果汇编为一份 Markdown 报告
6. **报告生成** — 将最终审查报告归档保存为独立的 MD、DOCX 和 PDF 文件

> 详细架构图和数据流图请参见 `project_intro/ARCHITECTURE.md`

---

## 🚀 快速开始

### 环境要求

- Python 3.10+
- 安装依赖：`pip install -r requirements.txt`
- 可编辑安装：`pip install -e .`

### 配置

复制 `.env.example` 为 `.env`，填入你的 LLM 和 API 配置：

```env
API_KEY=your_api_key_here
BASE_URL=https://your-llm-base-url.com/v1
LLM_NAME=qwen-plus
TEMPERATURE=0.0
TOP_P=0.01
SEED=42
PAGEINDEX_SEARCH=True          # True=PageIndex search, False=Evidence Collector
SERPER_API_KEY=your_serper_api_key
```

### 运行

```bash
python main.py
```

运行后系统将在控制台实时输出 6 个阶段的进度日志。运行结束后：

- **审查报告**：分别保存至 `docs/reports_md/`、`docs/reports_docx/` 和 `docs/reports_pdf/` 文件夹
- **对话日志**：`logs/conversations/`（每个智能体的完整 JSON 对话记录）
- **工作流日志**：`logs/`（运行级别的 Markdown 摘要，含 Mermaid 序列图）

---

## 📂 项目结构

```
deep_research_agent/
├── .env.example                  # 环境变量模板
├── config.py                     # 中央配置（路径、常量）
├── main.py                       # 入口脚本
├── pyproject.toml                # Python 项目配置
├── requirements.txt              # pip 依赖
├── agents/                       # 智能体模块
│   ├── base_agent.py             # 基础 Agent 类（LLM 通信、工具调用）
│   ├── agent_logger.py           # 智能体对话日志（JSON → logs/conversations/）
│   ├── planner.py                # Planner 智能体
│   ├── orchestrator.py           # Orchestrator 智能体
│   ├── evidence_collector.py     # Evidence Collector 智能体（逐章节证据提取）
│   ├── reflector.py              # Reflector 智能体
│   ├── summarizer.py             # Summarizer 智能体
│   └── prompts/cn_prompts.py     # 中文提示词定义
├── mcp_service/                  # MCP 客户端与服务端
│   ├── mcp_client/
│   │   ├── mcp_minimal.py        # MCP 客户端封装
│   │   └── mcp_logger.py         # MCP 客户端日志配置
│   └── mcp_server/mcp_server.py  # MCP 工具注册（6 个工具）
├── main_workflow/                # 工作流编排
│   ├── main_workflow.py          # 6 阶段流水线
│   └── workflow_logger.py        # 工作流日志（MD + Mermaid）
├── tools/                        # 工具模块
│   ├── document_tools.py         # 文件解析器 + 报告生成器
│   └── PageIndex-main/           # PageIndex 树结构 RAG 库
├── docs/                         # 文档目录
│   ├── contracts/                # 输入合同（.gitignore 排除）
│   └── contract_review_criteria/ # 审查标准（.gitignore 排除）
├── logs/                         # 所有运行时日志（.gitignore 排除）
│   ├── workflow/                 # 工作流日志（MD + Mermaid）
│   ├── conversations/            # 智能体对话日志（每次运行独立文件夹）
│   └── mcp/                      # MCP 客户端日志
└── project_intro/                # 项目说明
    ├── ARCHITECTURE.md           # 架构图与数据流
    └── PROJECT_OVERVIEW.md       # 项目概览
```

---

## ⚙️ 自定义配置

- **反思轮次上限**：修改 `config.py` 中的 `MAX_REFLECTION_ROUNDS`
- **模型与 Token 限制**：在 `.env` 中设置 `LLM_NAME`，系统会根据所选模型在 `config.py` 中自动匹配相应的 `MAX_CONTEXT_TOKENS` 和 `MAX_TOOL_CALLS`
- **提示词**：修改 `agents/prompts/cn_prompts.py` 可调整智能体行为
- **检索模式**：在 `.env` 中设置 `PAGEINDEX_SEARCH=True`（PageIndex 搜索）或 `False`（Evidence Collector 逐章节证据提取）
