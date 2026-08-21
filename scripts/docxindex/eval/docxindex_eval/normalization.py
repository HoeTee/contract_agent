from __future__ import annotations

import re
import unicodedata
from collections import Counter


TRANSLATION = str.maketrans(
    {
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "—": "-",
        "–": "-",
        "－": "-",
    }
)


def normalize_text(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).translate(TRANSLATION)
    value = re.sub(r"[\s\u200b\ufeff]+", "", value)
    return value


def ngrams(text: str, size: int = 3) -> Counter[str]:
    if not text:
        return Counter()
    if len(text) < size:
        return Counter({text: 1})
    return Counter(text[index : index + size] for index in range(len(text) - size + 1))
