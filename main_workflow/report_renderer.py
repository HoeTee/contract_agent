"""Programmatic markdown rendering for structured review results."""
from typing import Any


RISK_LABELS = {
    "high": "高",
    "medium": "中",
    "low": "低",
}

REVIEW_STATUS_LABELS = {
    "COMPLIANT": "compliant",
    "ISSUES_FOUND": "issues_found",
    "ERROR": "error",
}


def flatten_issues(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten result issues while carrying their parent criterion metadata."""
    issues: list[dict[str, Any]] = []
    for result in results:
        for issue in result["issues"]:
            issues.append(
                {
                    "section": result["section"],
                    "criterion_id": result["criterion_id"],
                    "criterion": result["criterion"],
                    **issue,
                }
            )
    return issues


def build_review_items(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build the section/criterion hierarchy consumed by the API layer."""
    review_items: list[dict[str, Any]] = []
    section_order: dict[str, int] = {}
    section_counts: dict[str, int] = {}

    for result in results:
        section = result["section"]
        if section not in section_order:
            section_order[section] = len(section_order) + 1
            section_counts[section] = 0
        section_counts[section] += 1

        criterion_issues = [
            {
                "section": section,
                "criterion_id": result["criterion_id"],
                "criterion": result["criterion"],
                **issue,
            }
            for issue in result["issues"]
        ]
        review_items.append(
            {
                "criterion_id": result["criterion_id"],
                "section": section,
                "criterion": result["criterion"],
                "section_order": section_order[section],
                "criterion_order": section_counts[section],
                "check_points": result["check_points"],
                "status": REVIEW_STATUS_LABELS[result["status"]],
                "issue_count": len(criterion_issues),
                "issues": criterion_issues,
                "error_message": result.get("error_message"),
            }
        )

    return review_items


def render_report_markdown(summary_sections: dict[str, str], results: list[dict[str, Any]]) -> str:
    """Render the complete markdown report from summary sections and issues."""
    return "\n\n".join(
        [
            "# 合同审查报告",
            summary_sections["overview_markdown"].strip(),
            _render_risk_overview_table(flatten_issues(results)),
            _render_review_details(results),
            summary_sections["priority_advice_markdown"].strip(),
        ]
    )


def _render_risk_overview_table(issues: list[dict[str, Any]]) -> str:
    lines = [
        "## 二、风险总览表",
        "",
        "| 序号 | 审查领域 | 主要问题 | 具体问题 | 风险等级 |",
        "|------|---------|---------|---------|---------|",
    ]
    for index, issue in enumerate(issues, start=1):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(index),
                    _table_cell(issue["section"]),
                    _table_cell(issue["issue_summary"]),
                    _table_cell(issue["conclusion"]),
                    RISK_LABELS[issue["risk_level"]],
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _render_review_details(results: list[dict[str, Any]]) -> str:
    lines = ["## 三、审查详情"]
    current_section = None
    issue_index = 1

    for result in results:
        if not result["issues"]:
            continue

        if result["section"] != current_section:
            current_section = result["section"]
            lines.extend(["", f"### {current_section}"])

        for issue in result["issues"]:
            lines.extend(
                [
                    "",
                    f"#### 检查要点 {issue_index}：{issue['issue_summary']}",
                    "",
                    f"- **风险等级**：{RISK_LABELS[issue['risk_level']]}",
                    f"- **审查结论**：{issue['conclusion']}",
                    "- **原文引用**：",
                    _quote_block(issue["quoted_text"]),
                    f"- **所在位置**：{issue['clause_location']}",
                    f"- **问题分析**：{issue['analysis']}",
                    f"- **法律依据**：{issue['legal_basis']}",
                    f"- **制度依据**：{issue['institutional_basis']}",
                    "- **修改建议**：",
                    _quote_block(issue["suggestion"]),
                ]
            )
            issue_index += 1

    return "\n".join(lines)


def _quote_block(text: str) -> str:
    return "\n".join(f"> {line}" for line in text.splitlines())


def _table_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", "<br>")
