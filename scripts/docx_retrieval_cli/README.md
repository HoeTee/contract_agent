# DOCX Retrieval CLI

实验性 DOCX 结构索引工具。

正常使用只需要一个命令：

```powershell
python scripts\docx_retrieval_cli\cli.py "C:\path\contract.docx" --out outputs\docx_index
```

目录批量：

```powershell
python scripts\docx_retrieval_cli\cli.py "C:\Users\lenovo\Downloads\合同样例" --out outputs\docx_index --batch
```

可选地在建立索引后做一次关键词检索：

```powershell
python scripts\docx_retrieval_cli\cli.py "C:\path\contract.docx" --out outputs\docx_index --query 支付方式
```

可选地在建立索引后展开一个 node：

```powershell
python scripts\docx_retrieval_cli\cli.py "C:\path\contract.docx" --out outputs\docx_index --node-id body/sec_002
```

每个 DOCX 会生成一个输出目录：

```text
document_index.json  完整 DocumentIndex
structure_tree.json  轻量结构树
titles.json          标题和标题候选
node_tokens.csv      node token 分布
attachments.json     附件结构
report.txt           人工检查摘要
```

`docx_index_cli.py` 是底层调试入口，保留给开发时单独调用 `build`、`structure`、`content`、`search`、`titles`。
