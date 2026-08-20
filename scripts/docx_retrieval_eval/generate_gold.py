from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock, Semaphore

from pydantic import BaseModel, ConfigDict, Field

PROJECT_DIR = Path(__file__).resolve().parent
REPO_ROOT = PROJECT_DIR.parents[1]
RETRIEVAL_PROJECT = REPO_ROOT / "scripts" / "docx_retrieval_cli"
sys.path.insert(0, str(RETRIEVAL_PROJECT))

from docx_retrieval.llm import LLMClient, LLMSettings
from docx_retrieval.parser import read_docx_items


TEMPLATE_DIR = Path(r"C:\Users\lenovo\Downloads\模板合同")
SAMPLE_DIR = Path(r"C:\Users\lenovo\Downloads\合同样例")
EXCLUDED_SAMPLE_PREFIX = SAMPLE_DIR / "【已审查】（2026年058号）2026年度GPU算力服务租赁采购合同-20260617_批注版 - 副本"
CRITERIA_PATH = REPO_ROOT / "resources" / "criteria" / "criteria-formal.docx"
OUTPUT_PATH = PROJECT_DIR / "data" / "retrieval_gold.csv"
CACHE_DIR = PROJECT_DIR / ".gold_cache"
CSV_FIELDS = ("case_id", "criterion_id", "contract", "contract_path", "query", "recall", "label", "notes")


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anchor: str
    quote: str
    notes: str = ""


class CriterionAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: int
    evidence: list[Evidence] = Field(default_factory=list)
    notes: str = ""


class DocumentAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criteria: list[CriterionAnnotation]


def discover_contracts() -> list[tuple[str, Path]]:
    contracts: list[tuple[str, Path]] = []
    for group, directory in (("TPL", TEMPLATE_DIR), ("SMP", SAMPLE_DIR)):
        for path in sorted(directory.rglob("*.docx"), key=lambda value: value.name):
            if group == "SMP" and str(path).casefold().startswith(str(EXCLUDED_SAMPLE_PREFIX).casefold()):
                continue
            if path.name.startswith("~$"):
                continue
            contracts.append((group, path.resolve()))
    return contracts


def load_criteria() -> dict[int, str]:
    result: dict[int, str] = {}
    for item in read_docx_items(CRITERIA_PATH):
        match = re.match(r"^(\d+)\.\s*(.+)$", item.text.strip(), flags=re.S)
        if match:
            result[int(match.group(1))] = f"{match.group(1)}. {match.group(2).strip()}"
    expected = set(range(1, 19))
    if set(result) != expected:
        raise ValueError(f"criteria file must contain 1-18, got {sorted(result)}")
    return result


def source_items(path: Path) -> tuple[list[dict[str, str]], dict[str, str]]:
    rows = []
    by_anchor = {}
    for item in read_docx_items(path):
        text = item.text.strip()
        if not text:
            continue
        rows.append({"anchor": item.anchor, "text": text})
        by_anchor[item.anchor] = text
    return rows, by_anchor


def annotation_prompt(path: Path, criteria: dict[int, str], items: list[dict[str, str]]) -> str:
    criteria_text = "\n".join(criteria[index] for index in range(1, 19))
    source_text = "\n".join(f"[{item['anchor']}] {item['text']}" for item in items)
    return f"""你正在制作合同检索系统的人工 Gold 证据测试集，不是在审查合同，也不是在执行检索。

任务：完整阅读下面合同的全部段落和表格，对 18 个审查要点分别标注“完成该项判断必须看到的原文证据”。

严格要求：
1. 每个 criterion_id 1-18 必须恰好返回一次，并按编号排列。
2. evidence.quote 必须逐字复制自对应 anchor 的原文，不得改写、总结、纠错或补充。
3. evidence.anchor 必须使用原文前的 p_XXXX 或 tbl_XXXX。
4. 没有对应原文时 evidence 返回空数组，并在 notes 说明“全文未发现对应内容”。
5. 合同首部、正文、签署区、表格和附件都属于检索范围。
6. 跨区域判断要返回所有必要证据。例如主体一致性需要首部和签署栏，附件一致性需要正文引用和实际附件标题。
7. 错别字、语病只标注明确存在的问题原句；没有明确问题则返回空数组。
8. 不要把批注意见或你自己的判断写入 quote。
9. 单项通常最多返回 8 条证据；合同框架和附件一致性最多返回 20 条。
10. 只返回符合 schema 的 JSON object，不返回 Markdown 或解释。

输出结构：
{{
  "criteria": [
    {{
      "criterion_id": 1,
      "evidence": [{{"anchor": "p_0001", "quote": "逐字原文", "notes": "证据作用"}}],
      "notes": "该审查要点的标注说明"
    }}
  ]
}}

合同文件：{path.name}

审查要点：
{criteria_text}

合同全文（每项前为原生顺序 anchor）：
{source_text}
"""


def validate_annotation(annotation: DocumentAnnotation, anchors: dict[str, str]) -> DocumentAnnotation:
    indexed = {item.criterion_id: item for item in annotation.criteria}
    validated = []
    for criterion_id in range(1, 19):
        item = indexed.get(criterion_id) or CriterionAnnotation(
            criterion_id=criterion_id,
            evidence=[],
            notes="模型未返回该审查要点",
        )
        evidence = []
        seen = set()
        for candidate in item.evidence:
            anchor_text = anchors.get(candidate.anchor)
            if not anchor_text:
                continue
            quote = candidate.quote.strip()
            if not quote or quote not in anchor_text:
                quote = anchor_text
            key = (candidate.anchor, quote)
            if key in seen:
                continue
            seen.add(key)
            evidence.append(Evidence(anchor=candidate.anchor, quote=quote, notes=candidate.notes))
        validated.append(CriterionAnnotation(criterion_id=criterion_id, evidence=evidence, notes=item.notes))
    return DocumentAnnotation(criteria=validated)


def enrich_rule_evidence(annotation: DocumentAnnotation, items: list[dict[str, str]], path: Path) -> DocumentAnnotation:
    indexed = {item.criterion_id: item for item in annotation.criteria}

    def add_when_empty(criterion_id: int, predicate, limit: int, note: str) -> None:
        target = indexed[criterion_id]
        if target.evidence:
            return
        matches = [item for item in items if predicate(item["text"])]
        target.evidence = [
            Evidence(anchor=item["anchor"], quote=item["text"], notes=note)
            for item in matches[:limit]
        ]
        if target.evidence:
            target.notes = "确定性规则补标"

    add_when_empty(
        4,
        lambda text: "采购" in path.stem and "采购" in text and len(text) <= 100,
        1,
        "合同名称包含采购",
    )
    add_when_empty(
        5,
        lambda text: "金额" in text
        and len(text) <= 80
        and bool(re.match(r"^(?:第[^，。；]{0,30}条|合同金额)", text)),
        2,
        "金额标题触发证据",
    )
    add_when_empty(
        8,
        lambda text: "违约责任" in text and len(text) <= 80,
        4,
        "违约责任标题触发证据",
    )
    add_when_empty(
        9,
        lambda text: "甲方住所地人民法院" in text,
        2,
        "法院管辖关键词证据",
    )
    sensitive_words = ("招标单位", "中标单位", "投标单位", "谈判单位", "谈判响应单位", "采购人", "投标人", "入围单位", "征集单位")
    add_when_empty(
        16,
        lambda text: any(word in text for word in sensitive_words),
        8,
        "敏感词证据",
    )
    add_when_empty(
        17,
        lambda text: "以下为合同签署栏" in text or "以下无正文" in text,
        2,
        "正文结尾标记证据",
    )
    return DocumentAnnotation(criteria=[indexed[index] for index in range(1, 19)])


def annotate_contract(
    position: int,
    group: str,
    path: Path,
    criteria: dict[int, str],
    client: LLMClient,
    semaphore: Semaphore,
    console_lock: Lock,
    no_cache: bool,
) -> tuple[int, str, Path, DocumentAnnotation]:
    cache_path = CACHE_DIR / f"{group}_{position:03d}.json"
    items, anchors = source_items(path)
    if cache_path.exists() and not no_cache:
        annotation = DocumentAnnotation.model_validate_json(cache_path.read_text(encoding="utf-8"))
    else:
        prompt = annotation_prompt(path, criteria, items)
        with semaphore:
            annotation = client.complete_model(prompt, DocumentAnnotation, retries=2)
        annotation = validate_annotation(annotation, anchors)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(annotation.model_dump_json(indent=2), encoding="utf-8")
    annotation = validate_annotation(annotation, anchors)
    annotation = enrich_rule_evidence(annotation, items, path)
    with console_lock:
        evidence_count = sum(len(item.evidence) for item in annotation.criteria)
        console_encoding = sys.stdout.encoding or "utf-8"
        safe_name = path.name.encode(console_encoding, errors="replace").decode(console_encoding)
        print(f"[gold] {position:02d}/30 {safe_name}: {evidence_count} evidence", flush=True)
    return position, group, path, annotation


def write_gold(
    annotated: list[tuple[int, str, Path, DocumentAnnotation]],
    criteria: dict[int, str],
    output: Path,
) -> None:
    rows = []
    for position, group, path, annotation in sorted(annotated):
        contract_key = f"{group}{position:03d}"
        for item in annotation.criteria:
            case_id = f"{contract_key}-C{item.criterion_id:02d}"
            if item.evidence:
                for evidence in item.evidence:
                    notes = "；".join(part for part in (item.notes, evidence.notes, f"anchor={evidence.anchor}") if part)
                    rows.append(
                        {
                            "case_id": case_id,
                            "criterion_id": item.criterion_id,
                            "contract": path.name,
                            "contract_path": str(path),
                            "query": criteria[item.criterion_id],
                            "recall": evidence.quote,
                            "label": 1,
                            "notes": notes,
                        }
                    )
            else:
                rows.append(
                    {
                        "case_id": case_id,
                        "criterion_id": item.criterion_id,
                        "contract": path.name,
                        "contract_path": str(path),
                        "query": criteria[item.criterion_id],
                        "recall": "",
                        "label": 0,
                        "notes": item.notes or "全文未发现对应内容",
                    }
                )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate the DOCX retrieval Gold CSV from complete contract text.")
    parser.add_argument("--out", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--no-cache", action="store_true", help="Ignore saved annotation responses.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    contracts = discover_contracts()
    if len(contracts) != 30:
        raise ValueError(f"expected 30 eligible DOCX contracts, found {len(contracts)}")
    criteria = load_criteria()
    settings = LLMSettings.from_sources().model_copy(update={"timeout_seconds": 600.0})
    client = LLMClient(settings)
    semaphore = Semaphore(min(max(args.workers, 1), 10))
    console_lock = Lock()
    annotated = []
    with ThreadPoolExecutor(max_workers=min(max(args.workers, 1), 10)) as pool:
        futures = [
            pool.submit(
                annotate_contract,
                position,
                group,
                path,
                criteria,
                client,
                semaphore,
                console_lock,
                args.no_cache,
            )
            for position, (group, path) in enumerate(contracts, start=1)
        ]
        for future in as_completed(futures):
            annotated.append(future.result())
    write_gold(annotated, criteria, args.out.resolve())
    print(json.dumps({"contracts": len(contracts), "cases": len(contracts) * 18, "output": str(args.out.resolve())}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
