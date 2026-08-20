from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))

from retrieval_eval.config import load_config
from retrieval_eval.runner import run_evaluation


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate DOCX retrieval recall against a Gold CSV.")
    parser.add_argument("--config", type=Path, default=PROJECT_DIR / "config.yaml")
    parser.add_argument("--case", action="append", dest="case_ids", help="Run only this case_id; repeatable.")
    parser.add_argument("--limit", type=positive_int, help="Run only the first N complete case_id groups.")
    parser.add_argument("--no-cache", action="store_true", help="Disable retrieval LLM cache.")
    parser.add_argument("--quiet", action="store_true", help="Only print the final summary.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = load_config(args.config)
    return run_evaluation(
        config,
        case_ids=set(args.case_ids or []),
        limit=args.limit,
        no_cache=args.no_cache,
        quiet=args.quiet,
    )


if __name__ == "__main__":
    raise SystemExit(main())
