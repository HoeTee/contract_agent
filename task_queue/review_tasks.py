from __future__ import annotations

import asyncio

from endpoints.review.job_worker import run_async_review_job
from task_queue.celery_app import celery_app


@celery_app.task(name="review.run_job")
def run_review_job_task(client_dir: str, task_id: str) -> dict[str, str]:
    asyncio.run(run_async_review_job(client_dir, task_id))
    return {
        "client_dir": client_dir,
        "task_id": task_id,
        "status": "finished",
    }

