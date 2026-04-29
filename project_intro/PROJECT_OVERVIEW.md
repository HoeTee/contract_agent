# 项目概览

## 1. 项目定位

`deep_research_agent` 是一个面向合同审查场景的多智能体系统，目标是把「文档解析、条款检索、逐项审查、报告生成」串成一条可重复执行的自动化流程。

当前仓库（分支 `rollback-0313-with-mineru`）专注于核心后端实现：

- 工作流引擎：负责编排解析、检索、审查、反思与汇总
- 多智能体协作层：Planner、Orchestrator、EvidenceCollector、Reflector、Summarizer
- MCP 工具层：统一暴露文件解析、检索、报告生成、网页搜索等能力
- CLI 入口：`main.py`，便于本地链路调试

> 本分支不包含前端工作台与 FastAPI Web 服务。如果你看到的旧版本文档提到 `frontend/` 或 `api/`，那是之前 Web 形态的描述，不适用于当前仓库。

## 2. 适用场景

适合以下类型的任务：

- 对合同正文进行批量审查
- 根据「审核要点 / 审查标准」逐项检查合同
- 输出结构化问题清单和正式报告
- 对同一份合同切换不同检索策略做效果对比

## 3. 核心能力

### 3.1 多智能体协作

系统包含以下核心角色：

- `Planner`
  - 把审查标准拆成结构化任务列表

- `Orchestrator`
  - 调度检索、子智能体执行和反思循环

- `EvidenceCollector`
  - 在 `evidence` 模式下逐段收集证据

- `Reflector`
  - 对子智能体输出进行质量复核

- `Summarizer`
  - 汇总所有审查结果，输出最终报告

### 3.2 三种检索模式

系统支持三种检索模式：

| 模式 | 标识 | 说明 | 适合场景 |
| --- | --- | --- | --- |
| LlamaIndex 向量检索 | `llamaindex` | 向量召回 + 可选重排 | 长文档、语义召回要求高 |
| PageIndex 树检索 | `pageindex` | 基于文档结构树的两阶段检索 | 条款结构较清晰的合同 |
| Evidence Collector | `evidence` | 按章节迭代提取证据 | 需要更细粒度证据整理 |

其中：

- 默认检索模式由 `.env` 中的 `LLAMA_INDEX` 与 `PAGEINDEX_SEARCH` 推导（详见 `config.py`）
- 检索模式由 `.env` 唯一决定，工作流与 Orchestrator 不再支持通过参数覆盖

### 3.3 多格式报告输出

系统会生成三类产物：

- Markdown 报告
- DOCX 报告
- PDF 报告

当原始合同为 `.docx` 时，DOCX 导出会优先尝试基于原合同插入批注，而不是简单另存为纯报告文档。

### 3.4 可观测性

系统会保留：

- 工作流日志（`logs/workflow/`）
- 智能体对话日志（`logs/conversations/`）
- MCP 客户端日志（`logs/mcp/`）
- RAG 索引或树缓存（`RAG_persist/`）

这使得它更适合调试、复盘和后续优化。

## 4. 运行形态

当前仓库提供 CLI 模式：

入口：

- [`main.py`](../main.py)

特点：

- 直接在本地执行完整工作流
- 适合开发调试和效果验证
- 通过本地脚本路径以子进程方式启动 MCP（`mcp_service/mcp_server/mcp_server.py`），不需要单独拉起 HTTP 服务

如果未来需要 Web 形态（FastAPI + 前端），可在此基础上自行扩展，详见 `DEPLOYMENT.md` 末尾的扩展方向。

## 5. 工作流主链路

一次合同审查任务大致分为 6 个阶段：

1. 文件解析
   - 解析合同与审查标准文件

2. 建树或建索引
   - `pageindex` / `evidence` 模式构建结构树
   - `llamaindex` 模式构建向量索引

3. 任务规划
   - 从审查标准提取结构化审查项

4. 审查执行
   - 检索证据
   - 子智能体逐项审查
   - Reflector 做质量复核

5. 结果汇总
   - Summarizer 汇总所有审查项

6. 报告导出
   - 生成 `md`、`docx`、`pdf`

## 6. 项目结构

```text
deep_research_agent/
├── agents/                     # 智能体实现
├── main_workflow/              # 6 阶段工作流编排
├── mcp_service/                # MCP 客户端与服务端
├── tools/                      # 文件解析、检索、报告生成
├── RAG_persist/                # 索引、树缓存、manifest
├── project_intro/              # 项目说明文档
├── config.py                   # 全局配置与默认检索模式
├── DEPLOYMENT.md               # 部署 / 运行说明
├── main.py                     # CLI 调试入口
├── requirements.txt
└── pyproject.toml
```

> 实际运行时还会在根目录下生成 `docs/`、`uploads/`、`logs/` 等数据目录，这些不是源代码的一部分，但属于运行产物。

## 7. 关键模块说明

| 模块 | 位置 | 作用 |
| --- | --- | --- |
| 配置 | `config.py` | 统一维护路径、默认检索模式、LLM 上下文配置 |
| 工作流 | `main_workflow/main_workflow.py` | 编排完整合同审查链路 |
| 智能体 | `agents/` | 规划、检索调度、反思、汇总 |
| MCP 服务 | `mcp_service/mcp_server/mcp_server.py` | 注册文件解析、检索、报告生成、网页搜索工具 |
| MCP 客户端 | `mcp_service/mcp_client/` | 工作流调用 MCP 的封装 |
| 文档解析 | `tools/document/` | MinerU、本地 PDF/DOCX 解析与回退 |
| 检索 | `tools/retrieval/` | PageIndex 与 LlamaIndex 实现 |
| CLI 入口 | `main.py` | 本地一键跑完整工作流 |

## 8. 输入与输出

### 8.1 输入

- 合同文件（默认放在 `docs/contracts/`）
- 审查标准文件（默认放在 `docs/contract_review_criteria/`）
- 可选：在工作流调用处显式指定检索模式

CLI 入口当前限制上传后缀为：

- `.pdf`
- `.docx`

### 8.2 输出

结构化输出包括：

- 审查问题清单
- 分条审查结果
- Markdown 报告
- DOCX 报告
- PDF 报告

文件输出目录：

- `docs/reports_md/`
- `docs/reports_docx/`
- `docs/reports_pdf/`

## 9. 当前实现特点

### 9.1 优点

- 检索策略可切换
- 有明确的阶段化状态
- 报告导出链路完整
- 日志较全，便于排查
- 适合继续演进成更完整的审查平台

### 9.2 当前限制

- 仅有 CLI 形态，没有 Web 前端或 HTTP API
- MCP 通过本地脚本进程方式调用，未对外暴露 HTTP 端点
- 没有数据库、任务队列、鉴权
- 外部模型、网页搜索、MinerU 等能力都依赖外部服务稳定性

## 10. 你应该先看哪份文档

如果你的目标是：

- 了解部署和运行方式：看 [`DEPLOYMENT.md`](../DEPLOYMENT.md)
- 了解整体架构：看 [`ARCHITECTURE.md`](./ARCHITECTURE.md)
- 想直接跑一遍：先看 `DEPLOYMENT.md` 里的本地运行章节，再回到根目录执行 `python main.py`
