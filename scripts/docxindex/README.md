# docxindex

这是独立的合同 DOCX 结构化索引、检索与评测项目，包含索引构建、LLM 摘要与语义拆分、向量补召回、召回评测和表格映射实验。统一入口：

```powershell
python scripts\docxindex\cli.py <command>
```

## 项目结构

```text
scripts/docxindex/
  cli.py                         索引与检索统一入口
  ../../config.yaml             主程序统一的索引、路由、召回和并发配置
  docxindex/                     核心 Python 包
  docs/DESIGN.md                 检索算法设计文档
  tests/                         核心单元测试
  eval/                          Gold 数据与召回评测 CLI
  experiments/table_mapping/     表格 Markdown/XML 映射实验
  tools/                         DOCX 检查与附件诊断脚本
  outputs/                       本项目索引及实验产物，不提交 Git
  logs/                          本项目运行日志，不提交 Git
```

## 安装依赖

```powershell
pip install -r scripts\docxindex\requirements.txt
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
config.yaml -> retrieval.docxindex
```

检索预算、自动路由、向量检索、重排序和并发参数均集中在该文件中。自动路由从 `resources/criteria/criteria-formal.docx` 读取正式审查要点，不保存“审查要点编号 -> 方法”的硬编码映射。

默认内容：

```yaml
retrieval:
  backend: docxindex
  llamaindex: ...
  docxindex:
    input_tokens: 20000
    output_tokens: 12000
    scan_batch_tokens: 12000
    vector:
      enabled: true
      score_threshold: 0.60
      auto_build: true
    rerank:
      enabled: true
    indexing: ...
    routing: ...
    concurrency:
      llm: 10
      embedding: 10
      reranker: 10
```

含义：

- `input_tokens`：结构树输入、向量候选和 rerank 候选的单次模型输入预算，默认 20000。
- `output_tokens`：普通 `ask` 单批返回的节点原文预算，默认 12000。
- `scan_batch_tokens`：全文扫描时单批返回的原文预算，默认 12000。
- `vector.enabled`：`ask` 默认启用向量补召回。
- `vector.score_threshold`：低于该相似度的向量候选不进入候选池。
- `vector.auto_build`：缺少 `vector_index.json` 时，`ask` 默认自动构建。
- `rerank.enabled`：默认对结构召回和向量召回合并后的候选做 rerank。
- `indexing.heading.profiles`：按优先顺序定义正文标题体系。每层至少提供一个示例；同层存在不同编号形式时，每种形式提供一个。程序从示例确定性生成编号正则并自动选择 profile，不调用 LLM，也没有 `selection` 配置。
- `indexing.paragraph.split_threshold_tokens`：普通文本叶节点超过1000 tokens后才启动兜底拆分。
- `indexing.paragraph.chunk_target_tokens`：启动拆分后，按完整段落组成约700 tokens的子节点。
- `indexing.hierarchy`：正文大叶子和附件内部结构共用的 LLM 层级推断预算、候选分批、重叠、最大层级和重试次数。
- `indexing.table.split_threshold_tokens`：Markdown表格不超过20000 tokens时保持为单个完整节点。
- `indexing.table.chunk_target_tokens`：超大表按完整数据行拆分为约18000 tokens的子节点；每个子节点重复表头。
- `indexing.attachment.max_levels`：附件内部最多构建六级标题。
- `indexing.summary.batch_max_nodes`：一次摘要请求最多包含10个 node；模型仍为每个 node 分别返回摘要。
- `indexing.summary.batch_max_tokens`：一次摘要请求中所有 node 原文的合计预算，默认20000 tokens。
- `routing`：自动路由使用的审查要点来源、六种检索方法和补充召回候选参数。

LLM 请求默认携带 `enable_thinking=false`。结构树选点和 rerank 属于检索阶段，不需要模型输出长 thinking 内容。

LLM 和 embedding 地址优先级：

```text
CLI 参数 > scripts/docxindex/.env > 系统环境变量 > 项目根目录 config.yaml > 内置默认值
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
-> 所有 w:tbl 转为独立 Markdown 表格节点并建立 source_ref/XML 映射
-> 正文大叶子与附件共用 LLM 层级归纳、候选分批及 anchor/连续编号/outlineLvl 校验
-> LLM summary
-> vector index
```

单文件：

```powershell
python scripts\docxindex\cli.py build "C:\path\contract.docx" --out outputs\index
```

所有相对的 `--out`、`--doc` 和 `--log-dir` 均以 `scripts/docxindex` 为基准，不受当前终端工作目录影响。默认索引位于本项目的 `outputs/index`，默认日志位于本项目的 `logs`，不会写入 `contract_agent` 根目录。

目录批量：

```powershell
python scripts\docxindex\cli.py build "C:\Users\lenovo\Downloads\合同样例" --out outputs\index --batch
```

关闭某个阶段：

```powershell
python scripts\docxindex\cli.py build "C:\path\contract.docx" --out outputs\index --no-vector
python scripts\docxindex\cli.py build "C:\path\contract.docx" --out outputs\index --no-llm-expand
python scripts\docxindex\cli.py build "C:\path\contract.docx" --out outputs\index --no-llm-summary
python scripts\docxindex\cli.py build "C:\path\contract.docx" --out outputs\index --no-llm-attachment
python scripts\docxindex\cli.py build "C:\path\contract.docx" --out outputs\index --no-cache
```

`--llm-summary` 不再需要显式传入。默认生成的 node summary 控制在 200 tokens 内。summary 用于 LLM 读取结构树并选择 node，不用于替代原文审查。

如果只想快速验证确定性 DOCX XML 解析，不调用模型、不构建向量：

```powershell
python scripts\docxindex\cli.py build "C:\path\contract.docx" --out outputs\index --no-llm-expand --no-llm-summary --no-llm-attachment --no-vector
```

## 检索

完整检索：

```powershell
python scripts\docxindex\cli.py ask --doc "outputs\index\合同目录名" --query "支付方式"
```

`ask` 默认流程：

```text
读取 structure_tree 与正式审查要点
-> LLM 自动规划 title/region/rule/join/scan/hybrid 路由
-> 执行确定性标题、区域、全文关键词或全文扫描
-> 仅在路由要求 fallback 或确定性结果为空时执行结构树 LLM + vector + rerank
-> 从 content_store/anchor_store 展开原文 nodes
```

六种业务路由：

- `title`：检查正式目录标题及顺序；完整目录返回全部正式章节标题。
- `region`：返回合同首部、正文、合同末尾、附件，或明确标题下的内容。
- `rule`：扫描全部 anchor，返回所有精确关键词、枚举敏感词及金额字面命中。
- `join`：组合主体首尾、正文与附件或其他多区域证据。
- `scan`：按 `anchor_store` 阅读顺序返回全文，超出预算时通过 `next_part` 继续。
- `hybrid`：将嵌套结构树交给 LLM 选择具体节点，并使用向量结果补召回后统一 rerank。

`hybrid`仍通过内部 fallback 执行结构树 LLM、向量召回和 rerank，不改变最终只返回统一 `nodes` 的接口。

关闭向量补召回：

```powershell
python scripts\docxindex\cli.py ask --doc "outputs\index\合同目录名" --query "支付方式" --no-vector
```

关闭 rerank：

```powershell
python scripts\docxindex\cli.py ask --doc "outputs\index\合同目录名" --query "支付方式" --no-rerank
```

关闭 LLM 结果缓存：

```powershell
python scripts\docxindex\cli.py ask --doc "outputs\index\合同目录名" --query "支付方式" --no-cache
```

临时调整输入预算：

```powershell
python scripts\docxindex\cli.py ask --doc "outputs\index\合同目录名" --query "支付方式" --input-tokens 30000
```

只做关键词检索，不调用模型：

```powershell
python scripts\docxindex\cli.py search --doc "outputs\index\合同目录名" --keyword "支付方式"
```

只做向量检索：

```powershell
python scripts\docxindex\cli.py vector-search --doc "outputs\index\合同目录名" --query "支付方式"
```

展开单个 node 原文：

```powershell
python scripts\docxindex\cli.py content --doc "outputs\index\合同目录名" --node body/sec_002
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

评测或离线批处理需要在一次固定路由计划中取得全部原文批次时使用：

```powershell
python scripts\docxindex\cli.py ask --doc "outputs\index\合同目录名" --query "是否有错别字" --all-parts
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
python scripts\docxindex\cli.py ask --doc "outputs\index\合同目录名" --query "支付方式" --debug
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
python scripts\docxindex\cli.py ask --doc "outputs\index\合同目录名" --query "支付方式" --quiet
```

默认会写入本地日志：

```text
logs/build_YYYYMMDD_HHMMSS_PID.log
logs/ask_YYYYMMDD_HHMMSS_PID.log
logs/vector_search_YYYYMMDD_HHMMSS_PID.log
```

索引阶段的 LLM 并发上限读取项目根目录 `config.yaml` 中的 `retrieval.docxindex.concurrency.llm`。附件层级推理和正文大叶子节点推理采用“并发计算、按原文顺序写回”；摘要节点不分树深度等待，按 `batch_max_nodes` 和 `batch_max_tokens` 组批后并发生成。父节点摘要输入使用索引构建阶段已有的子节点初始摘要，因此每个 node 仍有独立 LLM 摘要，但不会形成逐层串行网络请求。Embedding 按每批 10 个节点提交，并发批次数读取 `retrieval.docxindex.concurrency.embedding`。这些并发共享各自客户端的上限，不改变节点顺序、anchor 或父子关系。

自动路由只接收结构树前三级的标题目录。路由阶段只选择检索方法，不负责选择最终 node，因此不会把附件深层标题全部重复输入路由模型；深层节点仍由具体的结构检索、区域检索、规则检索或向量补召回定位。
指定日志目录：

```powershell
python scripts\docxindex\cli.py ask --doc "outputs\index\合同目录名" --query "支付方式" --log-dir logs
```

关闭本地日志：

```powershell
python scripts\docxindex\cli.py ask --doc "outputs\index\合同目录名" --query "支付方式" --no-log
```

## 输出文件

每个 DOCX 会生成一个独立输出目录：

```text
document_index.json  manifest，总入口，记录 source_file、doc_name、doc_title、files、stats
structure_tree.json  PageIndex-like 轻量结构树，第一阶段给 LLM 选 node，不包含正文 text
content_store.json   node_id -> 原文 text 与 start_index/end_index/start_anchor/end_anchor
anchor_store.json    anchor_id/body_child_index -> DOCX XML 定位信息
table_store.json     table_id -> Markdown、逻辑网格、source_ref、原始段落与 XML path
vector_index.json    默认生成的向量补召回索引，保存 embedding 与 node_id
titles.json          标题类 node 列表
node_tokens.csv      node token 分布
attachments.json     附件结构
report.txt           人工检查摘要
summary.json         批量任务汇总，位于 --out 目录
```

## 当前边界

- `ask` 只准备检索上下文，不执行最终合同审查，也不写批注。
- 父 section 不重复保存表格全文；表格由独立 `table` node 返回。超过20000 tokens时，父表格 node 只保留结构信息，原文按完整行拆成 `table_chunk` children。表格及其行块在检索阶段保持原子返回，不按普通文本预算从行内截断。
- 使用 `--no-llm-summary` 后，summary 会退回截断式摘要。
- 使用 `--no-llm-expand` 后，大 node 只做 token chunk 兜底切分。
- 页码依赖 `w:lastRenderedPageBreak`，DOCX 没有该标记时页码为空。
- 当前工具尚未接入 `/api/review/jobs` workflow。
