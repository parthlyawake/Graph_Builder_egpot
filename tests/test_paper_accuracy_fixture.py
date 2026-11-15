"""Source-evidenced closed-scope benchmark regression on the bundled polyglot API fixture."""
import json
from pathlib import Path
import unittest

from graft_ckg import CKGBuilder
from bench.verify_graph_accuracy import evaluate


ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/"benchmarks"/"polyglot_api"
LABELS=ROOT/"bench"/"labels"/"polyglot_api_closed_scopes.json"


class TestClosedScopePaperLabels(unittest.TestCase):
    def test_source_evidence_and_http_ground_truth(self):
        labels=json.loads(LABELS.read_text(encoding="utf-8"))
        builder=CKGBuilder(str(FIXTURE))
        builder.build()
        report=evaluate(builder.graph,labels,source_root=FIXTURE)
        self.assertTrue(report["passed"],report)
        self.assertEqual(report["sampled_edges"]["found"],6)
        self.assertFalse(report["negative_violations"])
        self.assertEqual(report["source_evidence"]["missing"],0)
        self.assertEqual(report["closed_scopes"][0]["tp"],6)
        self.assertEqual(report["closed_scopes"][0]["fp"],0)
        self.assertFalse(report["publication_ready"],"Human sign-off is required")


if __name__=="__main__":unittest.main()
