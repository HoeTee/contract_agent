from __future__ import annotations

from pathlib import Path

from config import MCP_SERVER_PATH
from endpoints.api.support.task_store import (
    cleanup_runtime_input,
    is_cancel_requested,
    mark_cancelled,
    mark_failed,
    mark_running,
    mark_succeeded,
    read_task,
    task_api_events_path,
    task_conversation_log_dir,
    task_mcp_log_file,
    task_workflow_log_dir,
    write_task_log_event,
)
from endpoints.runtime.errors import ModelCallError
from endpoints.runtime.review_runtime import review_semaphore
from loggers.agent_logger import reset_conversation_log_dir, set_conversation_log_dir
from main_workflow.main_workflow import ContractReviewWorkflow


async def run_async_review_job(task_id: str) -> None:
    task = read_task(task_id)
    if task is None:
        return

    try:
        if is_cancel_requested(task_id):
            mark_cancelled(task_id)
            return

        mark_running(task_id)
        write_task_log_event(task_id, "review_started", task_id=task_id)

        workflow = ContractReviewWorkflow(
            server_script_path=str(MCP_SERVER_PATH),
            workflow_log_dir=(
                str(task_workflow_log_dir(task_id)) if task_workflow_log_dir(task_id) else None
            ),
            conversation_log_dir=(
                str(task_conversation_log_dir(task_id)) if task_conversation_log_dir(task_id) else None
            ),
            mcp_log_file=str(task_mcp_log_file(task_id)) if task_mcp_log_file(task_id) else None,
            api_events_path=(
                str(task_api_events_path(task_id)) if task_api_events_path(task_id) else None
            ),
        )

        token = set_conversation_log_dir(task_conversation_log_dir(task_id))
        try:
            if review_semaphore is None:
                result = await workflow.run(
                    contract_path=task["input"]["contract_path"],
                    criteria_path=task["input"]["criteria_path"],
                    output_path=task["output"]["result_path"],
                )
            else:
                async with review_semaphore:
                    result = await workflow.run(
                        contract_path=task["input"]["contract_path"],
                        criteria_path=task["input"]["criteria_path"],
                        output_path=task["output"]["result_path"],
                    )
        finally:
            reset_conversation_log_dir(token)

        if is_cancel_requested(task_id):
            mark_cancelled(task_id)
            write_task_log_event(task_id, "review_cancelled", task_id=task_id)
            return

        output_path = Path(result["report_docx"])
        if not output_path.exists():
            raise RuntimeError("Output DOCX file was not found.")

        mark_succeeded(task_id)
        write_task_log_event(task_id, "review_completed", result_file=str(output_path))
    except Exception as exc:
        if isinstance(exc, ModelCallError):
            write_task_log_event(
                task_id,
                exc.event_type,
                component=exc.component,
                error=str(exc),
            )
            mark_failed(task_id, code=exc.event_type, message=exc.user_message)
        else:
            mark_failed(task_id, code="REVIEW_FAILED", message="Review failed. Check task logs.")
        write_task_log_event(task_id, "review_failed", error=repr(exc))
    finally:
        cleanup_runtime_input(task_id)
