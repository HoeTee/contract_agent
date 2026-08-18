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

## 目录结构

```text
scripts/docx_retrieval_cli/
  cli.py                         # 单命令试验入口，默认使用这个
  docx_index_cli.py              # 兼容旧版的调试入口，保留 build/structure/content/search/titles
  docx_retrieval/
    schema.py                    # BodyItem 和 Node 数据结构
    constants.py                 # 正则、XML namespace、token 阈值
    docx_package.py              # DOCX zip 包读取，解析 document.xml/styles.xml
    heading_detector.py          # 正文标题、视觉标题识别
    attachment_detector.py       # 附件 section 和附件内部 node 识别
    regions.py                   # 合同首部、正文、合同末尾、附件区域边界判断
    hierarchy.py                 # 正文章节树构建
    node_factory.py              # node 文本、页码、summary、anchor 组装
    splitter.py                  # 超长叶子 node 切分
    retriever.py                 # 基于 DocumentIndex 的关键词检索
    io.py                        # JSON 读写和 node 查询
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
- 这个目录仍是试验脚本，后续稳定后再考虑迁移到 `tools/retrieval/`。
