from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any

import yaml
from docx import Document
from docx.table import Table
from lxml import etree

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.document.docx_anchor_index import iter_blocks
from tools.document.reporting.docx_report import DocxReportGenerator
from tools.document.table_markdown_map import (
    TableMarkdownMapping,
    cell_source_refs,
    render_table_markdown,
    resolve_agent_evidence,
)


DEFAULT_DOCX = Path(
    r"C:\Users\lenovo\Downloads\合同样例\【20251224已审查】2025年度算力资源服务租赁项目（算力资源一）采购合同1223 - 副本.docx"
)
DEFAULT_CONFIG = Path(__file__).with_name("config.yaml")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="验证 DOCX 表格 Markdown 与 XML 批注映射。")
    parser.add_argument("docx", nargs="?", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--table-block", type=int)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--write-mode", choices=("copy", "in_place"))
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = build_parser().parse_args()
    settings = _load_settings(args)
    source_docx = settings["docx"]
    table_block = settings["table_block"]
    out_dir = settings["artifacts_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = Document(str(source_docx))
    table = _table_at_block(doc, table_block)
    mapping = render_table_markdown(table, f"body/tbl{table_block}")

    (out_dir / "attachment4.md").write_text(mapping.markdown, encoding="utf-8")
    (out_dir / "source_map.json").write_text(
        json.dumps(mapping.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    cases = _cases(mapping)
    annotated_doc = Document(str(source_docx))
    existing_case_ids = _existing_test_case_ids(source_docx)
    comments = []
    seen_comments: set[tuple[str, str]] = set()
    results = []
    for case in cases:
        resolution = resolve_agent_evidence(
            mapping,
            case["quoted_text"],
            case.get("source_ref"),
        )
        status = resolution.status
        comment_written = False
        if status == "matched" and case.get("write_comment", True):
            identity = (resolution.paragraph_anchor_id or "", resolution.matched_original_text or "")
            if case["case_id"] in existing_case_ids:
                status = "existing_comment_skipped"
                seen_comments.add(identity)
            elif identity in seen_comments:
                status = "duplicate_skipped"
            else:
                anchor = DocxReportGenerator._find_text_range_anchor_in_xml_anchor(
                    annotated_doc,
                    "paragraph",
                    resolution.paragraph_anchor_id or "",
                    resolution.matched_original_text or "",
                )
                if anchor is None:
                    status = "xml_match_failed"
                else:
                    comments.append(
                        {
                            "anchor": anchor,
                            "comment_text": f"[{case['case_id']}] {case['comment_text']}",
                            "author": "TableMappingTest",
                        }
                    )
                    seen_comments.add(identity)
                    comment_written = True
        results.append(
            {
                **case,
                **resolution.to_dict(),
                "status": status,
                "comment_written": comment_written,
                "comment_expected": status in {"matched", "existing_comment_skipped"}
                and case.get("write_comment", True),
            }
        )

    if comments:
        DocxReportGenerator._add_comments_to_doc(annotated_doc, comments)
    staged_path = _staged_output_path(source_docx, out_dir, settings["write_mode"])
    annotated_doc.save(staged_path)
    verification = _verify_test_comments(staged_path, results)
    if not verification["all_matched"]:
        staged_path.unlink(missing_ok=True)
        raise RuntimeError("批注回读验证失败，目标 DOCX 未被替换")

    backup_path = None
    if settings["write_mode"] == "in_place":
        if settings["backup"]:
            backup_path = source_docx.with_name(
                f"{source_docx.stem}.before-table-mapping{source_docx.suffix}"
            )
            if not backup_path.exists():
                shutil.copy2(source_docx, backup_path)
        os.replace(staged_path, source_docx)
        annotated_path = source_docx
    else:
        annotated_path = staged_path

    _write_csv(out_dir / "annotation_cases.csv", results)
    report = {
        "source_docx": str(source_docx),
        "write_mode": settings["write_mode"],
        "backup_docx": str(backup_path) if backup_path else None,
        "table_block": table_block,
        "table_anchor_id": mapping.table_anchor_id,
        "rows": len(table.rows),
        "columns": len(table.columns),
        "sources": len(mapping.sources),
        "comments_written": sum(bool(item["comment_written"]) for item in results),
        "comments_present": sum(bool(item["comment_expected"]) for item in results),
        "status_counts": _status_counts(results),
        "annotation_verification": verification,
        "annotated_docx": str(annotated_path.resolve()),
        "cases": results,
    }
    (out_dir / "test_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def _load_settings(args: argparse.Namespace) -> dict[str, Any]:
    config: dict[str, Any] = {}
    if args.config.exists():
        loaded = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"配置文件必须是对象: {args.config}")
        config = loaded

    source_docx = args.docx or Path(config.get("docx", DEFAULT_DOCX))
    table_block = args.table_block or int(config.get("table_block", 225))
    out_dir = args.out or Path(
        config.get("artifacts_dir", PROJECT_ROOT / "outputs" / "table_mapping_test")
    )
    write_mode = args.write_mode or config.get("write_mode", "copy")
    if write_mode not in {"copy", "in_place"}:
        raise ValueError(f"不支持的 write_mode: {write_mode}")
    if not source_docx.is_file():
        raise FileNotFoundError(source_docx)
    return {
        "docx": source_docx.resolve(),
        "table_block": table_block,
        "artifacts_dir": out_dir.resolve(),
        "write_mode": write_mode,
        "backup": bool(config.get("backup", True)),
    }


def _staged_output_path(source_docx: Path, out_dir: Path, write_mode: str) -> Path:
    if write_mode == "in_place":
        return source_docx.with_name(f".{source_docx.name}.table-mapping.tmp")
    return out_dir / "annotated_test.docx"


def _existing_test_case_ids(path: Path) -> set[str]:
    with zipfile.ZipFile(path) as archive:
        if "word/comments.xml" not in archive.namelist():
            return set()
        comments = etree.fromstring(archive.read("word/comments.xml"))
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    result = set()
    for comment in comments.iter(f"{{{namespace}}}comment"):
        match = re.match(r"^\[(TC\d+)]", "".join(comment.itertext()))
        if match:
            result.add(match.group(1))
    return result


def _table_at_block(doc, block_number: int) -> Table:
    blocks = list(iter_blocks(doc))
    if block_number < 1 or block_number > len(blocks):
        raise ValueError(f"table block out of range: {block_number}")
    block = blocks[block_number - 1]
    if not isinstance(block, Table):
        raise ValueError(f"body block {block_number} is not a table")
    return block


def _source(mapping: TableMarkdownMapping, row: int, column: int, text: str | None = None) -> str:
    refs = cell_source_refs(mapping, row, column)
    if text is None:
        return refs[0]
    return next(ref for ref in refs if mapping.sources[ref].original_text == text)


def _cases(mapping: TableMarkdownMapping) -> list[dict[str, Any]]:
    amount_925129 = _source(mapping, 2, 6)
    amount_842420 = _source(mapping, 3, 6)
    amount_190968 = _source(mapping, 4, 6)
    category = _source(mapping, 2, 1)
    quantity_2 = _source(mapping, 2, 4)
    quantity_header = _source(mapping, 1, 4, "预估数量（台）")
    later_ref = _source(mapping, 20, 6)
    later_text = mapping.sources[later_ref].original_text
    return [
        _case("TC01", "925129", amount_925129, "该项小计应与数量、单价及服务期限的计算结果保持一致。"),
        _case("TC02", "842420", None, "唯一文本已通过 Markdown 位置反查到原始小计单元格。"),
        _case("TC03", "算力服务资源类别一", category, "合并类别单元格映射测试。"),
        _case("TC04", "2", None, "重复短文本不得默认选择第一处。", write_comment=False),
        _case("TC05", "2", quantity_2, "指定 source_ref 后应定位本行预估数量。"),
        _case("TC06", "999999999", None, "不存在文本不得写入批注。", write_comment=False),
        _case("TC07", "预估数量（台）", quantity_header, "表头原始段落映射测试。"),
        _case("TC08", "算力服务资源类别一", category, "继承位置应复用原合并单元格。", write_comment=False),
        _case("TC09", later_text, later_ref, "后续表格区域 source_ref 映射测试。"),
        _case("TC10", "190 968", amount_190968, "规范化文本应回到未插入空格的原文。"),
        _case("TC11", "842420", amount_925129, "source_ref 与引用文本不一致时不得批注。", write_comment=False),
        _case("TC12", "925129", amount_925129, "重复证据不得重复写入批注。"),
    ]


def _case(case_id, quoted_text, source_ref, comment_text, write_comment=True):
    return {
        "case_id": case_id,
        "agent_source_ref": source_ref or "",
        "source_ref": source_ref,
        "quoted_text": quoted_text,
        "comment_text": comment_text,
        "write_comment": write_comment,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "case_id", "agent_source_ref", "quoted_text", "status", "source_ref",
        "md_start", "md_end", "table_anchor_id", "paragraph_anchor_id",
        "matched_original_text", "comment_written", "comment_text", "candidates",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            item = dict(row)
            item["candidates"] = "|".join(item.get("candidates") or [])
            writer.writerow(item)


def _status_counts(rows):
    result = {}
    for row in rows:
        result[row["status"]] = result.get(row["status"], 0) + 1
    return result


def _verify_test_comments(path: Path, cases: list[dict[str, Any]]) -> dict[str, Any]:
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    namespaced_id = f"{{{namespace}}}id"
    with zipfile.ZipFile(path) as archive:
        document = etree.fromstring(archive.read("word/document.xml"))
        comments = etree.fromstring(archive.read("word/comments.xml"))

    bodies = {
        comment.get(namespaced_id): "".join(comment.itertext())
        for comment in comments.iter(f"{{{namespace}}}comment")
    }
    active: list[str] = []
    captured: dict[str, list[str]] = {}
    for event, element in etree.iterwalk(document, events=("start", "end")):
        local_name = etree.QName(element).localname
        if event == "start" and local_name == "commentRangeStart":
            comment_id = element.get(namespaced_id)
            active.append(comment_id)
            captured.setdefault(comment_id, [])
        elif event == "start" and local_name == "t":
            for comment_id in active:
                captured[comment_id].append(element.text or "")
        elif event == "end" and local_name == "commentRangeEnd":
            comment_id = element.get(namespaced_id)
            if comment_id in active:
                active.remove(comment_id)

    expected = {
        case["case_id"]: case.get("matched_original_text")
        for case in cases
        if case.get("comment_expected")
    }
    resolved = []
    for comment_id, body in bodies.items():
        match = re.match(r"^\[(TC\d+)]", body)
        if not match:
            continue
        case_id = match.group(1)
        anchored_text = "".join(captured.get(comment_id, []))
        resolved.append(
            {
                "case_id": case_id,
                "comment_id": comment_id,
                "anchored_text": anchored_text,
                "expected_text": expected.get(case_id),
                "matched": anchored_text == expected.get(case_id),
            }
        )
    return {
        "expected_comments": len(expected),
        "resolved_comments": len(resolved),
        "all_matched": len(resolved) == len(expected) and all(item["matched"] for item in resolved),
        "comments": resolved,
    }


if __name__ == "__main__":
    raise SystemExit(main())
