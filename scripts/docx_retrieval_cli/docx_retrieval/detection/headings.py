from __future__ import annotations

from docx_retrieval.schema import BodyItem

from .patterns import ATTACHMENT_RE, LEVEL2_RE, LEVEL3_RE, MAIN_SECTION_RE


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


def is_title_excluded(item: BodyItem) -> bool:
    return bool(heading_level(item) or ATTACHMENT_RE.match(item.text))
