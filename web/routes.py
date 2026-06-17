from __future__ import annotations

from fastapi import APIRouter

from web.api.review import api_router
from web.core.document_validation import (
    DOCX_MEDIA_TYPE,
    validate_review_criteria_content,
    validate_uploaded_docx,
)
from web.core.filenames import build_report_display_name, safe_upload_filename, strip_task_file_prefix
from web.user.routes import (
    ctx_path,
    get_request_ctx,
    sync_context_user,
    user_router,
)


router = APIRouter()
router.include_router(api_router)
router.include_router(user_router)
