# docxindex 召回评测

本项目用于评测 `scripts/docxindex` 对合同审查要点的原文召回能力。Gold 测试集和实际运行结果严格分离：`data/retrieval_gold.csv` 只保存人工审查语义下的期望证据，运行结果写入 `logs/<时间戳>/`，不会回写 Gold。

所有配置相对路径均以本项目的 `config.yaml` 所在目录为基准。评测日志固定写入本项目 `logs/`，索引固定读取同级 `docxindex/outputs/index`，不会在 `contract_agent` 根目录创建 `/outputs`。

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

评测器通过当前 Python 解释器启动 `docxindex/cli.py`，因此该 requirements 文件会同时安装检索 CLI 的全部依赖，包括 `tiktoken`。

评测器只通过现有 `../cli.py` 执行 `build` 和 `ask`，不复制索引或检索实现。缺少索引时自动执行完整 `build`；同一合同后续 case 复用该索引。

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

按 CSV 数据行号执行第 1 至第 18 行（表头不计入，首尾均包含）：

```powershell
python cli.py --start 1 --end 18 --no-cache
```

`--start/--end` 在按 `case_id` 分组前生效，只评测范围内的 Gold 行，不会自动补齐范围外的同一 `case_id` 证据。两者必须同时提供，且不能与 `--limit` 或 `--case` 同时使用。

重复输入 `--start/--end` 可以执行多个范围：

```powershell
python cli.py --start 1 --end 18 --start 101 --end 120 --no-cache
```

多个 `--start` 和 `--end` 按出现顺序配对，数量不一致时在索引或 LLM 调用前以退出码 2 结束。重叠范围只执行一次，最终按 Gold CSV 的原始行顺序评测。

评测器会通过 `../cli.py` 执行完整流程：索引不存在时先运行 `build`，然后为每个 `case_id` 运行一次 `ask`。同一合同只建立一次索引。

缓存开关：

```powershell
# 同时关闭建索引和检索阶段的 LLM 缓存
python cli.py --limit 18 --no-cache

# 只关闭建索引阶段缓存（仅在需要建立索引时生效）
python cli.py --limit 18 --no-build-cache

# 只关闭检索与 rerank 阶段缓存
python cli.py --limit 18 --no-query-cache

# 强制使用当前代码为每份选中合同重新建立索引
python cli.py --limit 18 --rebuild-index
```

`--no-cache` 和 `--no-build-cache` 只控制 LLM 响应缓存；`--rebuild-index` 单独控制是否复用已有 `document_index.json`。验证索引算法改动时应组合使用 `--rebuild-index --no-cache`。

只显示最终汇总：

```powershell
python cli.py --quiet
```

评测数据、索引目录和评分阈值位于本目录的 `config.yaml`；其中 `retrieval_config` 指向 `../config.yaml`。索引建立和检索都会使用该统一配置中的 token、路由、向量、重排序及并发参数。

## 测试逻辑

评测器按 `case_id` 分组，并通过 `ask --all-parts` 在一次固定路由计划中取得全部分页结果。前 1、3、5 个 Node 指标用于观察排序质量；主召回指标使用该 case 全部返回 Node。

Gold 的 `notes` 中保存证据 anchor。主命中判断为：返回 Node 覆盖 Gold anchor，或者标准化后的 Gold 原文覆盖率达到阈值。anchor 命中优先，文本覆盖率用于兼容无法稳定映射 anchor 的内容并作为诊断值。

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

- `Micro Recall`：基于一个 case 全部返回 Node 的正样本证据命中率；
- `Micro Recall@1/3/5`：前 K 个 Node 的命中率，用于评估排序；
- `Macro Recall`：各正样本 case 完整召回率的平均值；
- `Strict Case Accuracy`：一个 case 的全部 Gold 均命中的比例；
- `label=0` 的 case 标记为 `SKIP`，不进入召回率计算。

召回率只衡量是否漏掉 Gold，不惩罚返回文本过长。噪声和精确率应作为单独指标评测。

## 输出与日志

每次运行创建：

```text
logs/<时间戳>/
├── run.log
├── recall_results.csv
├── contract_metrics.json
└── summary.json
```

`recall_results.csv` 在 Gold 字段后追加：

```text
coverage_at_1,coverage_at_3,coverage_at_5,
hit_at_1,hit_at_3,hit_at_5,
retrieved_node_ids,elapsed_seconds,error
```

`recall_results.csv` 另外记录每个 case 的 `index_build_seconds` 和 `retrieval_seconds`。`contract_metrics.json` 按合同记录索引耗时以及检索平均值、P50、P95 和最大值；复用既有索引时 `build_seconds` 为 `null`。`summary.json` 汇总本次实际重建合同和实际执行检索的 P50、P95、最大耗时。评测器只记录指标，不依据耗时或召回阈值修改索引与检索行为。

终端逐个显示 case 的 `PASS/FAIL/SKIP`、Recall@5、返回 Node 数量、耗时和召回文本摘要，最后输出总体 JSON 汇总。
