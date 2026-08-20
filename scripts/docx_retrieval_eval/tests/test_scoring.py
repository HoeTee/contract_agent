from __future__ import annotations

import unittest

from retrieval_eval.normalization import normalize_text
from retrieval_eval.scoring import evidence_coverage, score_row


class ScoringTests(unittest.TestCase):
    def test_normalization_ignores_spacing_and_quote_variants(self) -> None:
        self.assertEqual(normalize_text("甲方 “付款”\n30 日"), '甲方"付款"30日')

    def test_exact_evidence_is_full_coverage(self) -> None:
        nodes = [{"text": "合同有效期为三年，自签署之日起计算。"}]
        self.assertEqual(evidence_coverage("有效期为三年", nodes), 1.0)

    def test_partial_evidence_uses_coverage_threshold(self) -> None:
        nodes = [{"text": "付款计划第一期支付40%，第二期支付30%。"}]
        result = score_row("第一期支付40%，第二期支付30%，第三期支付30%。", nodes, (1,), 0.8)
        self.assertLess(result["coverage_at_1"], 0.8)
        self.assertEqual(result["hit_at_1"], 0)


if __name__ == "__main__":
    unittest.main()
