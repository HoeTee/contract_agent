from __future__ import annotations

import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from config import DEFAULT_REVIEW_CRITERIA_PATH


def safe_path_part(value: str, fallback: str = "item") -> str: # 文件/文件夹名
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip().strip(".") # 
    cleaned = re.sub(r"\s+", "_", cleaned) # \s 空白字符 \s+ 一个或多个空白字符 \t TAB \n 换行 \r 回车
    return cleaned or fallback


def ensure_default_criteria_file(user_root: Path) -> Path:
    criteria_path = user_root / "contract_review_criteria" / "criteria.docx"
    default_criteria_path = Path(DEFAULT_REVIEW_CRITERIA_PATH)
    if not criteria_path.exists():
        if not default_criteria_path.exists():
            raise FileNotFoundError(f"未找到系统默认审查要点文件：{default_criteria_path}")
        shutil.copy2(default_criteria_path, criteria_path)
    return criteria_path


@dataclass(frozen=True)
class ResolvedReviewTaskPaths:
    username: str
    original_filename: str
    data_dir: Path
    created_at: datetime
    task_id: str
    safe_contract_stem: str

    @property
    def date_str(self) -> str:
        return self.created_at.strftime("%Y-%m-%d")

    @property
    def file_prefix(self) -> str:
        return f"{self.created_at.strftime('%Y%m%d')}_{self.task_id}"

    @property
    def task_name(self) -> str:
        return f"{self.task_id}_{self.safe_contract_stem}"

    @property
    def user_root(self) -> Path:
        return self.data_dir / self.username

    @property
    def criteria_path(self) -> Path:
        return self.user_root / "contract_review_criteria" / "criteria.docx"

    @property
    def uploaded_criteria_path(self) -> Path:
        return self.task_log_dir / "criteria.docx"

    @property
    def contracts_dir(self) -> Path:
        return self.user_root / "contracts"

    @property
    def reports_docx_dir(self) -> Path:
        return self.user_root / "reports_docx"

    @property
    def logs_dir(self) -> Path:
        return self.user_root / "logs"

    @property
    def stored_contract_path(self) -> Path:
        return self.contracts_dir / f"{self.file_prefix}_{self.original_filename}"

    @property
    def final_report_path(self) -> Path:
        return self.reports_docx_dir / f"{self.file_prefix}_{self.safe_contract_stem}_批注版.docx"

    @property
    def task_log_dir(self) -> Path:
        return self.logs_dir / self.date_str / self.task_name

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

    def ensure_user_dirs(self) -> None:
        for path in (
            self.user_root / "contract_review_criteria",
            self.contracts_dir,
            self.reports_docx_dir,
            self.logs_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
        ensure_default_criteria_file(self.user_root)

    def ensure_task_dirs(self) -> None:
        self.ensure_user_dirs()
        for path in (
            self.workflow_log_dir,
            self.conversation_log_dir,
            self.mcp_log_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


def resolve_review_task_paths(
    *,
    username: str,
    original_filename: str,
    data_dir: Path,
) -> ResolvedReviewTaskPaths:
    created_at = datetime.now()
    safe_filename = Path(original_filename.replace("\\", "/")).name
    stem = safe_path_part(Path(safe_filename).stem, "contract")
    task_id = f"{created_at.strftime('%H%M%S')}_{uuid.uuid4().hex[:8]}"
    return ResolvedReviewTaskPaths(
        username=safe_path_part(username, "user"),
        original_filename=safe_filename,
        data_dir=data_dir,
        created_at=created_at,
        task_id=task_id,
        safe_contract_stem=stem,
    )


def initialize_user_data_dir(data_dir: Path, username: str) -> Path:
    user_root = data_dir / safe_path_part(username, "user") # 用户文件夹名
    for child in (
        "contract_review_criteria",
        "contracts",
        "reports_docx",
        "logs",
    ):
        (user_root / child).mkdir(parents=True, exist_ok=True) # 建立用户文件夹及一系列子文件夹
    ensure_default_criteria_file(user_root)
    return user_root
