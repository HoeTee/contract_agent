from __future__ import annotations

from .constants import (
    ATTACHMENT_RE,
    LEVEL2_RE,
    LEVEL3_RE,
    MAIN_SECTION_RE,
    PLAIN_LABEL_RE,
    LABEL_KEYWORD_RE,
    TITLE_KEYWORD_RE,
)
from .schema import BodyItem


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
