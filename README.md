# Deep Research Agent

面向合同审查场景的多智能体工作流。当前重点是本地 CLI + MCP 工具链：解析合同和审查标准，规划审查任务，按审查要点调用检索工具，结合制度文件检索结果进行审查，汇总结构化结果，并导出 Markdown、批注 DOCX 和 PDF 报告。

前端和 API 层暂不作为当前 README 的重点。现阶段主要入口是 `main.py`、MCP 工具和少量维护脚本。

## 当前架构

```text
main.py
  |
  v
main_workflow/
  |
  +--> agents/
  |
  +--> mcp_service/
          |
          v
        tools/
```

核心分层：

- `main.py`：本地运行入口，指定合同和审查标准文件。
- `main_workflow/`：工作流编排层，负责阶段顺序、日志、结果组装和报告生成调用。
- `agents/`：Planner、Orchestrator、Reflector、Summarizer 等智能体。
- `mcp_service/`：MCP client/server，向工作流暴露文件解析、检索和报告生成工具。
- `tools/document/`：文件解析、DOCX 清洗、报告生成。
- `tools/retrieval/`：合同检索和制度文件检索。

## 主审查工作流

主流程是一次合同审查运行，由 `python main.py` 触发。

```text
+-----------------------------+
| Phase 1: 文件解析            |
| Input : contract file        |
|         criteria file        |
| Tool  : MCP ingest_file      |
| Output: contract_md          |
|         criteria_md          |
+--------------+--------------+
               |
               v
+-----------------------------+
| Phase 2: 合同索引建立        |
| Input : contract_md          |
|         CONTRACT_RETRIEVAL_MODE |
| Tool  : build_pageindex_tree |
|         llamaindex_build_index |
|         or evidence mode     |
| Output: contract_index       |
|         pageindex: tree_json |
|         llamaindex: memory index |
|         evidence: no index   |
+--------------+--------------+
               |
               v
+-----------------------------+
| Phase 3: 审查任务规划        |
| Input : criteria_md          |
| Agent : Planner              |
| Output: criteria_list        |
+--------------+--------------+
               |
               v
+-----------------------------+
| Phase 4: 执行审查 + 反思     |
| Input : criteria_list        |
|         contract_index       |
|         institutional_search |
| Agent : Orchestrator         |
|         SubAgent per item    |
|         Reflector loop       |
| Output: results              |
+--------------+--------------+
               |
               v
+-----------------------------+
| Phase 5: 汇总 + Markdown渲染 |
| Input : results              |
| Agent : Summarizer           |
| Code  : report_renderer      |
| Output: report_markdown      |
+--------------+--------------+
               |
               v
+-----------------------------+
| Phase 6: 报告导出            |
| Input : report_markdown      |
|         results              |
|         original contract    |
| Tool  : generate_final_report|
| Code  : ReportGenerator      |
| Output: reports_md/*.md      |
|         reports_docx/*.docx  |
|         reports_pdf/*.pdf    |
+-----------------------------+
```

说明：

- Reflection 不是单独的 workflow phase。它在 Phase 4 的 Orchestrator 内部完成。
- Phase 2 的合同索引只为当前合同、当前运行服务，不保留持久索引。
- Phase 4 如果启用制度文件 RAG，会在每个审查要点执行时调用 `institutional_search`。

## 制度文件索引维护流程

制度文件索引不是 `main.py` 主流程的一部分，而是独立维护流程。你需要手动运行脚本建立或更新索引。

```text
+----------------------------------+
| Manual command                    |
| python scripts/build_institutional_index.py |
+----------------+-----------------+
                 |
                 v
+----------------------------------+
| 扫描制度文件目录                  |
| Input : docs/institutional_docs/  |
| Files : .docx .pdf .md .txt       |
+----------------+-----------------+
                 |
                 v
+----------------------------------+
| 对比 manifest                     |
| Input : institutional_manifest.json |
| Output: added / modified / deleted|
|         unchanged                 |
+----------------+-----------------+
                 |
                 v
+----------------------------------+
| 解析变化文件                      |
| Parser: MinerU or local parser    |
| Output: document text             |
+----------------+-----------------+
                 |
                 v
+----------------------------------+
| 建立或更新制度文件向量索引        |
| Engine: LlamaIndex                |
| Output: RAG_persist/institutional_index/ |
|         RAG_persist/institutional_manifest.json |
+----------------------------------+
```

制度文件索引的生命周期和合同索引不同：

- 制度文件索引是持久的。
- 制度文件索引支持增量更新。
- 制度文件索引保存在 `RAG_persist/`。
- 合同原文索引不允许持久保存。

## 检索设计

合同原文检索和制度文件检索是两套不同生命周期。

### 合同原文

合同原文不保留任何持久索引。

可选模式由 `.env` 显式设置：

```env
CONTRACT_RETRIEVAL_MODE=pageindex
```

可选值：

- `pageindex`：为当前合同临时构建 PageIndex 树，并通过树节点检索合同内容。
- `llamaindex`：为当前合同临时构建 LlamaIndex 向量索引，不写入 `RAG_persist/`。
- `evidence`：使用 EvidenceCollector 读取合同证据，不建立向量索引。

重要约束：

- 合同索引只存在于当前运行过程。
- 合同 PageIndex 树不再写入 `RAG_persist/pageindex_tree/`。
- 合同 LlamaIndex 不再写入持久向量目录。
- 每次运行 `main.py` 都会重新处理当前合同。

### 制度文件

制度文件使用持久索引，目录来自：

```env
INSTITUTIONAL_DOCS_DIR=docs/institutional_docs
ENABLE_INSTITUTIONAL_RAG=True
```

索引输出：

```text
RAG_persist/institutional_index/
RAG_persist/institutional_manifest.json
```

制度文件索引是手动维护的：

```powershell
python scripts\build_institutional_index.py
```

该脚本会根据 manifest 做增量更新：

- 新增文件：加入索引。
- 修改文件：删除旧节点后重新加入。
- 删除文件：从索引中删除。
- 未变化文件：跳过。

制度文件支持 `.docx`、`.pdf`、`.md`、`.txt`。文件解析策略与主工作流一致：如果 `PARSE_FILE_WITH_MINERU=True`，优先走 MinerU；否则走本地解析。

## Agent 输入输出数据结构

工作流内部优先传递结构化数据。Markdown 是最终导出格式，不再作为后续工具的数据源。

### Planner

输入：

```text
criteria_md: str
```

输出：

```python
{
    "criteria": [
        {
            "id": "C1",
            "section": "审查分类",
            "criterion": "审查标准正文",
            "check_points": ["检查点1", "检查点2"]
        }
    ]
}
```

该输出在 workflow 中记为：

```text
criteria_list: list[dict]
```

### Orchestrator / SubAgent / Reflector

每个审查任务的输入：

```python
{
    "id": "C1",
    "section": "审查分类",
    "criterion": "审查标准正文",
    "check_points": ["检查点1", "检查点2"]
}
```

Orchestrator 会补充上下文：

```text
contract_context: 来自 pageindex_search / llamaindex_search / evidence
institutional_context: 来自 institutional_search
```

SubAgent 输出结构化 JSON，核心是：

```python
{
    "status": "compliant | issues_found",
    "issues": [
        {
            "risk_level": "high | medium | low | none | unknown",
            "clause_location": "合同位置",
            "quoted_text": "合同原文证据",
            "issue_summary": "问题摘要",
            "analysis": "分析意见",
            "institutional_basis": "制度依据",
            "suggestion": "修改建议",
            "comment_text": "写入 Word 批注的内容"
        }
    ]
}
```

Reflector 在 Orchestrator 内部循环执行。它的输入是 SubAgent 的输出和当前审查标准；输出是：

```python
{
    "status": "PASS | REJECT",
    "feedback": "需要补充或修正的意见"
}
```

最终每个审查要点返回：

```python
{
    "criterion_id": "C1",
    "criterion": "审查标准正文",
    "section": "审查分类",
    "check_points": ["检查点1", "检查点2"],
    "status": "COMPLIANT | ISSUES_FOUND",
    "issues": [...],
    "review_output": "原始结构化审查输出",
    "reflection_rounds": 0,
    "tokens": 0,
    "error_message": None
}
```

workflow 中整体结果记为：

```text
results: list[dict]
```

调试时会写入：

```text
logs/workflow/last_results.json
```

### ReviewResult / ReviewIssue

共享结构定义在：

```text
main_workflow/review_schema.py
```

`ReviewIssue` 表示一个具体问题，核心字段：

```text
issue_id
criterion_id
section
criterion
risk_level
clause_location
quoted_text
issue_summary
analysis
institutional_basis
suggestion
comment_text
annotation_status
metadata
```

`ReviewResult` 表示一个审查要点的结果，核心字段：

```text
criterion_id
criterion
section
status
issues
raw_output
check_points
error_message
tokens
metadata
```

### Summarizer

输入：

```text
results: list[dict]
```

Summarizer 主要读取每个 issue 的：

```text
section
criterion_id
criterion
risk_level
clause_location
issue_summary
institutional_basis
suggestion
```

输出：

```python
{
    "overview": "报告概要",
    "priority_advice": "优先处理建议"
}
```

最终 Markdown 不是由 Summarizer 整篇生成，而是由：

```text
main_workflow/report_renderer.py
```

根据 `summary_sections + results` 程序化渲染。

## MCP 设计要点

MCP server 暴露的关键工具包括：

- `ingest_file`：解析合同或审查标准。
- `build_pageindex_tree`：为当前合同临时建立 PageIndex 树。
- `pageindex_search`：检索 PageIndex 树。
- `llamaindex_build_index`：为当前合同临时建立 LlamaIndex 索引。
- `llamaindex_search`：检索当前合同临时 LlamaIndex。
- `institutional_search`：检索制度文件持久索引。
- `generate_final_report`：生成最终报告。

近期重要调整：

- 当 `CONTRACT_RETRIEVAL_MODE=llamaindex` 时，MCP server 启动时会预热 LlamaIndex engine。
- 预热只初始化 LLM、Embedding、Reranker 调用对象，不读取合同、不生成合同向量、不保存合同索引。
- 这样可以避免在 `llamaindex_build_index` 请求处理中懒加载 LlamaIndex 导致长时间卡住。

## 报告生成

报告生成入口：

```text
tools/document/report_generator.py
```

它负责：

- 保存 Markdown 报告到 `docs/reports_md/`。
- 如果原合同是 DOCX，并且审查结果中有可定位证据，则生成带批注的 DOCX 到 `docs/reports_docx/`。
- 调用 Pandoc + xelatex 从 Markdown 生成 PDF 到 `docs/reports_pdf/`。

PDF 生成依赖：

- Python 包：`pypandoc-binary`
- 本机软件：`xelatex`，通常来自 MiKTeX、TeX Live 或 TinyTeX
- 中文字体：当前配置使用 `SimSun`

如果 PDF 没生成，而 MD/DOCX 已生成，优先检查：

```powershell
python -c "import pypandoc; print(pypandoc.get_pandoc_version())"
xelatex --version
```

## 运行方式

安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

配置 `.env`：

```powershell
Copy-Item .env.example .env
```

至少需要配置：

```env
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_NAME=qwen-plus

EMBED_API_KEY=your_api_key_here
EMBED_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBED_NAME=text-embedding-v4

CONTRACT_RETRIEVAL_MODE=pageindex
ENABLE_INSTITUTIONAL_RAG=True
INSTITUTIONAL_DOCS_DIR=docs/institutional_docs
PARSE_FILE_WITH_MINERU=True
```

运行制度文件索引：

```powershell
python scripts\build_institutional_index.py
```

运行单合同审查：

```powershell
python main.py
```

## 目录说明

```text
agents/                         智能体实现
main_workflow/                  工作流编排
mcp_service/                    MCP client/server
tools/document/                 文件解析、清洗、报告生成
tools/retrieval/                PageIndex、LlamaIndex、制度文件检索
scripts/                        手动维护脚本
docs/contracts/                 本地测试合同
docs/contract_review_criteria/  审查标准
docs/institutional_docs/        制度文件
docs/reports_md/                Markdown 报告
docs/reports_docx/              DOCX / 批注 DOCX 报告
docs/reports_pdf/               PDF 报告
logs/                           运行日志
RAG_persist/                    制度文件持久索引
```

## 重要约束

- 合同原文不得保留持久索引。
- `RAG_persist/` 只用于制度文件索引。
- `CONTRACT_RETRIEVAL_MODE` 必须显式设置为 `pageindex`、`llamaindex` 或 `evidence`。
- 结构化审查结果是后续 Markdown、DOCX 批注和 PDF 报告的共同数据来源。
- 不再依赖 formatter 生成最终报告文本，报告更偏向由结构化结果程序化渲染。
- 当前默认工作方式是本地 CLI 调试；前端/API 不是当前主线。
