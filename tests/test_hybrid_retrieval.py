import contextlib
import io
import json
from pathlib import Path
import unittest

from graft_ckg import CKGBuilder
from hybrid_retrieval import CONFIGS, HybridRetriever


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "hybrid_retrieval_system"
LABELS = Path(__file__).resolve().parents[1] / "bench" / "labels" / "hybrid_retrieval_demo.json"


class HybridRetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.builder = CKGBuilder(str(EXAMPLE))
            cls.builder.build()
        cls.retriever = HybridRetriever(cls.builder)

    def test_all_configurations_return_a_common_schema(self):
        for config_id in CONFIGS:
            result = self.retriever.retrieve("Where is the order total calculated?", config_id, top_k=4)
            self.assertEqual(result["requested_config"], config_id)
            self.assertIn("top_matches", result)
            self.assertIn("context", result)
            self.assertLessEqual(result["bpe_tokens"], result["token_budget"])

    def test_static_hybrid_finds_calculation_symbol(self):
        result = self.retriever.retrieve("Where is the order total price calculated?", "R5")
        self.assertTrue(any("calculate_total" in item["node_id"] for item in result["top_matches"]))

    def test_adaptive_router_selects_contract_path(self):
        result = self.retriever.retrieve("Which HTTP endpoint creates an order?", "R12")
        self.assertEqual(result["effective_config"], "R9")
        self.assertEqual(result["intent"], "cross-service / contract")

    def test_r13_preserves_router_strategy_and_adds_reranking(self):
        result = self.retriever.retrieve("Which HTTP endpoint creates an order?", "R13")
        self.assertEqual(result["effective_config"], "R13")
        self.assertTrue(result["top_matches"])

    def test_benchmark_executes_every_configuration(self):
        report = self.retriever.benchmark(json.loads(LABELS.read_text(encoding="utf-8")), top_k=5, token_budget=1000)
        self.assertEqual(set(report["methods"]), set(CONFIGS))
        self.assertEqual(report["task_count"], 3)
        self.assertIn("MRR@5", report["methods"]["R5"])

    def test_context_packer_enforces_the_exact_budget(self):
        result = self.retriever.retrieve("Where is the order total price calculated?", "R5", token_budget=120)
        self.assertLessEqual(result["bpe_tokens"], 120)


if __name__ == "__main__":
    unittest.main()
