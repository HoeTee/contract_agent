from __future__ import annotations

import argparse
import json
import math
import re
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
}
W = f"{{{NS['w']}}}"

CN_NUM = "一二三四五六七八九十百零〇两"
MAIN_SECTION_RE = re.compile(rf"^第[{CN_NUM}0-9]+[条章]")
ATTACHMENT_PARENT_RE = re.compile(rf"^第[{CN_NUM}0-9]+[条章]\s*附件\s*$")
ATTACHMENT_RE = re.compile(rf"^附件\s*([{CN_NUM}0-9]+)(?:\s*$|[：:、\s])")
ATTACHMENT_LIST_ITEM_RE = re.compile(r"^\d+[.、]\s*附件")
LEVEL2_RE = re.compile(rf"^[{CN_NUM}]+、")
LEVEL3_RE = re.compile(rf"^（[{CN_NUM}]+）")
LOCAL_NUM_RE = re.compile(r"^\d+(?:\.\d+)*[.．、]")
TITLE_KEYWORD_RE = re.compile(r"(细则|标准|协议|说明书|承诺书|清单|要求|任务书|方案|需求|报告|函)$")
LABEL_KEYWORD_RE = re.compile(
    r"(目的|对象|分工|内容|方式|结果|其他|要求|标准|范围|期限|责任|义务|说明|证明|来源|包装|请假|考核|罚则|承诺|服务|电话)"
)
PLAIN_LABEL_RE = re.compile(r"^[\u4e00-\u9fa5A-Za-z0-9（）()]{2,24}[。；;：:]$")
TAIL_MARKER_RE = re.compile(r"(以下无正文|以下为合同签署栏|签署|签字|盖章|法定代表人|授权代表)")

NODE_TARGET_TOKENS = 700
NODE_SOFT_LIMIT_TOKENS = 1000
NODE_HARD_LIMIT_TOKENS = 1800
SUMMARY_TRIGGER_MIN_TOKENS = 300
SUMMARY_MAX_CHARS = 180
STRUCTURE_INLINE_BUDGET_TOKENS = 6000
STRUCTURE_PAGED_BUDGET_TOKENS = 20000


@dataclass
class BodyItem:
    kind: str
    anchor: str
    body_child_index: int
    text: str
    direct_outline: int | None = None
    style_outline: int | None = None
    style_id: str | None = None
    style_name: str | None = None
    alignment: str | None = None
    bold_fraction: float = 0.0
    max_font_size: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    page_breaks: int = 0

    @property
    def effective_outline(self) -> int | None:
        return self.direct_outline if self.direct_outline is not None else self.style_outline


@dataclass
class Node:
    node_id: str
    node_type: str
    title: str
    start_anchor: str
    end_anchor: str
    level: int | None = None
    parent_id: str | None = None
    text: str = ""
    summary: str = ""
    token_estimate: int = 0
    page_start: int | None = None
    page_end: int | None = None
    page_source: str = "unavailable"
    page_confidence_score: int = 0
    confidence_score: int = 0
    confidence_evidence: list[str] = field(default_factory=list)
    children: list["Node"] = field(default_factory=list)
    source_start: int | None = None
    source_end: int | None = None

    def to_storage(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "parent_id": self.parent_id,
            "node_type": self.node_type,
            "level": self.level,
            "title": self.title,
            "text": self.text,
            "summary": self.summary,
            "start_anchor": self.start_anchor,
            "end_anchor": self.end_anchor,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "page_source": self.page_source,
            "page_confidence_score": self.page_confidence_score,
            "token_estimate": self.token_estimate,
            "confidence_score": self.confidence_score,
            "confidence_evidence": self.confidence_evidence,
            "children": [child.node_id for child in self.children],
        }

    def to_structure(self) -> dict[str, Any]:
        data = {
            "node_id": self.node_id,
            "title": self.title,
            "node_type": self.node_type,
            "summary": self.summary,
            "token_estimate": self.token_estimate,
        }
        if self.page_start is not None or self.page_end is not None:
            data["page_start"] = self.page_start
            data["page_end"] = self.page_end
        if self.children:
            data["children"] = [child.to_structure() for child in self.children]
        return data


def _attr_value(element: ET.Element | None, name: str = "val") -> str | None:
    return element.attrib.get(W + name) if element is not None else None


def _text_of(element: ET.Element) -> str:
    parts = []
    for child in element.iter():
        if child.tag in (W + "t", W + "delText") and child.text:
            parts.append(child.text)
    return "".join(parts).strip()


def _table_text(element: ET.Element) -> str:
    rows = []
    for row in element.findall(".//w:tr", NS):
        cells = []
        for cell in row.findall("./w:tc", NS):
            cells.append(_text_of(cell))
        if any(cells):
            rows.append("\t".join(cells))
    return "\n".join(rows).strip() or "[TABLE]"


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


def _paragraph_item(element: ET.Element, styles: dict[str, dict[str, str | None]], anchor: str, body_child_index: int) -> BodyItem:
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
        style_id = _attr_value(ppr.find("./w:pStyle", NS))
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

    return BodyItem(
        kind="p",
        anchor=anchor,
        body_child_index=body_child_index,
        text=_text_of(element),
        direct_outline=direct_outline,
        style_outline=_style_outline(style_id, styles),
        style_id=style_id,
        style_name=styles.get(style_id, {}).get("name") if style_id else None,
        alignment=alignment,
        bold_fraction=bold_chars / total_chars if total_chars else 0.0,
        max_font_size=max(sizes) if sizes else None,
        page_breaks=sum(1 for child in element.iter() if child.tag == W + "lastRenderedPageBreak"),
    )


def read_docx_items(path: Path) -> list[BodyItem]:
    with zipfile.ZipFile(path) as docx:
        styles = _load_styles(docx)
        document = ET.fromstring(docx.read("word/document.xml"))
    body = document.find(".//w:body", NS)
    if body is None:
        return []

    items: list[BodyItem] = []
    paragraph_index = 0
    table_index = 0
    page = 1
    has_page_break = False
    for body_child_index, child in enumerate(list(body), start=1):
        if child.tag == W + "p":
            paragraph_index += 1
            item = _paragraph_item(child, styles, f"p_{paragraph_index:04d}", body_child_index)
        elif child.tag == W + "tbl":
            table_index += 1
            item = BodyItem(
                kind="tbl",
                anchor=f"tbl_{table_index:04d}",
                body_child_index=body_child_index,
                text=_table_text(child),
                page_breaks=sum(1 for sub in child.iter() if sub.tag == W + "lastRenderedPageBreak"),
            )
        else:
            continue
        item.page_start = page
        if item.page_breaks:
            has_page_break = True
            page += item.page_breaks
        item.page_end = page
        items.append(item)

    if not has_page_break:
        for item in items:
            item.page_start = None
            item.page_end = None
    return items


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    ascii_chars = sum(1 for char in text if ord(char) < 128)
    non_ascii = len(text) - ascii_chars
    return max(1, math.ceil(non_ascii / 1.6 + ascii_chars / 4))


def make_summary(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= SUMMARY_MAX_CHARS:
        return compact
    return compact[:SUMMARY_MAX_CHARS].rstrip() + "..."


def is_level1(item: BodyItem, use_cn_comma_as_level1: bool = False) -> bool:
    if item.kind != "p":
        return False
    if MAIN_SECTION_RE.match(item.text):
        return True
    return use_cn_comma_as_level1 and LEVEL2_RE.match(item.text) is not None


def heading_level(item: BodyItem, use_cn_comma_as_level1: bool = False) -> int | None:
    if item.kind != "p" or not item.text:
        return None
    if is_level1(item, use_cn_comma_as_level1):
        return 1
    if LEVEL2_RE.match(item.text):
        return 2
    if LEVEL3_RE.match(item.text):
        return 3
    return None


def heading_score(item: BodyItem, level: int | None, inside_attachment: bool = False) -> tuple[int, list[str]]:
    score = 0
    evidence = []
    if level is not None:
        score += 2
        evidence.append("number_pattern")
    if item.direct_outline is not None:
        score += 4
        evidence.append("direct_outline")
    elif item.style_outline is not None:
        score += 3
        evidence.append("style_outline")
    if item.alignment == "center":
        score += 1
        evidence.append("center")
    if item.bold_fraction >= 0.5:
        score += 1
        evidence.append("bold")
    if (item.max_font_size or 0) >= 28:
        score += 1
        evidence.append("large_font")
    if inside_attachment:
        score += 2
        evidence.append("inside_attachment")
    return score, evidence


def is_visual_title(item: BodyItem, following: list[BodyItem], position: int) -> bool:
    if item.kind != "p" or not item.text or len(item.text) > 55:
        return False
    if heading_level(item) or ATTACHMENT_RE.match(item.text):
        return False
    score = 0
    if item.alignment == "center":
        score += 1
    if item.bold_fraction >= 0.5:
        score += 1
    if (item.max_font_size or 0) >= 28:
        score += 1

    followed_by_content = False
    for next_item in following[:5]:
        if next_item.kind == "tbl":
            followed_by_content = True
            break
        if next_item.kind == "p" and next_item.text and (heading_level(next_item) or len(next_item.text) > 25):
            followed_by_content = True
            break
    return followed_by_content and ((position <= 8 and score >= 2) or (score >= 2 and bool(TITLE_KEYWORD_RE.search(item.text))))


def is_plain_label(item: BodyItem) -> bool:
    if item.kind != "p" or not item.text:
        return False
    if heading_level(item) or ATTACHMENT_RE.match(item.text):
        return False
    return bool(PLAIN_LABEL_RE.match(item.text) and (len(item.text) <= 16 or LABEL_KEYWORD_RE.search(item.text)))


def item_range_text(items: list[BodyItem], start: int, end: int) -> str:
    return "\n".join(item.text for item in items[start:end] if item.text).strip()


def item_page_range(items: list[BodyItem], start: int, end: int) -> tuple[int | None, int | None, str, int]:
    pages = [item.page_start for item in items[start:end] if item.page_start is not None]
    page_ends = [item.page_end for item in items[start:end] if item.page_end is not None]
    if not pages and not page_ends:
        return None, None, "unavailable", 0
    return min(pages), max(page_ends), "lastRenderedPageBreak", 1


def make_node(
    node_id: str,
    node_type: str,
    title: str,
    items: list[BodyItem],
    start: int,
    end: int,
    level: int | None,
    parent_id: str | None,
    score: int = 0,
    evidence: list[str] | None = None,
) -> Node:
    text = item_range_text(items, start, end)
    page_start, page_end, page_source, page_score = item_page_range(items, start, end)
    token_estimate = estimate_tokens(text)
    return Node(
        node_id=node_id,
        node_type=node_type,
        level=level,
        title=title or node_type,
        text=text,
        summary=make_summary(text) if token_estimate >= SUMMARY_TRIGGER_MIN_TOKENS else make_summary(title or text),
        start_anchor=items[start].anchor if start < len(items) else "",
        end_anchor=items[end - 1].anchor if end > start else (items[start].anchor if start < len(items) else ""),
        page_start=page_start,
        page_end=page_end,
        page_source=page_source,
        page_confidence_score=page_score,
        token_estimate=token_estimate,
        confidence_score=score,
        confidence_evidence=evidence or [],
        parent_id=parent_id,
        source_start=start,
        source_end=end,
    )


def split_long_leaf(node: Node, items: list[BodyItem], start: int, end: int) -> None:
    if node.token_estimate <= NODE_SOFT_LIMIT_TOKENS or node.children:
        return

    chunks = []
    chunk_start = start
    chunk_tokens = 0
    chunk_index = 1
    for index in range(start, end):
        item_tokens = estimate_tokens(items[index].text)
        should_flush = chunk_tokens >= NODE_TARGET_TOKENS and index > chunk_start
        hard_flush = chunk_tokens + item_tokens > NODE_HARD_LIMIT_TOKENS and index > chunk_start
        if should_flush or hard_flush:
            chunks.append((chunk_start, index))
            chunk_start = index
            chunk_tokens = 0
        chunk_tokens += item_tokens
    if chunk_start < end:
        chunks.append((chunk_start, end))

    if len(chunks) <= 1:
        return

    for chunk_start, chunk_end in chunks:
        child = make_node(
            f"{node.node_id}/chunk_{chunk_index:03d}",
            "chunk",
            f"{node.title} / chunk {chunk_index}",
            items,
            chunk_start,
            chunk_end,
            None,
            node.node_id,
            score=node.confidence_score,
            evidence=node.confidence_evidence + ["token_chunk"],
        )
        node.children.append(child)
        chunk_index += 1


def split_long_leaves(nodes: list[Node], items: list[BodyItem]) -> None:
    for node in nodes:
        split_long_leaves(node.children, items)
        if node.children:
            continue
        if node.source_start is None or node.source_end is None:
            continue
        split_long_leaf(node, items, node.source_start, node.source_end)


def build_hierarchy_for_range(
    items: list[BodyItem],
    start: int,
    end: int,
    parent_id: str,
    node_prefix: str,
    use_cn_comma_as_level1: bool = False,
) -> list[Node]:
    root_nodes: list[Node] = []
    stack: list[tuple[int, Node, int]] = []
    heading_positions: list[tuple[int, int]] = []
    sibling_counts: dict[tuple[str, int], int] = {}
    for index in range(start, end):
        level = heading_level(items[index], use_cn_comma_as_level1)
        if level is not None:
            heading_positions.append((index, level))

    for pos, (index, level) in enumerate(heading_positions):
        next_index = end
        for future_index, future_level in heading_positions[pos + 1 :]:
            if future_level <= level:
                next_index = future_index
                break
        item = items[index]
        while stack and stack[-1][0] >= level:
            stack.pop()
        local_parent = stack[-1][1].node_id if stack else parent_id
        key = (local_parent, level)
        sibling_counts[key] = sibling_counts.get(key, 0) + 1
        count = sibling_counts[key]
        node_id = f"{node_prefix}/sec_{count:03d}" if level == 1 and not stack else f"{local_parent}/l{level}_{count:03d}"
        score, evidence = heading_score(item, level)
        node = make_node(node_id, "section", item.text, items, index, next_index, level, local_parent, score, evidence)
        if stack:
            stack[-1][1].children.append(node)
        else:
            root_nodes.append(node)
        stack.append((level, node, index))

    split_long_leaves(root_nodes, items)
    return root_nodes


def find_first_body_start(items: list[BodyItem]) -> int:
    for index, item in enumerate(items):
        if item.kind == "p" and MAIN_SECTION_RE.match(item.text):
            return index
    # Some legacy contracts use 一、二、三、 as the highest level.
    cn_headings = [index for index, item in enumerate(items) if item.kind == "p" and LEVEL2_RE.match(item.text)]
    return cn_headings[0] if len(cn_headings) >= 2 else 0


def find_attachment_parent(items: list[BodyItem], body_start: int) -> int | None:
    for index in range(body_start, len(items)):
        item = items[index]
        if item.kind == "p" and ATTACHMENT_PARENT_RE.match(item.text):
            return index
    return None


def find_tail_start(items: list[BodyItem], body_start: int, body_end: int) -> int | None:
    for index in range(body_end - 1, body_start - 1, -1):
        if items[index].kind == "p" and TAIL_MARKER_RE.search(items[index].text):
            return index
    return None


def attachment_starts(items: list[BodyItem], start: int, end: int) -> list[int]:
    raw = []
    for index in range(start, end):
        item = items[index]
        if item.kind == "p" and ATTACHMENT_RE.match(item.text) and not ATTACHMENT_LIST_ITEM_RE.match(item.text):
            raw.append(index)
    last_by_number: dict[str, int] = {}
    for index in raw:
        match = ATTACHMENT_RE.match(items[index].text)
        if match:
            last_by_number[match.group(1)] = index
    return sorted(last_by_number.values())


def build_attachment_children(items: list[BodyItem], start: int, end: int, parent_id: str) -> list[Node]:
    nodes: list[Node] = []
    candidate_positions = []
    for position, index in enumerate(range(start, end)):
        item = items[index]
        if item.kind == "tbl":
            candidate_positions.append((index, "table", None))
        elif heading_level(item) is not None:
            candidate_positions.append((index, "heading", heading_level(item)))
        elif is_visual_title(item, items[index + 1 : end], position):
            candidate_positions.append((index, "visual_title", None))
        elif is_plain_label(item):
            candidate_positions.append((index, "plain_label", None))

    for pos, (index, kind, level) in enumerate(candidate_positions):
        next_index = candidate_positions[pos + 1][0] if pos + 1 < len(candidate_positions) else end
        if kind == "table":
            title = "[TABLE]"
            node_type = "table"
        else:
            title = items[index].text
            node_type = kind
        score, evidence = heading_score(items[index], level, inside_attachment=True)
        evidence.append(kind)
        node = make_node(
            f"{parent_id}/{kind}_{pos + 1:03d}",
            node_type,
            title,
            items,
            index,
            next_index,
            level,
            parent_id,
            score,
            evidence,
        )
        split_long_leaf(node, items, index, next_index)
        nodes.append(node)
    return nodes


def build_attachments(items: list[BodyItem], start: int, end: int, parent_id: str) -> list[Node]:
    starts = attachment_starts(items, start, end)
    nodes = []
    for pos, attach_start in enumerate(starts):
        attach_end = starts[pos + 1] if pos + 1 < len(starts) else end
        item = items[attach_start]
        score, evidence = heading_score(item, None, inside_attachment=True)
        evidence.append("attachment_section")
        node = make_node(
            f"attachments/att_{pos + 1:03d}",
            "attachment_section",
            item.text,
            items,
            attach_start,
            attach_end,
            None,
            parent_id,
            score,
            evidence,
        )
        node.children = build_attachment_children(items, attach_start + 1, attach_end, node.node_id)
        nodes.append(node)
    return nodes


def flatten_nodes(nodes: list[Node]) -> list[Node]:
    result = []
    for node in nodes:
        result.append(node)
        result.extend(flatten_nodes(node.children))
    return result


def build_document_index(docx_path: Path) -> dict[str, Any]:
    items = read_docx_items(docx_path)
    if not items:
        raise ValueError(f"No readable word/document.xml body found: {docx_path}")

    body_start = find_first_body_start(items)
    attachment_parent = find_attachment_parent(items, body_start)
    body_end = attachment_parent if attachment_parent is not None else len(items)
    tail_start = find_tail_start(items, body_start, body_end)
    if tail_start is not None:
        body_content_end = tail_start
    else:
        body_content_end = body_end

    use_cn_as_l1 = not any(item.kind == "p" and MAIN_SECTION_RE.match(item.text) for item in items[body_start:body_content_end])
    roots: list[Node] = []

    frontmatter = make_node("frontmatter", "frontmatter", "合同首部", items, 0, max(body_start, 1), 0, None)
    body = make_node("body", "body", "正文", items, body_start, max(body_content_end, body_start + 1), 0, None)
    body.children = build_hierarchy_for_range(items, body_start, body_content_end, "body", "body", use_cn_as_l1)
    roots.extend([frontmatter, body])

    if tail_start is not None and tail_start < body_end:
        roots.append(make_node("tail", "tail", "合同末尾", items, tail_start, body_end, 0, None))
    else:
        roots.append(Node(node_id="tail", node_type="tail", title="合同末尾", start_anchor="", end_anchor="", level=0))

    attachments = Node(node_id="attachments", node_type="attachments", title="附件", start_anchor="", end_anchor="", level=0)
    if attachment_parent is not None:
        attachment_parent_node = make_node(
            "attachments/parent",
            "attachment_parent",
            items[attachment_parent].text,
            items,
            attachment_parent,
            len(items),
            1,
            "attachments",
        )
        attachment_parent_node.children = build_attachments(items, attachment_parent + 1, len(items), attachment_parent_node.node_id)
        attachments.children.append(attachment_parent_node)
    roots.append(attachments)

    flat_nodes = flatten_nodes(roots)
    anchor_order = {item.anchor: item.body_child_index for item in items}
    by_anchor = {}
    for item in items:
        item_order = item.body_child_index
        owner = None
        for node in reversed(flat_nodes):
            start_order = anchor_order.get(node.start_anchor)
            end_order = anchor_order.get(node.end_anchor)
            if start_order is not None and end_order is not None and start_order <= item_order <= end_order:
                owner = node.node_id
                break
        by_anchor[item.anchor] = {
            "body_child_index": item.body_child_index,
            "type": item.kind,
            "text": item.text,
            "node_id": owner,
            "page_start": item.page_start,
            "page_end": item.page_end,
        }

    return {
        "schema_version": "docx-index-v1",
        "source_file": str(docx_path),
        "top_regions": {
            "frontmatter": "frontmatter",
            "body": "body",
            "tail": "tail",
            "attachments": "attachments",
        },
        "settings": {
            "node_target_tokens": NODE_TARGET_TOKENS,
            "node_soft_limit_tokens": NODE_SOFT_LIMIT_TOKENS,
            "node_hard_limit_tokens": NODE_HARD_LIMIT_TOKENS,
            "summary_tree_inline_budget_tokens": STRUCTURE_INLINE_BUDGET_TOKENS,
        },
        "nodes": [node.to_storage() for node in flat_nodes],
        "root_nodes": [node.node_id for node in roots],
        "structure_tree": [node.to_structure() for node in roots],
        "anchor_map": by_anchor,
    }


def load_index(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_node(index: dict[str, Any], node_id: str) -> dict[str, Any]:
    for node in index["nodes"]:
        if node["node_id"] == node_id:
            return node
    raise KeyError(f"node_id not found: {node_id}")


def command_build(args: argparse.Namespace) -> int:
    data = build_document_index(args.docx)
    write_json(args.out, data)
    print(f"wrote: {args.out}")
    print(f"nodes={len(data['nodes'])} anchors={len(data['anchor_map'])}")
    return 0


def command_structure(args: argparse.Namespace) -> int:
    data = load_index(args.index)
    structure = data["structure_tree"]
    structure_tokens = estimate_tokens(json.dumps(structure, ensure_ascii=False))
    mode = "compact_structure"
    if structure_tokens > STRUCTURE_PAGED_BUDGET_TOKENS:
        mode = "filtered_or_paged_structure"
    elif structure_tokens > STRUCTURE_INLINE_BUDGET_TOKENS:
        mode = "paged_structure"
    print(json.dumps({
        "document_structure_mode": mode,
        "structure_tokens": structure_tokens,
        "structure_index": structure,
    }, ensure_ascii=False, indent=2))
    return 0


def command_content(args: argparse.Namespace) -> int:
    data = load_index(args.index)
    node = get_node(data, args.node_id)
    print(json.dumps({
        key: node.get(key)
        for key in ("node_id", "title", "node_type", "text", "start_anchor", "end_anchor", "token_estimate")
    }, ensure_ascii=False, indent=2))
    return 0


def command_search(args: argparse.Namespace) -> int:
    data = load_index(args.index)
    matches = []
    for keyword in args.keyword:
        for node in data["nodes"]:
            title = node.get("title") or ""
            text = node.get("text") or ""
            has_children = bool(node.get("children"))
            if keyword in title:
                matches.append({
                    "keyword": keyword,
                    "match_type": "title",
                    "match_text": title,
                    "node_id": node["node_id"],
                    "anchor": node.get("start_anchor"),
                })
            elif not has_children and keyword in text:
                pos = text.find(keyword)
                matches.append({
                    "keyword": keyword,
                    "match_type": "text",
                    "match_text": text[max(0, pos - 30): pos + len(keyword) + 30],
                    "node_id": node["node_id"],
                    "anchor": node.get("start_anchor"),
                })
    print(json.dumps({"matches": matches}, ensure_ascii=False, indent=2))
    return 0


def command_titles(args: argparse.Namespace) -> int:
    data = load_index(args.index)
    rows = [
        {
            "node_id": node["node_id"],
            "level": node.get("level"),
            "node_type": node.get("node_type"),
            "title": node.get("title"),
            "token_estimate": node.get("token_estimate"),
            "start_anchor": node.get("start_anchor"),
            "end_anchor": node.get("end_anchor"),
        }
        for node in data["nodes"]
        if node.get("node_type") in {"section", "attachment_parent", "attachment_section", "visual_title", "heading", "plain_label"}
    ]
    print(json.dumps({"titles": rows}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and inspect experimental DOCX structure retrieval indexes.")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Build a persistent DocumentIndex JSON from a DOCX file.")
    build.add_argument("--docx", type=Path, required=True)
    build.add_argument("--out", type=Path, required=True)
    build.set_defaults(func=command_build)

    structure = sub.add_parser("structure", help="Print the lightweight structure tree.")
    structure.add_argument("--index", type=Path, required=True)
    structure.set_defaults(func=command_structure)

    content = sub.add_parser("content", help="Print one node's original text.")
    content.add_argument("--index", type=Path, required=True)
    content.add_argument("--node-id", required=True)
    content.set_defaults(func=command_content)

    search = sub.add_parser("search", help="Search index title/text by keyword.")
    search.add_argument("--index", type=Path, required=True)
    search.add_argument("--keyword", action="append", required=True)
    search.set_defaults(func=command_search)

    titles = sub.add_parser("titles", help="Print title-like nodes.")
    titles.add_argument("--index", type=Path, required=True)
    titles.set_defaults(func=command_titles)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
