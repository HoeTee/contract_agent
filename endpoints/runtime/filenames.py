from __future__ import annotations

import re
from pathlib import Path


TASK_FILE_PREFIX_RE = re.compile(r"^\d{8}_\d{6}_[0-9a-f]{8}_")


def safe_upload_filename(filename: str | None) -> str:
    if not filename:
        return "uploaded.docx"
    return Path(filename.replace("\\", "/")).name


def build_report_display_name(contract_original_name: str) -> str:
    stem = Path(contract_original_name).stem or "审核结果"
    return f"【已AI审查】{stem}.docx"


def strip_task_file_prefix(filename: str | None) -> str:
    if not filename:
        return ""
    return TASK_FILE_PREFIX_RE.sub("", safe_upload_filename(filename))
