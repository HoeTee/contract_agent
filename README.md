# Deep Research Agent

Deep Research Agent 是一个合同审查服务。它接收合同 DOCX，读取审核要点，调用 LLM、临时合同检索和多 agent 审查流程，最后输出一份保留原合同正文结构的批注版 DOCX。

当前主流程只生成批注 DOCX，不把 Markdown/PDF 报告作为主输出。

## 运行入口

### API 服务

生产集成推荐使用 FastAPI 服务：

```powershell
uvicorn app:app --host 0.0.0.0 --port 5000
```

健康检查：

```powershell
curl http://localhost:5000/health
```

上传合同并保存返回结果：

```powershell
curl -X POST "http://localhost:5000/review" `
  -F "file=@docs/contracts/你的合同.docx" `
  --output result.docx
```

API 模式下，上传合同和输出结果会写入单次请求的临时目录 `runtime_temp/reviews/<request_id>/`，接口返回前读入内存，请求结束后删除该目录。服务启动和关闭时也会清空 `runtime_temp/reviews/`。

### 本地测试脚本

`main.py` 保留为本地测试入口：

```powershell
python main.py
```

`main.py` 使用固定合同样例和固定审核要点文件，输出目录由 `.env` 中的 `CLI_OUTPUT_DIR` 指定，默认建议为：

```env
CLI_OUTPUT_DIR=docs/reports_docx
```

## 必要配置

从 `.env.example` 创建 `.env`，至少设置：

```env
LLM_API_KEY=...
LLM_BASE_URL=...
LLM_NAME=qwen-plus

EMBED_API_KEY=...
EMBED_BASE_URL=...
EMBED_NAME=text-embedding-v4

RERANK_API_KEY=...
RERANK_BASE_URL=...
RERANK_NAME=qwen3-rerank

PARSE_FILE_WITH_MINERU=True
CLI_OUTPUT_DIR=docs/reports_docx
ENABLE_WORKFLOW_LOGS=False
MAX_ORCHESTRATOR_CONCURRENCY=8
MAX_API_CONCURRENT_REVIEWS=1
```

`ENABLE_WORKFLOW_LOGS` 是必填项。未填写时程序会启动失败。它控制文件日志是否落盘：

- `False`：API 部署推荐值，不写 workflow、agent conversation、MCP client 文件日志。
- `True`：本地调试推荐值，保留日志文件便于排查。

控制台输出不受该变量完全关闭，Docker/uvicorn 仍可看到基础运行信息。

## 并发控制

当前服务有两层并发控制：

- `MAX_ORCHESTRATOR_CONCURRENCY`：单个合同审查内部，同时执行的审查标准数量。默认值为 `8`。
- `MAX_API_CONCURRENT_REVIEWS`：API 层同时处理的完整合同审查请求数量。默认值为 `1`；显式设置为 `0` 时表示 API 层不限制并发。

根据 `results/` 中的模型压测结果，当前推荐配置为：

```env
MAX_ORCHESTRATOR_CONCURRENCY=8
MAX_API_CONCURRENT_REVIEWS=1
```

如果 API 层不限制并发，总模型压力大约会随同时处理的合同数线性放大。例如 `MAX_ORCHESTRATOR_CONCURRENCY=8` 且同时处理 3 个合同审查请求时，最多可能有约 24 条审查标准并发执行。

## Agent 架构

系统采用多 agent 编排，但核心执行入口统一在 `ContractReviewWorkflow`：

```text
app.py / main.py
  -> ContractReviewWorkflow
    -> PlannerAgent
    -> OrchestratorAgent
      -> SubAgent_N
      -> ReflectorAgent
    -> SummarizerAgent
    -> MCP tools
```

主要 agent：

- `PlannerAgent`：读取审核要点，拆分成结构化审查标准和检查点。
- `OrchestratorAgent`：针对每条审查标准检索合同上下文，并并发调度单项审查。
- `SubAgent_<criterion_id>`：执行单条审查标准，输出结构化问题列表。
- `ReflectorAgent`：校验单项审查结果的格式、引用和修改建议质量。
- `SummarizerAgent`：根据所有审查结果生成总体批注和优先修改建议。

## 单 Agent 设计

所有 LLM agent 基于 `agents/base_agent.py` 中的 `Agent`：

- 使用 OpenAI-compatible `AsyncOpenAI` 客户端，由 `.env` 中的 `LLM_*` 配置模型服务。
- 支持 MCP 工具调用，工具 schema 来自 MCP client。
- 维护 messages、token usage、tool call count。
- 使用 `MAX_CONTEXT_TOKENS`、`MAX_RESULT_TOKENS`、`MAX_TOOL_CALLS` 控制上下文和工具调用规模。
- 通过 `chat_until_valid_json` 对 Planner、SubAgent、Reflector、Summarizer 的 JSON 输出做结构校验和重试。

单 agent 不直接访问文件系统业务目录，文件解析、检索和报告生成通过 MCP 工具完成。

## 工作流设计

`ContractReviewWorkflow.run(contract_path, criteria_path, output_dir, ...)` 是统一工作流入口。`output_dir` 必须显式传入：

- API 模式传入单次请求临时目录。
- `main.py` 传入 `CLI_OUTPUT_DIR`。

执行阶段：

1. `ingest_file` 解析合同和审核要点为 Markdown 文本。
2. `llamaindex_build_index` 为当前合同构建临时内存索引。
3. `PlannerAgent` 从审核要点中抽取审查标准。
4. `OrchestratorAgent` 对每条标准检索合同上下文并启动单项审查。
5. `ReflectorAgent` 对有问题的审查结果进行反思校验，最多 `MAX_REFLECTION_ROUNDS` 轮。
6. `SummarizerAgent` 生成总览批注。
7. `generate_docx_report` 将审查意见写回原合同副本并输出批注版 DOCX。

工作流返回结构包含输出 DOCX 路径、审查项数量、问题数量、token 统计和可选日志路径。

## 工具设计

工具通过 MCP server 暴露，当前主流程使用：

- `ingest_file`：解析 DOCX/PDF/TXT 文件为 Markdown-like 文本。
- `llamaindex_build_index`：构建当前合同的临时 LlamaIndex 索引。
- `llamaindex_search`：按审查标准检索当前合同相关片段。
- `generate_docx_report`：在指定 `output_dir` 中生成批注版 DOCX。

`generate_markdown_report` 和 `generate_pdf_report` 仍存在，但不是当前主流程输出。

工具调用由 `MinimalMCPClient` 负责：

- 启动并连接 MCP server。
- 拉取可用工具列表供 agent tool calling 使用。
- 将 LLM tool call 转换为 MCP tool 调用。
- 把工具返回内容写回 agent message history。

## 解析设计

合同和审核要点走同一个解析入口：

```text
ingest_file
  -> FileParser
    -> MinerU parser 或 DefaultFileParser
```

解析策略由 `PARSE_FILE_WITH_MINERU` 控制：

- `True`：优先走 MinerU 解析链路。
- `False`：走本地 `DefaultFileParser`。

本地解析支持：

- `.docx`：使用 `python-docx` 读取段落，并将 Word heading 样式转换为 Markdown 标题。
- `.pdf`：使用 `pypdf.PdfReader` 抽取页面文本。
- `.txt`：按 UTF-8 文本读取。

当前 API 第一版只接受 `.docx` 上传，因为批注输出依赖 DOCX 原文结构。

## 检索设计

当前合同检索是临时 RAG：

```text
合同 Markdown
  -> LlamaIndex temporary in-memory index
  -> llamaindex_search
  -> Orchestrator context
```

特点：

- 每次工作流为当前合同构建临时索引。
- 当前合同索引不持久化到 `RAG_persist/`。
- 使用 OpenAI-compatible embedding 配置：`EMBED_API_KEY`、`EMBED_BASE_URL`、`EMBED_NAME`。
- 如配置 `RERANK_*`，检索结果会经过 Qwen rerank postprocessor。
- `local_tokenizers/Qwen3-Embedding-8B` 用于本地 tokenizer，Docker 离线镜像中需要包含该目录。

代码中保留了制度文档 persistent index 能力，但当前主工作流没有启用制度库 RAG。

## 批注设计

批注输出基于原合同 DOCX 副本：

1. 先清理原始 DOCX 中可能影响处理的兼容内容。
2. 将清理后的合同复制到 `output_dir`。
3. 遍历审查结果中的 `issues`。
4. 用 `quoted_text` 在正文段落和表格单元格中寻找最匹配 anchor。
5. 匹配成功的问题批注挂在对应段落。
6. 无法匹配到原文的问题合并为一条“缺失内容”批注，挂在文档开头。
7. 总结批注也挂在文档开头。

批注写入使用 DOCX OPC XML 操作创建或更新 `word/comments.xml`，不是生成独立审查报告。

## 日志设计

文件日志由 `ENABLE_WORKFLOW_LOGS` 统一控制：

- `logs/workflow/workflow_*.md`
- `logs/workflow/last_results.json`
- `logs/workflow/last_run_summary.json`
- `logs/conversations/run_*/`
- `logs/mcp/mcp_client.log`

关闭日志时，上述文件不落盘；工作流返回中的日志路径为 `None`。这适合 API 服务处理业务合同的场景。

保留日志设计的原因是本地调试、模型输出质量排查和工具调用排查仍然需要完整链路信息。

## API 集成设计

业务系统建议把本服务作为独立 HTTP 服务调用：

```text
业务系统后端
  -> POST /review multipart/form-data 上传合同 DOCX
  -> 接收返回的批注版 DOCX bytes
  -> 自行决定是否保存、下载或进入审批流
```

本服务不负责业务系统的用户、权限、流程和持久化，只负责合同审查计算。

如果审查耗时超过业务网关超时时间，后续建议升级为异步任务接口：

- `POST /review` 返回 `job_id`
- `GET /review/{job_id}/status` 查询状态
- `GET /review/{job_id}/result` 下载结果

当前版本先使用同步接口，便于联调。

## Docker 离线部署要点

建议在有互联网的环境构建镜像，再导出到内网：

```powershell
docker build -t deep-research-agent:offline .
docker save deep-research-agent:offline -o deep-research-agent-offline.tar
```

内网机器：

```powershell
docker load -i deep-research-agent-offline.tar
docker compose up
```

离线环境的 compose 文件应使用已加载镜像：

```yaml
image: deep-research-agent:offline
```

不要在无互联网环境中执行 `docker compose build`，除非已经准备好所有 Python wheels、基础镜像和系统包镜像源。

## 目录说明

```text
app.py                         FastAPI 服务入口
main.py                        本地测试入口
config.py                      全局配置和必填环境变量校验
main_workflow/                 工作流编排
agents/                        Planner / Orchestrator / Reflector / Summarizer
mcp_service/                   MCP client/server
tools/document/                文件解析、DOCX 清理、批注 DOCX 生成
tools/retrieval/llamaindex/    当前合同临时检索
local_tokenizers/              离线 tokenizer 资源
runtime_temp/                  API 请求临时目录，不应提交
logs/                          可选调试日志目录
```
