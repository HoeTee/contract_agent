from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import EvalConfig
from .dataset import GoldRow, group_cases, load_gold
from .reporting import write_results, write_summary
from .scoring import score_row


def _index_map(root: Path) -> tuple[dict[str, Path], dict[str, Path]]:
    by_path: dict[str, Path] = {}
    by_name: dict[str, Path] = {}
    if not root.exists():
        return by_path, by_name
    for manifest in root.rglob("document_index.json"):
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        source = str(payload.get("source_file") or "")
        if source:
            by_path[str(Path(source).resolve()).casefold()] = manifest.parent
            by_name[Path(source).name.casefold()] = manifest.parent
        doc_name = str(payload.get("doc_name") or "")
        if doc_name:
            by_name.setdefault(f"{doc_name}.docx".casefold(), manifest.parent)
        by_name.setdefault(f"{manifest.parent.name}.docx".casefold(), manifest.parent)
    return by_path, by_name


def _resolve_index(row: GoldRow, by_path: dict[str, Path], by_name: dict[str, Path]) -> Path | None:
    resolved = str(Path(row.contract_path).resolve()).casefold()
    direct = by_path.get(resolved) or by_name.get(Path(row.contract).name.casefold())
    if direct:
        return direct
    stem = Path(row.contract).stem
    safe_stem = re.sub(r'[<>:"/\\|?*\s]+', "_", stem).strip("._")[:120] or "document"
    return by_name.get(f"{safe_stem}.docx".casefold())


def _ask(config: EvalConfig, index_dir: Path, query: str, no_cache: bool) -> tuple[dict[str, Any], str]:
    command = [
        sys.executable,
        str(config.retrieval_cli),
        "ask",
        "--doc",
        str(index_dir),
        "--query",
        query,
        "--quiet",
        "--no-log",
    ]
    if no_cache:
        command.append("--no-cache")
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        command,
        cwd=config.retrieval_cli.parent,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        env=environment,
        timeout=config.timeout_seconds,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or f"exit code {completed.returncode}")
    return json.loads(completed.stdout), completed.stderr


def _excerpt(text: str, limit: int = 180) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else f"{compact[:limit]}..."


def run_evaluation(config: EvalConfig, case_ids: set[str], limit: int | None, no_cache: bool, quiet: bool) -> int:
    started = time.perf_counter()
    rows = load_gold(config.dataset)
    cases = group_cases(rows)
    if case_ids:
        unknown = sorted(case_ids - set(cases))
        if unknown:
            raise ValueError(f"unknown case_id: {', '.join(unknown)}")
        cases = {key: value for key, value in cases.items() if key in case_ids}
    if limit is not None:
        cases = dict(list(cases.items())[:limit])

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = config.logs_dir / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    log_path = run_dir / "run.log"
    result_path = run_dir / "recall_results.csv"
    summary_path = run_dir / "summary.json"
    by_path, by_name = _index_map(config.index_root)
    result_rows: list[dict[str, Any]] = []
    case_scores: list[float] = []
    strict_passes = 0
    positive_cases = 0
    negative_cases = 0

    with log_path.open("w", encoding="utf-8") as log:
        for case_id, gold_rows in cases.items():
            first = gold_rows[0]
            index_dir = _resolve_index(first, by_path, by_name)
            case_start = time.perf_counter()
            payload: dict[str, Any] = {"nodes": []}
            error = ""
            stderr = ""
            if index_dir is None:
                error = "index not found"
            else:
                try:
                    payload, stderr = _ask(config, index_dir, first.query, no_cache)
                except Exception as exc:
                    error = str(exc)
            elapsed = round(time.perf_counter() - case_start, 3)
            nodes = payload.get("nodes") or []
            positive_hits = []
            for gold in gold_rows:
                scored = score_row(gold.recall, nodes, config.top_k, config.coverage_threshold) if gold.label == 1 else {}
                largest_k = max(config.top_k)
                if gold.label == 1:
                    positive_hits.append(int(scored[f"hit_at_{largest_k}"]))
                result_rows.append(
                    {
                        "case_id": gold.case_id,
                        "criterion_id": gold.criterion_id,
                        "contract": gold.contract,
                        "contract_path": gold.contract_path,
                        "query": gold.query,
                        "recall": gold.recall,
                        "label": gold.label,
                        "notes": gold.notes,
                        **scored,
                        "retrieved_node_ids": json.dumps([node.get("node_id") for node in nodes], ensure_ascii=False),
                        "elapsed_seconds": payload.get("elapsed_seconds", elapsed),
                        "error": error,
                    }
                )
            if positive_hits:
                positive_cases += 1
                case_recall = sum(positive_hits) / len(positive_hits)
                case_scores.append(case_recall)
                strict = int(all(positive_hits) and not error)
                strict_passes += strict
                status = "PASS" if strict else "FAIL"
                recall_display = f"{case_recall:.3f}"
            else:
                negative_cases += 1
                status = "SKIP"
                recall_display = "n/a"
            line = f"[{case_id}] criterion={first.criterion_id} {status} Recall@{max(config.top_k)}={recall_display} nodes={len(nodes)} elapsed={elapsed:.3f}s"
            log.write(line + "\n")
            if stderr:
                log.write(stderr.rstrip() + "\n")
            log.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            if not quiet:
                print(line)
                for rank, node in enumerate(nodes, start=1):
                    print(f"  {rank}. {node.get('node_id')} {node.get('title') or ''}: {_excerpt(str(node.get('text') or ''))}")

    positive_rows = [row for row in result_rows if int(row["label"]) == 1]
    summary: dict[str, Any] = {
        "cases": len(cases),
        "positive_cases": positive_cases,
        "negative_cases_not_scored": negative_cases,
        "evidence": len(positive_rows),
        "coverage_threshold": config.coverage_threshold,
        "case_limit": limit,
        "no_cache": no_cache,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "strict_case_accuracy": round(strict_passes / positive_cases, 6) if positive_cases else 0.0,
        "macro_recall": round(sum(case_scores) / len(case_scores), 6) if case_scores else 0.0,
        "results_csv": str(result_path),
        "run_log": str(log_path),
    }
    for value in config.top_k:
        hits = sum(int(row.get(f"hit_at_{value}", 0)) for row in positive_rows)
        summary[f"micro_recall_at_{value}"] = round(hits / len(positive_rows), 6) if positive_rows else 0.0
    write_results(result_path, result_rows)
    write_summary(summary_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not any(row["error"] for row in result_rows) else 2
