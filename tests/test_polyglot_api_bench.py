"""Regression test for the labelled static API-link benchmark."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from eval_polyglot_api_bench import evaluate
from graft_ckg import CKGBuilder


class PolyglotApiBenchmarkTests(unittest.TestCase):
    def test_all_labelled_links_are_recovered_without_negative_links(self) -> None:
        fixture = Path(__file__).resolve().parents[1] / "benchmarks" / "polyglot_api"
        truth = json.loads((fixture / "ground_truth.json").read_text(encoding="utf-8"))
        result = evaluate(CKGBuilder, fixture, truth)
        self.assertEqual(result["true_positives"], 6)
        self.assertEqual(result["false_positives"], 0)
        self.assertEqual(result["false_negatives"], 0)
        self.assertEqual(result["negative_cases_passed"], 2)


if __name__ == "__main__":
    unittest.main()
