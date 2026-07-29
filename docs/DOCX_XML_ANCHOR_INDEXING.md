# LlamaIndex DOCX Anchor 检索与批注定位链路

## 直接结论

合同搜索索引不是基于 markdown 建立，而是基于 DOCX XML anchor 建立。系统把 DOCX 段落和表格转换成带结构坐标的 LlamaIndex `TextNode`，检索时返回 `NodeWithScore`，reranker 只替换分数、不重建文本节点；随后 `rag_engine.search()` 把 anchor metadata 格式化进检索上下文文本，SubAgent 在输出 `anchors` 时复用这些字段，最后批注工具再根据 `xml_anchor_type/xml_anchor_id + quoted_text` 写回原 DOCX。

整体链路：

```text
DOCX
-> DocxAnchorNode(text + xml_anchor_type + xml_anchor_id)
-> TextNode(text + id_ + metadata)
-> VectorStoreIndex
-> retriever 返回 list[NodeWithScore(node=TextNode, score=...)]
-> reranker postprocessor 返回重排后的 NodeWithScore list
-> rag_engine.search() 拼接正文 + xml_anchor metadata
-> SubAgentOutput.issues[].anchors
-> DocxReportGenerator 写入批注版 DOCX
```

## 1. DOCX 如何生成 Anchor Node

实现入口：

```text
tools/document/docx_anchor_index.py
```

核心函数：

```python
build_docx_anchor_nodes(docx_path)
```

这个函数按 DOCX XML 顺序遍历正文内容，只处理段落和表格：

```python
for child in parent_element.iterchildren():
    if isinstance(child, CT_P):
        yield Paragraph(child, parent)
    elif isinstance(child, CT_Tbl):
        yield Table(child, parent)
```

`iter_blocks()` 里包含 `yield`，所以调用 `iter_blocks(parent)` 会返回 generator。generator 是 iterable，因此可以被 `enumerate()` 遍历：

```python
for block_index, block in enumerate(iter_blocks(parent), start=1):
```

每个可检索块会生成一个 `DocxAnchorNode`：

```python
DocxAnchorNode(
    anchor_type="paragraph",
    anchor_id="path:body/p3",
    text="合同可见原文",
    path="body/p3",
)
```

## 2. Path ID 规则

当前 anchor ID 使用系统生成的结构路径：

```text
path:body/p3
```

表示正文 `w:body` 下第 3 个 block 是段落。

```text
path:body/tbl5
```

表示正文 `w:body` 下第 5 个 block 是表格。

```text
path:body/tbl5/r1c2/p1
```

表示正文第 5 个表格中，第 1 行第 2 列里的第 1 个段落。

边界：

```text
path:body/... 在同一份 DOCX、同一次审查任务内稳定。
跨文档版本、跨文件、文档结构被修改后不保证稳定。
```

当前流程是在同一次任务里完成：

```text
同一份合同 DOCX -> 建索引 -> 审查 -> 写回批注
```

所以这个结构路径可以满足当前批注定位需求。

## 3. Anchor Node 如何变成 TextNode

实现入口：

```text
tools/retrieval/llamaindex/rag_engine.py
```

`build_temporary_index_from_docx()` 会把每个 `DocxAnchorNode` 转成 LlamaIndex `TextNode`：

```python
TextNode(
    text=anchor.text,
    id_=f"{source_name}:{anchor.anchor_type}:{anchor.anchor_id}",
    metadata={
        "source_file": source_name,
        "doc_id": source_name,
        "index_scope": "temporary_contract",
        "xml_anchor_type": anchor.anchor_type,
        "xml_anchor_id": anchor.anchor_id,
        "xml_anchor_path": anchor.path,
    },
)
```

字段含义：

- `text`：合同可见原文，用于 embedding 和语义检索。
- `id_`：LlamaIndex node 自身 ID。
- `metadata`：项目业务元数据，后续用于批注定位。

这里的 `metadata` 不是最终 issue 结果。它先跟着 `TextNode` 进入索引，后面由 `rag_engine.search()` 格式化进检索上下文文本。

## 4. VectorStoreIndex 里保存的是什么

建索引时，`nodes` 是：

```python
list[TextNode]
```

然后进入 LlamaIndex 向量索引：

```python
self._index = VectorStoreIndex(nodes)
```

所以索引里保存的是带正文和 XML anchor metadata 的 `TextNode`。

## 5. 查询时 nodes 是什么

搜索时先从索引创建 retriever：

```python
retriever = self._index.as_retriever(similarity_top_k=self.similarity_top_k)
```

retriever 返回的是：

```python
list[NodeWithScore]
```

每个元素可以理解成：

```python
NodeWithScore(
    node=TextNode(...),
    score=0.83,
)
```

所以这里有两个不同层面的 `nodes`：

```text
建索引时：list[TextNode]
reranker 收到时：list[NodeWithScore]
```

`NodeWithScore` 是 LlamaIndex 自带包装类。它不是替代 `TextNode`，而是在 `TextNode` 外面加一层检索分数或重排分数。

## 6. RetrieverQueryEngine 如何调用 reranker

reranker 是作为 LlamaIndex node postprocessor 挂进去的：

```python
query_engine = RetrieverQueryEngine.from_args(
    retriever=retriever,
    node_postprocessors=[self.reranker],
)
```

`from_args()` 这一步只是保存 retriever 和 postprocessors，真正执行发生在 `query_engine.query(query)` 时。

内部语义可以简化成：

```text
retriever.retrieve(query) -> nodes
postprocessor.postprocess_nodes(nodes) -> reranked_nodes
response_synthesizer.synthesize(query, reranked_nodes)
```

所以 reranker 不负责构建 node。它接收 retriever 已经找出的候选 `NodeWithScore`，然后返回重排或重打分后的 `NodeWithScore` 列表。

## 7. reranker 的 index 为什么能映射回原 node

实现入口：

```text
tools/retrieval/llamaindex/qwen_reranker.py
```

reranker 先从检索出的 `nodes` 里提取纯文本：

```python
documents = [
    node.get_content(metadata_mode=MetadataMode.NONE)
    for node in nodes
]
```

这个过程保持列表顺序：

```text
documents[0] 来自 nodes[0]
documents[1] 来自 nodes[1]
documents[2] 来自 nodes[2]
```

外部 reranker 返回的 `index` 指向输入 `documents` 的位置：

```json
[
  {"index": 2, "score": 0.98},
  {"index": 0, "score": 0.91}
]
```

所以代码可以这样找回原始 node：

```python
original_node = nodes[item["index"]]
```

这里的 `item["index"]` 不是 `TextNode.id_`，也不是 `NodeWithScore` 的字段。它是 reranker 服务返回的输入文档下标。

边界：

```text
这里假设 reranker 返回的是 documents 数组的 0-based index。
如果某个 provider 返回 1-based index 或返回其他 ID 格式，这里的映射逻辑必须改。
```

## 8. 为什么 reranker 不重新放 text

reranker 重新生成结果时没有重建 `TextNode`：

```python
NodeWithScore(
    node=original_node.node,
    score=new_score,
)
```

含义是：

```text
保留原始 TextNode 的 text/id_/metadata
只替换 score
```

这样正文、node ID、XML anchor metadata 都不会丢。

## 9. metadata 如何进入 SubAgent

查询结束后，`rag_engine.search()` 读取 `response.source_nodes`：

```python
for i, source_node in enumerate(response.source_nodes, 1):
    text = source_node.get_content()
    metadata = getattr(source_node, "metadata", None) or {}
```

然后把部分 metadata 格式化进字符串：

```text
xml_anchor_type: paragraph
xml_anchor_id: path:body/p3
内容：
合同可见原文
```

关键边界：

```text
SubAgent 收到的不是原始 metadata 对象。
SubAgent 收到的是包含 xml_anchor_type/xml_anchor_id 的检索上下文字符串。
```

## 10. SubAgent anchors 如何落实

Orchestrator 把检索上下文字符串传给 SubAgent。

prompt 要求 SubAgent 复用检索结果里的 anchor 字段：

```text
输出 anchors 时必须原样复用对应检索结果中的 xml_anchor_type/xml_anchor_id；
quoted_text 只能摘录该 anchor 对应合同文本中的单一连续片段。
```

SubAgent 输出会被 `agents/schemas.py` 校验：

```python
class SubAgentAnchor:
    xml_anchor_type: Literal["paragraph", "table"]
    xml_anchor_id: str
    quoted_text: str
    comment_text: str
```

最终结构保存在：

```text
SubAgentOutput.issues[].anchors
```

然后沿工作流传递：

```text
parsed_opinion["issues"]
-> result["issues"]
-> results
-> results_json
-> generate_docx_report
```

## 11. DOCX 批注如何写回

实现入口：

```text
tools/document/reporting/docx_report.py
```

批注阶段读取每个 issue 的 anchor：

```python
anchor_type = anchor_item.get("xml_anchor_type", "")
anchor_id = anchor_item.get("xml_anchor_id", "")
reference = anchor_item.get("quoted_text", "")
comment_text = anchor_item.get("comment_text", "")
```

然后回到原 DOCX 里解析：

```python
_find_text_range_anchor_in_xml_anchor(
    doc,
    anchor_type,
    anchor_id,
    reference,
)
```

逻辑是：

```text
1. 用 xml_anchor_type 和 xml_anchor_id 锁定 paragraph/table 范围。
2. 只在该范围内查找 quoted_text。
3. 找到具体 run range。
4. 插入 Word 标准批注 XML。
```

写入 DOCX 的不是 `path:body/...`，而是 Word 标准批注标记：

```xml
<w:commentRangeStart w:id="6"/>
...
<w:commentRangeEnd w:id="6"/>
<w:commentReference w:id="6"/>
```

## 12. Markdown 的边界

合同临时检索索引不依赖合同 markdown。

markdown 仍用于：

- 审查标准 DOCX 解析后交给 planner 拆分审查任务。
- 部分报告生成辅助逻辑。
- 工作流日志中的文本长度统计。

需要明确区分：

```text
合同搜索索引：DOCX XML anchored TextNode
审查标准规划：markdown 文本
```

## 13. 边界与风险

- `path:body/...` 是从 DOCX 结构生成的，只保证同一份 DOCX、同一次任务内稳定。
- reranker 的 `index` 映射假设服务返回的是输入 `documents` 数组的 0-based 下标。
- LlamaIndex metadata 不会作为结构化对象传给 SubAgent，只会被格式化进检索上下文文本。
- 如果 SubAgent 编造 `xml_anchor_id`，或者 `quoted_text` 不在对应 anchor 范围内，批注定位会失败或跳过该 issue。
- 如果同一个 `quoted_text` 在同一个 anchor 范围内出现多次，当前使用首次出现位置。
