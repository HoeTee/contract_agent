from __future__ import annotations

import math

import tiktoken

PARAGRAPH_CHUNK_TARGET_TOKENS = 700
PARAGRAPH_SPLIT_THRESHOLD_TOKENS = 1000
SUMMARY_TRIGGER_MIN_TOKENS = 300
SUMMARY_MAX_CHARS = 180
STRUCTURE_INLINE_BUDGET_TOKENS = 6000
STRUCTURE_PAGED_BUDGET_TOKENS = 20000

_ENCODING = None


def _encoding():
    global _ENCODING
    if _ENCODING is None:
        try:
            _ENCODING = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _ENCODING = False
    return _ENCODING


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    encoding = _encoding()
    if encoding:
        return len(encoding.encode(text))
    ascii_chars = sum(1 for char in text if ord(char) < 128)
    non_ascii = len(text) - ascii_chars
    return max(1, math.ceil(non_ascii / 1.6 + ascii_chars / 4))


def document_mode(tokens: int) -> str:
    if tokens <= STRUCTURE_INLINE_BUDGET_TOKENS:
        return "compact_structure"
    if tokens <= STRUCTURE_PAGED_BUDGET_TOKENS:
        return "paged_structure"
    return "filtered_or_paged_structure"
