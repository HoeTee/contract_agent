from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))

from docxindex_eval.config import load_config
from docxindex_eval.runner import run_evaluation


def configure_utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate docxindex recall against a Gold CSV.")
    parser.add_argument("--config", type=Path, default=PROJECT_DIR / "config.yaml")
    parser.add_argument("--case", action="append", dest="case_ids", help="Run only this case_id; repeatable.")
    parser.add_argument("--limit", type=positive_int, help="Run only the first N complete case_id groups.")
    parser.add_argument("--start", type=positive_int, help="First CSV data row to run, one-based and inclusive.")
    parser.add_argument("--end", type=positive_int, help="Last CSV data row to run, one-based and inclusive.")
    parser.add_argument("--no-cache", action="store_true", help="Disable both index-build and retrieval LLM caches.")
    parser.add_argument("--no-build-cache", action="store_true", help="Disable only the index-build LLM cache.")
    parser.add_argument("--no-query-cache", action="store_true", help="Disable only the retrieval LLM cache.")
    parser.add_argument("--quiet", action="store_true", help="Only print the final summary.")
    return parser


def main() -> int:
    configure_utf8_console()
    args = build_parser().parse_args()
    range_requested = args.start is not None or args.end is not None
    if range_requested and (args.start is None or args.end is None):
        raise SystemExit("error: --start and --end must be provided together")
    if range_requested and args.start > args.end:
        raise SystemExit("error: --start must be less than or equal to --end")
    if range_requested and (args.limit is not None or args.case_ids):
        raise SystemExit("error: --start/--end cannot be combined with --limit or --case")
    config = load_config(args.config)
    return run_evaluation(
        config,
        case_ids=set(args.case_ids or []),
        limit=args.limit,
        start=args.start,
        end=args.end,
        no_build_cache=args.no_cache or args.no_build_cache,
        no_query_cache=args.no_cache or args.no_query_cache,
        quiet=args.quiet,
    )


if __name__ == "__main__":
    raise SystemExit(main())
