from __future__ import annotations

from lxml import etree

from .xml_utils import NS, attr_value, w_tag, xpath_one


def load_styles(root: etree._Element | None) -> dict[str, dict[str, str | None]]:
    if root is None:
        return {}
    styles: dict[str, dict[str, str | None]] = {}
    for style in root.xpath(".//w:style", namespaces=NS):
        style_id = style.get(w_tag("styleId"))
        if not style_id:
            continue
        styles[style_id] = {
            "name": attr_value(xpath_one(style, "./w:name")),
            "outline": attr_value(xpath_one(style, "./w:pPr/w:outlineLvl")),
            "based_on": attr_value(xpath_one(style, "./w:basedOn")),
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
