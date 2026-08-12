# Criterion 级恢复设计

本文说明第二阶段的 criterion 级状态持久化和局部重试设计。该设计不新增外部 API，不新增 Celery task，不新增 Docker worker；它复用第一阶段的 `review-worker`，在 workflow 内部保存每个 criterion 的输入、输出和错误。

## 解决的问题

旧执行方式中，一份合同审查任务进入 `workflow.run()` 后，会经历：

```text
ingest
build_index
plan
execute criteria
summary
generate docx
```

如果 `execute criteria` 阶段某个 `SubAgent_C12` 或 `Reflector_C12` 模型调用失败，异常会导致整份合同任务失败。此时已经完成的 `ingest`、`build_index`、`plan` 和其他已成功 criterion 无法直接复用。

第二阶段第一版的目标是：

```text
只重试失败 criterion
不重跑已成功 criterion
不重新 plan
不把业务状态写入 Redis broker
全部 criterion 成功后才进入 summary/docx
```

## 执行粒度

当前恢复粒度是 criterion，不是单次模型调用。

```text
criterion.C12
  检索合同片段
  SubAgent_C12 生成审查结果
  Reflector_C12 校验结果
  必要时 SubAgent_C12 修正
  产出 C12.output.json
```

这样做的原因是：SubAgent 的答案依赖检索结果和 reflector 反馈。把单次 LLM 调用单独拆出来会让恢复边界过碎，主流程需要额外管理检索结果、反思轮次和最终合并。criterion 是当前最清晰的业务节点。

## State 目录

每个任务会在任务目录下保存恢复状态：

```text
data/api/<task_id>/state/
  plan.json
  criteria/
    C1.input.json
    C1.output.json
    C1.error.json
    C2.input.json
    C2.output.json
```

目录边界：

```text
state/
  程序恢复用，保存最小可重放状态。

logs/
  人工排查用，保存 events.log、trace.json、mcp.log、conversations/。

task.json
  API 状态查询使用，保存任务整体状态。

output/
  保存最终审查后的 DOCX。
```

## 保存内容

`C12.input.json` 保存最小可重放输入：

```json
{
  "task_id": "20260812-120000-abcd",
  "criterion_id": "C12",
  "section": "合同框架",
  "criterion": "合同金额、付款计划是否完整",
  "check_points": ["合同金额", "付款计划"],
  "attempt": 1,
  "max_attempts": 2
}
```

`C12.output.json` 保存 criterion 审查结果：

```json
{
  "criterion_id": "C12",
  "criterion": "合同金额、付款计划是否完整",
  "section": "合同框架",
  "issues": [],
  "status": "COMPLIANT",
  "tokens": 1234,
  "error_message": null,
  "attempt": 1
}
```

`C12.error.json` 保存失败历史：

```json
{
  "task_id": "20260812-120000-abcd",
  "criterion_id": "C12",
  "attempt": 2,
  "max_attempts": 2,
  "latest_error": {
    "attempt": 2,
    "error_type": "ModelCallError",
    "message": "模型调用超时或重试失败",
    "http_status": 429,
    "component": "agent"
  },
  "attempts": []
}
```

不保存：

```text
完整合同全文
完整 API key
完整 conversation
完整 trace
```

这些信息已有固定归属：合同文件在 `input/`，模型对话在 `logs/conversations/`，执行树在 `logs/trace.json`。

## 为什么不写入 broker

Redis broker 只负责调度，不负责保存业务真相。

第一阶段 Celery broker 里只保存短期任务消息：

```text
task = review.run_job
args = client_dir + task_id
```

worker 消费消息后，会根据 `task_id` 读取任务目录。broker 消息不是审查状态主存储，也不适合作为人工排查材料。

criterion 输入、输出、错误使用 JSON 文件保存，是因为：

```text
1. 生命周期更长
   state 文件跟随 task_id 归档，broker 消息是消费型消息。

2. 排查路径更简单
   一个任务的状态、日志、输出都在 data/api/<task_id>/ 下。

3. 避免 Redis 变成隐藏业务数据库
   Redis 保持队列职责，业务恢复状态由项目目录管理。

4. 消息体更小
   broker 只传 task_id，避免重试和重投递时复制大量业务内容。
```

## 配置

```yaml
workflow:
  criterion_retry_max_attempts: 2
```

该配置表示每个 criterion 最多执行几次。它不是 OpenAI SDK 的 HTTP retry；它发生在 workflow 层，用于重新执行失败的 criterion。

## 边界

本阶段不处理：

```text
ingest 失败恢复
build_index 失败恢复
plan 失败恢复
partial_failed 生成 docx
单次 LLM 调用级恢复
embedding/reranker 独立 Celery 化
```

如果某个 criterion 重试耗尽后仍失败，整份合同任务仍会失败；区别是已成功 criterion 的 output 会保存在 `state/criteria/`，下一次重跑同一任务时可以复用。

