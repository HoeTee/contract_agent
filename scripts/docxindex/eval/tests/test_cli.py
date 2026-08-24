from __future__ import annotations

import argparse
import unittest

from cli import build_parser, parse_row_ranges


class CliArgumentsTest(unittest.TestCase):
    def test_limit_accepts_positive_integer(self) -> None:
        args = build_parser().parse_args(["--limit", "10"])

        self.assertEqual(args.limit, 10)

    def test_limit_rejects_zero(self) -> None:
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["--limit", "0"])

    def test_no_cache_can_be_scoped_by_stage(self) -> None:
        args = build_parser().parse_args(["--no-build-cache"])
        self.assertTrue(args.no_build_cache)
        self.assertFalse(args.no_query_cache)
        self.assertFalse(args.no_cache)

    def test_rebuild_index_is_independent_from_llm_cache(self) -> None:
        args = build_parser().parse_args(["--rebuild-index"])
        self.assertTrue(args.rebuild_index)
        self.assertFalse(args.no_build_cache)

    def test_row_range_accepts_positive_inclusive_bounds(self) -> None:
        args = build_parser().parse_args(["--start", "1", "--end", "18"])

        self.assertEqual(args.start, [1])
        self.assertEqual(args.end, [18])

    def test_multiple_row_ranges_are_paired_by_position(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--start", "1", "--end", "18", "--start", "101", "--end", "120"])

        self.assertEqual(parse_row_ranges(parser, args), [(1, 18), (101, 120)])

    def test_mismatched_row_range_counts_exit_before_evaluation(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--start", "1", "--end", "18", "--start", "101"])

        with self.assertRaises(SystemExit) as context:
            parse_row_ranges(parser, args)
        self.assertEqual(context.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
