from __future__ import annotations

import re
from dataclasses import dataclass


CN_NUMBER = "一二三四五六七八九十百千万零〇两壹贰叁肆伍陆柒捌玖拾佰仟萬"
ROMAN_NUMBER = "ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ"
CIRCLED_NUMBER = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


@dataclass(frozen=True)
class InferredNumberPattern:
    kind: str
    marker: str
    regex_source: str


def infer_number_pattern(example: str) -> InferredNumberPattern:
    text = example.strip()
    if not text:
        raise ValueError("heading example must not be empty")

    article = re.match(rf"^(第[{CN_NUMBER}0-9]+(?:条|章|节|部分))", text)
    if article:
        marker = article.group(1)
        suffix = next(value for value in ("部分", "条", "章", "节") if marker.endswith(value))
        return InferredNumberPattern("article", marker, rf"^第[{CN_NUMBER}0-9]+{re.escape(suffix)}")

    multilevel = re.match(r"^(\d+(?:[.．]\d+)+(?:[.．、])?)", text)
    if multilevel:
        return InferredNumberPattern(
            "arabic_multilevel",
            multilevel.group(1),
            r"^\d+(?:[.．]\d+)+(?:[.．、])?",
        )

    parenthesized = re.match(rf"^([（(])([{CN_NUMBER}]+|\d+)([）)])", text)
    if parenthesized:
        marker = parenthesized.group(0)
        if parenthesized.group(2).isdigit():
            return InferredNumberPattern("arabic_parenthesized", marker, r"^[（(]\d+[）)]")
        return InferredNumberPattern(
            "chinese_parenthesized",
            marker,
            rf"^[（(][{CN_NUMBER}]+[）)]",
        )

    chinese = re.match(rf"^([{CN_NUMBER}]+)([、.．])", text)
    if chinese:
        marker = chinese.group(0)
        punctuation = chinese.group(2)
        suffix = r"[.．]" if punctuation in {".", "．"} else re.escape(punctuation)
        return InferredNumberPattern("chinese_delimited", marker, rf"^[{CN_NUMBER}]+{suffix}")

    arabic = re.match(r"^(\d+)([、.．)）])", text)
    if arabic:
        marker = arabic.group(0)
        punctuation = arabic.group(2)
        if punctuation in {".", "．"}:
            regex_source = r"^\d+[.．]"
            kind = "arabic_dot"
        elif punctuation == "、":
            regex_source = r"^\d+、"
            kind = "arabic_comma"
        else:
            regex_source = r"^\d+[)）]"
            kind = "arabic_closing_parenthesis"
        return InferredNumberPattern(kind, marker, regex_source)

    alphabetic = re.match(r"^([A-Za-z])([、.．)）])", text)
    if alphabetic:
        punctuation = alphabetic.group(2)
        suffix = r"[.．]" if punctuation in {".", "．"} else re.escape(punctuation)
        return InferredNumberPattern("alphabetic", alphabetic.group(0), rf"^[A-Za-z]{suffix}")

    roman = re.match(rf"^([{ROMAN_NUMBER}]+)([、.．)）])", text)
    if roman:
        punctuation = roman.group(2)
        suffix = r"[.．]" if punctuation in {".", "．"} else re.escape(punctuation)
        return InferredNumberPattern("roman", roman.group(0), rf"^[{ROMAN_NUMBER}]+{suffix}")

    circled = re.match(rf"^([{CIRCLED_NUMBER}])", text)
    if circled:
        return InferredNumberPattern("circled", circled.group(1), rf"^[{CIRCLED_NUMBER}]")

    attachment = re.match(rf"^(附件\s*[{CN_NUMBER}0-9]+)", text)
    if attachment:
        return InferredNumberPattern("attachment", attachment.group(1), rf"^附件\s*[{CN_NUMBER}0-9]+")

    raise ValueError(f"cannot infer heading number pattern from example: {example!r}")


def compile_example_patterns(examples: list[str]) -> tuple[re.Pattern[str], tuple[str, ...]]:
    inferred = [infer_number_pattern(example) for example in examples]
    sources = list(dict.fromkeys(item.regex_source for item in inferred))
    kinds = tuple(dict.fromkeys(item.kind for item in inferred))
    combined = "^(?:" + "|".join(source.removeprefix("^") for source in sources) + ")"
    return re.compile(combined), kinds
