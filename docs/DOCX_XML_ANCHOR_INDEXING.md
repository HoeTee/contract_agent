# LlamaIndex DOCX Anchor Retrieval and Annotation Flow

## Direct Conclusion

The contract search index is built from DOCX XML anchors, not from markdown. The workflow converts DOCX paragraph/table anchors into LlamaIndex `TextNode` objects, retrieves them as `NodeWithScore`, reranks by replacing only the score, formats anchor metadata into text for the SubAgent, and finally writes Word comments by resolving the SubAgent's `anchors` back to the original DOCX XML range.

End-to-end flow:

```text
DOCX
-> DocxAnchorNode(text + xml_anchor_type + xml_anchor_id)
-> TextNode(text + id_ + metadata)
-> VectorStoreIndex
-> retriever returns list[NodeWithScore(node=TextNode, score=...)]
-> reranker postprocessor returns reranked NodeWithScore list
-> rag_engine.search() formats text + xml_anchor metadata
-> SubAgentOutput.issues[].anchors
-> DocxReportGenerator writes annotated DOCX comments
```

## 1. DOCX Anchor Nodes

Implementation entry:

```text
tools/document/docx_anchor_index.py
```

Core function:

```python
build_docx_anchor_nodes(docx_path)
```

The function walks DOCX body content in document order. It reads direct XML children and yields only paragraphs and tables:

```python
for child in parent_element.iterchildren():
    if isinstance(child, CT_P):
        yield Paragraph(child, parent)
    elif isinstance(child, CT_Tbl):
        yield Table(child, parent)
```

`iter_blocks()` contains `yield`, so calling `iter_blocks(parent)` returns a generator object. That generator is iterable and can be used by:

```python
for block_index, block in enumerate(iter_blocks(parent), start=1):
```

Each extracted block becomes a `DocxAnchorNode`:

```python
DocxAnchorNode(
    anchor_type="paragraph",
    anchor_id="path:body/p3",
    text="visible contract text",
    path="body/p3",
)
```

## 2. Path ID Rules

Current anchor IDs use generated structural paths:

```text
path:body/p3
```

This means the third top-level body block is a paragraph.

```text
path:body/tbl5
```

This means the fifth top-level body block is a table.

```text
path:body/tbl5/r1c2/p1
```

This means the first paragraph in row 1, cell 2 of the fifth top-level table.

Important boundary:

```text
path:body/... is stable within the same DOCX and the same review run.
It is not a permanent ID across document versions or structural edits.
```

This is acceptable because the current review flow builds the index and writes comments against the same DOCX in one run.

## 3. Anchor Nodes Become TextNode

Implementation entry:

```text
tools/retrieval/llamaindex/rag_engine.py
```

`build_temporary_index_from_docx()` converts every `DocxAnchorNode` into a LlamaIndex `TextNode`:

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

Field meaning:

- `text`: the visible contract text used for embedding and retrieval.
- `id_`: the LlamaIndex node ID.
- `metadata`: project-level information used later for annotation.

`metadata` is not the issue result. It is carried by the node until `rag_engine.search()` formats it into retrieved context text.

## 4. VectorStoreIndex Stores TextNode

During index construction, `nodes` is a `list[TextNode]`:

```python
self._index = VectorStoreIndex(nodes)
```

At this point, the index contains text nodes with XML anchor metadata.

## 5. Query Returns NodeWithScore

During search, the project creates a retriever from the index:

```python
retriever = self._index.as_retriever(similarity_top_k=self.similarity_top_k)
```

The retriever returns:

```python
list[NodeWithScore]
```

Each item is conceptually:

```python
NodeWithScore(
    node=TextNode(...),
    score=0.83,
)
```

So there are two different `nodes` lists in the flow:

```text
index build: list[TextNode]
reranker input: list[NodeWithScore]
```

`NodeWithScore` is a LlamaIndex wrapper. It keeps the original node and adds a retrieval or rerank score.

## 6. RetrieverQueryEngine Applies the Reranker

The reranker is attached as a LlamaIndex node postprocessor:

```python
query_engine = RetrieverQueryEngine.from_args(
    retriever=retriever,
    node_postprocessors=[self.reranker],
)
```

`from_args()` stores the retriever and postprocessors. The actual call happens when the query runs.

Internal behavior is:

```text
retriever.retrieve(query) -> nodes
postprocessor.postprocess_nodes(nodes) -> reranked_nodes
response_synthesizer.synthesize(query, reranked_nodes)
```

Therefore, the reranker does not build nodes. It receives candidate `NodeWithScore` objects from the retriever and returns a reordered/rescored list.

## 7. Reranker Index Mapping

Implementation entry:

```text
tools/retrieval/llamaindex/qwen_reranker.py
```

The reranker first extracts plain text documents from the retrieved nodes:

```python
documents = [
    node.get_content(metadata_mode=MetadataMode.NONE)
    for node in nodes
]
```

This preserves list order:

```text
documents[0] comes from nodes[0]
documents[1] comes from nodes[1]
documents[2] comes from nodes[2]
```

The external reranker returns indexes into that `documents` list:

```json
[
  {"index": 2, "score": 0.98},
  {"index": 0, "score": 0.91}
]
```

So the code can map the result back to the original node:

```python
original_node = nodes[item["index"]]
```

This works because `item["index"]` means "the position of the input document in the request".

Boundary:

```text
This assumes the reranker returns 0-based indexes into the submitted documents array.
If a provider returns 1-based indexes or another ID format, this mapping must change.
```

## 8. Reranker Keeps Text and Metadata

The reranker does not rebuild `TextNode` and does not copy text manually:

```python
NodeWithScore(
    node=original_node.node,
    score=new_score,
)
```

This means:

```text
keep original TextNode text/id_/metadata
replace only score
```

That is why the original text and XML anchor metadata survive reranking.

## 9. Metadata Becomes SubAgent Context

After query execution, `rag_engine.search()` reads `response.source_nodes`:

```python
for i, source_node in enumerate(response.source_nodes, 1):
    text = source_node.get_content()
    metadata = getattr(source_node, "metadata", None) or {}
```

It formats selected metadata into plain text:

```text
xml_anchor_type: paragraph
xml_anchor_id: path:body/p3
内容：
visible contract text
```

Important boundary:

```text
The raw metadata object is not passed to the SubAgent.
Only formatted text containing xml_anchor_type/xml_anchor_id is passed.
```

## 10. SubAgent Anchors

The Orchestrator sends the retrieved context string to the SubAgent.

The prompt requires the SubAgent to reuse anchor fields from the retrieved context:

```text
输出 anchors 时必须原样复用对应检索结果中的 xml_anchor_type/xml_anchor_id；
quoted_text 只能摘录该 anchor 对应合同文本中的单一连续片段。
```

The output is validated by `agents/schemas.py`:

```python
class SubAgentAnchor:
    xml_anchor_type: Literal["paragraph", "table"]
    xml_anchor_id: str
    quoted_text: str
    comment_text: str
```

The resulting structure is stored under:

```text
SubAgentOutput.issues[].anchors
```

Then the workflow carries it as:

```text
parsed_opinion["issues"]
-> result["issues"]
-> results
-> results_json
-> generate_docx_report
```

## 11. DOCX Annotation Writeback

Implementation entry:

```text
tools/document/reporting/docx_report.py
```

The annotation phase reads every issue anchor:

```python
anchor_type = anchor_item.get("xml_anchor_type", "")
anchor_id = anchor_item.get("xml_anchor_id", "")
reference = anchor_item.get("quoted_text", "")
comment_text = anchor_item.get("comment_text", "")
```

Then it resolves the anchor in the original DOCX:

```python
_find_text_range_anchor_in_xml_anchor(
    doc,
    anchor_type,
    anchor_id,
    reference,
)
```

The logic is:

```text
1. Use xml_anchor_type and xml_anchor_id to lock the paragraph/table scope.
2. Search quoted_text only inside that scope.
3. Resolve the matching run range.
4. Insert standard Word comment XML.
```

The generated DOCX uses Word comment markers, not the internal `path:body/...` ID:

```xml
<w:commentRangeStart w:id="6"/>
...
<w:commentRangeEnd w:id="6"/>
<w:commentReference w:id="6"/>
```

## 12. Markdown Usage Boundary

The temporary contract search index does not depend on contract markdown.

Markdown is still used for:

- Parsing review criteria before planning.
- Some report-generation helper paths.
- Workflow logging and text-length summaries.

Keep this boundary clear:

```text
contract search index: DOCX XML anchored TextNode
review criteria planning: markdown text
```

## 13. Risks and Boundaries

- `path:body/...` is generated from DOCX structure and is stable only within the same DOCX review run.
- The reranker `index` mapping assumes 0-based indexes into the input `documents` list.
- Raw LlamaIndex metadata is not passed as a structured object to the SubAgent; it is formatted into context text.
- If the SubAgent fabricates `xml_anchor_id` or quotes text outside the anchor scope, DOCX annotation may fail or skip that issue.
- If the same `quoted_text` appears multiple times inside the same anchor scope, the first occurrence is used.
