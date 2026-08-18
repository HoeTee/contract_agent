# DOCX Retrieval CLI

Experimental DOCX structure index builder for contract review retrieval tests.

Normal usage should start from one command:

```powershell
python scripts\docx_retrieval_cli\cli.py "C:\path\contract.docx" --out outputs\docx_index
```

## Layout

```text
scripts/docx_retrieval_cli/
  cli.py                         # PageIndex-style one-command experiment entry
  docx_index_cli.py              # Backward-compatible inspect subcommands
  docx_retrieval/
    schema.py                    # BodyItem and Node data structures
    constants.py                 # regexes, namespace, token thresholds
    docx_package.py              # docx zip + document.xml/styles.xml reader
    heading_detector.py          # title and visual-title detection
    attachment_detector.py       # attachment section and inner-node detection
    regions.py                   # frontmatter/body/tail/attachments boundaries
    hierarchy.py                 # section tree construction
    node_factory.py              # node text/page/summary/anchor assembly
    splitter.py                  # long leaf node chunking
    retriever.py                 # keyword retrieval over DocumentIndex
    io.py                        # json load/write and node lookup
```

## Directory Batch

```powershell
python scripts\docx_retrieval_cli\cli.py "C:\Users\lenovo\Downloads\合同样例" --out outputs\docx_index --batch
```

## Optional Checks

Search keywords after building:

```powershell
python scripts\docx_retrieval_cli\cli.py "C:\path\contract.docx" --out outputs\docx_index --query 支付方式
```

Expand one node after building:

```powershell
python scripts\docx_retrieval_cli\cli.py "C:\path\contract.docx" --out outputs\docx_index --node-id body/sec_002
```

Each DOCX gets one output directory:

```text
document_index.json  full DocumentIndex
structure_tree.json  lightweight structure tree
titles.json          title-like nodes
node_tokens.csv      node token distribution
attachments.json     attachment structure
report.txt           human inspection summary
```

`docx_index_cli.py` remains as a lower-level compatibility entry for `build`, `structure`, `content`, `search`, and `titles`.
