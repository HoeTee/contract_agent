# 系统架构

## 组件

```text
main.py
  |
  v
ContractReviewWorkflow
  |
  +-- Planner
  +-- Orchestrator
  +-- Reflector
  +-- Summarizer
  |
  v
MCP Server
  |
  +-- ingest_file
  +-- llamaindex_build_index
  +-- llamaindex_search
  +-- generate_docx_report
```

## 阶段

1. `ingest_file` 将合同和审查标准解析为 Markdown。
2. `llamaindex_build_index` 为当前合同建立临时索引。
3. `Planner` 将审查标准拆成结构化任务。
4. `Orchestrator` 对每个任务检索合同上下文并调用审查 agent。
5. `Reflector` 校验 agent 输出格式、引用和修改建议。
6. `Summarizer` 生成总览批注。
7. `generate_docx_report` 基于原合同副本写入 Word 批注。

## 批注写入规则

- 匹配到合同原文的 `quoted_text`：批注挂在对应段落。
- 没有匹配到合同原文的缺失问题：合并后挂在合同正文开头。
- 总结批注作者为 `AI审查总结`。
- 条款批注作者为 `AI条款审查`。

## 存储

- 批注 DOCX：`docs/reports_docx/`
- 原始结果：`logs/workflow/last_results.json`
- 运行摘要：`logs/workflow/last_run_summary.json`
- 工作流日志：`logs/workflow/`
