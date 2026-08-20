from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from retrieval_eval.runner import _build_index


class BuildIndexTest(unittest.TestCase):
    def test_build_uses_retrieval_cli_and_propagates_no_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output_dir = Path(temporary_dir) / "built"
            output_dir.mkdir()
            (output_dir / "document_index.json").write_text("{}", encoding="utf-8")
            config = SimpleNamespace(
                index_root=Path(temporary_dir) / "indexes",
                retrieval_cli=Path(temporary_dir) / "cli.py",
            )
            row = SimpleNamespace(contract_path=str(Path(temporary_dir) / "contract.docx"))
            payload = {"documents": [{"output_dir": str(output_dir)}]}

            with patch("retrieval_eval.runner._run_retrieval_cli", return_value=(payload, "", 1.25)) as run_cli:
                resolved, _, elapsed = _build_index(config, row, no_cache=True)

            self.assertEqual(resolved, output_dir)
            self.assertEqual(elapsed, 1.25)
            arguments = run_cli.call_args.args[1]
            self.assertEqual(arguments[0], "build")
            self.assertIn("--no-cache", arguments)
            self.assertIn(str(config.index_root), arguments)


if __name__ == "__main__":
    unittest.main()
