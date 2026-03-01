# 合同审查多智能体系统 — 项目概览

## 项目简介

基于多智能体架构的 AI 合同审查系统，使用 **PageIndex**（基于树结构的 RAG）进行文档检索。系统将审查标准分解为专项任务，分派给专家智能体执行审查（具备网络搜索能力），最终综合生成专业法律审查报告。

---

## 架构概览

```
┌─────────────────────┐         ┌──────────────────────┐
│   Main Workflow     │◄────────┤   MCP Client         │
│  （6 阶段流水线）    │         │  （工具代理）         │
└─────────────────────┘         └──────────────────────┘
         │                                │ stdio
         │                                ▼
         │                       ┌──────────────────────┐
         │                       │   MCP Server         │
         │                       │  （工具提供方）       │
         │                       └──────────────────────┘
         │                                │
         ▼                                ▼
┌─────────────────────┐         ┌──────────────────────┐
│   智能体集群        │          │  工具                │
│   - Planner         │         │  - ingest_docx       │
│   - Orchestrator    │         │  - build_pageindex_tree│
│   - Sub-Agents      │         │  - pageindex_search   │
│   - Reflector       │         │  - web_search         │
│   - Summarizer      │         │  - generate_report    │
└─────────────────────┘         └──────────────────────┘
```

---

## 工作流（6 阶段）

| 阶段           | 组件                                           | 操作                                                              |
| -------------- | ---------------------------------------------- | ----------------------------------------------------------------- |
| 1. 文件解析    | MCP: `ingest_docx`                             | 解析合同 + 审查标准 DOCX → Markdown                               |
| 2. 构建文档树  | MCP: `build_pageindex_tree`                    | 从合同 Markdown 构建 PageIndex 树                                 |
| 3. 任务规划    | `PlannerAgent`                                 | 将审查标准结构化为检查任务                                        |
| 4. 执行 + 反思 | `OrchestratorAgent` → `SubAgent` + `Reflector` | 逐条审查：pageindex_search → 子智能体审查 → 反思循环（最多 3 轮） |
| 5. 报告汇总    | `SummarizerAgent`                              | 汇总所有审查结果为报告文本                                        |
| 6. 生成报告    | MCP: `generate_final_report`                   | 生成带时间戳的 DOCX 报告                                          |

---

## 核心组件

### 1. 配置 — [config.py](file:///c:/Users/18014/agent_self_practice/deep_research_agent/config.py)

中央配置：`PROJECT_ROOT`、路径常量、`MAX_REFLECTION_ROUNDS`、`MAX_TOOL_CALLS`。通过 `dotenv` 加载 `.env` 中的 API 密钥。

### 2. 基础智能体 — [agents/base_agent.py](file:///c:/Users/18014/agent_self_practice/deep_research_agent/agents/base_agent.py)

基类，提供 LLM 对话、工具调用、上下文管理、Token 追踪、对话日志等通用功能。

### 3. 专项智能体 — [agents/](file:///c:/Users/18014/agent_self_practice/deep_research_agent/agents)

| 智能体           | 文件              | 职责                                                         |
| ---------------- | ----------------- | ------------------------------------------------------------ |
| **Planner**      | `planner.py`      | 解析审查标准 → 结构化 JSON 任务                              |
| **Orchestrator** | `orchestrator.py` | 逐条分派子智能体，执行反思循环                               |
| **SubAgent**     | （运行时创建）    | 针对单条标准审查合同，使用 `web_search` + `pageindex_search` |
| **Reflector**    | `reflector.py`    | 质量控制 — PASS/REJECT + 反馈                                |
| **Summarizer**   | `summarizer.py`   | 汇总审查结果为最终报告（不需 MCP）                           |

### 4. MCP Server — [mcp_server.py](file:///c:/Users/18014/agent_self_practice/deep_research_agent/mcp_service/mcp_server/mcp_server.py)

6 个工具：`web_search`、`read_url`、`ingest_docx`、`build_pageindex_tree`、`pageindex_search`、`generate_final_report`。

### 5. 工作流日志 — [workflow_logger.py](file:///c:/Users/18014/agent_self_practice/deep_research_agent/main_workflow/workflow_logger.py)

记录每个步骤，输出到 `logs/workflow_*.md`，包含 Mermaid 序列图和详细步骤信息。

---

## 目录结构

```
deep_research_agent/
├── main.py                       # 入口脚本
├── config.py                     # 中央配置（路径、常量、加载 .env）
├── .env                          # API 密钥（.gitignore 排除）
├── .env.example                  # 环境变量模板
├── pyproject.toml                # Python 项目配置
├── requirements.txt              # pip 依赖
├── agents/
│   ├── base_agent.py             # 基础 Agent 类
│   ├── agent_logger.py           # 智能体对话日志
│   ├── planner.py                # 标准 → 任务
│   ├── orchestrator.py           # 任务调度 + 反思循环
│   ├── reflector.py              # 质量控制
│   ├── summarizer.py             # 报告汇总
│   └── prompts/cn_prompts.py     # 中文提示词
├── mcp_service/
│   ├── mcp_client/
│   │   ├── mcp_minimal.py        # MCP 客户端封装
│   │   └── mcp_logger.py         # MCP 客户端日志配置
│   └── mcp_server/mcp_server.py  # 工具注册
├── main_workflow/
│   ├── main_workflow.py          # 6 阶段编排
│   └── workflow_logger.py        # 工作流日志（MD + Mermaid）
├── tools/
│   ├── document_tools.py         # 文件解析 + 报告生成
│   └── PageIndex-main/           # 基于树结构的 RAG 库
├── docs/
│   ├── contracts/                # 输入合同（.gitignore 排除）
│   └── contract_review_criteria/ # 审查标准（.gitignore 排除）
├── logs/                         # 所有运行时日志（.gitignore 排除）
│   ├── workflow/                 # 工作流日志（MD + Mermaid）
│   ├── conversations/            # 智能体对话日志（JSON）
│   └── mcp_client.log            # MCP 客户端日志
└── project_intro/
    ├── ARCHITECTURE.md           # 架构图
    └── PROJECT_OVERVIEW.md       # 本文件
```

---

## 环境配置

**`.env`**（参考 `.env.example`）：

```env
API_KEY=sk-...          # LLM API 密钥
BASE_URL=https://...    # LLM 端点
LLM_NAME=qwen-plus     # 模型名称
TOP_P=0.01             # 采样范围（越小越确定性）
SEED=42                # 随机种子（固定输出）
SERPER_API_KEY=...      # 网络搜索 API 密钥
```

**关键常量**（`config.py`）：

- `MAX_REFLECTION_ROUNDS = 3` — 反思循环上限
- `MAX_TOOL_CALLS = 10` — 工具调用上限
- `MAX_CONTEXT_TOKENS` — 根据模型自动设定

---

## 使用方法

```bash
pip install -r requirements.txt
pip install -e .
python main.py
```

**输出：**

1. 控制台实时显示 6 个阶段的进度
2. 报告保存至 `docs/reports_md/`（Markdown）+ 生成的 DOCX 路径
3. 工作流日志保存至 `logs/workflow_*.md`
4. 智能体对话日志保存至 `logs/conversations/`
