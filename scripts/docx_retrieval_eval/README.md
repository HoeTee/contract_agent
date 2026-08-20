# DOCX 检索召回评测

本项目用于评测 `scripts/docx_retrieval_cli` 对合同审查要点的原文召回能力。Gold 测试集和实际运行结果严格分离：`data/retrieval_gold.csv` 只保存人工审查语义下的期望证据，运行结果写入 `logs/<时间戳>/`，不会回写 Gold。

## 数据范围

Gold 数据覆盖 30 份 DOCX：

- `C:\Users\lenovo\Downloads\模板合同` 中的 7 份 DOCX；
- `C:\Users\lenovo\Downloads\合同样例` 中的 23 份 DOCX；
- 排除用户指定的“批注版 - 副本”解压目录及 ZIP；
- 排除 `.doc`、`.zip` 和其他所有非 DOCX 文件。

每份合同对应 `criteria-formal.docx` 中的 18 个审查要点，共 540 个 `case_id`。一个审查要点需要多处原文时，同一 `case_id` 会在 CSV 中出现多行。

## Gold 生成逻辑

`generate_gold.py` 只生成测试集，不执行召回测试：

1. 按 `word/document.xml` 的正文顺序读取全部段落和表格；
2. 为段落和表格保留 `p_XXXX`、`tbl_XXXX` anchor；
3. 将一份合同的完整文本和 18 个正式审查要点一次交给证据标注模型；
4. 要求模型只返回逐字原文、所属 anchor 和证据用途；
5. 使用 Pydantic 校验 1-18 项完整性和 JSON 结构；
6. 验证每条 quote 确实存在于对应 anchor，非法 quote 回退为该 anchor 的完整原文；
7. 对标题、法院管辖、敏感词和正文结尾标记等规则型要点进行确定性补标；
8. 全文不存在对应内容时写入空 `recall` 和 `label=0`。

生成命令：

```powershell
python generate_gold.py
```

忽略已有标注缓存并重新调用模型：

```powershell
python generate_gold.py --no-cache
```

Gold CSV 字段：

```text
case_id,criterion_id,contract,contract_path,query,recall,label,notes
```

`recall` 是期望召回的原文，不是召回率。`label=1` 表示存在待召回 Gold；`label=0` 表示全文未发现对应 Gold。负样本不进入召回率分母。

## 环境准备

安装依赖：

```powershell
pip install -r requirements.txt
```

评测器调用现有 `../docx_retrieval_cli/cli.py ask`。参与测试的合同必须先在 `../docx_retrieval_cli/outputs/docx_index` 下建立索引。缺少索引时该用例会记录 `index not found`，评测器不会自动建索引。

## 执行召回测试

执行全部用例：

```powershell
python cli.py
```

关闭现有检索工具的 LLM 缓存：

```powershell
python cli.py --no-cache
```

执行单个用例：

```powershell
python cli.py --case TPL007-C07 --no-cache
```

按测试集顺序只执行前 10 个完整用例：

```powershell
python cli.py --limit 10 --no-cache
```

`--limit` 在按 `case_id` 分组后生效，不会截断同一用例的多条 Gold 证据。与 `--case` 同时使用时，先按 `--case` 筛选，再取前 N 个用例。

只显示最终汇总：

```powershell
python cli.py --quiet
```

默认路径和阈值位于 `config.yaml`。

## 测试逻辑

评测器按 `case_id` 分组，同一合同、同一 Query 只调用一次 `ask`。CLI 返回的 Node 保持原排名，分别取前 1、3、5 个 Node 计算 Gold 证据覆盖率。

文本比较先执行：

- Unicode NFKC 规范化；
- 删除空格、换行、制表符和零宽字符；
- 统一引号和横线；
- 保留数字、金额、百分号和正文字符。

如果标准化后的 Gold 是返回文本的完整子串，覆盖率为 1。否则使用字符三元组计算覆盖率：

```text
coverage = Gold 三元组中被返回内容覆盖的数量 / Gold 三元组总数
```

默认 `coverage >= 0.8` 时 `hit=1`，否则 `hit=0`。最终报告包含：

- `Micro Recall@1/3/5`：全部正样本证据的命中率；
- `Macro Recall@5`：各正样本 case 召回率的平均值；
- `Strict Case Accuracy`：一个 case 的全部 Gold 均命中的比例；
- `label=0` 的 case 标记为 `SKIP`，不进入召回率计算。

召回率只衡量是否漏掉 Gold，不惩罚返回文本过长。噪声和精确率应作为单独指标评测。

## 输出与日志

每次运行创建：

```text
logs/<时间戳>/
├── run.log
├── recall_results.csv
└── summary.json
```

`recall_results.csv` 在 Gold 字段后追加：

```text
coverage_at_1,coverage_at_3,coverage_at_5,
hit_at_1,hit_at_3,hit_at_5,
retrieved_node_ids,elapsed_seconds,error
```

终端逐个显示 case 的 `PASS/FAIL/SKIP`、Recall@5、返回 Node 数量、耗时和召回文本摘要，最后输出总体 JSON 汇总。
