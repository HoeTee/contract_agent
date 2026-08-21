from __future__ import annotations

from docxindex.schema import BodyItem


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
