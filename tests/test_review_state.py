from __future__ import annotations

import tempfile
import unittest

from endpoints.review import task_store
from endpoints.review.review_state import ReviewStateStore


class ReviewStateStoreTest(unittest.TestCase):
    def test_persists_criterion_state_and_error_history(self) -> None:
        original_data_dir = task_store.DATA_DIR
        with tempfile.TemporaryDirectory() as temp_dir:
            task_store.DATA_DIR = temp_dir
            try:
                store = ReviewStateStore("client_a", "20260812-120000-abcd")
                criterion = {
                    "id": "C1",
                    "section": "合同主体",
                    "criterion": "核对合同主体",
                    "check_points": ["主体名称", "联系方式"],
                }

                store.save_plan([criterion])
                store.save_criterion_input(criterion, attempt=1, max_attempts=2)
                store.save_criterion_error(criterion, RuntimeError("first failure"), attempt=1, max_attempts=2)
                store.save_criterion_error(criterion, RuntimeError("second failure"), attempt=2, max_attempts=2)

                result = {
                    "criterion_id": "C1",
                    "criterion": "核对合同主体",
                    "section": "合同主体",
                    "issues": [],
                    "status": "COMPLIANT",
                    "tokens": 10,
                    "error_message": None,
                }
                store.save_criterion_output(result, attempt=2)

                output = store.load_criterion_output("C1")
                self.assertIsNotNone(output)
                self.assertEqual(output["status"], "COMPLIANT")
                self.assertEqual(output["attempt"], 2)

                error = store.criterion_error_path("C1").read_text(encoding="utf-8")
                self.assertIn("first failure", error)
                self.assertIn("second failure", error)
            finally:
                task_store.DATA_DIR = original_data_dir


if __name__ == "__main__":
    unittest.main()

