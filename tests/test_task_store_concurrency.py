from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from endpoints.review import task_store


class TaskStoreConcurrencyTest(unittest.TestCase):
    def test_write_task_uses_unique_temp_files_under_concurrent_updates(self):
        original_data_dir = task_store.DATA_DIR

        with TemporaryDirectory() as temp_dir:
            task_store.DATA_DIR = Path(temp_dir)
            client_dir = "client-a"
            task_id = "20260812-000000-abcd"

            def write_status(index: int) -> None:
                task_store.write_task(
                    {
                        "client_dir": client_dir,
                        "task_id": task_id,
                        "status": "running",
                        "sequence": index,
                    }
                )

            try:
                with ThreadPoolExecutor(max_workers=16) as executor:
                    list(executor.map(write_status, range(100)))

                task = task_store.read_task(client_dir, task_id)
                self.assertIsNotNone(task)
                self.assertEqual(task["client_dir"], client_dir)
                self.assertEqual(task["task_id"], task_id)
                self.assertEqual(task["status"], "running")
            finally:
                task_store.DATA_DIR = original_data_dir


if __name__ == "__main__":
    unittest.main()
