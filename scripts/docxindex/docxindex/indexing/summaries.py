from __future__ import annotations

import re

from .token_budget import SUMMARY_MAX_CHARS


def make_summary(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= SUMMARY_MAX_CHARS:
        return compact
    return compact[:SUMMARY_MAX_CHARS].rstrip() + "..."
