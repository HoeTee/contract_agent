from __future__ import annotations

from task_queue.review_tasks import run_review_job_task


def enqueue_review_job(client_dir: str, task_id: str) -> str:
    result = run_review_job_task.delay(client_dir, task_id)
    return str(result.id)
