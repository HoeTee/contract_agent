from __future__ import annotations

import importlib
import queue as stdlib_queue
import unittest
from unittest.mock import patch


class TaskQueuePackageTests(unittest.TestCase):
    def test_project_queue_imports_after_standard_library_queue(self) -> None:
        self.assertTrue(hasattr(stdlib_queue, "Queue"))

        review_queue = importlib.import_module("task_queue.review_queue")

        self.assertTrue(callable(review_queue.enqueue_review_job))
        self.assertNotEqual(stdlib_queue.__name__, review_queue.__package__)

    def test_enqueue_returns_celery_task_id(self) -> None:
        from task_queue.review_queue import enqueue_review_job

        with patch("task_queue.review_queue.run_review_job_task.delay") as delay:
            delay.return_value.id = "celery-task-001"

            result = enqueue_review_job("client-a", "review-task-001")

        self.assertEqual(result, "celery-task-001")
        delay.assert_called_once_with("client-a", "review-task-001")


if __name__ == "__main__":
    unittest.main()
