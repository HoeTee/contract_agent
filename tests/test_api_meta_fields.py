from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from endpoints.review import meta, task_store
from endpoints.review.response import present_review_task


class ApiMetaFieldsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.original_meta_required = meta.API_META_REQUIRED
        self.original_meta_fields = meta.API_META_FIELDS
        meta.API_META_FIELDS = ("templateCode", "serialNo")

    def tearDown(self) -> None:
        meta.API_META_REQUIRED = self.original_meta_required
        meta.API_META_FIELDS = self.original_meta_fields

    def test_optional_meta_fields_accept_missing_values(self) -> None:
        meta.API_META_REQUIRED = False

        result = meta.extract_configured_meta_fields({"templateCode": " template-001 "})

        self.assertEqual(
            result,
            {
                "templateCode": "template-001",
                "serialNo": "",
            },
        )

    def test_required_meta_fields_reject_missing_values(self) -> None:
        meta.API_META_REQUIRED = True

        with self.assertRaises(meta.MetaFieldsValidationError) as context:
            meta.extract_configured_meta_fields({"templateCode": "template-001"})

        self.assertEqual(context.exception.code, "META_FIELDS_REQUIRED")
        self.assertIn("serialNo", context.exception.message)

    def test_meta_fields_reject_non_string_values(self) -> None:
        meta.API_META_REQUIRED = False

        with self.assertRaises(meta.MetaFieldsValidationError) as context:
            meta.extract_configured_meta_fields(
                {"templateCode": "template-001", "serialNo": 1001}
            )

        self.assertEqual(context.exception.code, "META_FIELDS_INVALID")
        self.assertIn("serialNo", context.exception.message)

    def test_task_persists_meta_fields_and_status_presents_them(self) -> None:
        original_data_dir = task_store.DATA_DIR

        with TemporaryDirectory() as temp_dir:
            task_store.DATA_DIR = Path(temp_dir)
            try:
                task = task_store.create_task(
                    client_id="client-a",
                    client_dir="client-a",
                    task_id="20260824-120000-abcd",
                    contract_filename="contract.docx",
                    contract_path=Path(temp_dir) / "contract.docx",
                    criteria_source="default",
                    criteria_filename=None,
                    criteria_path=Path(temp_dir) / "criteria.docx",
                    result_filename="result.docx",
                    result_path=Path(temp_dir) / "result.docx",
                    meta_fields={
                        "templateCode": "template-001",
                        "serialNo": "serial-001",
                    },
                )
                stored = task_store.read_task("client-a", task["task_id"])
            finally:
                task_store.DATA_DIR = original_data_dir

        self.assertIsNotNone(stored)
        response = present_review_task(stored, include_meta_fields=True)
        self.assertEqual(
            response["meta_fields"],
            {
                "templateCode": "template-001",
                "serialNo": "serial-001",
            },
        )

    def test_old_task_without_meta_fields_returns_empty_object(self) -> None:
        task = {
            "task_id": "20260824-120000-abcd",
            "status": "running",
            "created_at": "2026-08-24T12:00:00+08:00",
            "started_at": "2026-08-24T12:00:01+08:00",
            "finished_at": None,
            "message": "Contract review is running.",
            "error": None,
            "input": {
                "contract_filename": "contract.docx",
                "contract_path": "data/api/task/input/contract.docx",
                "criteria_source": "default",
                "criteria_filename": None,
            },
            "output": {
                "result_filename": "result.docx",
                "result_path": "data/api/task/output/result.docx",
            },
            "logs": {},
        }

        response = present_review_task(task, include_meta_fields=True)

        self.assertEqual(response["meta_fields"], {})


if __name__ == "__main__":
    unittest.main()
