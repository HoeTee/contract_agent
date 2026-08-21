from __future__ import annotations

import json
from typing import Any

from docxindex.indexing import document_mode, estimate_tokens


def structure_summary(index: dict[str, Any]) -> dict[str, Any]:
    structure = index["structure_tree"]
    tokens = estimate_tokens(json.dumps(structure, ensure_ascii=False))
    return {
        "document_structure_mode": document_mode(tokens),
        "structure_tokens": tokens,
        "structure_index": structure,
    }
