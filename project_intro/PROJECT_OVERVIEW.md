# 项目概览

`deep_research_agent` 当前定位为本地合同审查工具：读取合同和审查标准，自动生成一份基于原合同正文的批注 DOCX。

## 当前目标

- 保留原合同正文结构。
- 将审查意见写入 Word 批注。
- 对能匹配到原文的意见，批注挂在对应合同段落上。
- 对合同缺失、无法匹配原文的意见，统一写在合同正文开头位置。
- 输出运行日志和结构化 JSON，便于排查问题。

## 当前流程

1. 解析合同和审查标准。
2. 为当前合同建立临时 LlamaIndex 索引。
3. Planner 拆分审查标准。
4. Orchestrator 针对每个标准检索合同内容并执行审查。
5. Reflector 校验审查输出是否合规。
6. Summarizer 生成简短总览批注。
7. DOCX 生成器把批注写入原合同副本。

## 当前输出

- `docs/reports_docx/`：批注版合同 DOCX。
- `logs/workflow/last_results.json`：逐项审查结果。
- `logs/workflow/last_run_summary.json`：本次运行摘要。
- `logs/workflow/`：工作流日志。

## 当前不作为主流程输出

- Markdown 报告。
- PDF 报告。
- PageIndex 检索。
- Web 搜索。
- 制度库 RAG。
