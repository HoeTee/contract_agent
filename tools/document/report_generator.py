from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from tools.document.reporting import (
    DocxReportGenerator,
    render_markdown_pdf_with_pandoc,
    save_markdown_report,
)


class ReportGenerator:
    """Coordinates MD, DOCX, and PDF report generation."""

    @staticmethod
    def _append_generation_info(content: str, elapsed_seconds: float | None) -> str:
        if elapsed_seconds is None:
            return content

        mins, secs = divmod(int(elapsed_seconds), 60)
        return (
            content
            + "\n\n---\n\n"
            + "## 附：报告生成信息\n\n"
            + f"- **总耗时**: {mins}m {secs}s\n"
            + f"- **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        )

    @staticmethod
    def generate_report(
        content: str,
        contract_name: str,
        elapsed_seconds: float = None,
        contract_path: str = None,
        results: list = None,
    ) -> dict:
        """Generate MD, DOCX, and PDF reports from markdown content."""
        project_root = Path(__file__).resolve().parents[2]
        md_dir = project_root / "docs" / "reports_md"
        docx_dir = project_root / "docs" / "reports_docx"
        pdf_dir = project_root / "docs" / "reports_pdf"
        for directory in (md_dir, docx_dir, pdf_dir):
            directory.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"审查报告_{contract_name}_{timestamp}"
        report_content = ReportGenerator._append_generation_info(content, elapsed_seconds)

        errors: dict[str, str] = {}

        md_path = save_markdown_report(report_content, md_dir / f"{base_name}.md")

        docx_output_path = docx_dir / f"{base_name}.docx"
        docx_path = DocxReportGenerator.generate_docx_report(
            report_content,
            contract_path=contract_path,
            results=results,
            output_path=str(docx_output_path),
        )
        if not docx_path:
            errors["docx"] = "DOCX report generation failed."

        pdf_output_path = pdf_dir / f"{base_name}.pdf"
        pdf_path = None
        try:
            pdf_path = render_markdown_pdf_with_pandoc(md_path, pdf_output_path)
        except Exception as exc:
            errors["pdf"] = str(exc)

        return {
            "md": os.path.abspath(md_path),
            "docx": os.path.abspath(docx_path) if docx_path else None,
            "pdf": os.path.abspath(pdf_path) if pdf_path else None,
            "errors": errors,
        }
