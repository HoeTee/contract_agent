from __future__ import annotations

from collections import Counter
from typing import Any

from .normalization import ngrams, normalize_text


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


def score_row(gold_text: str, nodes: list[dict[str, Any]], top_k: tuple[int, ...], threshold: float) -> dict[str, float | int]:
    result: dict[str, float | int] = {}
    for value in top_k:
        coverage = evidence_coverage(gold_text, nodes[:value])
        result[f"coverage_at_{value}"] = round(coverage, 6)
        result[f"hit_at_{value}"] = int(coverage >= threshold)
    return result
