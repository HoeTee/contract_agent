from __future__ import annotations

from collections import Counter
import re
from typing import Any

from .normalization import ngrams, normalize_text


ANCHOR = re.compile(r"anchor=((?:p|tbl)_\d+)", re.I)


def evidence_coverage(gold_text: str, nodes: list[dict[str, Any]]) -> float:
    gold = normalize_text(gold_text)
    if not gold:
        return 0.0
    normalized_nodes = [normalize_text(str(node.get("text") or "")) for node in nodes]
    if any(gold in text for text in normalized_nodes):
        return 1.0
    gold_grams = ngrams(gold)
    if not gold_grams:
        return 0.0
    returned_grams: Counter[str] = Counter()
    for text in normalized_nodes:
        returned_grams.update(ngrams(text))
    overlap = sum(min(count, returned_grams[gram]) for gram, count in gold_grams.items())
    return min(1.0, overlap / sum(gold_grams.values()))


def score_row(
    gold_text: str,
    notes: str,
    nodes: list[dict[str, Any]],
    top_k: tuple[int, ...],
    threshold: float,
) -> dict[str, float | int | str]:
    result: dict[str, float | int] = {}
    gold_anchor = _gold_anchor(notes)
    for value in top_k:
        coverage = evidence_coverage(gold_text, nodes[:value])
        anchor_hit = _anchor_hit(gold_anchor, nodes[:value])
        result[f"coverage_at_{value}"] = round(coverage, 6)
        result[f"anchor_hit_at_{value}"] = anchor_hit
        result[f"hit_at_{value}"] = int(anchor_hit or coverage >= threshold)
    coverage = evidence_coverage(gold_text, nodes)
    anchor_hit = _anchor_hit(gold_anchor, nodes)
    result["gold_anchor"] = gold_anchor
    result["coverage"] = round(coverage, 6)
    result["anchor_hit"] = anchor_hit
    result["hit"] = int(anchor_hit or coverage >= threshold)
    return result


def _gold_anchor(notes: str) -> str:
    match = ANCHOR.search(notes or "")
    return match.group(1).lower() if match else ""


def _anchor_hit(gold_anchor: str, nodes: list[dict[str, Any]]) -> int:
    if not gold_anchor:
        return 0
    kind, number_text = gold_anchor.split("_", 1)
    number = int(number_text)
    for node in nodes:
        start = str(node.get("start_anchor") or "").lower()
        end = str(node.get("end_anchor") or "").lower()
        if gold_anchor in {start, end}:
            return 1
        if kind != "p" or not start.startswith("p_") or not end.startswith("p_"):
            continue
        if int(start.split("_", 1)[1]) <= number <= int(end.split("_", 1)[1]):
            return 1
    return 0
