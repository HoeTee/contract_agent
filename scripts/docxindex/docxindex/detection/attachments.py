from __future__ import annotations

from docxindex.schema import BodyItem

from .headings import heading_level
from .patterns import ATTACHMENT_LIST_ITEM_RE, ATTACHMENT_RE, LABEL_KEYWORD_RE, PLAIN_LABEL_RE, TITLE_KEYWORD_RE


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
