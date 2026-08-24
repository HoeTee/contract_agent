from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from endpoints.api import review_jobs
from endpoints.review import meta


class _JsonRequest:
    def __init__(self, payload: object):
        self.headers = {"content-type": "application/json"}
        self._payload = payload

    async def json(self) -> object:
        return self._payload


class _FormRequest:
    def __init__(self, form: dict[str, object]):
        self.headers = {"content-type": "multipart/form-data; boundary=test"}
        self._form = form

    async def form(self) -> dict[str, object]:
        return self._form


class ReviewJobPreTaskValidationTest(unittest.IsolatedAsyncioTestCase):
    async def test_json_submit_missing_file_url_does_not_create_task(self) -> None:
        original_resolve_api_client = review_jobs.resolve_api_client
        original_new_task_id = review_jobs.new_task_id
        original_ensure_task_dirs = review_jobs.ensure_task_dirs

        async def resolve_api_client(_request):
            return SimpleNamespace(
                client_id="client-a",
                client_dir="client-a",
                source_ip="127.0.0.1",
            )

        def fail_new_task_id() -> str:
            raise AssertionError("new_task_id must not be called before submit body validation")

        def fail_ensure_task_dirs(_client_dir: str, _task_id: str) -> None:
            raise AssertionError("ensure_task_dirs must not be called before submit body validation")

        review_jobs.resolve_api_client = resolve_api_client
        review_jobs.new_task_id = fail_new_task_id
        review_jobs.ensure_task_dirs = fail_ensure_task_dirs
        try:
            response = await review_jobs.submit_review_job(_JsonRequest({"task_id": "20260814-174815-414c"}))
        finally:
            review_jobs.resolve_api_client = original_resolve_api_client
            review_jobs.new_task_id = original_new_task_id
            review_jobs.ensure_task_dirs = original_ensure_task_dirs

        body = json.loads(response.body)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(body["error"]["code"], "FILE_URL_REQUIRED")
        self.assertNotIn("task_id", body)

    async def test_required_meta_fields_are_validated_before_task_creation(self) -> None:
        original_resolve_api_client = review_jobs.resolve_api_client
        original_new_task_id = review_jobs.new_task_id
        original_ensure_task_dirs = review_jobs.ensure_task_dirs
        original_meta_required = meta.API_META_REQUIRED
        original_meta_fields = meta.API_META_FIELDS

        async def resolve_api_client(_request):
            return SimpleNamespace(
                client_id="client-a",
                client_dir="client-a",
                source_ip="127.0.0.1",
            )

        def fail_new_task_id() -> str:
            raise AssertionError("new_task_id must not be called before metadata validation")

        def fail_ensure_task_dirs(_client_dir: str, _task_id: str) -> None:
            raise AssertionError("ensure_task_dirs must not be called before metadata validation")

        review_jobs.resolve_api_client = resolve_api_client
        review_jobs.new_task_id = fail_new_task_id
        review_jobs.ensure_task_dirs = fail_ensure_task_dirs
        meta.API_META_REQUIRED = True
        meta.API_META_FIELDS = ("templateCode", "serialNo")
        try:
            response = await review_jobs.submit_review_job(
                _JsonRequest(
                    {
                        "file_url": "https://example.com/contract.docx",
                        "templateCode": "template-001",
                    }
                )
            )
        finally:
            review_jobs.resolve_api_client = original_resolve_api_client
            review_jobs.new_task_id = original_new_task_id
            review_jobs.ensure_task_dirs = original_ensure_task_dirs
            meta.API_META_REQUIRED = original_meta_required
            meta.API_META_FIELDS = original_meta_fields

        body = json.loads(response.body)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(body["error"]["code"], "META_FIELDS_REQUIRED")
        self.assertIn("serialNo", body["message"])
        self.assertNotIn("task_id", body)

    async def test_required_multipart_meta_fields_are_validated_before_task_creation(self) -> None:
        original_resolve_api_client = review_jobs.resolve_api_client
        original_new_task_id = review_jobs.new_task_id
        original_meta_required = meta.API_META_REQUIRED
        original_meta_fields = meta.API_META_FIELDS

        async def resolve_api_client(_request):
            return SimpleNamespace(
                client_id="client-a",
                client_dir="client-a",
                source_ip="127.0.0.1",
            )

        def fail_new_task_id() -> str:
            raise AssertionError("new_task_id must not be called before metadata validation")

        review_jobs.resolve_api_client = resolve_api_client
        review_jobs.new_task_id = fail_new_task_id
        meta.API_META_REQUIRED = True
        meta.API_META_FIELDS = ("templateCode", "serialNo")
        try:
            response = await review_jobs.submit_review_job(
                _FormRequest({"templateCode": "template-001"})
            )
        finally:
            review_jobs.resolve_api_client = original_resolve_api_client
            review_jobs.new_task_id = original_new_task_id
            meta.API_META_REQUIRED = original_meta_required
            meta.API_META_FIELDS = original_meta_fields

        body = json.loads(response.body)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(body["error"]["code"], "META_FIELDS_REQUIRED")
        self.assertIn("serialNo", body["message"])
        self.assertNotIn("task_id", body)


if __name__ == "__main__":
    unittest.main()
