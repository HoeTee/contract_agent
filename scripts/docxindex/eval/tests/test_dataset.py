from __future__ import annotations

import unittest

from docxindex_eval.dataset import GoldRow, select_data_rows


def _row(number: int, case_id: str) -> GoldRow:
    return GoldRow(
        row_number=number + 1,
        case_id=case_id,
        criterion_id=1,
        contract="contract.docx",
        contract_path="contract.docx",
        query="query",
        recall=f"evidence-{number}",
        label=1,
        notes="",
    )


class SelectDataRowsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [_row(1, "C01"), _row(2, "C01"), _row(3, "C02")]

    def test_range_is_one_based_and_inclusive(self) -> None:
        selected = select_data_rows(self.rows, 2, 3)

        self.assertEqual([row.recall for row in selected], ["evidence-2", "evidence-3"])

    def test_range_does_not_expand_a_partial_case(self) -> None:
        selected = select_data_rows(self.rows, 2, 2)

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].case_id, "C01")

    def test_end_cannot_exceed_data_row_count(self) -> None:
        with self.assertRaisesRegex(ValueError, "exceeds Gold data row count"):
            select_data_rows(self.rows, 1, 4)


if __name__ == "__main__":
    unittest.main()
