"""Exact-ID graph verification regression checks; independent of repository clones."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

import networkx as nx

SOURCE = Path(__file__).resolve().parents[1] / "bench" / "verify_graph_accuracy.py"
spec = importlib.util.spec_from_file_location("verify_graph_accuracy", SOURCE)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class GraphAccuracyTests(unittest.TestCase):
    def setUp(self):
        self.graph = nx.MultiDiGraph()
        self.graph.add_node("src/backend.py:serve", type="function")
        self.graph.add_node("src/client.py:request", type="function")
        self.graph.add_node("contract::Service.Get", type="rpc_contract")
        self.graph.add_edge("src/client.py:request", "contract::Service.Get", relation="CONSUMES", layer="Lcontract")
        self.labels = {
            "nodes": [{"id": "src/backend.py:serve"}],
            "edges": [{"source": "src/client.py:request", "relation": "CONSUMES",
                       "target": "contract::Service.Get", "language": "python"}],
            "closed_scopes": [{"relation": "CONSUMES", "sources": ["src/client.py:request"], "language": "python"}],
        }

    def test_correct_edge(self):
        result = audit.evaluate(self.graph, self.labels)
        self.assertTrue(result["passed"])
        self.assertFalse(result["publication_ready"])
        self.assertEqual(result["closed_scopes"][0]["f1"], 1)
        self.assertIsNone(result["sampled_edges"]["precision"])

    def test_wrong_target_is_false_positive_and_false_negative(self):
        self.graph.add_node("contract::Service.Other", type="rpc_contract")
        self.graph.remove_edge("src/client.py:request", "contract::Service.Get")
        self.graph.add_edge("src/client.py:request", "contract::Service.Other", relation="CONSUMES")
        result = audit.evaluate(self.graph, self.labels)
        self.assertEqual(result["closed_scopes"][0]["tp"], 0)
        self.assertEqual(result["closed_scopes"][0]["fp"], 1)
        self.assertEqual(result["closed_scopes"][0]["fn"], 1)

    def test_extra_edge_reduces_precision(self):
        self.graph.add_node("contract::Service.Other", type="rpc_contract")
        self.graph.add_edge("src/client.py:request", "contract::Service.Other", relation="CONSUMES")
        self.assertEqual(audit.evaluate(self.graph, self.labels)["closed_scopes"][0]["precision"], .5)

    def test_runtime_is_recall_only(self):
        trace = {"observed_edges": [
            {"source": "src/client.py:request", "relation": "CONSUMES", "target": "contract::Service.Get"},
            {"source": "src/backend.py:serve", "relation": "CALLS", "target": "src/client.py:request"}]}
        result = audit.evaluate_trace(self.graph, trace)
        self.assertEqual(result["observed_recall"], .5)
        self.assertIsNone(result["static_precision"])

    def test_source_provenance_and_missing_node(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "src" / "client.py"
            path.parent.mkdir()
            path.write_text("def request():\n    return 'rpc evidence'\n", encoding="utf-8")
            self.labels["edges"][0]["evidence"] = {"file": "src/client.py", "contains": "rpc evidence"}
            result = audit.evaluate(self.graph, self.labels, source_root=temp)
            self.assertEqual(result["source_evidence"]["verified"], 1)
            self.labels["edges"][0]["evidence"]["contains"] = "unrelated"
            self.assertFalse(audit.evaluate(self.graph, self.labels, source_root=temp)["passed"])
        self.labels["nodes"].append({"id": "src/backend.py:missing"})
        self.assertFalse(audit.evaluate(self.graph, self.labels)["passed"])

    def test_contradictory_labels(self):
        self.labels["negatives"] = list(self.labels["edges"])
        with self.assertRaisesRegex(ValueError, "Contradictory"):
            audit.evaluate(self.graph, self.labels)


if __name__ == "__main__":
    unittest.main()
