from __future__ import annotations

import shutil
import tempfile
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
    safe_contract_stem: str
    temp_dir: Path

    @property
    def date_str(self) -> str:
        return self.created_at.strftime("%Y-%m-%d")

    @property
    def task_log_dir(self) -> Path:
        return self.data_dir / "api_logs" / self.date_str / self.task_id

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
        return self.temp_dir / self.original_filename

    @property
    def uploaded_criteria_path(self) -> Path:
        return self.temp_dir / "criteria.docx"

    @property
    def final_report_path(self) -> Path:
        return self.temp_dir / f"{self.task_id}_{self.safe_contract_stem}_reviewed.docx"

    def ensure_dirs(self) -> None:
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        for path in (
            self.workflow_log_dir,
            self.conversation_log_dir,
            self.mcp_log_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def cleanup_temp_dir(self) -> None: # 销毁临时目录及其中的所有文件，确保不占用磁盘空间
        shutil.rmtree(self.temp_dir, ignore_errors=True)


def resolve_api_review_paths(
    *,
    original_filename: str,
    data_dir: Path,
) -> ResolvedApiReviewPaths:
    created_at = datetime.now()
    safe_filename = Path(original_filename.replace("\\", "/")).name
    stem = safe_path_part(Path(safe_filename).stem, "contract")
    task_id = f"{created_at.strftime('%H%M%S')}_{uuid.uuid4().hex[:8]}"
    temp_dir = Path(tempfile.mkdtemp(prefix=f"contract_review_api_{task_id}_"))
    return ResolvedApiReviewPaths(
        original_filename=safe_filename,
        data_dir=data_dir,
        created_at=created_at,
        task_id=task_id,
        safe_contract_stem=stem,
        temp_dir=temp_dir,
    )
