from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class ReviewStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ReviewStage(str, Enum):
    QUEUED = "queued"
    INGESTING = "ingesting"
    BUILDING_INDEX = "building_index"
    BUILDING_TREE = "building_tree"
    PLANNING = "planning"
    REVIEWING = "reviewing"
    SUMMARIZING = "summarizing"
    GENERATING_REPORT = "generating_report"
    COMPLETED = "completed"
    FAILED = "failed"


class RiskLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class RetrievalMode(str, Enum):
    LLAMAINDEX = "llamaindex"
    PAGEINDEX = "pageindex"
    EVIDENCE = "evidence"


class IssueBase(BaseModel):
    clause_location: str
    page: Optional[int] = None
    risk_level: RiskLevel
    violated_criteria: str
    conclusion: str
    analysis: str
    legal_basis: Optional[str] = None
    suggestion: str


class ReviewTaskCreate(BaseModel):
    contract_path: str
    criteria_path: str
    retrieval_mode: Optional[RetrievalMode] = None


class ReviewTaskResponse(BaseModel):
    task_id: str
    status: ReviewStatus
    created_at: datetime
    contract_name: Optional[str] = None
    retrieval_mode: Optional[RetrievalMode] = None
    stage: Optional[ReviewStage] = None
    progress_message: Optional[str] = None
    error: Optional[str] = None


class ReviewResultResponse(BaseModel):
    task_id: str
    status: ReviewStatus
    contract_name: str
    retrieval_mode: Optional[RetrievalMode] = None
    total_issues: int
    issues: List[IssueBase]
    report_md: Optional[str] = None
    report_docx: Optional[str] = None
    report_pdf: Optional[str] = None
    completed_at: Optional[datetime] = None
    stage: Optional[ReviewStage] = None
    progress_message: Optional[str] = None
    error: Optional[str] = None


class HistoryItem(BaseModel):
    task_id: str
    contract_name: str
    status: ReviewStatus
    created_at: datetime
    completed_at: Optional[datetime] = None
    retrieval_mode: Optional[RetrievalMode] = None
    stage: Optional[ReviewStage] = None
    progress_message: Optional[str] = None
    total_issues: int = 0
    error: Optional[str] = None
