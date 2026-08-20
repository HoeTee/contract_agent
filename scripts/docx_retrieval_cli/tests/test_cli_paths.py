from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import cli


class CliPathTest(unittest.TestCase):
    def test_default_build_output_and_log_are_project_local(self) -> None:
        args = cli.build_parser().parse_args(["build", "contract.docx"])
        self.assertEqual(PROJECT_DIR / "outputs" / "docx_index", args.out)
        self.assertEqual(PROJECT_DIR / "logs", args.log_dir)

    def test_relative_paths_are_resolved_under_cli_project(self) -> None:
        args = cli.build_parser().parse_args(
            ["ask", "--doc", "outputs/custom", "--query", "支付方式", "--log-dir", "run_logs"]
        )
        self.assertEqual((PROJECT_DIR / "outputs" / "custom").resolve(), args.doc)
        self.assertEqual((PROJECT_DIR / "run_logs").resolve(), args.log_dir)

    def test_absolute_paths_are_preserved(self) -> None:
        absolute = (PROJECT_DIR / "outputs" / "absolute").resolve()
        args = cli.build_parser().parse_args(
            ["ask", "--doc", str(absolute), "--query", "合同期限"]
        )
        self.assertEqual(absolute, args.doc)


if __name__ == "__main__":
    unittest.main()
