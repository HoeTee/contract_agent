from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


RESULT_FIELDS = (
    "case_id",
    "criterion_id",
    "contract",
    "contract_path",
    "query",
    "recall",
    "label",
    "notes",
    "coverage_at_1",
    "coverage_at_3",
    "coverage_at_5",
    "hit_at_1",
    "hit_at_3",
    "hit_at_5",
    "retrieved_node_ids",
    "elapsed_seconds",
    "error",
)


def write_results(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(RESULT_FIELDS)
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
