from __future__ import annotations

from pathlib import Path


def save_markdown_report(content: str, output_path: str | Path) -> str:
    """Save markdown report content and return the absolute output path."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path.resolve())
