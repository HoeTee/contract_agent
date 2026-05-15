"""
Pydantic schemas for validating structured agent outputs.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictOutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlannerCriterion(StrictOutputModel):
    id: str = Field(min_length=1)
    section: str = Field(min_length=1)
    criterion: str = Field(min_length=1)
    check_points: list[str] = Field(min_length=1)

    @field_validator("check_points")
    @classmethod
    def check_points_not_empty(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("check_points must not contain empty strings")
        return value


class PlannerOutput(StrictOutputModel):
    criteria: list[PlannerCriterion] = Field(min_length=1)


class ReviewIssue(StrictOutputModel):
    issue_id: str = Field(min_length=1)
    risk_level: Literal["high", "medium", "low"]
    quoted_text: str
    comment_text: str = Field(min_length=1, max_length=100)

    @field_validator("issue_id", "comment_text")
    @classmethod
    def required_text_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value


class SubAgentOutput(StrictOutputModel):
    status: Literal["compliant", "issues_found"]
    issues: list[ReviewIssue]

    @model_validator(mode="after")
    def validate_status_issues(self):
        if self.status == "compliant" and self.issues:
            raise ValueError("status is compliant, so issues must be empty")
        if self.status == "issues_found" and not self.issues:
            raise ValueError("status is issues_found, so issues must not be empty")
        return self


class ReflectorOutput(StrictOutputModel):
    status: Literal["PASS", "REJECT"]
    feedback: str = ""


class SummaryOutput(StrictOutputModel):
    overall_comment: str = ""
    priority_comments: list[str] = Field(default_factory=list)

    @field_validator("priority_comments")
    @classmethod
    def priority_comments_not_blank(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("priority_comments must not contain empty strings")
        return value

    @model_validator(mode="after")
    def validate_total_length(self):
        total_length = len(self.overall_comment) + sum(
            len(item) for item in self.priority_comments
        )
        if total_length > 200:
            raise ValueError("overall_comment and priority_comments must be <= 200 chars total")
        return self
