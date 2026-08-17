from __future__ import annotations

import argparse
import json
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
}
W = f"{{{NS['w']}}}"

MAIN_ATTACHMENT_RE = re.compile(r"^第[一二三四五六七八九十百零〇两0-9]+[条章]\s*附件\s*$")
MAIN_SECTION_RE = re.compile(r"^第[一二三四五六七八九十百零〇两0-9]+[条章]")
ATTACHMENT_RE = re.compile(r"^附件\s*([0-9一二三四五六七八九十百零〇两]+)(?:\s*$|[：:、\s])")
ATTACHMENT_LIST_ITEM_RE = re.compile(r"^\d+[.、]\s*附件")
ATTACHMENT_LIST_MARKER_RE = re.compile(r"^附件[:：]\s*$")

HEADING_PATTERNS = [
    ("chapter", re.compile(r"^第[一二三四五六七八九十百零〇两0-9]+章")),
    ("article", re.compile(r"^第[一二三四五六七八九十百零〇两0-9]+条")),
    ("cn_comma", re.compile(r"^[一二三四五六七八九十百零〇两]+、")),
    ("paren_cn", re.compile(r"^（[一二三四五六七八九十百零〇两]+）")),
    ("num_dot", re.compile(r"^\d+(?:\.\d+)*[.．]")),
    ("num_comma", re.compile(r"^\d+、")),
]

INLINE_HEADING_RE = re.compile(
    r"^(?P<prefix>（[一二三四五六七八九十百零〇两]+）|[一二三四五六七八九十百零〇两]+、|\d+(?:\.\d+)*[.．]|\d+、)"
    r"(?P<title>[^。；;：:\n]{1,40}[。；;：:])(?P<body>.+)$"
)
INLINE_LABEL_RE = re.compile(r"^(?P<title>[\u4e00-\u9fa5A-Za-z0-9（）()]{2,24}[。；;：:])(?P<body>.+)$")
STANDALONE_LABEL_RE = re.compile(r"^[\u4e00-\u9fa5A-Za-z0-9（）()]{2,24}[。；;：:]$")

TITLE_KEYWORD_RE = re.compile(r"(细则|标准|协议|说明书|承诺书|清单|要求|任务书|方案|需求|报告|函)$")
LABEL_KEYWORD_RE = re.compile(r"(目的|对象|分工|内容|方式|结果|其他|要求|标准|范围|期限|责任|义务|说明|证明|来源|包装|请假|考核|罚则|承诺|服务|电话)")


@dataclass
class Item:
    kind: str
    anchor: str
    index: int
    text: str = ""
    effective_outline: int | None = None
    direct_outline: int | None = None
    style_id: str | None = None
    style_name: str | None = None
    alignment: str | None = None
    bold_fraction: float = 0.0
    max_font_size: int | None = None


@dataclass
class Node:
    node_id: str
    type: str
    title: str = ""
    body: str = ""
    start_anchor: str = ""
    end_anchor: str = ""
    confidence: str = "medium"
    reasons: list[str] = field(default_factory=list)
    children: list["Node"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "node_id": self.node_id,
            "type": self.type,
            "title": self.title,
            "body": self.body,
            "start_anchor": self.start_anchor,
            "end_anchor": self.end_anchor,
            "confidence": self.confidence,
            "reasons": self.reasons,
        }
        if self.children:
            data["children"] = [child.to_dict() for child in self.children]
        return data


def _attr_value(element: ET.Element | None, name: str = "val") -> str | None:
    return element.attrib.get(W + name) if element is not None else None


def _text_of(element: ET.Element) -> str:
    parts = []
    for child in element.iter():
        if child.tag in (W + "t", W + "delText") and child.text:
            parts.append(child.text)
    return "".join(parts).strip()


def _load_styles(docx: zipfile.ZipFile) -> dict[str, dict[str, str | None]]:
    try:
        root = ET.fromstring(docx.read("word/styles.xml"))
    except KeyError:
        return {}
    styles: dict[str, dict[str, str | None]] = {}
    for style in root.findall(".//w:style", NS):
        style_id = style.attrib.get(W + "styleId")
        if not style_id:
            continue
        styles[style_id] = {
            "name": _attr_value(style.find("./w:name", NS)),
            "outline": _attr_value(style.find("./w:pPr/w:outlineLvl", NS)),
            "based_on": _attr_value(style.find("./w:basedOn", NS)),
        }
    return styles


def _style_outline(style_id: str | None, styles: dict[str, dict[str, str | None]]) -> int | None:
    seen: set[str] = set()
    current = style_id
    while current and current not in seen:
        seen.add(current)
        style = styles.get(current)
        if not style:
            return None
        outline = style.get("outline")
        if outline is not None:
            try:
                return int(outline)
            except ValueError:
                return None
        current = style.get("based_on")
    return None


def _paragraph_item(element: ET.Element, styles: dict[str, dict[str, str | None]], index: int) -> Item:
    ppr = element.find("./w:pPr", NS)
    direct_outline = None
    style_id = None
    alignment = None
    if ppr is not None:
        outline = _attr_value(ppr.find("./w:outlineLvl", NS))
        if outline is not None:
            try:
                direct_outline = int(outline)
            except ValueError:
                direct_outline = None
        style_node = ppr.find("./w:pStyle", NS)
        style_id = _attr_value(style_node)
        alignment = _attr_value(ppr.find("./w:jc", NS))

    total_chars = 0
    bold_chars = 0
    sizes: list[int] = []
    for run in element.findall("./w:r", NS):
        run_text = _text_of(run)
        if not run_text:
            continue
        total_chars += len(run_text)
        rpr = run.find("./w:rPr", NS)
        if rpr is None:
            continue
        if rpr.find("./w:b", NS) is not None:
            bold_chars += len(run_text)
        size = _attr_value(rpr.find("./w:sz", NS))
        if size:
            try:
                sizes.append(int(size))
            except ValueError:
                pass

    style_outline = _style_outline(style_id, styles)
    return Item(
        kind="p",
        anchor=f"p_{index:04d}",
        index=index,
        text=_text_of(element),
        effective_outline=direct_outline if direct_outline is not None else style_outline,
        direct_outline=direct_outline,
        style_id=style_id,
        style_name=styles.get(style_id, {}).get("name") if style_id else None,
        alignment=alignment,
        bold_fraction=bold_chars / total_chars if total_chars else 0.0,
        max_font_size=max(sizes) if sizes else None,
    )


def read_docx_items(path: Path) -> list[Item]:
    with zipfile.ZipFile(path) as docx:
        styles = _load_styles(docx)
        document = ET.fromstring(docx.read("word/document.xml"))
    body = document.find(".//w:body", NS)
    if body is None:
        return []

    items: list[Item] = []
    paragraph_index = 0
    table_index = 0
    for child in list(body):
        if child.tag == W + "p":
            paragraph_index += 1
            items.append(_paragraph_item(child, styles, paragraph_index))
        elif child.tag == W + "tbl":
            table_index += 1
            items.append(Item(kind="tbl", anchor=f"tbl_{table_index:04d}", index=table_index, text="[TABLE]"))
    return items


def _heading_pattern(text: str) -> str | None:
    for name, pattern in HEADING_PATTERNS:
        if pattern.match(text):
            return name
    return None


def _is_visual_local_title(item: Item, following: list[Item], position: int) -> bool:
    text = item.text
    if not text or len(text) > 55 or _heading_pattern(text) or ATTACHMENT_RE.match(text):
        return False

    visual_score = 0
    if item.alignment == "center":
        visual_score += 1
    if item.bold_fraction >= 0.5:
        visual_score += 1
    if (item.max_font_size or 0) >= 28:
        visual_score += 1

    followed_by_content = False
    for next_item in following[:5]:
        if next_item.kind == "tbl":
            followed_by_content = True
            break
        if next_item.kind == "p" and next_item.text and (_heading_pattern(next_item.text) or len(next_item.text) > 25):
            followed_by_content = True
            break

    return followed_by_content and (
        (position <= 8 and visual_score >= 2)
        or (visual_score >= 2 and bool(TITLE_KEYWORD_RE.search(text)))
    )


def _is_plain_label(item: Item) -> bool:
    if not item.text or _heading_pattern(item.text) or ATTACHMENT_RE.match(item.text):
        return False
    inline = INLINE_LABEL_RE.match(item.text)
    standalone = STANDALONE_LABEL_RE.match(item.text)
    if inline:
        return bool(LABEL_KEYWORD_RE.search(inline.group("title")))
    if standalone:
        return len(item.text) <= 16 or bool(LABEL_KEYWORD_RE.search(item.text))
    return False


def _classify_items(items: list[Item]) -> list[Node]:
    pattern_counts = Counter(_heading_pattern(item.text) for item in items if item.kind == "p" and _heading_pattern(item.text))
    nodes: list[Node] = []
    numeric_sequence_count = pattern_counts["num_dot"] + pattern_counts["num_comma"]

    for position, item in enumerate(items):
        if item.kind == "tbl":
            nodes.append(
                Node(
                    node_id=item.anchor,
                    type="table",
                    title="[TABLE]",
                    start_anchor=item.anchor,
                    end_anchor=item.anchor,
                    confidence="high",
                    reasons=["body_child_table"],
                )
            )
            continue

        if not item.text:
            continue

        pattern = _heading_pattern(item.text)
        node_type = None
        confidence = "low"
        reasons: list[str] = []
        title = item.text
        body = ""

        inline = INLINE_HEADING_RE.match(item.text)
        if inline and pattern in {"cn_comma", "paren_cn", "num_dot", "num_comma"}:
            title = f"{inline.group('prefix')}{inline.group('title')}"
            body = inline.group("body").strip()
            reasons.append("inline_heading_body_split")

        if pattern in {"chapter", "article"}:
            node_type = pattern
            confidence = "high"
            reasons.append("legal_number_pattern")
        elif pattern in {"cn_comma", "paren_cn"} and pattern_counts[pattern] >= 2:
            node_type = pattern
            confidence = "high"
            reasons.append("local_number_sequence")
        elif pattern in {"num_dot", "num_comma"} and numeric_sequence_count >= 3:
            node_type = "list_item"
            confidence = "medium"
            reasons.append("numeric_sequence")
        elif _is_visual_local_title(item, items[position + 1 :], position):
            node_type = "local_doc_title"
            confidence = "medium"
            reasons.append("visual_title")
        elif _is_plain_label(item):
            label_match = INLINE_LABEL_RE.match(item.text)
            if label_match:
                title = label_match.group("title")
                body = label_match.group("body").strip()
                reasons.append("inline_label_body_split")
            node_type = "plain_label"
            confidence = "medium"
            reasons.append("plain_label_sequence")
        elif item.effective_outline is not None and len(item.text) <= 90:
            node_type = "outline_title"
            confidence = "medium"
            reasons.append("effective_outline")

        if node_type:
            nodes.append(
                Node(
                    node_id=item.anchor,
                    type=node_type,
                    title=title,
                    body=body,
                    start_anchor=item.anchor,
                    end_anchor=item.anchor,
                    confidence=confidence,
                    reasons=reasons,
                )
            )
    return nodes


def _attachment_starts(items: list[Item], start: int, end: int) -> list[int]:
    raw_starts = []
    for index in range(start, end):
        item = items[index]
        if item.kind != "p":
            continue
        if ATTACHMENT_RE.match(item.text) and not ATTACHMENT_LIST_ITEM_RE.match(item.text):
            raw_starts.append(index)

    # A repeated attachment number commonly means an attachment-list entry first,
    # then the actual attachment body later. Keep the later start.
    last_by_number: dict[str, int] = {}
    for index in raw_starts:
        match = ATTACHMENT_RE.match(items[index].text)
        if match:
            last_by_number[match.group(1)] = index
    return sorted(last_by_number.values())


def extract_attachment_nodes(path: Path) -> dict[str, Any]:
    items = read_docx_items(path)
    parent_nodes: list[dict[str, Any]] = []

    for index, item in enumerate(items):
        if item.kind != "p" or not MAIN_ATTACHMENT_RE.match(item.text):
            continue

        section_end = len(items)
        for next_index in range(index + 1, len(items)):
            next_item = items[next_index]
            if (
                next_item.kind == "p"
                and MAIN_SECTION_RE.match(next_item.text)
                and next_item.effective_outline in (0, 1)
            ):
                section_end = next_index
                break

        starts = _attachment_starts(items, index + 1, section_end)
        attachments = []
        for attachment_position, start_index in enumerate(starts):
            end_index = starts[attachment_position + 1] if attachment_position + 1 < len(starts) else section_end
            attachment = items[start_index]
            children = _classify_items(items[start_index + 1 : end_index])
            attachments.append(
                Node(
                    node_id=attachment.anchor,
                    type="attachment_section",
                    title=attachment.text,
                    start_anchor=attachment.anchor,
                    end_anchor=items[end_index - 1].anchor if end_index > start_index else attachment.anchor,
                    confidence="high" if attachment.effective_outline is not None else "medium",
                    reasons=["attachment_number", "inside_attachment_parent"],
                    children=children,
                ).to_dict()
            )

        parent_nodes.append(
            {
                "title": item.text,
                "anchor": item.anchor,
                "effective_outline": item.effective_outline,
                "attachments": attachments,
            }
        )

    return {
        "file": str(path),
        "attachment_parents": parent_nodes,
    }


def iter_docx_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix.lower() == ".docx" and not path.name.startswith("~$"):
            files.append(path)
        elif path.is_dir():
            files.extend(p for p in sorted(path.rglob("*.docx")) if not p.name.startswith("~$"))
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect DOCX attachment section nodes.")
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, default=Path("outputs/docx_attachment_nodes"))
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    files = iter_docx_files(args.paths)

    summary = {
        "files": 0,
        "attachment_parent_count": 0,
        "attachment_section_count": 0,
        "zero_inner_attachment_sections": [],
        "node_type_counts": {},
    }
    type_counts: Counter[str] = Counter()

    for file_path in files:
        result = extract_attachment_nodes(file_path)
        if not result["attachment_parents"]:
            continue
        summary["files"] += 1
        output_name = f"{file_path.stem[:80]}__attachment_nodes.json"
        output_path = args.out / output_name
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        summary["attachment_parent_count"] += len(result["attachment_parents"])
        for parent in result["attachment_parents"]:
            for attachment in parent["attachments"]:
                summary["attachment_section_count"] += 1
                children = attachment.get("children", [])
                if not children:
                    summary["zero_inner_attachment_sections"].append(
                        {
                            "file": str(file_path),
                            "anchor": attachment["start_anchor"],
                            "title": attachment["title"],
                        }
                    )
                for child in children:
                    type_counts[child["type"]] += 1

    summary["node_type_counts"] = dict(type_counts)
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
