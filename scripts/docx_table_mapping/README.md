# DOCX 表格 Markdown 映射验证

本脚本验证 `DOCX XML 表格 -> Markdown + source_ref -> 原始 Word 批注位置`。

默认读取同目录 `config.yaml`，将测试批注直接写入配置指定的算力合同副本：

```powershell
python scripts\docx_table_mapping\cli.py
```

配置字段：

```yaml
docx: "C:/path/to/合同.docx"
table_block: 225
write_mode: in_place
backup: true
artifacts_dir: "outputs/table_mapping_test"
```

相对的 `artifacts_dir` 以 `config.yaml` 所在目录为基准，因此默认产物位于本子项目的 `outputs/table_mapping_test`。`in_place` 会先写临时文件并回读验证，验证成功后才替换目标 DOCX。首次执行会在目标文件旁生成 `.before-table-mapping.docx` 备份；重复执行不会重复写入已有 `TCxx` 批注。

命令行参数可覆盖配置：

```powershell
python scripts\docx_table_mapping\cli.py "合同.docx" --table-block 225 --out outputs\table_mapping_test --write-mode copy
```

输出：

```text
attachment4.md
source_map.json
annotation_cases.csv
test_report.json
annotated_test.docx（仅 `write_mode: copy` 时生成）
```

`write_mode: in_place` 时，配置指定的 DOCX 会被替换为带批注版本。批注以 `TC01` 等测试编号开头；失败、歧义和重复用例只记录到报告，不写入批注。

测试脚本将映射结果转换为生产 `results -> issues -> anchors` 结构，并调用 `DocxReportGenerator.generate_annotated_docx()`，不单独实现批注写入。

测试覆盖唯一文本反查、合并单元格、重复短文本歧义、指定 source_ref、未找到、表头、后续表格区域、空格规范化、source mismatch 和重复批注拦截。`test_report.json` 的 `annotation_verification.all_matched=true` 表示新增批注包围的 Word 原文全部与预期一致。
