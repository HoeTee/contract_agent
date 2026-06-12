# DOCX 批注与修订处理说明

本文档说明合同审查中 DOCX 文本清理、`quoted_text` 定位、原合同批注保留和 AI 批注写入的实现逻辑。

## 直接结论

系统现在区分两份 DOCX 语义：

- 给 subagent 审查的文本：使用 `clean_docx()` 生成，接受修订并清除原批注。
- 最终输出的批注版 DOCX：以用户上传的原始 DOCX 为基础，保留原批注和原修订，再追加 AI 批注和黄色高亮。

这样做的目的，是让 subagent 看到的文本和程序定位 `quoted_text` 时使用的临时匹配文本一致，同时不破坏客户上传合同中已有的批注和修订痕迹。

## 审查文本如何生成

实现位置：

- `tools/document/file_cleaner.py`

`clean_docx()` 用于生成给解析器和 subagent 使用的临时 DOCX。它不会作为最终批注版 DOCX 的输出基底。

清理规则：

- 普通 `w:t` 文本保留。
- `w:ins` / `w:moveTo` 中的文本保留，相当于接受插入。
- `w:del` / `w:moveFrom` 中的文本删除，相当于接受删除。
- `commentRangeStart`、`commentRangeEnd`、`commentReference` 删除。
- `word/comments.xml` 和相关 comments part 删除。
- 修订跟踪设置从 settings 中移除，避免清理后的审查文本继续显示修订状态。

输出结果是“接受修订、移除批注后的合同文本”，供后续解析和审查使用。

## quoted_text 如何映射回原合同

实现位置：

- `tools/document/reporting/docx_report.py`

最终批注版 DOCX 不再使用 `clean_docx()` 的结果作为基底，而是直接复制用户上传的原始合同：

```python
shutil.copy2(contract_path, output_path)
```

程序随后在这个原始 DOCX 上构造临时匹配文本。

核心结构：

- `CharRef`：临时匹配文本中的一个字符，对应原 DOCX 中的一个 `Run` 和该 run 内的字符 offset。
- `ParagraphTextView`：一个段落的临时匹配文本，以及每个字符到原始 run 的 `char_map`。
- `RunRange`：命中的 `quoted_text` 在某个原始 run 内的起止 offset。
- `TextAnchor`：一次 `quoted_text` 命中后的最终定位结果，包含段落、匹配文本和原始 run ranges。

匹配流程：

1. 遍历原始 DOCX 的段落。
2. 对每个段落构造 `ParagraphTextView`。
3. 构造时使用和 `clean_docx()` 一致的接受修订语义：
   - 保留普通文本和 `w:ins` 文本。
   - 忽略 `w:del` / `w:moveFrom` 文本。
   - 不读取 `comments.xml` 中的批注正文。
4. 将段落内可审查文本拼接成一个临时字符串。
5. 用 subagent 返回的 `quoted_text` 在这个临时字符串里匹配。
6. 匹配成功后，通过 `char_map` 找回原始 DOCX 中对应的 run 和 offset。
7. 再把 run + offset 转成 `RunRange`，供后续高亮和插入批注范围使用。

因此，`quoted_text` 不是直接去原始 XML 中硬搜，而是先在“接受修订后的临时段落文本”中命中，再映射回原始合同的真实 run 位置。

## AI 批注如何写入

实现位置：

- `tools/document/reporting/docx_report.py`

写入规则：

- 原始合同已有的 comments part 不删除。
- 新 AI 批注 id 从现有最大 comment id 后继续递增，避免覆盖原批注。
- 命中的文本会被拆分到精确 run 边界。
- 命中 run 添加 `w:highlight w:val="yellow"`。
- 程序插入新的 `commentRangeStart`、`commentRangeEnd` 和 `commentReference`。
- 原合同已有修订结构保留，AI 批注和黄色高亮叠加到命中位置上。

批注时间使用北京时间：

```python
datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
```

生成的 `w:date` 会包含 `+08:00`，不再使用本地 naive time 加 `Z`。

## fallback 批注

如果某个 issue 没有可用 `quoted_text`，或者 `quoted_text` 无法在临时匹配文本中命中，程序不会强行批到错误位置。

这类内容会汇总成文档开头的 fallback 批注。

总结性批注也会添加在文档开头第一个可批注段落上。

## 测试覆盖

实现位置：

- `tests/test_docx_report_annotations.py`

当前测试覆盖：

- 输入 DOCX 带已有 `comments.xml` 时，输出仍保留原批注。
- 新 AI 批注从已有 comment id 后追加。
- 输入 DOCX 带 `w:ins` 和 `w:del` 时，最终输出仍保留这些原始修订结构。
- `quoted_text` 可以按接受修订后的文本命中。
- AI 命中文本被黄色高亮。
- 新批注时间包含 `+08:00`。
- `clean_docx()` 输出接受修订后的审查文本，并移除原批注 part。

