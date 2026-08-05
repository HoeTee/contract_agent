# 智能体与工作流架构

本文说明合同审查的智能体（agent）与工作流（workflow）架构。工作流编排在 `workflow/workflow.py`，各 agent 在 `agents/`，检索与文档解析能力通过 MCP 工具提供。

## 总览

`ContractReviewWorkflow` 是单次合同审查的总编排层。它只负责阶段顺序、进度上报、日志和最终结果组装；解析、检索、逐条审查、汇总等细节交给各 agent 和 MCP 工具。

当前是简化工作流：没有 web search，也没有接入制度 RAG，检索模式固定为 LlamaIndex。

## 工作流 6 个阶段

| 阶段 | 实现 | 说明 |
| --- | --- | --- |
| 1. 解析 ingest | MCP `ingest_file` | 把合同和审查标准 DOCX 转成 markdown |
| 2. 建索引 build_index | MCP `llamaindex_build_index` | 为合同 DOCX XML anchor 节点建临时 LlamaIndex 向量索引 |
| 3. 规划 plan | `PlannerAgent.design_tasks` | 把审查标准 markdown 拆成结构化任务 `criteria_list` |
| 4. 执行+反思 execute | `OrchestratorAgent.execute_criteria` | 逐条审查标准，产出 `results` |
| 5. 汇总 summarize | `SummarizerAgent.compile_summary_comment` | 由 `results` 生成 `summary_sections` |
| 6. 批注 generate | MCP `generate_docx_report` | 用 `results` + `summary_sections` 生成批注版 DOCX |

每个阶段会通过 `progress_callback` 上报阶段名，便于前端展示进度：`ingesting`、`building_index`、`planning`、`reviewing`、`summarizing`、`generating_docx`、`completed`。

## 智能体角色

| Agent | 文件 | 职责 | 输入 | 输出 |
| --- | --- | --- | --- | --- |
| PlannerAgent | `agents/planner.py` | 把审查标准拆成结构化审查任务 | 审查标准 markdown | `criteria_list`（id / section / criterion / check_points） |
| OrchestratorAgent | `agents/orchestrator.py` | 逐条派发 SubAgent，串联检索、反思、并发控制 | `criteria_list` | `results` |
| SubAgent | `agents/base_agent.py` 的 `Agent` + `SUB_AGENT_BASE_PROMPT` | 审查单条标准，可调用白名单允许的 MCP 工具 | 标准 + 检索上下文 + 可见工具 | `SubAgentOutput`（status / issues） |
| ReflectorAgent | `agents/reflector.py` | 质量复核 SubAgent 输出 | criterion + subagent_output + 补充检索 | `{ status: PASS/REJECT, feedback }` |
| SummarizerAgent | `agents/summarizer.py` | 汇总所有结果生成开头总览批注 | `results` | `{ overall_comment, priority_comments }` |

基础设施：`agents/base_agent.py`（`Agent` 基类与 `Settings` 模型配置）、`agents/schemas.py`（结构化输出 schema）、`agents/prompts/cn_prompts.py`（所有提示词，含审查边界）。

## 智能体结构化输出 schema

各 agent 的输出由 `agents/schemas.py` 的 Pydantic 模型严格校验（`extra=forbid`，不接受未定义字段）。类与字段如下：

```python
class PlannerCriterion:
    id: str
    section: str
    criterion: str
    check_points: list[str]

class PlannerOutput:
    criteria: list[PlannerCriterion]

class SubAgentIssue:
    issue_id: str
    risk_level: Literal["high", "medium", "low"]
    anchors: list[SubAgentAnchor]
    reasoning: str
    criterion: str
    check_point: str

class SubAgentAnchor:
    xml_anchor_type: Literal["paragraph", "table"]
    xml_anchor_id: str
    quoted_text: str
    comment_text: str                     # 1~100 字

class SubAgentOutput:
    status: Literal["compliant", "issues_found", "not_applicable"]
    applicability_reason: str = ""
    issues: list[SubAgentIssue] = []

class ReflectorOutput:
    status: Literal["PASS", "REJECT"]
    feedback: str = ""

class SummaryOutput:
    overall_comment: str = ""
    priority_comments: list[str] = []     # overall + priority 合计 <=200 字
```

## 单条标准的执行与反思循环

`OrchestratorAgent.execute_single_criterion` 负责一条审查标准的完整处理：

1. 检索：调用 MCP `llamaindex_search`（query = 标准 + 检查要点），得到合同相关片段 `context`。检索结果会加一段 guardrail 提示，防止把“检索结果 1/2”“相关度分数”等检索包装文本误当成合同条款位置，并提供 `xml_anchor_type/xml_anchor_id` 给 SubAgent 复用。
2. SubAgent 审查：以 `SUB_AGENT_BASE_PROMPT` 创建 `SubAgent_<cid>`，只向模型暴露 `workflow.subagent_allowed_tools` 白名单中的 MCP 工具，输出 `SubAgentOutput`，`status` 为 `compliant` / `issues_found` / `not_applicable`，`issues[].anchors` 含 `xml_anchor_type`、`xml_anchor_id`、`quoted_text`、`comment_text` 等字段。
3. 若 `status == compliant`：短路，跳过反思直接返回。
4. 否则进入反思循环，最多 `MAX_REFLECTION_ROUNDS` 轮：
   - 对 `quoted_text` 为空的“缺失类” issue 再检索一次，生成 `missing_text_review_notes` 供 Reflector 判断。
   - `Reflector.review` 返回 `PASS` 或 `REJECT`。
   - `PASS` 跳出循环；`REJECT` 则 SubAgent 按 `feedback` 补充完善，再进入下一轮。
5. 返回该 criterion 结果：`criterion_id`、`section`、`issues`、`status`、`applicability_reason`、`tokens`。

并发与容错（`execute_criteria`）：

- 用 `asyncio.Semaphore(MAX_ORCHESTRATOR_CONCURRENCY)` 控制并发条数。
- 单条 criterion 抛 `ModelCallError` 会直接上抛，导致整次审查失败。
- 其他异常会被降级为该条 `status=ERROR`（记录 `error_message`），不影响其它 criterion。

## 数据流

```text
审查标准 DOCX -> ingest -> 审查标准 markdown -> Planner -> criteria_list
合同 DOCX     -> DOCX XML anchor nodes -> LlamaIndex 临时索引
每条 criterion: 检索 context -> SubAgent(可调用白名单工具) -> (Reflector 反思循环) -> 单条结果
所有单条结果 -> results -> Summarizer -> summary_sections
results + summary_sections -> generate_docx_report -> 批注版 DOCX
```

其中 `results` 决定逐条问题批注，`summary_sections` 决定文档开头总览批注。LlamaIndex DOCX anchor 检索链路见 `DOCX_XML_ANCHOR_INDEXING.md`，批注写入与 `quoted_text` 定位细节见 `DOCX_ANNOTATION_DESIGN.md`。

## 架构边界

- 简化工作流：无 web search、无制度 RAG，检索模式固定为 LlamaIndex。
- 审查只基于合同文本与检索片段；依赖外部数据或法律知识库的检查点处理方式见 `REVIEW_BOUNDARIES.md`。

## SubAgent 工具白名单

MCP server 可以暴露多个工具，但 SubAgent 不直接继承完整 MCP 工具列表。`OrchestratorAgent` 创建 SubAgent 前会根据 `config.yaml` 过滤工具：

```yaml
workflow:
  subagent_allowed_tools:
    - "llamaindex_search"
```

字段含义：

- `workflow.subagent_allowed_tools`：SubAgent 可见 MCP 工具白名单。
- 配置缺失时默认只允许 `llamaindex_search`。
- 配置为空列表时，SubAgent 不可调用任何 MCP 工具。
- 配置了 MCP server 未暴露的工具名时，该工具不会传给 SubAgent，程序不会回退为完整工具列表。

`llm.max_tool_calls` 仍是当前 `Agent` 的工具调用次数上限。不要在没有明确不同语义时新增另一个 SubAgent 工具次数配置；否则会形成两个配置控制同一件事。
