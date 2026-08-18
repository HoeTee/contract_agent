# DOCX 检索索引 CLI

这是一个用于试验合同 DOCX 结构化索引的命令行工具。目标不是直接替代现有审查流程，而是先验证：

- 能否从 `word/document.xml` 和 `word/styles.xml` 中稳定提取合同结构；
- 能否生成 `frontmatter/body/tail/attachments` 四类顶层区域；
- 能否把正文、附件、长文本切分成可检索的 node；
- 能否输出给 Agent 阅读的轻量结构树，以及用于回溯原文和批注定位的完整索引。

正常试验只需要一个命令：

```powershell
python scripts\docx_retrieval_cli\cli.py "C:\path\contract.docx" --out outputs\docx_index
```

## 安装依赖

这个试验工具有独立依赖文件：

```powershell
pip install -r scripts\docx_retrieval_cli\requirements.txt
```

当前真实使用的依赖：

- `lxml`：解析 `document.xml`、`styles.xml`，并保留 XML path；
- `openai`：调用 OpenAI-compatible LLM 和 embedding 模型；
- `pydantic`：定义 `BodyItem`、`DocumentNode`、`DocumentIndex`、检索结果等 schema；
- `PyYAML`：读取项目 `config.yaml` 中的 LLM 配置；
- `tiktoken`：计算 node、结构树和切分阈值的 token 数。

## 目录结构

```text
scripts/docx_retrieval_cli/
  cli.py                         # 单命令试验入口，默认使用这个
  docx_index_cli.py              # 兼容旧版的调试入口，保留 build/structure/content/search/titles
  requirements.txt               # 当前试验工具的最小依赖
  docx_retrieval/
    schema/                      # pydantic 数据模型
      items.py                   # BodyItem，表示 w:body 下的 p/tbl 单元
      nodes.py                   # DocumentNode，表示结构树 node
      index.py                   # DocumentIndex 和 AnchorRecord
      retrieval.py               # RetrievalMatch 和 RetrievalResult
    parser/                      # lxml DOCX XML 解析层
      package.py                 # DOCX zip 包读取
      document_xml.py            # document.xml -> BodyItem
      styles_xml.py              # styles.xml -> style outline 信息
      xml_utils.py               # namespace、XPath、文本抽取、XML path
    detection/                   # 结构识别规则
      headings.py                # 正文标题层级识别
      attachments.py             # 附件标题和附件内部标题识别
      regions.py                 # 合同首部、正文、合同末尾、附件边界
      scoring.py                 # 标题置信度证据
    indexing/                    # DocumentIndex 构建
      builder.py                 # 总装入口
      hierarchy.py               # 正文章节树
      anchors.py                 # anchor_map
      attachments.py             # 附件树
      llm_expand.py              # 大 node 语义拆分，LLM 只发现候选标题
      llm_summary.py             # 最终 node 摘要生成
      splitter.py                # 超长叶子 node 切分
      summaries.py               # 当前截断式摘要
      token_budget.py            # tiktoken token 预算
    llm/                         # LLM 调用、prompt、缓存
      client.py                  # OpenAI-compatible client
      prompts.py                 # expand / summary prompt
      cache.py                   # jsonl cache
      config.py                  # config.yaml/env/CLI 参数合并
    retrieval/                   # 检索视图
      keyword.py                 # 关键词检索
      structure.py               # 结构树视图
      content.py                 # node 原文展开
    vector/                      # 向量补召回
      client.py                  # OpenAI-compatible embedding client
      index.py                   # vector_index.json 构建和读写
      search.py                  # 本地余弦相似度检索
    output/                      # 输出文件
      writers.py                 # JSON/CSV 写入
      reports.py                 # titles/tokens/attachments/report
    evaluation/                  # 样例输入遍历
      samples.py
```

## 单文件构建

```powershell
python scripts\docx_retrieval_cli\cli.py "C:\path\contract.docx" --out outputs\docx_index
```

## 目录批量构建

目录输入必须显式加 `--batch`：

```powershell
python scripts\docx_retrieval_cli\cli.py "C:\Users\lenovo\Downloads\合同样例" --out outputs\docx_index --batch
```

## 构建后查询结构树

```powershell
python scripts\docx_retrieval_cli\cli.py "C:\path\contract.docx" --out outputs\docx_index --query 支付方式
```

`--query` 默认使用 `--query-mode llm`，会读取 `.env` 中的模型配置，让模型根据 `structure_tree` 选择相关 node。

可以重复传多个 query：

```powershell
python scripts\docx_retrieval_cli\cli.py "C:\path\contract.docx" --out outputs\docx_index --query 支付方式 --query 发票
```

如果只想做确定性关键词检索，不连接模型：

```powershell
python scripts\docx_retrieval_cli\cli.py "C:\path\contract.docx" --out outputs\docx_index --query 支付方式 --query-mode keyword
```

## 构建向量补召回索引

向量索引是补召回文件，不替代 `document_index.json`，也不创建新 node。它只保存 embedding 和指向已有结构 node 的 metadata。

```powershell
python scripts\docx_retrieval_cli\cli.py "C:\path\contract.docx" --out outputs\docx_index --build-vector
```

## 已构建索引后的单独检索

以下命令都基于某个合同输出目录执行，不需要手动输入 `document_index.json` 或 `vector_index.json` 的完整文件名。合同输出目录就是 `--out` 下按 DOCX 文件名生成的那一级目录。

只做结构树 LLM 检索：

```powershell
python scripts\docx_retrieval_cli\docx_index_cli.py ask --doc "outputs\docx_index\合同目录名" --query 支付方式
```

结构树 LLM 检索 + 向量补召回：

```powershell
python scripts\docx_retrieval_cli\docx_index_cli.py ask --doc "outputs\docx_index\合同目录名" --query 支付方式 --fallback-vector
```

如果还没有 `vector_index.json`，让命令自动补建：

```powershell
python scripts\docx_retrieval_cli\docx_index_cli.py ask --doc "outputs\docx_index\合同目录名" --query 支付方式 --fallback-vector --auto-vector
```

只做向量检索：

```powershell
python scripts\docx_retrieval_cli\docx_index_cli.py vector-search --doc "outputs\docx_index\合同目录名" --query 支付方式 --top-k 8
```

只做关键词检索，不调用模型：

```powershell
python scripts\docx_retrieval_cli\docx_index_cli.py search --index "outputs\docx_index\合同目录名\document_index.json" --keyword 支付方式
```

`.env` 支持的 embedding 变量名：

```text
EMBEDDING_MODEL_NAME
EMBEDDING_BASE
EMBED_API_KEY
```

## 开启 LLM 语义拆分和摘要

默认命令不会调用模型。需要显式打开：

```powershell
python scripts\docx_retrieval_cli\cli.py "C:\path\contract.docx" --out outputs\docx_index --llm-expand --llm-summary
```

参数来源优先级：

```text
CLI 参数 > scripts/docx_retrieval_cli/.env > 系统环境变量 > 指定 --config > 项目 config.yaml > 内置默认值
```

`.env` 支持的 LLM 变量名：

```text
LLM_MODEL_NAME
LLM_BASE
LLM_API_KEY
```

可以显式指定模型地址：

```powershell
python scripts\docx_retrieval_cli\cli.py "C:\path\contract.docx" `
  --out outputs\docx_index `
  --llm-expand `
  --llm-summary `
  --model qwen3.6-35b-a3b `
  --base-url http://192.168.0.75:1234/v1 `
  --api-key EMPTY
```

`--llm-expand` 的流程：

```text
确定性结构树
-> 找出超过 1000 tokens 的叶子 node
-> 按 anchor window 分批输入 LLM
-> LLM 返回真实存在的子标题 anchor/title/level_hint
-> 程序校验 anchor 和原文
-> 校验成功则生成 semantic_section
-> 失败才 fallback 到 token chunk
```

`--llm-summary` 的流程：

```text
最终结构树
-> 叶子 node 用原文摘要
-> 父 node 用 children title + summary 摘要
-> 写回 node.summary
```

LLM 结果会缓存到：

```text
<--out>/.cache/llm_expand.jsonl
<--out>/.cache/llm_summary.jsonl
<--out>/.cache/llm_query.jsonl
```

## 构建后展开指定 node

```powershell
python scripts\docx_retrieval_cli\cli.py "C:\path\contract.docx" --out outputs\docx_index --node-id body/sec_002
```

## 输出文件

每个 DOCX 会生成一个独立输出目录，目录名来自 DOCX 文件名。

```text
document_index.json  完整 DocumentIndex，包含 node、anchor_map、structure_tree
vector_index.json    可选向量补召回索引，保存 embedding 和 node_id metadata
structure_tree.json  轻量结构树，给 Agent 判断相关章节时使用
titles.json          标题类 node 列表，用于人工检查标题识别效果
node_tokens.csv      node token 分布，用于发现超长章节和切分问题
attachments.json     附件结构，用于检查附件标题和附件内部 node
report.txt           人工检查摘要，包含 node 数量、anchor 数量、最大 node 等
summary.json         批量任务的汇总文件，位于 --out 目录下
```

## 兼容调试入口

`docx_index_cli.py` 保留旧版子命令，方便单独检查某个环节。

构建索引：

```powershell
python scripts\docx_retrieval_cli\docx_index_cli.py build --docx "C:\path\contract.docx" --out outputs\index.json
```

查看结构树：

```powershell
python scripts\docx_retrieval_cli\docx_index_cli.py structure --index outputs\index.json
```

展开 node 原文：

```powershell
python scripts\docx_retrieval_cli\docx_index_cli.py content --index outputs\index.json --node-id body/sec_002
```

关键词检索：

```powershell
python scripts\docx_retrieval_cli\docx_index_cli.py search --index outputs\index.json --keyword 支付方式
```

已构建索引后的 LLM 结构树查询：

```powershell
python scripts\docx_retrieval_cli\docx_index_cli.py query --index outputs\index.json --query 支付方式
```

`query` 会读取 `.env` / 环境变量 / `config.yaml` 中的模型配置，让模型根据 `structure_tree` 选择相关 node；它不会重新构建索引，也不会自动展开原文。需要原文时继续使用 `content`：

```powershell
python scripts\docx_retrieval_cli\docx_index_cli.py content --index outputs\index.json --node-id body/sec_002
```

对已构建输出目录做一条命令检索：

```powershell
python scripts\docx_retrieval_cli\docx_index_cli.py ask --doc outputs\docx_index\合同目录名 --query 支付方式 --fallback-vector --auto-vector
```

`ask --doc` 会自动读取：

```text
outputs\docx_index\合同目录名\document_index.json
outputs\docx_index\合同目录名\vector_index.json
```

其中 `--fallback-vector` 表示同时做向量补召回，`--auto-vector` 表示缺少 `vector_index.json` 时自动创建。

单独构建向量索引：

```powershell
python scripts\docx_retrieval_cli\docx_index_cli.py build-vector --doc outputs\docx_index\合同目录名
```

单独向量检索：

```powershell
python scripts\docx_retrieval_cli\docx_index_cli.py vector-search --doc outputs\docx_index\合同目录名 --query 支付方式
```

查看标题类 node：

```powershell
python scripts\docx_retrieval_cli\docx_index_cli.py titles --index outputs\index.json
```

## 当前边界

- 未开启 `--llm-summary` 时，summary 仍是截断式摘要；
- 未开启 `--llm-expand` 时，大 node 仍只做 token chunk 兜底切分；
- `--query` 默认会调用 LLM；如需避免模型调用，使用 `--query-mode keyword`；
- 向量检索只做 fallback 补召回，返回已有 `node_id`，不创建新 node；
- 页码依赖 `w:lastRenderedPageBreak`，如果 DOCX 没有该标记，页码字段会为空；
- 当前目录已经按独立试验包组织，但还没有接入主审查 workflow；
- 后续稳定后再考虑迁移到 `tools/retrieval/`。
