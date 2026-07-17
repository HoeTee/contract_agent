# DOCX XML Anchor 索引与批注定位逻辑

## 直接结论

合同临时检索索引不再基于 markdown 建立，而是直接基于 DOCX XML 结构建立。系统遍历 DOCX 正文中的 `w:p` 段落和 `w:tbl` 表格，生成带结构坐标的 LlamaIndex node。审查结果写回 DOCX 时，先用结构坐标锁定原文范围，再在该范围内匹配 `quoted_text` 的首次出现位置并写入 Word 批注。

## 背景

旧逻辑是：

```text
DOCX -> python-docx 提取 markdown 文本 -> LlamaIndex 建索引
```

这个流程的问题是 markdown 只保留文本，不保留 DOCX XML 位置。模型发现问题后只能输出 `quoted_text`，批注阶段再到原 DOCX 全局查找这段文本。遇到重复文本、表格拼接、换行、修订、批注清理等情况时，容易出现“发现了问题但正文批注定位失败”或“批注落到错误位置”。

新逻辑是：

```text
DOCX -> 遍历 w:p / w:tbl -> anchored nodes(text + xml_anchor_type + xml_anchor_id) -> LlamaIndex
```

## Anchor Node

每个可检索节点包含两部分：

```json
{
  "text": "合同原文可见文本",
  "metadata": {
    "xml_anchor_type": "paragraph",
    "xml_anchor_id": "path:body/p3"
  }
}
```

`text` 用于 embedding 和语义检索；`metadata` 不参与语义判断，主要用于把审查结论写回原 DOCX。

实现入口：

```text
tools/document/docx_anchor_index.py
```

核心函数：

```python
build_docx_anchor_nodes(docx_path)
```

## Path ID 规则

当前统一使用遍历生成的结构路径，不再优先使用 `w14:paraId`。

规则如下：

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

这里的 block 只统计 `w:p` 和 `w:tbl`。代码通过 `python-docx` 的底层 XML 类型判断：

```python
if isinstance(child, CT_P):
    yield Paragraph(child, parent)
elif isinstance(child, CT_Tbl):
    yield Table(child, parent)
```

## Path ID 的性质

`path:body/...` 不是 DOCX 原文件自带 id，也不是 `python-docx` 原生 id。它是系统按 DOCX XML 顺序遍历时生成的结构坐标。

它的边界是：

```text
同一个 DOCX、同一次任务内稳定
跨版本、跨文件、文档结构被修改后不保证稳定
```

当前审查流程是一次任务内完成：

```text
同一份合同 DOCX -> 建索引 -> 审查 -> 写回批注
```

因此 `path:body/...` 可以满足当前批注定位需求。

## 检索链路

workflow 不再把合同 markdown 传给合同临时索引，而是传合同 DOCX 路径：

```text
main_workflow/main_workflow.py
  -> llamaindex_build_index(docx_path)
```

MCP 工具接收 `docx_path`：

```text
mcp_service/mcp_server/mcp_server.py
```

索引构建入口：

```text
tools/retrieval/index_retriever.py
  -> build_contract_llamaindex_index(docx_path)
```

LlamaIndex 建索引：

```text
tools/retrieval/llamaindex/rag_engine.py
  -> build_temporary_index_from_docx(docx_path)
```

每个 DOCX anchor node 会转换成 LlamaIndex `TextNode`：

```python
TextNode(
    text=anchor.text,
    metadata={
        "xml_anchor_type": anchor.anchor_type,
        "xml_anchor_id": anchor.anchor_id,
    },
)
```

## 搜索结果格式

搜索结果会把 anchor metadata 带给 sub-agent：

```text
xml_anchor_type: paragraph
xml_anchor_id: path:body/p3
内容：
浙江农村商业联合银行股份有限公司
```

sub-agent 输出 `anchors` 时必须复用检索结果中的 `xml_anchor_type` 和 `xml_anchor_id`。

当前 schema：

```json
{
  "xml_anchor_type": "paragraph",
  "xml_anchor_id": "path:body/p3",
  "quoted_text": "浙江农村商业联合银行股份有限公司",
  "comment_text": "批注意见"
}
```

## 批注写回逻辑

批注阶段不再对整个 DOCX 做全局 `quoted_text` 反查。

当前流程是：

```text
1. 读取 anchor.xml_anchor_type 和 anchor.xml_anchor_id
2. 按同一套 path 规则重新遍历原 DOCX
3. 找到对应 paragraph 或 table 范围
4. 只在该范围内查找 quoted_text 的首次出现位置
5. 成功后插入 Word 标准批注 XML
```

写入 DOCX 的不是 `path:body/...`，而是 Word 标准批注标记：

```xml
<w:commentRangeStart w:id="6"/>
...
<w:commentRangeEnd w:id="6"/>
<w:commentReference w:id="6"/>
```

批注实现位置：

```text
tools/document/reporting/docx_report.py
```

关键函数：

```python
_find_text_range_anchor_in_xml_anchor(...)
```

## Markdown 仍然在哪里使用

合同临时检索索引已经不依赖 markdown。

markdown 仍用于：

- 审查标准 DOCX 解析后交给 planner 拆分审查任务。
- 部分报告生成辅助逻辑。
- 工作流日志中的文本长度统计。

因此需要区分：

```text
合同搜索索引：DOCX XML anchored nodes
审查标准规划：markdown 文本
```

## 边界与风险

当前方案适用于同一次任务内使用同一份 DOCX 完成索引、审查和批注写回。

不适合以下场景：

- 建索引后替换合同文件。
- 建索引后人工插入或删除段落再写回批注。
- 将 `xml_anchor_id` 持久化后跨版本复用。

如果未来需要跨版本稳定定位，需要在预处理阶段向 DOCX 注入自定义 id，或构建更复杂的业务逻辑块 id。
