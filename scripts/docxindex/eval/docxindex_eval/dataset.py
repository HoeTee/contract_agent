from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


REQUIRED_FIELDS = (
    "case_id",
    "criterion_id",
    "contract",
    "contract_path",
    "query",
    "recall",
    "label",
    "notes",
)


@dataclass(frozen=True)
class GoldRow:
    row_number: int
    case_id: str
    criterion_id: int
    contract: str
    contract_path: str
    query: str
    recall: str
    label: int
    notes: str


def load_gold(path: Path) -> list[GoldRow]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        missing = [field for field in REQUIRED_FIELDS if field not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"Gold CSV is missing fields: {', '.join(missing)}")
        rows = []
        for row_number, raw in enumerate(reader, start=2):
            label = int(raw["label"])
            if label not in (0, 1):
                raise ValueError(f"row {row_number}: label must be 0 or 1")
            if label == 1 and not raw["recall"].strip():
                raise ValueError(f"row {row_number}: label=1 requires recall text")
            rows.append(
                GoldRow(
                    row_number=row_number,
                    case_id=raw["case_id"].strip(),
                    criterion_id=int(raw["criterion_id"]),
                    contract=raw["contract"].strip(),
                    contract_path=raw["contract_path"].strip(),
                    query=raw["query"].strip(),
                    recall=raw["recall"].strip(),
                    label=label,
                    notes=raw["notes"].strip(),
                )
            )
    _validate_cases(rows)
    return rows


def _validate_cases(rows: list[GoldRow]) -> None:
    seen: dict[str, tuple[int, str, str]] = {}
    for row in rows:
        if not row.case_id:
            raise ValueError(f"row {row.row_number}: case_id is required")
        identity = (row.criterion_id, row.contract_path, row.query)
        previous = seen.setdefault(row.case_id, identity)
        if previous != identity:
            raise ValueError(f"case_id {row.case_id} mixes different contracts, criteria, or queries")


def group_cases(rows: list[GoldRow]) -> dict[str, list[GoldRow]]:
    grouped: dict[str, list[GoldRow]] = {}
    for row in rows:
        grouped.setdefault(row.case_id, []).append(row)
    return grouped


def select_data_rows(
    rows: list[GoldRow],
    start: int | None,
    end: int | None,
) -> list[GoldRow]:
    """Select an inclusive, one-based range of CSV data rows."""
    if start is None and end is None:
        return rows
    if start is None or end is None:
        raise ValueError("--start and --end must be provided together")
    if start > end:
        raise ValueError("--start must be less than or equal to --end")
    if end > len(rows):
        raise ValueError(f"--end {end} exceeds Gold data row count {len(rows)}")
    return rows[start - 1 : end]
