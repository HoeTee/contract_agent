from __future__ import annotations

import re
from dataclasses import dataclass

from lxml import etree

from .xml_utils import NS


CN_DIGITS = "零一二三四五六七八九"


@dataclass(frozen=True)
class NumberingLevel:
    num_format: str
    level_text: str
    start: int = 1


class NumberingResolver:
    def __init__(self, numbering_xml: etree._Element | None):
        self.levels = _load_levels(numbering_xml)
        self.counters: dict[tuple[str, int], int] = {}

    def next_prefix(self, num_id: str | None, ilvl: int | None) -> str | None:
        if not num_id or ilvl is None:
            return None
        level = self.levels.get((num_id, ilvl))
        if level is None:
            return None
        key = (num_id, ilvl)
        current = self.counters.get(key)
        if current is None:
            current = level.start
        else:
            current += 1
        self.counters[key] = current
        return _format_level_text(level, current)


def normalize_number_spacing(text: str) -> str:
    text = re.sub(r"^([一二三四五六七八九十百千万零〇两]+)\s+、", r"\1、", text)
    text = re.sub(r"^(\d+)\s+、", r"\1、", text)
    text = re.sub(r"^(\d+)\s+\.", r"\1.", text)
    return text


def apply_numbering_prefix(text: str, prefix: str | None) -> str:
    normalized = normalize_number_spacing(text)
    if not prefix:
        return normalized
    compact_prefix = prefix.strip()
    if not compact_prefix:
        return normalized
    if _has_visible_number_prefix(normalized):
        return normalized
    return f"{compact_prefix}{normalized}".strip()


def _load_levels(numbering_xml: etree._Element | None) -> dict[tuple[str, int], NumberingLevel]:
    if numbering_xml is None:
        return {}
    abstract_ids: dict[str, str] = {}
    for num in numbering_xml.xpath("./w:num", namespaces=NS):
        num_id = num.get(f"{{{NS['w']}}}numId")
        abstract = num.xpath("./w:abstractNumId/@w:val", namespaces=NS)
        if num_id and abstract:
            abstract_ids[num_id] = abstract[0]

    abstract_levels: dict[tuple[str, int], NumberingLevel] = {}
    for abstract in numbering_xml.xpath("./w:abstractNum", namespaces=NS):
        abstract_id = abstract.get(f"{{{NS['w']}}}abstractNumId")
        if not abstract_id:
            continue
        for level in abstract.xpath("./w:lvl", namespaces=NS):
            ilvl_raw = level.get(f"{{{NS['w']}}}ilvl")
            if ilvl_raw is None:
                continue
            try:
                ilvl = int(ilvl_raw)
            except ValueError:
                continue
            num_format = _first_attr(level, "./w:numFmt/@w:val") or "decimal"
            level_text = _first_attr(level, "./w:lvlText/@w:val") or "%1."
            start_raw = _first_attr(level, "./w:start/@w:val")
            try:
                start = int(start_raw) if start_raw is not None else 1
            except ValueError:
                start = 1
            abstract_levels[(abstract_id, ilvl)] = NumberingLevel(num_format=num_format, level_text=level_text, start=start)

    levels: dict[tuple[str, int], NumberingLevel] = {}
    for num_id, abstract_id in abstract_ids.items():
        for (candidate_abstract_id, ilvl), level in abstract_levels.items():
            if candidate_abstract_id == abstract_id:
                levels[(num_id, ilvl)] = level
    return levels


def _first_attr(element: etree._Element, xpath: str) -> str | None:
    values = element.xpath(xpath, namespaces=NS)
    return values[0] if values else None


def _format_level_text(level: NumberingLevel, value: int) -> str:
    rendered = _format_number(level.num_format, value)
    return level.level_text.replace("%1", rendered)


def _format_number(num_format: str, value: int) -> str:
    if num_format in {"chineseCounting", "chineseCountingThousand", "ideographDigital"}:
        return _to_chinese_number(value)
    if num_format == "lowerLetter":
        return chr(ord("a") + value - 1) if 1 <= value <= 26 else str(value)
    if num_format == "upperLetter":
        return chr(ord("A") + value - 1) if 1 <= value <= 26 else str(value)
    return str(value)


def _to_chinese_number(value: int) -> str:
    if value <= 0:
        return str(value)
    if value < 10:
        return CN_DIGITS[value]
    if value == 10:
        return "十"
    if value < 20:
        return "十" + CN_DIGITS[value % 10]
    if value < 100:
        tens, ones = divmod(value, 10)
        return CN_DIGITS[tens] + "十" + (CN_DIGITS[ones] if ones else "")
    return str(value)


def _has_visible_number_prefix(text: str) -> bool:
    return bool(
        re.match(r"^第[一二三四五六七八九十百千万零〇两0-9]+[条章]", text)
        or re.match(r"^[一二三四五六七八九十百千万零〇两]+、", text)
        or re.match(r"^（[一二三四五六七八九十百千万零〇两0-9]+）", text)
        or re.match(r"^\d+[、.]", text)
    )
