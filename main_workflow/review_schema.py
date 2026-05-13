"""Shared data structures for contract review results.

The workflow should pass these structures between summarization, API response
building, and DOCX annotation. Markdown remains an export format, not the data
source for downstream tools.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


RiskLevel = Literal["high", "medium", "low", "none", "unknown"]
ReviewStatus = Literal["compliant", "issues_found", "error", "unknown"]
AnnotationStatus = Literal["pending", "matched", "unmatched", "skipped"]


@dataclass(slots=True)
class ReviewIssue:
    """One concrete review issue found for a criterion."""

    issue_id: str
    criterion_id: str
    section: str
    criterion: str
    risk_level: RiskLevel = "unknown"
    clause_location: str = ""
    quoted_text: str = ""
    issue_summary: str = ""
    analysis: str = ""
    institutional_basis: str = ""
    suggestion: str = ""
    comment_text: str = ""
    annotation_status: AnnotationStatus = "pending"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ReviewResult:
    """Structured result for one review criterion."""

    criterion_id: str
    criterion: str
    section: str
    status: ReviewStatus
    issues: list[ReviewIssue] = field(default_factory=list)
    raw_output: str = ""
    check_points: list[dict[str, Any]] = field(default_factory=list)
    error_message: str | None = None
    tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AnnotatedDocxResult:
    """Result returned by a DOCX annotation tool."""

    output_path: str | None
    matched_count: int = 0
    unmatched_count: int = 0
    skipped_count: int = 0
    unmatched_issue_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
