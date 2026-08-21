from __future__ import annotations

import argparse
import unittest

from cli import build_parser


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


if __name__ == "__main__":
    unittest.main()
