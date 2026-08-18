# DOCX 检索索引 CLI

这是一个用于试验合同 DOCX 结构化索引和检索链路的命令行工具。

唯一推荐入口：

```powershell
python scripts\docx_retrieval_cli\cli.py <command>
```

## 安装依赖

```powershell
pip install -r scripts\docx_retrieval_cli\requirements.txt
```

当前使用的依赖：

- `lxml`：解析 `word/document.xml`、`word/styles.xml`；
- `openai`：调用 OpenAI-compatible LLM 和 embedding 模型；
- `pydantic`：校验索引、LLM 输出和检索配置；
- `PyYAML`：读取配置；
- `tiktoken`：估算结构树、向量候选和原文上下文 token。

## 配置

检索配置文件：

```text
scripts/docx_retrieval_cli/config.yaml
```

默认内容：

```yaml
retrieval:
  input_tokens: 6000
  max_depth: 6
  vector:
    enabled: true
    score_threshold: 0.60
    auto_build: true
  rerank:
    enabled: true
```

含义：

- `input_tokens`：每次输入模型的 token 预算。结构树输入、向量候选输入、原文上下文展开都使用这个统一预算。
- `max_depth`：结构树最大深度，当前作为配置保留。
- `vector.enabled`：`ask` 默认启用向量补召回。
- `vector.score_threshold`：向量相似度低于该值的候选不进入后续候选池。
- `vector.auto_build`：缺少 `vector_index.json` 时，`ask` 默认自动构建。
- `rerank.enabled`：`ask` 默认对结构召回和向量召回的合并候选做 rerank。

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

## 构建索引

单文件：

```powershell
python scripts\docx_retrieval_cli\cli.py build "C:\path\contract.docx" --out outputs\docx_index
```

单文件，同时构建向量索引：

```powershell
python scripts\docx_retrieval_cli\cli.py build "C:\path\contract.docx" --out outputs\docx_index --vector
```

目录批量：

```powershell
python scripts\docx_retrieval_cli\cli.py build "C:\Users\lenovo\Downloads\合同样例" --out outputs\docx_index --batch --vector
```

开启 LLM 语义拆分和摘要：

```powershell
python scripts\docx_retrieval_cli\cli.py build "C:\path\contract.docx" `
  --out outputs\docx_index `
  --vector `
  --llm-expand `
  --llm-summary
```

## 检索

对已构建的合同目录执行完整检索：

```powershell
python scripts\docx_retrieval_cli\cli.py ask --doc "outputs\docx_index\合同目录名" --query "支付方式"
```

`ask` 默认流程：

```text
structure_tree 轻量结构召回
-> vector_index 向量补召回
-> 合并候选 node_id
-> rerank 重排序
-> 从 document_index.json 展开原文 content_context
```

关闭向量补召回：

```powershell
python scripts\docx_retrieval_cli\cli.py ask --doc "outputs\docx_index\合同目录名" --query "支付方式" --no-vector
```

关闭 rerank：

```powershell
python scripts\docx_retrieval_cli\cli.py ask --doc "outputs\docx_index\合同目录名" --query "支付方式" --no-rerank
```

临时调整输入预算：

```powershell
python scripts\docx_retrieval_cli\cli.py ask --doc "outputs\docx_index\合同目录名" --query "支付方式" --input-tokens 8000
```

如果返回 `pagination.has_more=true`，继续取下一批原文：

```powershell
python scripts\docx_retrieval_cli\cli.py ask --doc "outputs\docx_index\合同目录名" --query "支付方式" --part 2
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
python scripts\docx_retrieval_cli\cli.py content --doc "outputs\docx_index\合同目录名" --node body/sec_002/l2_003
```

开启调试输出：

```powershell
python scripts\docx_retrieval_cli\cli.py ask --doc "outputs\docx_index\合同目录名" --query "支付方式" --debug
```

关闭阶段耗时输出：

```powershell
python scripts\docx_retrieval_cli\cli.py ask --doc "outputs\docx_index\合同目录名" --query "支付方式" --quiet
```

关闭 LLM 结果缓存：

```powershell
python scripts\docx_retrieval_cli\cli.py ask --doc "outputs\docx_index\合同目录名" --query "支付方式" --no-cache
```

`--no-cache` 只影响 LLM 响应缓存，不会删除或重建 `vector_index.json`。

## ask 返回

`ask` 默认只返回最终检索结果：

```json
{
  "query": "支付方式",
  "nodes": [],
  "elapsed_seconds": 1.234
}
```

真正给审查 LLM 的内容只应使用：

```text
nodes[].node_id
nodes[].title
nodes[].text
nodes[].start_anchor
nodes[].end_anchor
```

开启 `--debug` 后才会额外返回内部检索过程：

```json
{
  "query": "支付方式",
  "nodes": [],
  "elapsed_seconds": 1.234,
  "debug": {
    "ranked_matches": [],
    "structure_matches": [],
    "vector_matches": [],
    "pagination": {},
    "budget": {},
    "timings": {
      "ask.load_index": 0.012,
      "ask.llm_structure_query": 15.451,
      "ask.load_vector_index": 0.018,
      "ask.vector_search": 1.203,
      "ask.rerank": 8.337,
      "ask.build_content_context": 0.004
    }
  }
}
```

`debug.pagination`、`debug.budget`、`score`、`reason` 只用于程序控制、日志和调试，不进入审查正文 prompt。

所有 CLI 命令都会输出总耗时字段：

```text
elapsed_seconds       当前命令耗时，单位秒
total_elapsed_seconds 批量 build 总耗时，单位秒
```

`build`、`ask`、`vector-search` 默认还会在终端 stderr 打印阶段耗时，不影响 stdout 的 JSON：

```text
[timing] ask.load_index: 0.012s
[timing] ask.llm_structure_query: 15.451s
[timing] ask.load_vector_index: 0.018s
[timing] ask.vector_search: 1.203s
[timing] ask.rerank: 8.337s
[timing] ask.build_content_context: 0.004s
[timing] ask.total: 25.032s
```

如果只需要机器读取 stdout JSON，使用 `--quiet` 关闭 stderr 阶段耗时。

## 输出文件

每个 DOCX 会生成一个独立输出目录，目录名来自 DOCX 文件名。

```text
document_index.json  主索引，包含完整 node、anchor_map、structure_tree
vector_index.json    可选向量补召回索引，保存 embedding -> node_id
structure_tree.json  轻量结构树
titles.json          标题类 node 列表
node_tokens.csv      node token 分布
attachments.json     附件结构
report.txt           人工检查摘要
summary.json         批量任务汇总，位于 --out 目录下
```

## 当前边界

- `ask` 只准备检索上下文，不执行最终合同审查，也不写批注；
- 未开启 `--llm-summary` 时，summary 仍是截断式摘要；
- 未开启 `--llm-expand` 时，大 node 仍只做 token chunk 兜底切分；
- 页码依赖 `w:lastRenderedPageBreak`，DOCX 没有该标记时页码为空；
- 当前工具尚未接入主 `/api/review/jobs` workflow。
