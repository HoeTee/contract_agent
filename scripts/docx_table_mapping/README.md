# DOCX 表格 Markdown 映射验证

本脚本验证 `DOCX XML 表格 -> Markdown + source_ref -> 原始 Word 批注位置`。

默认运行指定的算力合同副本及附件4表格：

```powershell
python scripts\docx_table_mapping\cli.py
```

指定其他文件和正文表格 block：

```powershell
python scripts\docx_table_mapping\cli.py "合同.docx" --table-block 225 --out outputs\table_mapping_test
```

输出：

```text
attachment4.md
source_map.json
annotation_cases.csv
test_report.json
annotated_test.docx
```

原始 DOCX 不会被修改。`annotated_test.docx` 中的批注以 `TC01` 等测试编号开头；失败、歧义和重复用例只记录到报告，不写入批注。

测试覆盖唯一文本反查、合并单元格、重复短文本歧义、指定 source_ref、未找到、表头、后续表格区域、空格规范化、source mismatch 和重复批注拦截。`test_report.json` 的 `annotation_verification.all_matched=true` 表示新增批注包围的 Word 原文全部与预期一致。
