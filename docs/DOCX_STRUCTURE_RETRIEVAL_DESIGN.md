# DOCX 结构化索引与检索算法设计

本文定义合同审查场景下的 DOCX 结构化索引和检索机制。

核心结论：

```text
持久化 DOCX 结构树索引是主索引。
规则审查只是少数审查要点的执行方式，不单独设计“规则索引”。
向量检索不产生新 node，只对已有结构 node 做 fallback 补召回。
最终审查必须展开结构树中的原文 node。
```

当前审查要点来源：

```text
resources/criteria/criteria-formal.docx
```

## 1. 审查要点分类

`criteria-formal.docx` 中的审查要点按执行方式分为四类。

| 类别 | 审查要点 | 执行方式 |
|---|---|---|
| 关键词规则审查 | 4、5、8、9、16 | 使用关键词或正则扫描全文，返回命中的 node 和 anchor |
| 标题规则审查 | 2 | 检查结构树 title 是否存在、是否符合要求 |
| 全文遍历审查 | 12、15 | 遍历结构树 node，逐个展开 node 输入模型检查 |
| 普通 LLM 审查 | 其他审查要点 | 先用结构树检索候选 node，再展开原文交给模型审查 |

其中 12、15 可以归入规则审查的大类，但执行方式不是关键词命中，而是“遍历每个 node 后逐个判断”。

标题顺序混乱也归入规则审查：直接检查结构树中标题编号是否连续、层级是否跳变、同级标题是否乱序。

## 2. 总体架构

整体流程：

```text
DOCX
  -> 解析 word/document.xml、word/styles.xml
  -> 生成 body child anchor
  -> 识别合同首部、正文、合同末尾、附件
  -> 构建结构树 node
  -> 计算 node token 并切分超长 node
  -> 生成 summary tree
  -> 持久化 DocumentIndex
  -> 审查要点驱动检索和原文展开
  -> SubAgent 输出 issue
  -> 批注工具通过 anchor 回写 DOCX
```

主索引只有一个：

```text
DocumentIndex
```

规则检索和向量检索都只返回 `node_id` / `anchor`，然后回到 DocumentIndex 展开原文。

## 3. DocumentIndex 持久化索引

每个任务解析 DOCX 后生成一个持久化索引，建议写入：

```text
data/{client_dir}/tasks/{task_id}/index/document_index.json
```

索引主结构：

```json
{
  "schema_version": "docx-index-v1",
  "task_id": "20260818-xxxx",
  "source_file": "contract.docx",
  "top_regions": {
    "frontmatter": "frontmatter",
    "body": "body",
    "tail": "tail",
    "attachments": "attachments"
  },
  "nodes": [],
  "anchor_map": {}
}
```

只存一份完整 node 数据。所谓 `structure_view`、`content_view` 不是额外存储两份索引，而是从同一份完整 node 中按场景裁剪字段。

完整 node 示例：

```json
{
  "node_id": "body/sec_002/l2_003",
  "parent_id": "body/sec_002",
  "node_type": "section",
  "level": 2,
  "title": "三、本合同款项的分批支付方式及时限如下",
  "text": "三、本合同款项的分批支付方式及时限如下：...",
  "summary": "约定分批付款节点、比例、发票类型和付款期限。",
  "start_anchor": "p_0042",
  "end_anchor": "p_0051",
  "page_start": null,
  "page_end": null,
  "page_source": "unavailable",
  "page_confidence_score": 0,
  "token_estimate": 720,
  "confidence_score": 9,
  "confidence_evidence": ["number_pattern", "sequence", "style_outline"],
  "children": []
}
```

## 4. 数据来源

| 数据 | 来源 | 用途 |
|---|---|---|
| 阅读顺序 | `word/document.xml` 的 `w:body` 直接子节点 | 保证结构树顺序 |
| 段落 | `w:body > w:p` | 生成 paragraph anchor 和文本 |
| 表格 | `w:body > w:tbl` | 生成 table anchor 和 TableNode |
| 段落文本 | `w:t`、`w:delText` | 标题识别、node text、关键词检索 |
| direct outline | `w:pPr/w:outlineLvl` | 标题强证据 |
| style outline | `w:pPr/w:pStyle -> word/styles.xml` | 标题强证据 |
| 样式继承 | `styles.xml` 中 `w:basedOn` 链 | 计算 effective outline |
| 对齐 | `w:pPr/w:jc` | 视觉标题判断 |
| 字号 | `w:rPr/w:sz` | 视觉标题判断 |
| 加粗 | `w:rPr/w:b` | 视觉标题判断 |
| 页码 | `w:lastRenderedPageBreak` | 可选展示字段 |
| 批注关系 | `word/_rels/document.xml.rels` 指向 `word/comments.xml` | 读取和写入批注正文 |

`w:lastRenderedPageBreak` 并非所有 DOCX 都存在。它只能作为可选页码来源，不影响检索、审查和批注。

## 5. Body Child Anchor

`word/document.xml` 中 `w:body` 的直接子节点是结构索引的基础。

遍历规则：

```text
遇到 w:p   -> 生成 p_0001、p_0002、...
遇到 w:tbl -> 生成 tbl_0001、tbl_0002、...
保持它们在 w:body 中的原始顺序。
```

`anchor_map` 示例：

```json
{
  "p_0042": {
    "body_child_index": 42,
    "type": "p",
    "text": "三、本合同款项的分批支付方式及时限如下：",
    "node_id": "body/sec_002/l2_003"
  },
  "tbl_0003": {
    "body_child_index": 58,
    "type": "tbl",
    "text": "表格提取后的文本",
    "node_id": "body/sec_008"
  }
}
```

`p_...` / `tbl_...` 不是业务 ID，而是检索结果和批注工具之间的桥梁。

## 6. 顶层区域

结构树必须保留四个顶层区域：

```text
frontmatter  合同首部
body         正文
tail         合同末尾
attachments  附件
```

### 6.1 合同首部 FrontMatter

合同首部包括正式正文开始前的内容，例如合同标题页、合同编号、甲乙方信息、签署提示等。

识别规则：

```text
从 document.xml 开始扫描；
遇到第一个正式正文标题后，之前内容归入 frontmatter；
正式正文标题通常是 第X条 / 第X章。
```

### 6.2 正文 Body

正文从第一个正式正文标题开始，到合同末尾或附件父章节前结束。

正文标题识别不包含：

```text
附件内部的 第X条 / 第X章
表格单元格内的标题文本
附件清单里的 附件N
```

表格内容仍然属于正文，只是不参与正文章节标题识别。

### 6.3 合同末尾 Tail

合同末尾用于保存正文结束后的签署页、无正文提示、盖章栏和附件前的尾部内容。

TailNode 不只依赖“以下无正文”“以下为合同签署栏”。

建议使用多信号识别：

```text
最后一个正式正文 Level1 section 之后的连续内容进入 tail 候选；
出现签署、盖章、法定代表人、授权代表、日期等信号时提高得分；
如果后续出现正式附件 section，则附件开始前的签署/空白/说明内容归 tail；
没有明确 tail marker 时，正文标题连续性结束后的内容可形成低置信度 tail。
```

### 6.4 附件 Attachments

附件区从正文中的附件父章节或正文末尾的正式附件 section 开始。

附件父章节示例：

```text
第二十条 附件
第十四条 附件
```

正式附件 section 示例：

```text
附件1
附件 1
附件一
附件1：
附件1、
```

正式附件 section 必须位于附件父章节之后，或位于正文末尾附件区。正文中的“详见附件3”不应直接升格为附件 section。

## 7. 正文章节 Node 构建

正文默认提取到三级：

```text
Level 1: 第X条 / 第X章
Level 2: 一、二、三、
Level 3: （一）（二）（三）
```

标题判断信号：

```text
1. 编号形态
2. 编号连续性
3. effective_outlineLvl
4. 样式、字号、加粗、居中等辅助信号
```

`effective_outlineLvl` 计算顺序：

```text
1. 段落 direct outlineLvl
2. 当前 pStyle 自身 outlineLvl
3. pStyle basedOn 链上的 outlineLvl
```

`outlineLvl` 是强证据，但不是唯一条件。对于没有 outline 的合同，仍然要依赖编号形态和连续性识别章节。

标题置信度使用数字化字段：

```json
{
  "confidence_score": 9,
  "confidence_evidence": [
    "number_pattern",
    "sequence",
    "style_outline"
  ]
}
```

示例计分：

```text
编号形态命中 +2
同级编号连续 +3
direct outlineLvl +4
style outlineLvl +3
视觉标题得分 +0 到 +4
附件上下文命中 +2
排除规则命中 -5
```

## 8. 附件内部 Node 构建

附件内部不能依赖统一 `outlineLvl`。先识别正式附件 section，再在附件 section 内部做局部切分。

附件内部标题候选包括：

```text
视觉标题：科技部门驻场外包考核细则
编号标题：第一条、第一章、一、（一）、1、
局部标签：目的：、范围：、包装：、考核：、罚则：
表格：独立 TableNode
```

视觉标题参数：

```json
{
  "visual_title_max_chars": 55,
  "visual_title_min_score": 2,
  "large_font_size_threshold": 28,
  "bold_fraction_threshold": 0.5,
  "attachment_start_window": 8
}
```

视觉标题打分：

```text
+1 居中
+1 加粗比例 >= 0.5
+1 最大字号 >= 28
+1 后 5 个 body child 内出现正文、编号标题或表格
```

PlainLabel 参数：

```json
{
  "plain_label_keywords": [
    "目的",
    "对象",
    "分工",
    "内容",
    "方式",
    "结果",
    "要求",
    "标准",
    "范围",
    "期限",
    "责任",
    "义务",
    "说明",
    "证明",
    "来源",
    "包装",
    "请假",
    "考核",
    "罚则",
    "承诺",
    "服务",
    "电话"
  ],
  "standalone_plain_label_max_chars": 16
}
```

PlainLabel 只作为局部内容边界，不提升为正式正文章节。

## 9. Node Token 阈值与 ChunkNode

不照搬 PageIndex 的 20000 token。合同审查需要精确计算、定位和批注，node 应更小。

建议参数：

```yaml
node_target_tokens: 700
node_soft_limit_tokens: 1000
node_hard_limit_tokens: 1800
chunk_overlap_tokens: 80
```

含义：

| 参数 | 含义 |
|---|---|
| `node_target_tokens` | 理想子 node 大小 |
| `node_soft_limit_tokens` | 超过后优先按子标题或编号拆 |
| `node_hard_limit_tokens` | 超过后必须拆，即使只能按段落聚合 |
| `chunk_overlap_tokens` | 相邻 chunk 的上下文重叠 |

ChunkNode 生成逻辑：

```text
1. 一个结构 node 超过 soft limit 时，先找更细编号或视觉子标题。
2. 如果找到可靠子标题，按子标题生成子 node。
3. 如果没有可靠子标题，按 w:body child 顺序聚合段落和表格。
4. 聚合目标是 node_target_tokens。
5. 单个 chunk 不应超过 node_hard_limit_tokens。
6. 表格不拆散；单个表格过大时独立为 TableNode，并标记 oversized=true。
```

ChunkNode 示例：

```json
{
  "node_id": "body/sec_008/l3_002/chunk_001",
  "node_type": "chunk",
  "title": "（二）服务内容 / chunk 1",
  "start_anchor": "p_0212",
  "end_anchor": "p_0238",
  "token_estimate": 700,
  "chunk_index": 1,
  "chunk_count": 3,
  "overlap_tokens": 80
}
```

## 10. Summary Tree

summary tree 是给 LLM 的低 token 导航，不是最终事实判断依据。

summary 生成规则：

```text
叶子 node：基于自身原文生成 summary。
非叶子 node：基于 children 的 title 和 summary 汇总生成 summary。
短 node 可不生成 summary，直接使用 title 和 token_estimate。
```

建议参数：

```yaml
summary_trigger_min_tokens: 300
summary_max_tokens_per_node: 120
summary_tree_inline_budget_tokens: 6000
```

输出给 LLM 的结构视图只包含轻量字段：

```json
{
  "node_id": "body/sec_002",
  "title": "第二条 合同金额及支付方式",
  "summary": "约定合同金额、付款方式、发票和账户。",
  "token_estimate": 1200,
  "children": []
}
```

## 11. 结构树加载方式

是否一次返回完整结构树，只看 summary tree 的 token 估算。

```text
structure_tokens <= 6000
  -> compact_structure

6000 < structure_tokens <= 20000
  -> paged_structure

structure_tokens > 20000
  -> filtered_or_paged_structure
```

`compact_structure`：一次返回完整 summary tree。

`paged_structure`：按顶层区域或 Level1 section 分批返回。

`filtered_or_paged_structure`：先按审查要点的标题关键词或候选区域过滤，再分页返回。

注意：这里分页的是结构树 summary，不是合同原文。

## 12. 检索工具接口

结构树工具应提供少量稳定接口。

### 12.1 get_document_structure

返回结构树 summary，不返回全文。

输入：

```json
{
  "part": 1,
  "filter": null
}
```

输出：

```json
{
  "document_structure_mode": "compact_structure",
  "structure_tokens": 4200,
  "part": 1,
  "total_parts": 1,
  "structure_index": []
}
```

### 12.2 get_node_content

按 `node_id` 展开原文。

输入：

```json
{
  "node_id": "body/sec_002"
}
```

输出：

```json
{
  "node_id": "body/sec_002",
  "title": "第二条 合同金额及支付方式",
  "text": "...完整原文...",
  "start_anchor": "p_0038",
  "end_anchor": "p_0058",
  "token_estimate": 1200
}
```

### 12.3 search_by_keyword

关键词规则检索。只做命中定位，不做字段抽取缓存。

输入：

```json
{
  "keywords": ["支付方式", "付款", "合同金额"]
}
```

输出：

```json
{
  "matches": [
    {
      "keyword": "支付方式",
      "match_text": "第二条 合同金额及支付方式",
      "match_type": "title",
      "node_id": "body/sec_002",
      "anchor": "p_0038"
    }
  ]
}
```

### 12.4 validate_title_sequence

检查结构树标题顺序。

输出：

```json
{
  "issues": [
    {
      "node_id": "body/sec_006",
      "title": "第八条 违约责任",
      "message": "同级标题从第六条跳到第八条，缺少第七条。"
    }
  ]
}
```

### 12.5 vector_search_nodes

语义补召回。只返回已有结构树 node，不创建新 node。

输入：

```json
{
  "query": "维护响应机制"
}
```

输出：

```json
{
  "matches": [
    {
      "node_id": "body/sec_008/l3_002",
      "score": 0.82,
      "title": "售后服务要求"
    }
  ]
}
```

## 13. 规则审查执行方式

规则审查不设计独立“规则索引”。规则审查直接使用 DocumentIndex 的 text、title、anchor 和 node 顺序。

关键词规则审查要点：

```text
4、5、8、9、16
```

执行流程：

```text
1. 根据审查要点配置关键词或正则。
2. 在 DocumentIndex 的 title/text 中扫描。
3. 返回命中的 node_id、anchor、match_text。
4. 根据审查要点直接生成问题，或展开命中 node 后交给 LLM 复核。
```

标题规则审查要点：

```text
2
```

执行流程：

```text
1. 读取结构树 title。
2. 检查标题是否存在、是否符合审查要求。
3. 如果发现缺失或异常，返回对应 node_id 或父级 node_id。
```

标题顺序规则：

```text
遍历同级 title；
解析 第X条、一、（一） 等序号；
检查是否连续、是否重复、是否跳号、是否层级反转。
```

## 14. 全文遍历型审查

全文遍历型审查要点：

```text
12、15
```

执行方式：

```text
1. 遍历 DocumentIndex 中需要审查的 leaf node 或 chunk node。
2. 每次输入一个 node 的原文给模型。
3. 模型判断该 node 是否存在对应问题。
4. 输出 issue 时必须带 node_id、quoted_text、comment_text。
5. 汇总所有 node 的结果。
```

这种方式可以算作规则审查的一部分，因为它的遍历范围是确定的；但单个 node 内部的问题判断仍然由模型完成。

## 15. 普通 LLM 审查与累加加载

除规则审查、标题审查、全文遍历审查以外的审查要点，使用结构树检索后交给 LLM。

默认流程：

```text
1. 输入审查要点。
2. 读取 summary tree。
3. 根据标题关键词、结构位置或模型选择候选 node。
4. 展开候选 node 原文。
5. 判断内容是否足够。
6. 不足时继续累加相关 node。
7. 基于展开后的原文审查。
8. 输出 issue。
```

累加顺序：

```text
第 1 层：命中的 node
第 2 层：命中 node 的 children
第 3 层：命中 node 的前后 sibling
第 4 层：命中 node 的 parent
第 5 层：被规则命中的交叉引用 node，例如“详见附件”
第 6 层：必要时 vector_search_nodes 返回的 node
```

继续累加条件：

```text
命中 node 太短：< 80 tokens
命中 node 太长但有 children：先展开 children，不直接塞父 node
审查要素不完整
出现引用：详见附件、见清单、另行约定
模型返回“信息不足”
```

建议预算：

```yaml
initial_load_tokens: 3000
max_accumulated_tokens: 12000
min_useful_node_tokens: 80
```

## 16. 向量补召回

向量检索只用于 fallback，不用于构建结构树。

向量索引对象来自 DocumentIndex 中已有 node 或 chunk：

```text
embedding(node.text)
metadata.node_id = node.node_id
metadata.start_anchor = node.start_anchor
metadata.end_anchor = node.end_anchor
```

向量 metadata 必须与结构树统一：

```json
{
  "node_id": "body/sec_002/l2_003",
  "start_anchor": "p_0042",
  "end_anchor": "p_0051",
  "node_type": "section",
  "token_estimate": 720
}
```

触发条件：

```text
结构标题没有命中但审查要点明显需要相关内容；
关键词规则命中太少；
命中 node token < 80；
出现“详见附件/另行约定”但无法解析具体 node；
模型对已展开原文返回信息不足。
```

向量召回结果只用于找到已有 `node_id`。召回后仍然调用 `get_node_content(node_id)` 展开原文，再进行审查。

## 17. 批注定位链路

审查结果必须能回到 DOCX XML。

链路：

```text
task_id
  -> DocumentIndex
  -> node_id
  -> start_anchor/end_anchor
  -> document.xml 中的 w:p / w:tbl
  -> quoted_text 精确匹配字符范围
  -> 插入 commentRangeStart/commentRangeEnd/commentReference
  -> comments.xml 写入批注正文
```

SubAgent 输出 issue 时至少包含：

```json
{
  "node_id": "body/sec_002/l2_003",
  "quoted_text": "支付合同总金额的40%",
  "comment_text": "建议核验付款比例加总是否等于合同总金额。",
  "severity": "medium"
}
```

如果能计算字符位置，则补充：

```json
{
  "char_start": 36,
  "char_end": 48
}
```

## 18. 实施顺序

建议按以下顺序实施：

```text
1. DOCX body child anchor 提取：p/tbl 顺序和文本。
2. DocumentIndex 落盘结构。
3. 顶层区域识别：frontmatter/body/tail/attachments。
4. 正文 Level1/Level2/Level3 标题识别。
5. 附件 section 识别。
6. 附件内部 node 识别。
7. node token 统计与 ChunkNode 切分。
8. summary tree 生成。
9. 结构树加载接口。
10. 关键词规则审查：4、5、8、9、16。
11. 标题规则审查：2。
12. 标题顺序规则检查。
13. 全文遍历审查：12、15。
14. 普通 LLM 审查的累加加载。
15. 向量补召回。
16. 批注定位链路对接。
```

优先稳定结构树和 anchor，再接入向量补召回。否则即使召回命中，也无法可靠展开原文和写回批注。
