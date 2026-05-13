from __future__ import annotations

from tempfile import TemporaryDirectory
from pathlib import Path

import pypandoc


DEFAULT_PDF_ENGINE = "xelatex"
DEFAULT_MAIN_FONT = "Microsoft YaHei"
DEFAULT_GEOMETRY = "margin=2.5cm"
DEFAULT_TEMPLATE = Path(__file__).resolve().parent / "pandoc_xelatex_template.tex"


def build_pandoc_extra_args(
    *,
    pdf_engine: str = DEFAULT_PDF_ENGINE,
    main_font: str = DEFAULT_MAIN_FONT,
    cjk_font: str = DEFAULT_MAIN_FONT,
    geometry: str = DEFAULT_GEOMETRY,
    template: str | Path | None = DEFAULT_TEMPLATE,
    resource_path: str | Path | None = None,
    toc: bool = True,
    number_sections: bool = True,
) -> list[str]:
    """Build Pandoc arguments matching the verified md2pdf_test conversion path."""
    extra_args = [
        f"--pdf-engine={pdf_engine}",
        "-V",
        f"geometry:{geometry}",
        "-V",
        f"mainfont={main_font}",
        "-V",
        f"CJKmainfont={cjk_font}",
    ]

    if toc:
        extra_args.append("--toc")
    if number_sections:
        extra_args.append("--number-sections")

    template_path = Path(template) if template else None
    if template_path and template_path.exists():
        extra_args.extend(["--template", str(template_path)])

    if resource_path:
        extra_args.extend(["--resource-path", str(resource_path)])

    return extra_args


def render_markdown_pdf_with_pandoc(
    md_path: str | Path,
    output_path: str | Path,
    *,
    pdf_engine: str = DEFAULT_PDF_ENGINE,
    main_font: str = DEFAULT_MAIN_FONT,
    cjk_font: str = DEFAULT_MAIN_FONT,
    geometry: str = DEFAULT_GEOMETRY,
    template: str | Path | None = DEFAULT_TEMPLATE,
    resource_path: str | Path | None = None,
) -> str:
    """Render markdown to PDF with Pandoc and xelatex."""
    md_file = Path(md_path)
    pdf_file = Path(output_path)
    if not md_file.exists():
        raise FileNotFoundError(f"Markdown file not found: {md_file}")
    if md_file.suffix.lower() != ".md":
        raise ValueError(f"Input is not a Markdown file: {md_file}")

    pdf_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        with TemporaryDirectory() as temp_dir:
            pandoc_input = md_file
            content = md_file.read_text(encoding="utf-8")
            if "\\n" in content:
                pandoc_input = Path(temp_dir) / md_file.name
                pandoc_input.write_text(content.replace("\\n", "\n"), encoding="utf-8")

            pypandoc.convert_file(
                str(pandoc_input),
                to="pdf",
                outputfile=str(pdf_file),
                extra_args=build_pandoc_extra_args(
                    pdf_engine=pdf_engine,
                    main_font=main_font,
                    cjk_font=cjk_font,
                    geometry=geometry,
                    template=template,
                    resource_path=resource_path,
                ),
            )
    except RuntimeError as exc:
        message = str(exc)
        if "xelatex not found" in message:
            raise RuntimeError(
                "Pandoc is installed, but xelatex was not found. "
                "Install MiKTeX, TeX Live, or TinyTeX and reopen PowerShell."
            ) from exc
        raise

    return str(pdf_file.resolve())
