# DOCX 检索索引 CLI

这是用于试验合同 DOCX 结构树索引、LLM 语义拆分、LLM 摘要、向量补召回和原文上下文展开的命令行工具。统一入口：

```powershell
python scripts\docx_retrieval_cli\cli.py <command>
```

## 安装依赖

```powershell
pip install -r scripts\docx_retrieval_cli\requirements.txt
```

主要依赖：

- `lxml`：解析 `word/document.xml`、`word/styles.xml`。
- `openai`：调用 OpenAI-compatible LLM 和 embedding 模型。
- `pydantic`：校验索引、LLM 输出和检索配置。
- `PyYAML`：读取配置。
- `tiktoken`：估算结构树、向量候选和原文上下文 token。

## 配置

默认配置文件：

```text
scripts/docx_retrieval_cli/config.yaml
```

自动路由配置文件：

```text
scripts/docx_retrieval_cli/route.yaml
```

`route.yaml` 从 `resources/criteria/criteria-formal.docx` 读取正式审查要点，只配置五种通用检索方法及预算，不保存“审查要点编号 -> 方法”的硬编码映射。

默认内容：

```yaml
retrieval:
  input_tokens: 20000
  max_depth: 6
  vector:
    enabled: true
    score_threshold: 0.60
    auto_build: true
  rerank:
    enabled: true
```

含义：

- `input_tokens`：结构树输入、向量候选、rerank 候选、原文上下文展开共用的单次输入预算。默认 20000，用于减少结构树分页次数。
- `max_depth`：结构树最大深度，当前作为配置保留。
- `vector.enabled`：`ask` 默认启用向量补召回。
- `vector.score_threshold`：低于该相似度的向量候选不进入候选池。
- `vector.auto_build`：缺少 `vector_index.json` 时，`ask` 默认自动构建。
- `rerank.enabled`：默认对结构召回和向量召回合并后的候选做 rerank。

LLM 请求默认携带 `enable_thinking=false`。结构树选点和 rerank 属于检索阶段，不需要模型输出长 thinking 内容。

LLM 和 embedding 地址优先级：

```text
CLI 参数 > scripts/docx_retrieval_cli/.env > 系统环境变量 > 项目 config.yaml > 内置默认值
```

`.env` 支持：

```text
LLM_MODEL_NAME
LLM_BASE
LLM_API_KEY
EMBEDDING_MODEL_NAME
EMBEDDING_BASE
EMBED_API_KEY
```

## 建立索引

默认 build 执行完整流程：

```text
确定性 DOCX XML 解析
-> LLM expand
-> LLM summary
-> vector index
```

单文件：

```powershell
python scripts\docx_retrieval_cli\cli.py build "C:\path\contract.docx" --out outputs\docx_index
```

目录批量：

```powershell
python scripts\docx_retrieval_cli\cli.py build "C:\Users\lenovo\Downloads\合同样例" --out outputs\docx_index --batch
```

关闭某个阶段：

```powershell
python scripts\docx_retrieval_cli\cli.py build "C:\path\contract.docx" --out outputs\docx_index --no-vector
python scripts\docx_retrieval_cli\cli.py build "C:\path\contract.docx" --out outputs\docx_index --no-llm-expand
python scripts\docx_retrieval_cli\cli.py build "C:\path\contract.docx" --out outputs\docx_index --no-llm-summary
python scripts\docx_retrieval_cli\cli.py build "C:\path\contract.docx" --out outputs\docx_index --no-cache
```

`--llm-summary` 不再需要显式传入。默认生成的 node summary 控制在 200 tokens 内。summary 用于 LLM 读取结构树并选择 node，不用于替代原文审查。

如果只想快速验证确定性 DOCX XML 解析，不调用模型、不构建向量：

```powershell
python scripts\docx_retrieval_cli\cli.py build "C:\path\contract.docx" --out outputs\docx_index --no-llm-expand --no-llm-summary --no-vector
```

## 检索

完整检索：

```powershell
python scripts\docx_retrieval_cli\cli.py ask --doc "outputs\docx_index\合同目录名" --query "支付方式"
```

`ask` 默认流程：

```text
读取 structure_tree 与正式审查要点
-> LLM 自动规划 title/region/rule/join/scan 路由
-> 执行确定性标题、区域、全文关键词或全文扫描
-> 仅在路由要求 fallback 或确定性结果为空时执行结构树 LLM + vector + rerank
-> 从 content_store/anchor_store 展开原文 nodes
```

五种业务路由：

- `title`：检查正式目录标题及顺序；完整目录返回全部正式章节标题。
- `region`：返回合同首部、正文、合同末尾、附件，或明确标题下的内容。
- `rule`：扫描全部 anchor，返回所有精确关键词、枚举敏感词及金额字面命中。
- `join`：组合主体首尾、正文与附件或其他多区域证据。
- `scan`：按 `anchor_store` 阅读顺序返回全文，超出预算时通过 `next_part` 继续。

原有结构树 LLM、向量召回和 rerank 是内部语义 fallback，不作为第六种业务路由。

关闭向量补召回：

```powershell
python scripts\docx_retrieval_cli\cli.py ask --doc "outputs\docx_index\合同目录名" --query "支付方式" --no-vector
```

关闭 rerank：

```powershell
python scripts\docx_retrieval_cli\cli.py ask --doc "outputs\docx_index\合同目录名" --query "支付方式" --no-rerank
```

关闭 LLM 结果缓存：

```powershell
python scripts\docx_retrieval_cli\cli.py ask --doc "outputs\docx_index\合同目录名" --query "支付方式" --no-cache
```

临时调整输入预算：

```powershell
python scripts\docx_retrieval_cli\cli.py ask --doc "outputs\docx_index\合同目录名" --query "支付方式" --input-tokens 30000
```

只做关键词检索，不调用模型：

```powershell
python scripts\docx_retrieval_cli\cli.py search --doc "outputs\docx_index\合同目录名" --keyword "支付方式"
```

只做向量检索：

```powershell
python scripts\docx_retrieval_cli\cli.py vector-search --doc "outputs\docx_index\合同目录名" --query "支付方式"
```

展开单个 node 原文：

```powershell
python scripts\docx_retrieval_cli\cli.py content --doc "outputs\docx_index\合同目录名" --node body/sec_002
```

## 返回结果

`ask` 默认只返回最终可给审查 LLM 使用的节点：

```json
{
  "query": "支付方式",
  "mode": ["title", "region"],
  "nodes": [],
  "next_part": 2,
  "elapsed_seconds": 1.234
}
```

只有仍有后续原文批次时才返回 `next_part`。调用方使用同一 Query 加 `--part 2` 继续获取；确定性 `rule` 与 `scan` 不会因为单次输出 token 上限而缩小扫描范围。

评测或离线批处理需要在一次固定路由计划中取得全部页时使用：

```powershell
python scripts\docx_retrieval_cli\cli.py ask --doc "outputs\docx_index\合同目录名" --query "是否有错别字" --all-parts
```

`--all-parts` 可能返回大量原文，不应直接用于单次审查模型输入。

真正进入后续审查 prompt 的字段应只使用：

```text
nodes[].node_id
nodes[].title
nodes[].text
nodes[].start_index
nodes[].end_index
nodes[].start_anchor
nodes[].end_anchor
```

开启 `--debug` 后才额外返回内部过程：

```powershell
python scripts\docx_retrieval_cli\cli.py ask --doc "outputs\docx_index\合同目录名" --query "支付方式" --debug
```

debug 中的 `route_plan`、`routed_matches`、`structure_matches`、`vector_matches`、`ranked_matches`、`pagination`、`budget` 只用于调试和控制，不进入审查正文 prompt。

## 耗时与日志

默认会在 stderr 输出阶段耗时，不影响 stdout JSON：

```text
[timing] ask.llm_structure_query.part_count: 1
[timing] ask.llm_structure_query.part_1: 15.451s
[timing] ask.llm_structure_query: 15.451s
[timing] ask.vector_search: 1.203s
[timing] ask.rerank: 8.337s
[timing] ask.total: 25.032s
```

关闭阶段耗时输出：

```powershell
python scripts\docx_retrieval_cli\cli.py ask --doc "outputs\docx_index\合同目录名" --query "支付方式" --quiet
```

默认会写入本地日志：

```text
logs/build_YYYYMMDD_HHMMSS_PID.log
logs/ask_YYYYMMDD_HHMMSS_PID.log
logs/vector_search_YYYYMMDD_HHMMSS_PID.log
```

指定日志目录：

```powershell
python scripts\docx_retrieval_cli\cli.py ask --doc "outputs\docx_index\合同目录名" --query "支付方式" --log-dir logs
```

关闭本地日志：

```powershell
python scripts\docx_retrieval_cli\cli.py ask --doc "outputs\docx_index\合同目录名" --query "支付方式" --no-log
```

## 输出文件

每个 DOCX 会生成一个独立输出目录：

```text
document_index.json  manifest，总入口，记录 source_file、doc_name、doc_title、files、stats
structure_tree.json  PageIndex-like 轻量结构树，第一阶段给 LLM 选 node，不包含正文 text
content_store.json   node_id -> 原文 text 与 start_index/end_index/start_anchor/end_anchor
anchor_store.json    anchor_id/body_child_index -> DOCX XML 定位信息
vector_index.json    默认生成的向量补召回索引，保存 embedding 与 node_id
titles.json          标题类 node 列表
node_tokens.csv      node token 分布
attachments.json     附件结构
report.txt           人工检查摘要
summary.json         批量任务汇总，位于 --out 目录
```

## 当前边界

- `ask` 只准备检索上下文，不执行最终合同审查，也不写批注。
- 使用 `--no-llm-summary` 后，summary 会退回截断式摘要。
- 使用 `--no-llm-expand` 后，大 node 只做 token chunk 兜底切分。
- 页码依赖 `w:lastRenderedPageBreak`，DOCX 没有该标记时页码为空。
- 当前工具尚未接入 `/api/review/jobs` workflow。
