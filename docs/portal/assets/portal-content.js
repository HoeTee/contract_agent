// 由 docs/*.md 提取重排成的网站结构化内容。
// 块类型: heading | para | list | table | code | callout
// para 与 list.items 内的 `反引号` 会渲染为内联 code。
window.DOCS_PORTAL_CONTENT = {
  "docx-annotation": [
    {
      type: "para",
      text: "本文档说明合同审查中 DOCX 文本清理、`quoted_text` 定位、原合同批注保留和 AI 批注写入的实现逻辑。",
    },
    {
      type: "callout",
      title: "直接结论",
      text: "系统现在区分两份 DOCX 语义：给 subagent 审查的文本用 `clean_docx()` 生成（接受修订并清除原批注）；最终输出的批注版 DOCX 以用户上传的原始 DOCX 为基础，保留原批注和原修订，再追加 AI 批注和黄色高亮。这样 subagent 看到的文本和程序定位 `quoted_text` 的临时匹配文本一致，同时不破坏客户合同里已有的批注和修订痕迹。",
    },

    { type: "heading", text: "审查结果从哪里来" },
    { type: "para", text: "批注生成阶段同时使用两类结构化结果：" },
    {
      type: "list",
      items: [
        "`results`：来自 Orchestrator 执行所有审查标准后的结果。每个 criterion 下包含 SubAgent/Reflector 最终确认的 `issues`，其中每个 issue 提供 `quoted_text` 和 `comment_text`。",
        "`summary_sections`：来自 SummaryAgent 对 `results` 的再汇总，只用于生成文档开头的总览批注。",
      ],
    },
    { type: "para", text: "因此，`results` 不是 SummaryAgent 的输出。真实数据流是：" },
    {
      type: "code",
      text: "SubAgentOutput\n  -> Orchestrator 汇总成 results\n  -> SummaryAgent 读取 results\n  -> 输出 summary_sections\n  -> DOCX 批注生成器同时使用 results 和 summary_sections",
    },
    {
      type: "list",
      items: [
        "`results` 决定逐条问题批注的位置和正文。",
        "`summary_sections` 决定文档开头的总览批注。SummaryAgent 不修改 `results`，不参与 `quoted_text` 定位，也不决定逐条问题批注是否高亮。",
      ],
    },

    { type: "heading", text: "审查文本如何生成" },
    { type: "para", text: "实现位置：`tools/document/file_cleaner.py`" },
    {
      type: "para",
      text: "`clean_docx()` 用于生成给解析器和 subagent 使用的临时 DOCX。它不会作为最终批注版 DOCX 的输出基底。",
    },
    { type: "para", text: "清理规则：" },
    {
      type: "list",
      items: [
        "普通 `w:t` 文本保留。",
        "`w:ins` / `w:moveTo` 中的文本保留，相当于接受插入。",
        "`w:del` / `w:moveFrom` 中的文本删除，相当于接受删除。",
        "`commentRangeStart`、`commentRangeEnd`、`commentReference` 删除。",
        "`word/comments.xml` 和相关 comments part 删除。",
        "修订跟踪设置从 settings 中移除，避免清理后的审查文本继续显示修订状态。",
      ],
    },
    { type: "para", text: "输出结果是“接受修订、移除批注后的合同文本”，供后续解析和审查使用。" },

    { type: "heading", text: "quoted_text 如何映射回原合同" },
    { type: "para", text: "实现位置：`tools/document/reporting/docx_report.py`" },
    {
      type: "para",
      text: "最终批注版 DOCX 不再使用 `clean_docx()` 的结果作为基底，而是直接复制用户上传的原始合同：",
    },
    { type: "code", text: "shutil.copy2(contract_path, output_path)" },
    { type: "para", text: "程序随后在这个原始 DOCX 上构造临时匹配文本。核心结构：" },
    {
      type: "list",
      items: [
        "`CharRef`：临时匹配文本中的一个字符，对应原 DOCX 中的一个 `Run` 和该 run 内的字符 offset。",
        "`ParagraphTextView`：一个段落的临时匹配文本，以及每个字符到原始 run 的 `char_map`。",
        "`TextMatch`：`quoted_text` 在 `ParagraphTextView.text` 中命中的起止字符位置和实际命中文本。",
        "`RunRange`：命中的 `quoted_text` 在某个原始 run 内的起止 offset。",
        "`TextAnchor`：一次 `quoted_text` 命中后的最终定位结果，包含段落、匹配文本和原始 run ranges。",
      ],
    },
    { type: "para", text: "效果链路：" },
    {
      type: "code",
      text: "ParagraphTextView\n  -> TextMatch\n  -> RunRange\n  -> TextAnchor\n  -> Word 批注 XML",
    },
    { type: "para", text: "匹配流程：" },
    {
      type: "list",
      ordered: true,
      items: [
        "遍历原始 DOCX 的段落。",
        "对每个段落构造 `ParagraphTextView`。",
        "构造时使用和 `clean_docx()` 一致的接受修订语义：保留普通文本和 `w:ins` 文本；忽略 `w:del` / `w:moveFrom` 文本；不读取 `comments.xml` 中的批注正文。",
        "将段落内可审查文本拼接成一个临时字符串。",
        "用 subagent 返回的 `quoted_text` 在这个临时字符串里匹配。",
        "匹配成功后生成 `TextMatch`，记录命中的 `start_index`、`end_index` 和 `matched_text`。",
        "通过 `ParagraphTextView.char_map` 找回原始 DOCX 中对应的 run 和 offset。",
        "再把连续的 run + offset 折叠成一个或多个 `RunRange`。",
        "最终生成 `TextAnchor`，供后续高亮和插入批注范围使用。",
      ],
    },
    {
      type: "para",
      text: "因此，`quoted_text` 不是直接去原始 XML 中硬搜，而是先在“接受修订后的临时段落文本”中命中，再映射回原始合同的真实 run 位置。",
    },

    { type: "heading", text: "跨段 quoted_text 匹配" },
    {
      type: "para",
      text: "`quoted_text` 可以跨相邻段落，但必须仍然是合同原文中连续出现的一段文本。当前跨段匹配不是只支持两段，而是通用的连续段落匹配：",
    },
    {
      type: "list",
      ordered: true,
      items: [
        "先为每个可审查段落生成 `ParagraphTextView`。",
        "从任意一个段落开始，把该段和后续相邻段落的 normalized text 连续拼接成 `combined_text`。",
        "在 `combined_text` 中查找 normalized 后的 `quoted_text`。",
        "如果命中，再把命中范围映射回第一个实际覆盖到的 `ParagraphTextView`。",
        "生成 `TextAnchor` 后，只对这个可定位片段插入批注和高亮。",
      ],
    },
    {
      type: "para",
      text: "因此，只要 `quoted_text` 是连续跨相邻段落的文本，跨 2 段、3 段或更多段都使用同一套逻辑，不需要按段数新增代码。",
    },
    { type: "para", text: "不支持的情况：" },
    {
      type: "list",
      items: [
        "`quoted_text` 使用 `...`、`……` 等省略号把两个不相邻片段拼成一个引用。",
        "`quoted_text` 混合正文和附件，或混合不同附件中的不连续证据。",
        "`quoted_text` 是模型概括后的句子，而不是合同原文连续片段。",
      ],
    },
    {
      type: "para",
      text: "这类内容不应由 DOCX 锚定器强行猜测落点。正确处理方式是让 SubAgent 输出可连续匹配的主落点文本；如需多个不连续证据，应在结构上拆成多个证据字段，而不是塞进一个 `quoted_text`。",
    },

    { type: "heading", text: "AI 批注如何写入" },
    { type: "para", text: "实现位置：`tools/document/reporting/docx_report.py`" },
    { type: "para", text: "写入规则：" },
    {
      type: "list",
      items: [
        "原始合同已有的 comments part 不删除。",
        "新 AI 批注 id 从现有最大 comment id 后继续递增，避免覆盖原批注。",
        "总览批注作者为 `AI 审查总结`，正文标题使用 `总体审查结论：` 和 `优先修改建议：`。",
        "总览批注中 `总体审查结论` 和 `优先修改建议` 之间保留一个空白段落。",
        "逐条问题批注作者为 `AI 条款审查`，正文先写入 `风险等级：高/中/低`，再写入修改建议。",
        "命中的文本会被拆分到精确 run 边界。",
        "命中 run 添加 `w:highlight w:val=\"yellow\"`。",
        "程序插入新的 `commentRangeStart`、`commentRangeEnd` 和 `commentReference`。",
        "原合同已有修订结构保留，AI 批注和黄色高亮叠加到命中位置上。",
      ],
    },
    { type: "para", text: "高亮代码逻辑：" },
    {
      type: "list",
      ordered: true,
      items: [
        "`_generate_docx_with_comments()` 读取每个 issue 的 `quoted_text`。",
        "`_find_text_range_anchor()` 尝试把 `quoted_text` 定位成 `TextAnchor`。",
        "成功定位后，`comments_data` 中保存 `TextAnchor`、风险等级和批注正文。",
        "`_add_comments_to_doc()` 写入 `comments.xml` 中的新 `w:comment`。",
        "如果 anchor 是 `TextAnchor`，调用 `_add_comment_markers_to_text_range()`。",
        "`_add_comment_markers_to_text_range()` 根据 `RunRange` 拆分原始 run，并对命中的 run 调用 `_set_run_highlight()`。",
        "`_set_run_highlight()` 在 run 的 `w:rPr` 下写入 `w:highlight w:val=\"yellow\"`。",
        "最后再插入同 id 的 `commentRangeStart`、`commentRangeEnd` 和 `commentReference`。",
      ],
    },
    {
      type: "para",
      text: "如果 issue 没有生成 `TextAnchor`，它不会写入逐条 Word 批注，因此也不会出现没有黄色高亮的逐条 AI 问题批注。总览批注使用段落级 anchor，不属于逐条问题批注，不要求高亮。",
    },
    { type: "para", text: "批注时间使用北京时间：" },
    {
      type: "code",
      text: "datetime.now(timezone(timedelta(hours=8))).isoformat(timespec=\"seconds\")",
    },
    { type: "para", text: "生成的 `w:date` 会包含 `+08:00`，不再使用本地 naive time 加 `Z`。" },

    { type: "heading", text: "Word 批注 XML 完整性约束" },
    {
      type: "para",
      text: "DOCX 批注不是只在正文里插入一个标记。一个有效批注至少同时涉及：",
    },
    {
      type: "list",
      items: [
        "`word/document.xml` 中的 `commentRangeStart`、`commentRangeEnd`、`commentReference`。",
        "`word/comments.xml` 中对应的 `w:comment`。",
        "`word/_rels/document.xml.rels` 中指向标准 comments part 的 relationship。",
      ],
    },
    { type: "para", text: "必须满足以下约束：" },
    {
      type: "list",
      items: [
        "`commentRangeStart/@w:id`、`commentRangeEnd/@w:id`、`commentReference/@w:id` 与 `comments.xml` 中的 `w:comment/@w:id` 必须一致。",
        "`document.xml` 中出现的每个 `commentReference/@w:id`，都必须能在 `word/comments.xml` 中找到同 id 的 `w:comment`。",
        "新增 AI 批注必须写入标准 comments part，relationship type 必须是 `http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments`。",
        "不能用 `reltype` 字符串包含 `comments` 的方式查找 comments part，因为 Word 文档可能同时包含 `commentsExtended.xml`、`commentsIds.xml` 等扩展 part。",
        "如果已有 `comments.xml`，新增批注后要同时更新 python-docx part 的 `_blob` 和 `_element`，避免保存时丢失新批注或破坏旧批注。",
      ],
    },
    {
      type: "para",
      text: "这几个约束来自 Open XML 的基本批注模型：Microsoft Open XML 文档说明 `commentReference` 会把 `Comments.xml` 中的 comment 连接到 `Document.xml` 的具体位置，且 comment、range start、range end、reference 的 id 需要一致；Open XML 标准资料也明确说明，如果 `commentReference` 找不到匹配 id 的 comment，则文档不符合规范。",
    },
    { type: "para", text: "参考资料：" },
    {
      type: "list",
      items: [
        "Microsoft Learn: Insert a comment into a word processing document — https://learn.microsoft.com/en-us/office/open-xml/word/how-to-insert-a-comment-into-a-word-processing-document",
        "Open XML `commentReference` 规范说明 — https://c-rex.net/samples/ooxml/e1/part4/OOXML_P4_DOCX_commentReference_topic_ID0E4PNV.html",
        "ECMA-376 Office Open XML 标准入口 — https://ecma-international.org/publications-and-standards/standards/ecma-376/",
      ],
    },

    { type: "heading", text: "fallback 批注" },
    { type: "para", text: "总览批注保留文档开头批注设计，不要求高亮。" },
    {
      type: "para",
      text: "逐条 issue 批注不再使用文档开头 fallback。原因是逐条问题批注必须对应合同原文中的具体高亮位置：",
    },
    {
      type: "list",
      items: [
        "如果 issue 的 `quoted_text` 成功命中，生成 `TextAnchor`，写入 Word 批注并高亮原文。",
        "如果 issue 没有 `quoted_text`，或者 `quoted_text` 无法在临时匹配文本中命中，程序不会把它写成 Word 批注。",
        "未锚定 issue 仍会记录到同名 `*_annotation_events.json`，用于排查 SubAgent 输出和 quoted_text 质量。",
      ],
    },
    {
      type: "para",
      text: "因此，输出 DOCX 中除总览批注外，所有 AI 问题批注都必须有对应黄色高亮。",
    },

    { type: "heading", text: "为什么有批注但没有高亮" },
    {
      type: "para",
      text: "是否高亮取决于批注锚点类型，而不是批注内容是否提到了具体条款。",
    },
    {
      type: "table",
      headers: ["annotation event 状态", "批注位置", "是否高亮", "含义"],
      rows: [
        ["anchored", "quoted_text 命中的原文位置", "是", "已生成 TextAnchor，程序知道具体 run range。"],
        ["missing_text_fallback", "不写入 Word 批注", "否", "issue 没有提供 quoted_text，没有可高亮文本。"],
        ["unmatched", "不写入 Word 批注", "否", "quoted_text 非空但无法在合同原文中连续命中。"],
      ],
    },
    {
      type: "para",
      text: "所以，看到批注内容里写了某个条款，并不等于程序已经定位到了这个条款。真正判断依据是同名 `*_annotation_events.json`：",
    },
    {
      type: "list",
      items: [
        "`status=anchored`：应当存在黄色高亮。",
        "`status=missing_text_fallback` 或 `status=unmatched`：不会生成逐条 Word 批注。",
        "`matched_text`：程序实际命中的原文。",
        "`paragraph_path`、`start_char`、`end_char`：程序插入批注和高亮的定位信息。",
      ],
    },
    {
      type: "para",
      text: "如果 Word 中出现“批注连接到了具体条款但没有黄色高亮”，应优先检查该批注是不是原合同已有批注，或者检查当前输出 DOCX 的 `document.xml` 中对应 run 是否存在 `w:highlight w:val=\"yellow\"`。除总览外，AI 新增且成功锚定的逐条问题批注应同时具备批注范围和黄色高亮。",
    },

    { type: "heading", text: "测试覆盖" },
    { type: "para", text: "实现位置：`tests/test_docx_report_annotations.py`" },
    { type: "para", text: "当前测试覆盖：" },
    {
      type: "list",
      items: [
        "输入 DOCX 带已有 `comments.xml` 时，输出仍保留原批注。",
        "即使文档同时存在 `commentsExtended.xml`，AI 批注也必须写入标准 `comments.xml`。",
        "新 AI 批注从已有 comment id 后追加。",
        "输入 DOCX 带 `w:ins` 和 `w:del` 时，最终输出仍保留这些原始修订结构。",
        "`quoted_text` 可以按接受修订后的文本命中。",
        "连续跨相邻段落的 `quoted_text` 可以被锚定到实际原文片段。",
        "AI 命中文本被黄色高亮，批注正文包含风险等级。",
        "未锚定 issue 不写入 Word 批注，只记录到 annotation events。",
        "新批注时间包含 `+08:00`。",
        "`clean_docx()` 输出接受修订后的审查文本，并移除原批注 part。",
      ],
    },
  ],

  "review-boundaries": [
    {
      type: "para",
      text: "本文档说明 SubAgent 和 Reflector 当前遵守的合同审查边界。对应提示词定义在 `agents/prompts/cn_prompts.py`。",
    },

    { type: "heading", text: "正文与附件" },
    {
      type: "list",
      items: [
        "正文与附件分开审查。",
        "正文条款只审正文，附件内容只审附件本身。",
        "正文与附件勾稽审查只限于正文附件清单与所有附件标题是否对应。",
        "对正文所列附件，只判断是否存在对应附件标题。",
        "不扩展审查正文条款与附件具体内容是否一致，除非审查标准明确要求。",
      ],
    },

    { type: "heading", text: "兜底条款" },
    {
      type: "para",
      text: "兜底条款是对未逐项列明的违约、损失、责任、救济或未尽事项作一般性覆盖的条款。常见表达包括：",
    },
    {
      type: "list",
      items: ["其他违约情形。", "未尽事宜。", "因违约造成损失应承担赔偿责任。"],
    },
    {
      type: "para",
      text: "审查时不机械要求每份合同都新增兜底条款。合同已有具体责任条款或一般违约责任条款能够覆盖相应风险时，不应输出缺少兜底条款的 issue。",
    },

    { type: "heading", text: "外部数据与法律知识库" },
    {
      type: "para",
      text: "当前审查只基于合同文本和检索到的合同片段，未接入工商、涉诉、知识产权、法人主体、授权信息、法律法规知识库。",
    },
    {
      type: "callout",
      text: "完全依赖外部数据或法律知识库的检查点，SubAgent 不得编造事实，也不得判断有效性、真实性或合规性。此类检查点应返回 `not_applicable`，并在 `applicability_reason` 中说明当前未接入对应数据源。",
    },
    { type: "para", text: "外部依赖项示例：" },
    {
      type: "list",
      items: [
        "通过工商数据比对签约主体是否存在重大涉法涉诉事项。",
        "核对合同提供信息是否与工商登记一致，包括联系地址、联系电话、传真、法定代表人或负责人、联系人等。",
        "判断购买软件等产品是否拥有核心知识产权。",
        "核对签约主体是否为独立法人，以及分公司是否获得相应授权。",
        "判断援引法律法规是否现行有效或适用。",
      ],
    },
    {
      type: "para",
      text: "部分可基于合同文本审查的检查点，只审合同文本能够支持的部分。例如经营范围与合同标的是否匹配，只有在合同文本提供经营范围、资质或相关主体信息时才审查；文本未提供时不得臆测。",
    },

    { type: "heading", text: "Reflector 校验" },
    { type: "para", text: "Reflector 会复核 SubAgent 是否遵守上述边界：" },
    {
      type: "list",
      items: [
        "完全依赖外部数据或法律知识库的检查点，如果 SubAgent 返回 `not_applicable` 且理由明确，应通过。",
        "如果 SubAgent 编造工商、涉诉、知识产权、独立法人、法律法规有效性等外部事实，应退回。",
        "如果 SubAgent 将合同文本内可审查的经营范围、附件清单、合同义务等事项一概返回 `not_applicable`，也应退回。",
      ],
    },
  ],

  "api-review": [
    { type: "para", text: "本文说明无登录、同步执行合同审查的 API：`POST /api/review`。" },
    { type: "para", text: "对应实现：" },
    {
      type: "list",
      items: [
        "`web/routes.py`：定义路由、接收上传、校验 DOCX、调用 workflow、返回 DOCX 或错误 JSON。",
        "`loggers/resolve_api_review_paths.py`：集中生成本次 API 调用的数据目录、日志目录、输入文件路径和输出文件路径。",
        "`main_workflow/main_workflow.py`：执行完整合同审查流程并生成批注版 DOCX。",
      ],
    },
    {
      type: "callout",
      title: "直接结论",
      text: "`/api/review` 不使用 `data/default`，也不写入普通用户目录。默认 `API_STORE=True`，每次 API 调用会在 `data/api/` 下创建一个独立任务目录，合同、审查标准、输出批注合同和日志都保存在这个目录中。",
    },
    {
      type: "code",
      text: "data/\n  api/\n    20260610-153012-a1b2/\n      合同原文件名.docx\n      审查标准原文件名.docx\n      合同原文件名_reviewed.docx\n      logs/\n        api_events.jsonl\n        workflow/\n        conversations/\n        mcp/\n          mcp_client.log",
    },
    { type: "para", text: "目录名格式为 `YYYYMMDD-HHMMSS-xxxx`，其中 `xxxx` 是短随机后缀，用于避免同一秒多次请求冲突。" },

    { type: "heading", text: "接口分层" },
    { type: "para", text: "本项目目前同时存在以下 HTTP 路由类型：" },
    {
      type: "table",
      headers: ["类型", "路由", "用途", "调用方", "返回形式"],
      rows: [
        ["直接 API", "POST /api/review", "无登录、同步执行合同审查", "外部系统、脚本、集成服务", "成功返回 DOCX；失败返回 JSON"],
        ["前端审查", "POST /review", "登录用户在 Web 页面提交审查", "浏览器表单", "立即 303 跳回 /work，审查在后台任务中执行"],
        ["前端状态", "GET /session/status", "前端轮询登录状态和角色", "浏览器 JS", "JSON"],
        ["前端下载", "GET /download/{filename}", "登录用户下载自己的批注版 DOCX", "浏览器", "DOCX 或 404"],
        ["前端页面", "GET /login、/work、/settings、/history", "页面渲染", "浏览器", "HTML 或重定向"],
        ["管理后台", "/admin/...", "用户、审查要点、日志查看管理", "管理员浏览器页面", "HTML、重定向或文件下载"],
      ],
    },
    { type: "para", text: "对外集成时只应使用 `POST /api/review`。`POST /review` 是 Web 前端表单接口，依赖登录态、session、用户目录和后台任务状态，不适合作为外部系统直接调用接口。" },

    { type: "heading", text: ".env 开关" },
    { type: "code", text: "API_STORE=True" },
    {
      type: "table",
      headers: ["值", "行为"],
      rows: [
        ["True", "默认行为。输入文件、输出文件和日志持久保存在 DATA_DIR/api/<任务目录>/。"],
        ["False", "使用系统临时目录执行本次 API；响应完成或失败后清理，不长期保存输入文件、输出文件和日志。"],
      ],
    },
    { type: "para", text: "不需要额外配置 API 目录。持久化目录固定使用现有 `DATA_DIR` 下的 `api/` 子目录；目录不存在时会自动创建。" },

    { type: "heading", text: "输入字段" },
    { type: "para", text: "请求必须使用 `multipart/form-data`。" },
    { type: "para", text: "`file`（必填，DOCX 文件，待审查合同）。代码入口：" },
    { type: "code", text: "file: UploadFile = File(...)" },
    { type: "para", text: "处理链路：" },
    {
      type: "list",
      ordered: true,
      items: [
        "使用 `safe_upload_filename(file.filename)` 清洗上传文件名，只保留文件名，不信任客户端路径。",
        "校验文件名必须以 `.docx` 结尾。",
        "将上传合同写入本次 API 任务目录。",
      ],
    },
    { type: "para", text: "`criteria_file`（可选，DOCX 文件，本次审查专用审查标准）。如果上传了它，会清洗文件名、校验 `.docx`、写入任务目录并保留上传文件名、校验为可读 DOCX、校验内容符合审查标准要求。如果没有上传，则使用系统默认审查标准 `DEFAULT_REVIEW_CRITERIA_PATH`（不存在时返回 404），并复制到任务目录，文件名保持 `criteria.docx`。" },

    { type: "heading", text: "输出文件" },
    { type: "para", text: "workflow 输出的批注版 DOCX 会写入本次 API 任务目录，路径由 `ResolvedApiReviewPaths.final_report_path` 生成，形如 `data/api/<任务目录>/<合同名>_reviewed.docx`。HTTP 响应直接返回这个 DOCX 文件。" },
    {
      type: "callout",
      text: "响应仍会注册后台清理任务，但只有 `API_STORE=False` 时才删除临时目录；`API_STORE=True` 时不会删除 `data/api/<任务目录>/`。",
    },

    { type: "heading", text: "日志目录" },
    { type: "para", text: "`API_STORE=True` 时，API 日志不再写入旧的 `data/api_logs/`，而是写入同一个任务目录下的 `logs/`。" },
    {
      type: "table",
      headers: ["事件", "含义"],
      rows: [
        ["api_review_received", "收到 API 请求"],
        ["criteria_uploaded", "本次请求上传了审查标准"],
        ["criteria_default_saved", "本次请求使用默认审查标准并已复制到任务目录"],
        ["contract_saved", "合同已保存到任务目录"],
        ["docx_validation_passed", "合同 DOCX 校验通过"],
        ["review_started", "workflow 开始运行"],
        ["review_completed", "workflow 成功生成输出 DOCX"],
        ["review_failed", "审查失败"],
      ],
    },

    { type: "heading", text: "成功响应" },
    { type: "para", text: "成功时返回 DOCX 文件，响应头包含：" },
    {
      type: "table",
      headers: ["响应头", "含义"],
      rows: [
        ["X-Review-Task-Id", "本次 API 审查任务 ID"],
        ["X-Review-Log-Path", "本次 API 事件日志路径"],
        ["X-Review-Criteria-Source", "审查标准来源，值为 default 或 uploaded"],
      ],
    },

    { type: "heading", text: "失败响应" },
    { type: "para", text: "失败时返回 JSON，不返回 DOCX，并保留已写入的任务目录便于排查：" },
    {
      type: "code",
      text: '{\n  "task_id": "153012_a1b2c3d4",\n  "status": "failed",\n  "message": "错误信息",\n  "api_events_path": "data/api/20260610-153012-a1b2/logs/api_events.jsonl"\n}',
    },
    {
      type: "table",
      headers: ["HTTP 状态码", "触发条件", "日志事件"],
      rows: [
        ["400", "合同文件名不是 .docx / 旧版 .doc / 非有效 DOCX 结构 / criteria_file 非 .docx 或无法解析", "review_failed"],
        ["404", "未上传 criteria_file 且系统默认审查标准不存在", "review_failed"],
        ["422", "请求不是合法 multipart/form-data，或缺少必填字段 file", "FastAPI 进入路由前返回，通常不写入 api_events"],
        ["503", "Agent、Embedding、Reranker 等模型调用失败（ModelCallError）", "先写具体模型失败事件，再写 review_failed"],
        ["500", "workflow、DOCX 生成或其他未分类异常", "review_failed"],
      ],
    },
    { type: "para", text: "`503` 是模型或外部模型服务类失败，可结合 `X-Review-Task-Id`、返回 JSON 的 `task_id`、`api_events_path` 和任务日志定位组件。`500` 表示服务内部未分类异常，应优先查看 `api_events.jsonl`、`workflow/run_summary.json`、`conversations/` 和 `mcp/` 日志。" },

    { type: "heading", text: "调用示例" },
    { type: "para", text: "PowerShell：" },
    {
      type: "code",
      text: '$form = @{\n  file = Get-Item "C:\\path\\合同A.docx"\n  criteria_file = Get-Item "C:\\path\\本次审查标准.docx"\n}\n\nInvoke-WebRequest `\n  -Uri "http://127.0.0.1:5000/api/review" `\n  -Method Post `\n  -Form $form `\n  -OutFile "合同A_批注版.docx"',
    },
    { type: "para", text: "curl（不上传审查标准时省略 criteria_file，服务端会复制系统默认 criteria.docx）：" },
    {
      type: "code",
      text: 'curl -X POST "http://127.0.0.1:5000/api/review" \\\n  -F "file=@/path/to/合同A.docx" \\\n  -F "criteria_file=@/path/to/本次审查标准.docx" \\\n  -o "合同A_批注版.docx"',
    },
  ],

  deployment: [
    { type: "heading", text: "构建镜像" },
    { type: "code", text: "docker build -t deep-research-agent:latest ." },
    { type: "heading", text: "启动服务" },
    { type: "code", text: "docker compose up -d" },

    { type: "heading", text: "服务器上必须准备的文件和目录" },
    { type: "code", text: ".env\nuser_profiles/\ndata/" },
    { type: "para", text: "当前 `docker-compose.yaml` 会把 `.env`、`user_profiles/` 和 `data/` 挂载进容器：" },
    {
      type: "code",
      text: "volumes:\n  - ./.env:/app/.env:ro\n  - ./user_profiles:/app/user_profiles\n  - ./data:/app/data",
    },
    { type: "para", text: "`user_profiles/` 可以是空目录，首次创建用户时程序会自动生成 `user_profiles/users.json`。它需要可写挂载，因为管理员后台和 CLI 会创建账号，普通用户也可在前端修改显示名称。" },
    { type: "para", text: "如果从旧部署迁移，原来的 `users.json` 需要手动移动到 `user_profiles/users.json`；也可在 `.env` 设置 `USERS_FILE=users.json` 临时兼容旧路径，但新部署推荐使用 `user_profiles/` 目录挂载。" },
    { type: "para", text: "如果要自定义新用户默认审查要点模板，可以挂载单个文件：" },
    { type: "code", text: "- ./criteria.docx:/app/resources/review_criteria/criteria.docx:ro" },
    {
      type: "callout",
      text: "不要挂载空的 `resources/review_criteria/` 目录覆盖容器内默认模板，除非宿主机目录中已经有 `criteria.docx`。",
    },

    { type: "heading", text: "端口说明" },
    { type: "para", text: "当前 compose 命令让容器内部服务监听 `0.0.0.0:8000`。`docker-compose.yaml` 中的端口映射决定外部如何访问。例如：" },
    { type: "code", text: 'ports:\n  - "0.0.0.0:5000:8000"' },
    { type: "para", text: "表示允许通过服务器 5000 端口访问 `http://服务器IP:5000`。如果只允许服务器本机访问，需要改为：" },
    { type: "code", text: 'ports:\n  - "127.0.0.1:5000:8000"' },
    { type: "para", text: "然后访问 `http://127.0.0.1:5000`。" },

    { type: "heading", text: "健康检查" },
    { type: "para", text: "宿主机访问 `http://127.0.0.1:5000/health`。容器内部健康检查访问的是 `http://127.0.0.1:8000/health`，这是容器内端口，不是宿主机端口。" },
  ],

  "user-management": [
    { type: "para", text: "本文是项目用户管理专题文档，覆盖普通用户界面、管理员界面、后端数据、审查要点、CLI 和 Docker 部署落点。前端完整用户旅程、页面状态和多标签页行为见 `FRONTEND_USER_JOURNEY.md`。" },

    { type: "heading", text: "角色和入口" },
    { type: "para", text: "当前系统支持两类角色：`user`（普通用户）和 `admin`（管理员）。角色定义在 `web/auth.py` 的 `VALID_ROLES` 中，实际值保存在用户账号 JSON 里。" },
    {
      type: "list",
      items: [
        "登录成功后，普通用户进入 `/work`。",
        "管理员进入 `/admin`。",
        "管理员访问 `/work`、`/history`、`/settings` 会被重定向回 `/admin`。",
      ],
    },

    { type: "heading", text: "普通用户前端" },
    {
      type: "list",
      items: [
        "`/work`（`web/templates/index.html`）：上传合同 DOCX、可选上传本次审查要点；不上传则用 `data/<username>/contract_review_criteria/criteria.docx`；审核中禁用提交并定时刷新状态；完成后提供下载入口。",
        "`/history`（`web/templates/history.html`）：展示输入/输出文件名、大小、时间、审查要点来源和下载入口。数据读取自 `data/<username>/records/review_history.json`（逻辑在 `loggers/review_history.py`），不是扫描目录生成。",
        "`/settings`（`web/templates/settings.html`）：查看用户名、修改显示名称 `display_name`。显示名称写回账号 JSON，不改变用户目录名。",
      ],
    },

    { type: "heading", text: "管理员前端" },
    { type: "para", text: "管理员后台路由在 `web/admin_routes.py`，数据聚合在 `web/admin_services.py`。" },
    {
      type: "list",
      items: [
        "`/admin`：展示用户总数、管理员数量、禁用用户数量、成功审查数量、最近有审查记录的用户。",
        "`/admin/users`：创建用户、设初始密码/显示名称/角色，查看全部用户，进入详情。创建用户时会初始化用户数据目录并复制系统默认审查要点。",
        "`/admin/users/{username}`：改角色、重置密码、启用/禁用/删除用户（可选保留数据目录）、管理默认审查要点、查看该用户历史和日志。",
      ],
    },
    {
      type: "callout",
      text: "后端保护：管理员不能禁用当前登录的自己、不能删除自己、不能移除自己的管理员角色。",
    },

    { type: "heading", text: "后端账号数据" },
    { type: "para", text: "账号数据路径由 `config.py` 中的 `USERS_FILE` 决定，默认 `<PROJECT_ROOT>/user_profiles/users.json`，可用环境变量覆盖。账号 JSON 结构：" },
    {
      type: "code",
      text: '{\n  "users": [\n    {\n      "username": "user001",\n      "password_hash": "pbkdf2_sha256$...",\n      "display_name": "张三",\n      "role": "user",\n      "enabled": true,\n      "created_at": "2026-06-01 12:00:00"\n    }\n  ]\n}',
    },
    { type: "para", text: "密码只保存 PBKDF2 哈希，不保存明文。禁用用户后，只有“用户名存在、密码正确、但 `enabled=false`”时登录页才显示“账号已被禁用，请联系管理员。”；用户名不存在或密码错误时显示用户名或密码错误。" },

    { type: "heading", text: "用户数据目录" },
    { type: "para", text: "用户数据根目录由 `config.py` 中的 `DATA_DIR` 决定（默认 `<PROJECT_ROOT>/data`）。创建用户后会生成：" },
    {
      type: "code",
      text: "data/<username>/\n  contract_review_criteria/\n    criteria.docx\n  institutional_docs/\n  contracts/\n  reports_docx/\n  records/\n    review_history.json\n  logs/",
    },
    { type: "para", text: "目录初始化逻辑在 `loggers/resolve_review_task_paths.py`。" },

    { type: "heading", text: "审查要点" },
    { type: "para", text: "系统默认审查要点模板是 `resources/review_criteria/criteria.docx`，新建用户时复制到 `data/<username>/contract_review_criteria/criteria.docx`。普通用户在 `/work` 上传的审查要点只用于本次任务；管理员在用户详情页上传会覆盖该用户默认文件。上传前会做 DOCX 格式检查和内容检查，拒绝明显不是审查要点的 DOCX。" },

    { type: "heading", text: "共享用户管理服务与 CLI" },
    { type: "para", text: "CLI 和管理员 Web 页面共用 `services/user_management.py`：`create_user_account()`、`set_user_role()`、`reset_user_password()`、`set_user_enabled()`、`delete_user_account()`。CLI 文件为 `scripts/manage_users.py`。" },
    {
      type: "code",
      text: "# 创建普通用户\npython scripts/manage_users.py create --username user001 --password Abc123456 --display-name 张三\n# 创建管理员\npython scripts/manage_users.py create --username admin --password Admin123456 --display-name 管理员 --role admin\n# 改角色 / 重置密码 / 启停 / 删除\npython scripts/manage_users.py set-role --username user001 --role admin\npython scripts/manage_users.py reset-password --username user001 --password NewPass123\npython scripts/manage_users.py disable --username user001\npython scripts/manage_users.py delete --username user001 --keep-data",
    },
    { type: "para", text: "删除目录前，后端会检查目标路径必须位于 `DATA_DIR` 内，避免误删不安全路径。" },

    { type: "heading", text: "会话与多标签页上下文 (ctx)" },
    { type: "para", text: "Web 登录态保存在 `contract_review_session` cookie 中。同一浏览器多个标签页共享该 cookie，通过 URL 中的 `ctx` 区分各标签页当前账号；ctx 与账号上下文的映射保存在 session 的 `auth_contexts` 中：" },
    { type: "code", text: "auth_contexts[ctx] = {\n  username,\n  display_name,\n  role,\n}" },
    { type: "para", text: "页面 URL 带 ctx，例如 `/work?ctx=<ctx>`、`/history?ctx=<ctx>`、`/admin?ctx=<ctx>`。`POST /logout?ctx=<ctx>` 只退出该 ctx，不影响其他标签页。" },

    { type: "heading", text: "Docker 部署落点" },
    { type: "para", text: "需要区分开发机、远端宿主机、正在运行的服务容器和临时管理容器。仓库默认 `.env.example` 配置 `DATA_DIR=data`、`USERS_FILE=user_profiles/users.json`；compose 挂载后容器内等价于 `/app/data` 和 `/app/user_profiles/users.json`。" },
    {
      type: "callout",
      text: "如果没有挂载 `DATA_DIR`，账号和数据会写进服务容器内部文件系统，容器重建后有丢失风险。",
    },

    { type: "heading", text: "当前边界" },
    {
      type: "list",
      items: [
        "所有用户共享一个 `USERS_FILE`。",
        "用户之间通过 `DATA_DIR/<username>` 分区。",
        "管理员是全局管理员，不是租户管理员。",
        "还没有租户表或租户级权限模型；后续进入租户阶段需扩展为 `data/<tenant_id>/<username>/`。",
      ],
    },
  ],

  "project-structure": [
    { type: "para", text: "仓库整体结构：" },
    {
      type: "code",
      text: "deep_research_agent/\n  README.md\n  app.py\n  main.py\n  config.py\n  user_profiles/\n    users.json\n  agents/\n  main_workflow/\n  mcp_service/\n  tools/\n  services/\n    user_management.py\n  scripts/\n    manage_users.py\n  resources/\n    review_criteria/\n      criteria.docx\n  loggers/\n  web/\n    admin_routes.py\n    admin_services.py\n    auth.py\n    routes.py\n    templates/\n    static/\n  docs/\n  data/\n    <username>/",
    },

    { type: "heading", text: "入口文件" },
    {
      type: "list",
      items: [
        "`app.py`：FastAPI Web 服务入口，创建应用、启用 session middleware、挂载静态文件、注册路由。",
        "`main.py`：本地 CLI 审查入口，按用户分区读取合同和审查要点。",
        "`config.py`：集中读取项目路径和环境变量，包括系统默认审查要点路径。",
      ],
    },

    { type: "heading", text: "Web 目录" },
    {
      type: "list",
      items: [
        "`web/routes.py`：登录、工作台、上传审查、历史记录、下载等 Web 路由。",
        "`web/admin_routes.py`：管理员后台路由（用户管理、审查要点管理、日志查看）。",
        "`web/admin_services.py`：管理员后台展示所需的数据聚合。",
        "`web/auth.py`：用户读取、密码哈希、登录校验。",
        "`web/templates/`：HTML 模板；`web/static/`：CSS 和前端脚本。",
      ],
    },

    { type: "heading", text: "数据目录" },
    { type: "para", text: "`data/` 是运行时持久化目录，按用户名分区：" },
    {
      type: "list",
      items: [
        "`contract_review_criteria/`：该用户默认审查要点，默认文件名 `criteria.docx`。",
        "`institutional_docs/`：制度文档预留目录。",
        "`contracts/`：上传合同原件；`reports_docx/`：批注版合同输出。",
        "`records/`：跨任务结构化记录，当前存放 `review_history.json`。",
        "`logs/`：审查任务日志。",
      ],
    },

    { type: "heading", text: "账号、资源与文档目录" },
    {
      type: "list",
      items: [
        "`user_profiles/users.json`：用户账号持久化文件，首次创建用户时自动生成，不应提交真实账号数据。",
        "`resources/review_criteria/criteria.docx`：系统默认审查要点模板，创建用户目录时复制到用户目录。",
        "`docs/`：只用于存放 Markdown 文档，不作为程序运行时输入或输出目录。",
      ],
    },
  ],

  "logger-design": [
    { type: "para", text: "日志相关代码统一放在 `loggers/` 目录下。`resolve_review_task_paths.py` 负责生成任务编号和所有输入、输出、日志路径；其他 logger 模块只负责写日志。" },

    { type: "heading", text: "任务目录" },
    { type: "para", text: "每次合同审查都会创建一个独立任务目录：" },
    { type: "code", text: "data/<username>/logs/<YYYY-MM-DD>/<HHMMSS_shortid_contractname>/" },
    {
      type: "callout",
      text: "当前普通用户日志目录名包含 task_id 和合同文件名 stem。合同名过长时，conversations 下文件完整路径可能超过 Windows 路径长度限制。后续应收敛为短目录 `data/<username>/logs/<YYYY-MM-DD>/<task_id>/`，合同名通过 records/review_history.json 读取。",
    },
    { type: "para", text: "无登录 API 审查使用独立日志目录 `data/api/<任务目录>/logs/`，不写入用户合同、报告和历史记录目录。`<任务目录>` 由 `loggers/resolve_api_review_paths.py` 生成，格式为 `YYYYMMDD-HHMMSS-xxxx`。" },
    { type: "para", text: "任务目录按日志来源拆分：`workflow/`、`conversations/`、`mcp/`、`api_events.jsonl`。" },

    { type: "heading", text: "日志读取与合同名关联" },
    { type: "para", text: "普通用户历史记录写入 `data/<username>/records/review_history.json`，用于生成历史列表，也用于建立 `task_id` 与合同名的对应关系。关键字段：" },
    {
      type: "code",
      text: '{\n  "task_id": "164455_f78fbf27",\n  "contract_original_name": "原始合同文件名.docx",\n  "contract_stored_name": "20260614_164455_f78fbf27_原始合同文件名.docx",\n  "report_stored_name": "20260614_164455_f78fbf27_原始合同文件名_批注版.docx"\n}',
    },
    { type: "para", text: "日志读取应兼容两种目录：优先用历史记录中的 `task_id` 匹配短目录；短目录不存在时，再匹配以 `<task_id>_` 开头的旧目录。" },

    { type: "heading", text: "各类日志模块" },
    {
      type: "table",
      headers: ["模块", "产出文件", "记录内容"],
      rows: [
        ["loggers/workflow_logger.py", "workflow/workflow_*.md、results.json、run_summary.json", "阶段流转、输入输出摘要、耗时、token 统计、最终结果"],
        ["loggers/agent_logger.py", "conversations/Planner_*.json、SubAgent_*.json、Reflector_*.json、Summarizer_*.json", "agent 调用大模型时的 messages、prompt、response、tool message"],
        ["loggers/mcp_logger.py", "mcp/mcp_client.log", "MCP client 的连接、断开、工具列表和异常"],
        ["loggers/api_event_logger.py", "api_events.jsonl", "API 层事件，每行一个独立 JSON 对象"],
      ],
    },

    { type: "heading", text: "API Event 枚举" },
    {
      type: "code",
      text: "upload_received              收到上传请求和原始文件名\napi_review_received          收到无登录 API 审查请求和原始文件名\ncriteria_uploaded            本次任务上传了临时审查要点\ncontract_saved               合同文件已保存到用户数据目录\ndocx_validation_passed       DOCX 文件格式校验通过\nreview_started               后台审查任务开始执行\nagent_model_call_failed      Agent 大模型调用超时或重试失败\nembedding_call_failed        Embedding 模型调用超时或重试失败\nreranker_call_retry          Reranker 模型调用发生一次重试\nreranker_call_failed         Reranker 模型调用超时或重试失败\nreview_completed             审查完成并生成批注 DOCX\nreview_failed                审查任务失败，记录最终失败原因",
    },
    { type: "para", text: "模型类失败事件会先记录具体组件事件，再记录 `review_failed`。前端 `/work` 显示模型类失败的具体文案；直接 API `/api/review` 返回 `503` 和 JSON；非模型类异常返回通用失败提示并要求查看任务日志。" },

    { type: "heading", text: "日志开关" },
    { type: "para", text: "`.env` 中的 `ENABLE_WORKFLOW_LOGS` 控制是否写入 workflow、conversations、mcp 文件日志。设为 `False` 时任务目录仍可能创建，但这三类不写文件日志；`api_events.jsonl` 仍记录 API 层事件。" },
  ],

  "frontend-journey": [
    { type: "para", text: "本文只描述 Web 前端用户旅程和页面状态，不覆盖 agent 内部审查流程。页面由 `web/routes.py` 提供路由、`web/templates/` 渲染，交互脚本在 `web/static/app.js`。" },

    { type: "heading", text: "页面入口" },
    {
      type: "table",
      headers: ["路径", "角色", "页面/行为"],
      rows: [
        ["/", "未登录用户", "显示登录页"],
        ["/", "普通用户 / 管理员", "重定向到 /work 或 /admin"],
        ["/login", "所有用户", "显示登录页；成功登录后创建新的 ctx"],
        ["/work、/history、/settings", "普通用户", "上传工作台、审核历史、用户设置"],
        ["/admin、/admin/users、/admin/users/{username}", "管理员", "后台首页、用户管理、用户详情"],
      ],
    },
    {
      type: "list",
      items: [
        "`POST /login` 登录成功会创建新的账号上下文 `ctx`，不覆盖其他 tab 的 ctx。",
        "同一浏览器再次登录同一个账号会创建新 ctx，并使该账号旧 ctx 失效。",
        "`POST /logout?ctx=...` 只退出当前 ctx。",
        "同一浏览器多个 tab 共享一个 `contract_review_session` cookie，但每个 tab 通过 URL 中的 `ctx` 区分当前账号。",
        "同一个账号同一时间只允许一个审核任务处于 `queued` 或 `running`。",
      ],
    },

    { type: "heading", text: "完整主旅程" },
    {
      type: "code",
      text: "打开 http://host:5000\n  -> GET /\n  -> session 有效? 否=登录页 login.html / 是=按 role 跳转\n  -> POST /login -> 账号密码正确? 否=显示错误 / 是=创建 ctx(ctx -> username/role)\n  -> 普通用户进入 /work\n  -> 上传合同 DOCX（可选审查要点 DOCX）\n  -> POST /review -> 创建审核任务 review_tasks[username]\n  -> 页面回到 /work 显示审核中\n  -> 后台任务完成，生成批注版 DOCX\n  -> /work 显示下载入口 -> 下载结果或查看历史",
    },

    { type: "heading", text: "审核任务状态旅程" },
    { type: "para", text: "审核任务状态由后端内存字典 `review_tasks` 按用户名记录，前端只展示当前用户自己的任务状态。" },
    {
      type: "code",
      text: "无任务\n  | 用户提交 /review\nqueued\n  | 后台任务开始执行\nrunning\n  | 成功 -> completed -> /work 显示下载入口 -> 用户下载 DOCX\n  | 失败 -> failed    -> /work 显示错误信息 -> 用户重新提交",
    },
    { type: "para", text: "同一用户重复提交时，`get_running_task(user)` 有运行任务则拒绝新任务并回到 /work；无则创建新任务。" },

    { type: "heading", text: "登录和多标签页旅程" },
    { type: "para", text: "浏览器按域名共享 cookie，同一浏览器多个 tab 共享同一个 `contract_review_session`，系统用 URL 里的 `ctx` 区分每个 tab 当前绑定的账号。" },
    {
      type: "code",
      text: "Tab A: 用户 A 在 /work?ctx=A 审核中\n  | 同一浏览器打开 Tab B -> GET /login\n  | 用户 B 登录成功，后端创建 ctx=B\nTab B 自动进入 /work?ctx=B 或 /admin?ctx=B，Tab A 仍保持 /work?ctx=A\n\nTab A: POST /logout?ctx=A -> 后端删除 ctx=A -> Tab A 回到 /login；Tab B 的 ctx=B 仍有效",
    },
    {
      type: "callout",
      text: "ctx 是同一浏览器 session 内的账号上下文，不是跨设备共享登录链接；服务重启或 session cookie 丢失后需要重新登录。",
    },

    { type: "heading", text: "前端自动行为" },
    {
      type: "table",
      headers: ["行为", "触发条件"],
      rows: [
        ["审核中页面自动刷新", "页面存在 .status-box"],
        ["提交表单后禁用提交按钮", "表单带 data-loading-form"],
        ["定时检查 session", "body 带 data-auth-check=\"true\""],
      ],
    },
    { type: "para", text: "session 检查每 10 秒请求 `/session/status`，返回 401 则跳转 `/login`，否则保持当前页。" },

    { type: "heading", text: "当前产品边界" },
    {
      type: "list",
      items: [
        "普通用户不能直接访问管理员页面；管理员 ctx 访问 `/work` 会被重定向回 `/admin?ctx=...`。",
        "同一账号不能同时运行多个审核任务。",
        "不同账号可分别提交任务，但并行数量受 `MAX_API_CONCURRENT_REVIEWS` 控制。",
        "账号 ctx 存在浏览器 session cookie 中；服务重启不保留服务端 ctx 与进行中任务状态。",
        "历史记录来自 `data/<username>/records/review_history.json`，不是扫描输出目录临时生成。",
      ],
    },
  ],

  "quick-start": [
    { type: "para", text: "本文用于验证服务是否能端到端跑通。" },

    { type: "heading", text: "1. 安装依赖" },
    { type: "code", text: "pip install -r requirements.txt" },

    { type: "heading", text: "2. 创建测试用户" },
    { type: "code", text: "python scripts/manage_users.py create --username testuser --password Test123456 --display-name TestUser" },
    { type: "para", text: "创建用户时会自动初始化用户目录，并从 `resources/review_criteria/criteria.docx` 复制默认审查要点。已存在时可用 `reset-password` 重置密码。" },

    { type: "heading", text: "3. 确认审查要点" },
    { type: "para", text: "默认审查要点应已存在于 `data/testuser/contract_review_criteria/criteria.docx`。可在 `/work` 上传本次审查要点临时使用，或用管理员后台进入用户详情页上传覆盖默认审查要点。" },

    { type: "heading", text: "4. 创建管理员用户" },
    { type: "code", text: "python scripts/manage_users.py create --username admin --password Admin123456 --display-name 管理员 --role admin" },

    { type: "heading", text: "5. 启动 Web 服务" },
    { type: "code", text: "uvicorn app:app --host 0.0.0.0 --port 5000" },
    { type: "para", text: "本机浏览器访问 `http://127.0.0.1:5000`，登录 `testuser / Test123456`；管理员后台为 `http://127.0.0.1:5000/admin`。" },

    { type: "heading", text: "6. 上传合同" },
    { type: "para", text: "在页面中上传真实 `.docx` 合同文件。审查成功后会写入以下目录，页面显示批注版 DOCX 下载链接：" },
    { type: "code", text: "data/testuser/contracts/\ndata/testuser/reports_docx/\ndata/testuser/records/review_history.json\ndata/testuser/logs/" },

    { type: "heading", text: "7. 使用 curl 测试" },
    { type: "para", text: "先保存登录 cookie 与 login_token，再登录拿到 ctx，最后带 ctx 上传：" },
    {
      type: "code",
      text: '$loginPage = Invoke-WebRequest -Uri http://127.0.0.1:5000/login -SessionVariable webSession\n$loginToken = [regex]::Match($loginPage.Content, \'name="login_token" type="hidden" value="([^"]+)"\').Groups[1].Value\n\n$loginResponse = Invoke-WebRequest -Uri http://127.0.0.1:5000/login -Method Post -WebSession $webSession -Body @{\n  username = "testuser"; password = "Test123456"; login_token = $loginToken\n}\n$ctx = [regex]::Match($loginResponse.Headers.Location, \'ctx=([^&]+)\').Groups[1].Value\n\n$form = @{ file = Get-Item "data/testuser/contracts/合同文件名.docx" }\nInvoke-WebRequest -Uri "http://127.0.0.1:5000/review?ctx=$ctx" -Method Post -WebSession $webSession -Form $form',
    },
    { type: "para", text: "`$webSession` 是 PowerShell 用来模拟浏览器保存登录态的临时对象；正常 Web 运行时浏览器会自动保存和发送 cookie。" },

    { type: "heading", text: "8. Docker 冒烟测试" },
    { type: "para", text: "确认服务器上存在 `.env`、`user_profiles/`、`data/`（后两者可为空，首次创建用户时自动生成 `users.json`）。构建并启动：" },
    { type: "code", text: "docker build -t deep-research-agent:latest .\ndocker compose up -d" },
    { type: "para", text: "当前 compose 映射 `http://<server-ip>:5000`。只允许本机访问时改 `docker-compose.yaml` 端口为 `127.0.0.1:5000:8000`。" },

    { type: "heading", text: "9. 预期输出" },
    {
      type: "table",
      headers: ["内容", "路径"],
      rows: [
        ["上传合同", "data/testuser/contracts/<task_prefix>_<original_filename>.docx"],
        ["批注结果", "data/testuser/reports_docx/<task_prefix>_<contract_name>_批注版.docx"],
        ["任务日志", "data/testuser/logs/<YYYY-MM-DD>/<task>/"],
        ["历史索引", "data/testuser/records/review_history.json"],
      ],
    },
  ],
};
