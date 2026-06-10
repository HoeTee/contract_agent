from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from loggers.resolve_review_task_paths import safe_path_part


@dataclass(frozen=True)
class ResolvedApiReviewPaths:
    original_filename: str
    data_dir: Path
    created_at: datetime
    task_id: str
    run_dir_name: str
    safe_contract_stem: str

    @property
    def task_dir(self) -> Path:
        return self.data_dir / "api" / self.run_dir_name

    @property
    def task_log_dir(self) -> Path:
        return self.task_dir / "logs"

    @property
    def workflow_log_dir(self) -> Path:
        return self.task_log_dir / "workflow"

    @property
    def conversation_log_dir(self) -> Path:
        return self.task_log_dir / "conversations"

    @property
    def mcp_log_dir(self) -> Path:
        return self.task_log_dir / "mcp"

    @property
    def api_events_path(self) -> Path:
        return self.task_log_dir / "api_events.jsonl"

    @property
    def stored_contract_path(self) -> Path:
        return self.task_dir / self.original_filename

    def stored_criteria_path(self, original_filename: str | None) -> Path:
        safe_filename = Path((original_filename or "criteria.docx").replace("\\", "/")).name
        return self.task_dir / (safe_filename or "criteria.docx")

    @property
    def final_report_path(self) -> Path:
        return self.task_dir / f"{self.safe_contract_stem}_reviewed.docx"

    def ensure_dirs(self) -> None:
        for path in (
            self.task_dir,
            self.workflow_log_dir,
            self.conversation_log_dir,
            self.mcp_log_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


def resolve_api_review_paths(
    *,
    original_filename: str,
    data_dir: Path,
) -> ResolvedApiReviewPaths:
    created_at = datetime.now()
    safe_filename = Path(original_filename.replace("\\", "/")).name
    stem = safe_path_part(Path(safe_filename).stem, "contract")
    unique_suffix = uuid.uuid4().hex[:8]
    task_id = f"{created_at.strftime('%H%M%S')}_{unique_suffix}"
    run_dir_name = f"{created_at.strftime('%Y%m%d-%H%M%S')}-{unique_suffix[:4]}"
    return ResolvedApiReviewPaths(
        original_filename=safe_filename,
        data_dir=data_dir,
        created_at=created_at,
        task_id=task_id,
        run_dir_name=run_dir_name,
        safe_contract_stem=stem,
    )
