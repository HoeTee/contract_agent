# DOCX 结构化索引与检索算法设计

本文设计新的 DOCX 结构化索引方案。目标不是用向量检索替代结构判断，而是先建立类似 PageIndex 的 LLM 可读索引树，再按审查要点选择规则检索、结构检索或必要时的向量补召回。

当前审查要点来源：

```text
resources/criteria/criteria-formal.docx
```

## 1. 设计目标

问题答复：本方案的主线应收敛为 DOCX XML anchor -> 结构树 node -> token 阈值切分 -> summary tree -> 累加加载原文 -> 审查。向量检索不是默认入口，只在结构树和规则索引无法确定候选范围时补召回。

索引需要同时满足四类能力：

1. 支持 LLM 先阅读合同结构树和 section summary，再决定展开哪些正文。
2. 支持正文第三级标题以下超长内容继续切分。
3. 支持附件内部无统一标题样式时的局部结构切分。
4. 支持批注回写到原始 DOCX XML anchor，并尽量携带页码。

不把向量检索作为默认入口。默认入口是结构树和规则索引；向量只在结构或规则无法确定候选范围时补召回。

## 2. 数据来源

问题答复：数据来源足够，但主轴必须是 `word/document.xml` 中 `w:body` 的直接子节点顺序。`outlineLvl`、`pStyle`、字号、加粗、居中等都是标题判断信号，不能替代 `w:p` / `w:tbl` 的阅读顺序和 anchor 边界。

| 数据 | 来源 | 用途 |
|---|---|---|
| 段落顺序 | `word/document.xml` 的 `w:body` 直接子节点 | 保证阅读顺序 |
| 段落文本 | `w:t`、`w:delText` | 生成 node text、标题判断 |
| 表格 | `w:tbl` | 生成 `TableNode` |
| 段落 anchor | 遍历 `w:body > w:p` 生成 `p_0001` | 批注和检索定位 |
| 表格 anchor | 遍历 `w:body > w:tbl` 生成 `tbl_0001` | 表格定位 |
| direct outline | `w:pPr/w:outlineLvl` | 标题强证据 |
| style outline | `w:pPr/w:pStyle -> word/styles.xml` | 标题强证据 |
| style 继承 | `styles.xml` 中 `w:basedOn` 链 | 计算 effective outline |
| 对齐 | `w:pPr/w:jc` | 附件内部视觉标题判断 |
| 字号 | `w:rPr/w:sz` | 附件内部视觉标题判断 |
| 加粗 | `w:rPr/w:b` | 附件内部视觉标题判断 |
| 页码 | `w:lastRenderedPageBreak` | 页码估算 |
| 批注关系 | `word/_rels/document.xml.rels` 指向 `word/comments.xml` | 批注正文读写 |

`effective_outlineLvl` 计算顺序：

```text
1. 段落 direct outlineLvl
2. 当前 pStyle 自身 outlineLvl
3. pStyle basedOn 链上的 outlineLvl
```

## 3. 页码策略

问题答复：页码只能作为展示和人工核查字段，不能作为批注定位依据。DOCX 的 `w:lastRenderedPageBreak` 来自 Word 上次渲染，不是稳定分页模型；批注定位必须依赖 `start_anchor/end_anchor + quoted_text + char_start/char_end`。

DOCX XML 不天然保存稳定页码。可用的是 Word 上次渲染遗留的：

```xml
<w:lastRenderedPageBreak/>
```

页码字段必须带来源和置信度：

```json
{
  "page_start": 4,
  "page_end": 5,
  "page_source": "lastRenderedPageBreak",
  "page_confidence": "medium"
}
```

如果文档没有 `w:lastRenderedPageBreak`：

```json
{
  "page_start": null,
  "page_end": null,
  "page_source": "unavailable",
  "page_confidence": "none"
}
```

页码只用于展示和人工核查；批注定位必须使用 `start_anchor/end_anchor + quoted_text`。

## 4. 顶层区域识别

问题答复：顶层区域识别需要保留，但应只承担粗分区职责：首部、正文、尾部、附件区。`第X条 附件` 是附件父章节，不能和 `附件1/附件2` 这类正式附件 section 混成同一级。

合同先分成四个顶层区域：

```text
ContractIndex
  FrontMatterNode
  BodyNode
  TailNode
  AttachmentRootNode
```

### 4.1 FrontMatterNode

合同首部包括文件标题页、合同名称、合同编号、签约主体信息，以及第一个正式正文标题前的内容。

触发参数：

```json
{
  "frontmatter_max_scan_paragraphs": 80,
  "body_start_patterns": ["^第.+条", "^第.+章"]
}
```

识别规则：

```text
从 document.xml 开始扫描；
遇到第一个正式 第X条/第X章 后，之前内容归入 FrontMatterNode；
如果前 80 个段落内没有正式正文标题，继续扫描全文，但 structure_confidence 降为 medium。
```

### 4.2 BodyNode

正文从第一个正式 `第X条` 或 `第X章` 开始，到正文尾部或附件父章节前结束。

正文中的正式章节不包括：

```text
附件内部的 第一章/第一条
表格单元格内的标题文本
附件清单项中的 附件N
```

### 4.3 TailNode

合同末尾主要用于审查第 17、18 条：

```text
17. 正文结尾处是否写上“以下为合同签署栏”或“以下无正文”
18. 正文结尾处提到附件是否附在正文后，名称是否一致
```

触发标记：

```json
{
  "tail_markers": [
    "以下无正文",
    "以下为合同签署栏",
    "签字",
    "盖章",
    "附件："
  ],
  "tail_scan_after_last_main_section": true
}
```

识别规则：

```text
优先从最后一个非附件正文 section 的末尾向后扫描；
遇到“以下无正文”“以下为合同签署栏”后，后续签署栏内容归入 TailNode；
如果正文附件清单出现在“第X条 附件”内，则同时生成 AttachmentListNode。
```

### 4.4 AttachmentRootNode

附件区从正文中的附件父章节开始：

```json
{
  "attachment_parent_patterns": [
    "^第.+条\\s*附件$",
    "^第.+章\\s*附件$"
  ]
}
```

示例：

```text
第二十条 附件
第十四条 附件
```

## 5. 正文标题层级

问题答复：正文默认提取到三级是合理的。标题判断优先使用编号形态和连续性，`effective_outlineLvl` 是强证据但不是唯一条件，视觉样式只做辅助兜底。

正文默认提取到三级：

```text
Level 1: 第X条 / 第X章
Level 2: 一、
Level 3: （一）
```

判断信号：

```text
1. 文本编号形态
2. 编号连续性
3. effective_outlineLvl
4. 段落样式、字号、加粗、对齐
```

`outlineLvl` 是强证据，不是唯一条件。404 号这类没有 outline 的合同，仍需依靠 `一、二、三` 连续编号识别主层级。

正文标题候选规则：

```json
{
  "main_level_1_patterns": ["^第.+条", "^第.+章", "^[一二三四五六七八九十]+、"],
  "main_level_2_patterns": ["^[一二三四五六七八九十]+、"],
  "main_level_3_patterns": ["^（[一二三四五六七八九十]+）"],
  "require_sequence_for_no_outline": true,
  "min_sequence_siblings": 2
}
```

## 6. 第三级超长切分

问题答复：这里不应照搬 PageIndex 的 20000 token。合同审查需要精确计算和批注定位，建议使用 `node_target_tokens=700`、`node_soft_limit_tokens=1000`、`node_hard_limit_tokens=1800`：超过软阈值优先按子编号继续拆，超过硬阈值必须拆。

第三级标题下内容可能过长。触发阈值：

```json
{
  "level3_split_char_threshold": 1800,
  "level3_split_token_threshold": 1000,
  "chunk_target_tokens": 700,
  "chunk_overlap_tokens": 80
}
```

触发行为：

```text
如果 Level3 node <= 1000 token：
  保持完整 Level3 node。

如果 Level3 node > 1000 token：
  先按局部编号 1. / 1、 / 1.1 拆成 ListItemNode 或 SubHeadingNode。

如果拆分后的单个子 node 仍 > 1000 token：
  按段落窗口生成 ChunkNode。

如果包含表格：
  表格作为独立 TableNode，不拆散到多个 chunk。
```

ChunkNode 字段示例：

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

## 7. 附件 section 识别

问题答复：附件 section 识别应优先限定上下文，再判断标题形态。只有位于 `第X条 附件` 之后或正文末尾附件区内的 `附件1/附件一/附件1：/附件1、` 才应作为正式附件 section；正文里的“详见附件3”和附件清单项不能直接升格为附件 section。

附件识别和正文标题识别分开处理。

正式附件标题候选：

```text
附件1
附件1 软件产品配置清单
附件1：备品备件清单
附件1、非标准技术人天付费标准
```

排除清单项：

```text
附件：
附件1：xxx
3. 附件3：xxx
4、附件4：xxx
```

排除项不是丢弃，而是生成：

```text
AttachmentListNode
  AttachmentListItemNode
```

正式附件 section 规则：

```json
{
  "attachment_title_pattern": "^附件\\s*[0-9一二三四五六七八九十]+(?:\\s*$|[：:、\\s])",
  "attachment_list_item_pattern": "^\\d+[.、]\\s*附件",
  "prefer_later_duplicate_attachment_number": true,
  "require_following_content_or_table": true
}
```

如果同一个附件编号出现两次：

```text
第一次位于“附件：”清单区；
第二次后面跟正文或表格；
则第二次作为正式 AttachmentSectionNode。
```

## 8. 附件内部切分

问题答复：附件内部不能依赖统一 `outlineLvl`。应使用 DOCX 可取得的视觉标题信号打分，例如短文本、居中、加粗比例、字号、后续是否出现正文/编号标题/表格。这是模仿 PageIndex 的版式信号思想，不是复用 PageIndex 的 PDF 解析代码。

附件内部不以 `outlineLvl` 为主。附件内部标题大多没有有效 outline，需要局部结构识别。

附件内部 node 类型：

| 类型 | 识别依据 |
|---|---|
| `LocalDocNode` | 附件开头或中部的短文本，居中/加粗/大字号，后面跟正文、编号或表格 |
| `ChapterNode` | `第一章`、`第二章` |
| `ArticleNode` | `第一条`、`第二条` |
| `HeadingNode` | `一、`、`（一）` 且形成连续编号 |
| `PlainLabelNode` | `考核目的。`、`质量要求：`、`验收要求：` |
| `ListItemNode` | `1.`、`1、`、`1.1` 连续编号链 |
| `TableNode` | `w:tbl` |
| `ParagraphNode` | 普通段落 |

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

同段标题正文拆分：

```text
（一）外包工作质量。主要衡量外包人员...
```

输出：

```json
{
  "node_type": "heading",
  "title": "（一）外包工作质量。",
  "body": "主要衡量外包人员...",
  "start_anchor": "p_0626",
  "end_anchor": "p_0626"
}
```

PlainLabel 只作为中低层级节点，不直接等同于正式章节：

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

## 9. Node 字段设计

问题答复：字段设计需要强制区分三类 ID：`node_id` 是系统自建结构树 ID，`start_anchor/end_anchor` 是 DOCX body child anchor，`xml_native_id` 保存 Word 原生 ID。最终批注应从 node anchor 回到原始 XML 位置。

每个 node 必须保留结构、检索、批注和页码字段。

```json
{
  "node_id": "body/sec_020/att_011/local_002/h_005",
  "node_type": "section",
  "title": "（五）考勤考核制度及罚则。",
  "body": "",
  "text": "完整可检索文本",
  "summary": "本节点主要约定驻场外包人员考勤违规的扣费和辞退规则。",
  "path": [
    "第二十条 附件",
    "附件11",
    "科技部门驻场外包考核细则",
    "（五）考勤考核制度及罚则。"
  ],
  "start_anchor": "p_0649",
  "end_anchor": "p_0656",
  "page_start": 12,
  "page_end": 13,
  "page_source": "lastRenderedPageBreak",
  "page_confidence": "medium",
  "parent_id": "body/sec_020/att_011/local_002",
  "children_ids": [],
  "char_count": 1200,
  "token_estimate": 850,
  "structure_confidence": "high",
  "reasons": [
    "paren_cn_sequence",
    "inside_attachment_section"
  ]
}
```

`node_id` 是系统生成的索引 ID；`start_anchor/end_anchor` 是 DOCX XML 定位范围。批注工具不得用 `node_id` 直接写入 DOCX，必须回到 anchor 范围定位。

## 10. Summary Tree

问题答复：summary tree 只负责导航，不负责最终事实判断。LLM 可以读取 summary tree 来选择需要展开的 node；一旦进入审查，必须展开对应原文 node，再基于原文、规则结果和 anchor 输出问题。

结构树需要给 LLM 一个低 token 的总览。

summary 触发参数：

```json
{
  "summary_trigger_min_tokens": 300,
  "summary_max_tokens": 120,
  "section_summary_max_tokens": 180,
  "attachment_summary_max_tokens": 200
}
```

summary 内容要求：

```text
SectionNode:
  概括本节主题、金额、期限、义务、附件引用。

AttachmentNode:
  概括附件类型、是否表格清单、是否包含技术要求、验收、维保、承诺。

LongNode:
  概括内部子结构和关键词，不替代原文。
```

summary 不参与最终事实判断。最终审查必须展开原文 node 或走规则索引。

## 11. 规则索引

问题答复：规则索引应保持简单，负责全文关键词、金额、比例、日期、附件引用等可计算信号的扫描。它的输出是候选 anchor/node，不直接替代 LLM 的法律语义判断。

规则索引服务 `criteria-formal.docx` 中确定性审查点。

字段：

```json
{
  "titles": [],
  "parties": [],
  "amounts": [],
  "dates": [],
  "invoice_types": [],
  "payment_terms": [],
  "sensitive_words": [],
  "attachment_references": [],
  "attachment_sections": [],
  "tail_markers": []
}
```

典型用途：

| 审查要点 | 规则索引字段 |
|---:|---|
| 1 合同基本信息 | `parties`、`frontmatter` |
| 2 必备标题 | `titles` |
| 3 项目负责人 | `full_text_keywords`、正则 |
| 4 合同名称含采购 | `contract_title` |
| 5 目录含金额 | `titles` |
| 6 支付方式 | `payment_terms`、`amounts`、`invoice_types` |
| 7 合同期限 | `dates`、期限表达式 |
| 8 违约责任 | `titles` |
| 9 甲方住所地人民法院 | `full_text_keywords` |
| 10 主体一致 | `parties` |
| 11 正文附件一致 | `structure_tree` + 补召回 |
| 12 错别字 | 全文通读或语言检查 |
| 13 标题顺序 | `structure_tree` |
| 14 金额大小写一致 | `amounts` |
| 15 语病重复 | 全文通读或语言检查 |
| 16 敏感词 | `sensitive_words` |
| 17 正文结尾 | `tail_markers` |
| 18 附件名称一致 | `attachment_references`、`attachment_sections` |

## 12. 检索流程

问题答复：检索流程应采用累加加载：先用规则索引和结构树 summary 找候选 node，再展开候选原文；如果内容不足，再按 children、相邻 sibling、parent、引用 node 的顺序继续累加，直到满足审查要素或达到预算。

默认流程：

```text
criterion
  -> criterion profile
  -> rule_index / structure_tree
  -> 判断内容是否足够
  -> 必要时 vector recall
  -> 展开原文 node
  -> 规则或 LLM 审查
  -> anchor resolver
  -> comment writer
```

内容不足的可计算条件：

```json
{
  "min_section_tokens": 80,
  "external_reference_patterns": [
    "详见附件",
    "见附件",
    "以附件",
    "详见.*清单",
    "详见.*说明书"
  ],
  "required_signal_missing_triggers_vector": true
}
```

触发向量补召回的条件：

```text
1. 结构标题未命中。
2. 结构命中但 token < 80。
3. 结构命中但缺少审查必要信号。
4. section 明确引用附件或清单。
5. 审查要点天然跨章节，例如正文与附件相同条款一致性。
6. 结构候选超过阈值，需要 rerank。
```

候选过多参数：

```json
{
  "structure_candidate_rerank_threshold": 12,
  "vector_top_k": 8,
  "rerank_top_k": 5
}
```

## 13. 第 6 条支付方式示例

问题答复：支付方式审查不适合纯向量检索。正确路径是结构树定位“合同金额及支付方式”，规则索引抽取总价、分项价、付款比例、固定金额、发票类型和维保节点，再展开完整支付章节进行加总核验。

审查要点：

```text
如果合同目录中出现“支付方式”四字，对于这个标题下的内容进行检索...
```

profile：

```json
{
  "criterion_id": 6,
  "strategy": "structure_then_rule",
  "title_keywords": [
    "支付方式",
    "付款",
    "价款",
    "合同金额",
    "结算"
  ],
  "required_signals": [
    "payment_amount_or_percent",
    "payment_trigger",
    "invoice_type"
  ],
  "vector_enabled": "fallback_only"
}
```

流程：

```text
1. 在 structure_tree 中找标题含“支付方式/付款/价款/合同金额/结算”的 node。
2. 如果找到完整 section，展开原文。
3. 规则抽取合同总金额、分项金额、付款金额、付款比例、发票类型、排除项。
4. 分类加总：
   - 合同总金额比例
   - 分项金额比例
   - 固定金额
   - 履约保证金/押金/违约金/抵扣款排除
5. 规则输出问题 anchor。
6. LLM 只负责将确定性计算结果改写成审查意见。
```

如果 section 只写：

```text
具体支付安排详见附件4《服务费用结算清单》。
```

则触发：

```text
结构引用附件 -> 找附件4 -> 如果附件标题不清楚，再向量补召回。
```

## 14. 向量检索的位置

问题答复：向量检索只用于补召回。触发场景包括标题没有命中但语义相关、关键词规则未覆盖同义表达、结构命中内容过短、出现不明确引用、或模型明确判断信息不足。

向量索引建立在结构 node 上，不替代结构树。

向量 node 来源：

```text
1. section summary
2. attachment summary
3. leaf node text
4. 超长 section 的 chunk text
```

metadata 必须包含：

```json
{
  "node_id": "body/sec_006",
  "node_type": "section",
  "path": ["第二条 合同金额及支付方式"],
  "start_anchor": "p_0045",
  "end_anchor": "p_0058",
  "page_start": 2,
  "page_end": 3,
  "summary": "..."
}
```

向量检索只返回候选，不做最终判断。最终判断仍由规则或 LLM 基于原文完成。

## 15. 输出给 LLM 的结构

问题答复：输出给 LLM 应分为导航输入和原文输入。导航输入只包含 `node_id/title/summary/page/token_estimate` 等轻量字段；原文输入才包含 `text/anchors`。不能一开始把所有 node 原文交给 LLM。

先给 summary tree：

```json
{
  "contract_title": "2026年度GPU算力服务租赁项目合同",
  "frontmatter_summary": "首部包含合同名称、合同编号、甲乙方基本信息。",
  "body_sections": [
    {
      "node_id": "body/sec_002",
      "title": "第二条 合同金额及支付方式",
      "summary": "约定合同总价、付款节点、发票类型和账户信息。",
      "page_start": 2,
      "page_end": 3
    }
  ],
  "attachments": [
    {
      "node_id": "attachment/att_007",
      "title": "附件7 算力服务资源验收要求",
      "summary": "约定产品验收、项目验收和验收失败情形。",
      "page_start": 18,
      "page_end": 19
    }
  ]
}
```

需要审查时再展开原文 node：

```json
{
  "node_id": "body/sec_002",
  "title": "第二条 合同金额及支付方式",
  "text": "第二条 合同金额及支付方式\n一、合同总价...",
  "start_anchor": "p_0045",
  "end_anchor": "p_0058",
  "page_start": 2,
  "page_end": 3
}
```

## 16. 实施顺序

问题答复：实施顺序应先稳定结构和 anchor，再做召回增强。优先完成 body child anchor、正文标题层级、附件 section、附件内部切分、token 切分、summary tree、规则索引和累加加载；向量补召回应放在结构链路稳定之后。

建议分三阶段实施：

```text
阶段 1：结构索引
  - FrontMatter/Body/Tail/AttachmentRoot
  - 正文三级标题
  - 附件 section
  - node anchor/page 字段

阶段 2：细分与 summary
  - 第三级超阈值切分
  - 附件内部 LocalDoc/Heading/List/Table
  - summary tree

阶段 3：检索接入
  - criterion profile
  - rule_index
  - fallback vector recall
  - LlamaIndex TextNode metadata 对齐
```

阶段 1、2 完成前，不建议改动现有审查主流程。
