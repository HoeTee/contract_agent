# 日志设计

日志相关代码统一放在 `loggers/` 目录下。`resolve_review_task_paths.py` 负责生成任务编号和所有输入、输出、日志路径；其他 logger 模块只负责写日志。

## 任务目录

每次合同审查都会创建一个独立任务目录：

```text
data/<username>/logs/<YYYY-MM-DD>/<HHMMSS_shortid_contractname>/
```

任务目录按日志来源拆分：

```text
workflow/
conversations/
mcp/
api_events.jsonl
```

## 路径解析

模块：

```text
loggers/resolve_review_task_paths.py
```

职责：

```text
为单次审查任务生成任务 ID，以及上传合同、批注输出、审查要点和各类日志的完整路径。
```

主要生成：

```text
stored_contract_path
final_report_path
criteria_path
task_log_dir
workflow_log_dir
conversation_log_dir
mcp_log_dir
api_events_path
```

## Workflow 日志

模块：

```text
loggers/workflow_logger.py
```

文件：

```text
workflow/workflow_YYYYMMDD_HHMMSS.md
workflow/results.json
workflow/run_summary.json
```

记录内容：

```text
workflow 阶段流转、阶段输入输出摘要、耗时、token 统计、最终审查结果和任务摘要。
```

## Agent 对话日志

模块：

```text
loggers/agent_logger.py
```

文件：

```text
conversations/Planner_*.json
conversations/SubAgent_C1_*.json
conversations/Reflector_*.json
conversations/Summarizer_*.json
```

记录内容：

```text
agent 调用大模型时的 messages、system prompt、user prompt、assistant response、tool message 等对话上下文。
```

## MCP 日志

模块：

```text
loggers/mcp_logger.py
```

文件：

```text
mcp/mcp_client.log
```

记录内容：

```text
MCP client 的连接、断开、工具列表和异常信息。
```

## API 事件日志

模块：

```text
loggers/api_event_logger.py
```

文件：

```text
api_events.jsonl
```

`jsonl` 表示每一行都是一个独立 JSON 对象。这里用于追加记录 API 层事件，例如上传文件、DOCX 校验通过、审查开始、审查完成和失败原因。

## 日志开关

`.env` 中的配置控制是否写入 workflow、conversations 和 mcp 文件日志：

```env
ENABLE_WORKFLOW_LOGS=True
```

如果设置为 `False`，任务目录仍可能被创建，但 `workflow/`、`conversations/`、`mcp/` 下不会写入日志文件；`api_events.jsonl` 仍用于记录 API 层事件。
