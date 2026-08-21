from __future__ import annotations

from pathlib import Path


def iter_docx_inputs(path: Path, batch: bool) -> list[Path]:
    if path.is_file():
        if path.suffix.lower() != ".docx":
            raise ValueError(f"input file must be .docx: {path}")
        return [path]
    if path.is_dir():
        if not batch:
            raise ValueError("directory input requires --batch")
        return [p for p in sorted(path.rglob("*.docx")) if not p.name.startswith("~$")]
    raise FileNotFoundError(path)
