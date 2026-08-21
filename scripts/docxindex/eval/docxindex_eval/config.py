from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class EvalConfig:
    project_dir: Path
    dataset: Path
    retrieval_cli: Path
    retrieval_config: Path
    index_root: Path
    logs_dir: Path
    coverage_threshold: float
    top_k: tuple[int, ...]
    query_timeout_seconds: int
    build_timeout_seconds: int


def _resolve(base: Path, value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def load_config(path: Path) -> EvalConfig:
    config_path = path.resolve()
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    base = config_path.parent
    top_k = tuple(sorted({int(value) for value in payload.get("top_k", [1, 3, 5]) if int(value) > 0}))
    if not top_k:
        raise ValueError("top_k must contain at least one positive integer")
    threshold = float(payload.get("coverage_threshold", 0.8))
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("coverage_threshold must be between 0 and 1")
    return EvalConfig(
        project_dir=base,
        dataset=_resolve(base, payload.get("dataset", "data/retrieval_gold.csv")),
        retrieval_cli=_resolve(base, payload.get("retrieval_cli", "../cli.py")),
        retrieval_config=_resolve(base, payload.get("retrieval_config", "../config.yaml")),
        index_root=_resolve(base, payload.get("index_root", "../outputs/index")),
        logs_dir=_resolve(base, payload.get("logs_dir", "logs")),
        coverage_threshold=threshold,
        top_k=top_k,
        query_timeout_seconds=int(payload.get("query_timeout_seconds", payload.get("timeout_seconds", 600))),
        build_timeout_seconds=int(payload.get("build_timeout_seconds", 1800)),
    )
