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
- `pydantic`：定义 `BodyItem`、`DocumentNode`、`DocumentIndex`、检索结果等 schema；
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
      splitter.py                # 超长叶子 node 切分
      summaries.py               # 当前截断式摘要
      token_budget.py            # tiktoken token 预算
    retrieval/                   # 检索视图
      keyword.py                 # 关键词检索
      structure.py               # 结构树视图
      content.py                 # node 原文展开
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

## 构建后顺手检索关键词

```powershell
python scripts\docx_retrieval_cli\cli.py "C:\path\contract.docx" --out outputs\docx_index --query 支付方式
```

可以重复传多个关键词：

```powershell
python scripts\docx_retrieval_cli\cli.py "C:\path\contract.docx" --out outputs\docx_index --query 支付方式 --query 发票
```

## 构建后展开指定 node

```powershell
python scripts\docx_retrieval_cli\cli.py "C:\path\contract.docx" --out outputs\docx_index --node-id body/sec_002
```

## 输出文件

每个 DOCX 会生成一个独立输出目录，目录名来自 DOCX 文件名。

```text
document_index.json  完整 DocumentIndex，包含 node、anchor_map、structure_tree
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

查看标题类 node：

```powershell
python scripts\docx_retrieval_cli\docx_index_cli.py titles --index outputs\index.json
```

## 当前边界

- 当前 summary 仍是截断式摘要，不是 LLM 生成摘要；
- 当前关键词检索只是确定性字符串检索，不是向量检索；
- 页码依赖 `w:lastRenderedPageBreak`，如果 DOCX 没有该标记，页码字段会为空；
- 当前目录已经按独立试验包组织，但还没有接入主审查 workflow；
- 后续稳定后再考虑迁移到 `tools/retrieval/`。
