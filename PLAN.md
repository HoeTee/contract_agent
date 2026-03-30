# 项目重构计划

## 现状分析

当前项目存在以下核心问题：
1. **路由逻辑混乱**：`PAGEINDEX_SEARCH` 和 `LLAMA_INDEX` 两个开关的组合路径不清晰
2. **tools/ 目录结构混乱**：PageIndex-main 是外部库直接放进来的，LlamaIndex 未集成
3. **LlamaIndex 未接入 MCP**：只是一个独立的 TRAD_RAG 类
4. **MCP Server 的 pageindex_search** 虽然发送的是去除 text 的树结构（非全文），但树结构本身在大文档时仍然很大，缺少摘要导航的两阶段策略
5. **Token 追踪缺失**：MCP Server 内部的 LLM 调用（pageindex_search、build_pageindex_tree 的 summary 生成）token 完全未返回

---

## 重构目标

```
.env 配置组合：
┌─────────────────┬──────────────────┬─────────────────────────────┐
│ LLAMA_INDEX     │ PAGEINDEX_SEARCH │ 行为                         │
├─────────────────┼──────────────────┼─────────────────────────────┤
│ False           │ False            │ PageIndex 树 + EvidenceCollector │
│ False           │ True             │ PageIndex 树 + pageindex_search  │
│ True            │ (忽略)           │ LlamaIndex RAG via MCP tool      │
└─────────────────┴──────────────────┴─────────────────────────────┘
```

---

## 阶段一：config.py 和 .env 清理

**目标**：统一配置入口，明确三条路径

1. 在 `.env.example` 中添加 `LLAMA_INDEX=False`
2. 在 `config.py` 中加载 `LLAMA_INDEX` 布尔值
3. 确保 `PAGEINDEX_SEARCH` 仅在 `LLAMA_INDEX=False` 时生效
4. 添加配置校验：启动时打印当前使用的检索模式

**改动文件**：`config.py`, `.env.example`

---

## 阶段二：tools/ 目录整理

**目标**：清晰的目录结构

当前：
```
tools/
├── document_tools.py
├── clean_docx.py
├── PageIndex-main/          # 外部库，直接复制进来的
├── LlamaIndex/
│   ├── LlamaIndex.py        # TRAD_RAG 类
│   ├── qwen_reranker.py
│   └── playground.py (已删除)
└── document/parsers/
    └── mineru_pdf_parser.py
```

整理后：
```
tools/
├── document/
│   ├── file_parser.py        # 从 document_tools.py 拆出文件解析
│   ├── report_generator.py   # 从 document_tools.py 拆出报告生成
│   ├── clean_docx.py         # 保持不变
│   └── parsers/
│       └── mineru_pdf_parser.py
├── retrieval/
│   ├── pageindex/            # PageIndex-main 内容移入
│   │   ├── __init__.py
│   │   ├── page_index_md.py
│   │   └── utils.py
│   └── llamaindex/
│       ├── __init__.py
│       ├── rag_engine.py     # 重命名自 LlamaIndex.py，类名 TRAD_RAG → LlamaIndexRAG
│       └── qwen_reranker.py
└── __init__.py
```

**改动**：
- 拆分 `document_tools.py` → `file_parser.py` + `report_generator.py`
- 移动 `PageIndex-main/pageindex/` → `tools/retrieval/pageindex/`
- 重命名 `LlamaIndex/LlamaIndex.py` → `tools/retrieval/llamaindex/rag_engine.py`
- 更新所有 import 路径

---

## 阶段三：LlamaIndex 接入 MCP Server

**目标**：将 LlamaIndex 作为 MCP tool 暴露

在 `mcp_server.py` 中新增两个工具：

```python
@mcp.tool()
async def llamaindex_build_index(markdown_content: str) -> str:
    """使用 LlamaIndex 构建向量索引，返回索引 ID"""
    # 1. 将 markdown 写入临时文件
    # 2. 调用 LlamaIndexRAG 构建索引（embedding + vector store）
    # 3. 持久化到 RAG_persist/
    # 4. 返回索引标识 + token usage JSON

@mcp.tool()
async def llamaindex_search(query: str, index_id: str) -> str:
    """使用 LlamaIndex 向量检索 + 重排序"""
    # 1. 加载已有索引
    # 2. retriever.retrieve(query) + reranker
    # 3. 返回检索结果 + token usage JSON
```

**改动文件**：`mcp_server.py`, `tools/retrieval/llamaindex/rag_engine.py`

---

## 阶段四：改进 pageindex_search 为两阶段摘要导航

**目标**：避免将整棵树结构一次性发给 LLM

当前实现：去除 text 后将整棵树（含 node_id, title, summary, 层级结构）一次发给 LLM → 返回 node_id 列表。

改进为**两阶段**：

**阶段 A：顶层摘要选择**
```
只发送第一层节点的 {node_id, title, summary} 列表
→ LLM 选择相关的顶层节点
```

**阶段 B：子树细化**
```
对每个选中的顶层节点，发送其子树的 {node_id, title, summary}
→ LLM 选择最终的叶子节点
→ 提取对应 text
```

好处：
- 每次 LLM 调用的 context 更小
- 大文档（100+ 节点）不会溢出
- 保留了结构感知的优势

**改动文件**：`mcp_server.py` 中的 `pageindex_search` 函数

---

## 阶段五：main_workflow.py 重构

**目标**：简化工作流，根据配置走不同路径

```python
class ContractReviewWorkflow:
    async def run(self):
        # Phase 1: Ingest (不变)
        contract_md = await self._ingest(contract_path)
        criteria_md = await self._ingest(criteria_path)

        # Phase 2: Build Index (根据模式不同)
        if LLAMA_INDEX:
            index_ref = await self._build_llamaindex(contract_md)
        else:
            tree_json = await self._build_pageindex_tree(contract_md)

        # Phase 3: Plan (不变)
        criteria_list = await self._plan(criteria_md)

        # Phase 4: Execute (统一接口，内部分支)
        results = await self._execute_criteria(
            criteria_list,
            index_ref if LLAMA_INDEX else tree_json
        )

        # Phase 5-6: Summarize + Report (不变)
```

**在 orchestrator.py 中统一检索接口**：

```python
async def retrieve_context(self, criterion, index_data) -> str:
    if LLAMA_INDEX:
        return await self.mcp_client.call_tool("llamaindex_search", {...})
    elif PAGEINDEX_SEARCH:
        return await self.mcp_client.call_tool("pageindex_search", {...})
    else:
        collector = EvidenceCollectorAgent(...)
        return await collector.collect_evidence(criterion, index_data)
```

**改动文件**：`main_workflow.py`, `orchestrator.py`

---

## 阶段六：Token 追踪完善

**目标**：所有 LLM 调用的 token 都被追踪

### 6.1 MCP Server 端：返回 token usage

每个涉及 LLM 调用的 MCP tool 返回统一的 JSON 格式：

```json
{
  "result": "实际结果文本",
  "token_usage": {
    "prompt_tokens": 1234,
    "completion_tokens": 567,
    "total_tokens": 1801
  }
}
```

涉及的工具：
- `pageindex_search`：内部 LLM 调用追踪
- `build_pageindex_tree`：PageIndex 库的 summary 生成 LLM 调用追踪
- `llamaindex_search`：embedding 调用量追踪
- `llamaindex_build_index`：embedding 调用量追踪

### 6.2 MCP Client 端：解析 token usage

在 `mcp_minimal.py` 的 `call_tool` 中：
```python
async def call_tool(self, name, args):
    raw_result = await session.call_tool(name, args)
    text = self._extract_text(raw_result)

    # 尝试解析 JSON 格式的结果
    try:
        parsed = json.loads(text)
        if "token_usage" in parsed:
            self.accumulated_tokens += parsed["token_usage"]["total_tokens"]
            return parsed["result"]
    except:
        pass
    return text
```

### 6.3 Workflow 端：汇总所有 token

在最终报告中添加分项统计：
```
Token 使用统计：
- Planner: xxx tokens
- 检索（PageIndex/LlamaIndex）: xxx tokens  ← 新增
- 树构建（Summary 生成）: xxx tokens          ← 新增
- SubAgent 审查: xxx tokens
- Reflector 质控: xxx tokens
- Summarizer 汇总: xxx tokens
- 总计: xxx tokens
```

**改动文件**：`mcp_server.py`, `mcp_minimal.py`, `main_workflow.py`, `base_agent.py`

---

## 执行顺序

```
阶段一 (config)  ──→  阶段二 (tools整理)  ──→  阶段三 (LlamaIndex MCP)
                                                      │
                                               阶段四 (pageindex改进)
                                                      │
                                               阶段五 (workflow重构)
                                                      │
                                               阶段六 (token追踪)
```

阶段一和阶段二是基础，必须先做。阶段三、四可以并行。阶段五依赖三和四。阶段六贯穿但主要在最后完善。

---

## 风险点

1. **tools/ 目录重组会导致大量 import 变更**：需要全局搜索替换，确保无遗漏
2. **PageIndex-main 作为外部库移动可能有隐藏依赖**：需要检查其内部的相对 import
3. **LlamaIndex 索引持久化**：需要确保 RAG_persist/ 目录的索引 ID 管理不冲突
4. **两阶段 pageindex_search 可能在浅层文档上过度拆分**：需要加阈值判断（节点数 < 20 时退回单阶段）
