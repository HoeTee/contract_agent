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
    parser.add_argument("--start", type=positive_int, action="append", help="First CSV data row in a range; repeatable.")
    parser.add_argument("--end", type=positive_int, action="append", help="Last CSV data row in a range; repeatable.")
    parser.add_argument("--no-cache", action="store_true", help="Disable both index-build and retrieval LLM caches.")
    parser.add_argument("--no-build-cache", action="store_true", help="Disable only the index-build LLM cache.")
    parser.add_argument("--no-query-cache", action="store_true", help="Disable only the retrieval LLM cache.")
    parser.add_argument("--quiet", action="store_true", help="Only print the final summary.")
    return parser


def parse_row_ranges(parser: argparse.ArgumentParser, args: argparse.Namespace) -> list[tuple[int, int]]:
    starts = args.start or []
    ends = args.end or []
    if len(starts) != len(ends):
        parser.error(
            "--start and --end must appear the same number of times; "
            f"received {len(starts)} --start values and {len(ends)} --end values"
        )
    if starts and (args.limit is not None or args.case_ids):
        parser.error("--start/--end cannot be combined with --limit or --case")
    ranges = list(zip(starts, ends))
    for position, (start, end) in enumerate(ranges, start=1):
        if start > end:
            parser.error(f"range {position}: --start {start} must be less than or equal to --end {end}")
    return ranges


def main() -> int:
    configure_utf8_console()
    parser = build_parser()
    args = parser.parse_args()
    row_ranges = parse_row_ranges(parser, args)
    config = load_config(args.config)
    return run_evaluation(
        config,
        case_ids=set(args.case_ids or []),
        limit=args.limit,
        row_ranges=row_ranges,
        no_build_cache=args.no_cache or args.no_build_cache,
        no_query_cache=args.no_cache or args.no_query_cache,
        quiet=args.quiet,
    )


if __name__ == "__main__":
    raise SystemExit(main())
