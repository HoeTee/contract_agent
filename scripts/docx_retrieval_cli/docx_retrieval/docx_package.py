from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from .constants import NS, W
from .schema import BodyItem


def attr_value(element: ET.Element | None, name: str = "val") -> str | None:
    return element.attrib.get(W + name) if element is not None else None


def text_of(element: ET.Element) -> str:
    parts = []
    for child in element.iter():
        if child.tag in (W + "t", W + "delText") and child.text:
            parts.append(child.text)
    return "".join(parts).strip()


def table_text(element: ET.Element) -> str:
    rows = []
    for row in element.findall(".//w:tr", NS):
        cells = []
        for cell in row.findall("./w:tc", NS):
            cells.append(text_of(cell))
        if any(cells):
            rows.append("\t".join(cells))
    return "\n".join(rows).strip() or "[TABLE]"


def load_styles(docx: zipfile.ZipFile) -> dict[str, dict[str, str | None]]:
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
            "name": attr_value(style.find("./w:name", NS)),
            "outline": attr_value(style.find("./w:pPr/w:outlineLvl", NS)),
            "based_on": attr_value(style.find("./w:basedOn", NS)),
        }
    return styles


def style_outline(style_id: str | None, styles: dict[str, dict[str, str | None]]) -> int | None:
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


def paragraph_item(element: ET.Element, styles: dict[str, dict[str, str | None]], anchor: str, body_child_index: int) -> BodyItem:
    ppr = element.find("./w:pPr", NS)
    direct_outline = None
    style_id = None
    alignment = None
    if ppr is not None:
        outline = attr_value(ppr.find("./w:outlineLvl", NS))
        if outline is not None:
            try:
                direct_outline = int(outline)
            except ValueError:
                direct_outline = None
        style_id = attr_value(ppr.find("./w:pStyle", NS))
        alignment = attr_value(ppr.find("./w:jc", NS))

    total_chars = 0
    bold_chars = 0
    sizes: list[int] = []
    for run in element.findall("./w:r", NS):
        run_text = text_of(run)
        if not run_text:
            continue
        total_chars += len(run_text)
        rpr = run.find("./w:rPr", NS)
        if rpr is None:
            continue
        if rpr.find("./w:b", NS) is not None:
            bold_chars += len(run_text)
        size = attr_value(rpr.find("./w:sz", NS))
        if size:
            try:
                sizes.append(int(size))
            except ValueError:
                pass

    return BodyItem(
        kind="p",
        anchor=anchor,
        body_child_index=body_child_index,
        text=text_of(element),
        direct_outline=direct_outline,
        style_outline=style_outline(style_id, styles),
        style_id=style_id,
        style_name=styles.get(style_id, {}).get("name") if style_id else None,
        alignment=alignment,
        bold_fraction=bold_chars / total_chars if total_chars else 0.0,
        max_font_size=max(sizes) if sizes else None,
        page_breaks=sum(1 for child in element.iter() if child.tag == W + "lastRenderedPageBreak"),
    )


def read_docx_items(path: Path) -> list[BodyItem]:
    with zipfile.ZipFile(path) as docx:
        styles = load_styles(docx)
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
            item = paragraph_item(child, styles, f"p_{paragraph_index:04d}", body_child_index)
        elif child.tag == W + "tbl":
            table_index += 1
            item = BodyItem(
                kind="tbl",
                anchor=f"tbl_{table_index:04d}",
                body_child_index=body_child_index,
                text=table_text(child),
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
