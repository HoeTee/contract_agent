from __future__ import annotations

import math
import re

from .constants import SUMMARY_MAX_CHARS


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    ascii_chars = sum(1 for char in text if ord(char) < 128)
    non_ascii = len(text) - ascii_chars
    return max(1, math.ceil(non_ascii / 1.6 + ascii_chars / 4))


def make_summary(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= SUMMARY_MAX_CHARS:
        return compact
    return compact[:SUMMARY_MAX_CHARS].rstrip() + "..."
