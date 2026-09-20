"""
test_lineage.py  —  Unit tests for GRAFT-CKG Git Lineage Layer (L_lineage)
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from graft_ckg import CKGBuilder
from lineage import LineageLayer, CommitRecord


POLYGLOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "examples", "polyglot_system",
)


def _build_and_layer():
    b = CKGBuilder(POLYGLOT)
    b.build()
    layer = LineageLayer(b)
    return b, layer


class LineageLayerTests(unittest.TestCase):

    def test_ingest_real_repo(self):
        """Lineage layer ingests the GRAFT-CKG repo's own git history (or handles no-git gracefully)."""
        b, layer = _build_and_layer()
        n = layer.ingest(max_commits=10)
        # Either 0 (no git) or >0 commits
        self.assertGreaterEqual(n, 0)

    def test_manual_commit_adds_node_and_edge(self):
        """Manually injecting a commit record creates correct commit and TOUCHES nodes/edges."""
        b, layer = _build_and_layer()

        rec = CommitRecord(
            sha="deadbeef0000",
            message="Fix shipping cost calculation",
            author="alice",
            date="2024-06-01",
        )
        rec.files.append((10, 3, "services/order_py/order_service.py"))
        layer.commits["deadbeef0000"] = rec
        layer._add_commit_node(rec)
        layer._add_touches_edge("deadbeef0000", "services/order_py/order_service.py", 10, 3)

        commit_nid = "commit::deadbeef0000"
        self.assertTrue(b.graph.has_node(commit_nid))
        self.assertEqual(b.graph.nodes[commit_nid]["type"], "commit")
        self.assertEqual(b.graph.nodes[commit_nid]["layer"], "Llineage")

        touches_edges = [
            (u, v, d) for u, v, d in b.graph.edges(data=True)
            if d.get("relation") == "TOUCHES" and u == commit_nid
        ]
        self.assertGreater(len(touches_edges), 0)
        self.assertEqual(touches_edges[0][2]["lines_added"], 10)
        self.assertEqual(touches_edges[0][2]["lines_removed"], 3)

    def test_who_changed_returns_correct_commit(self):
        """who_changed finds commits that touched a given symbol."""
        b, layer = _build_and_layer()

        rec = CommitRecord(sha="cafef00d1234", message="Refactor handle_checkout",
                           author="bob", date="2024-07-01")
        rec.files.append((5, 1, "services/order_py/order_service.py"))
        layer.commits["cafef00d1234"] = rec
        layer._add_commit_node(rec)
        layer._add_touches_edge("cafef00d1234", "services/order_py/order_service.py", 5, 1)

        results = layer.who_changed("handle_checkout")
        # Should find the commit we injected (sha is stored as sha[:12])
        shas = [r["sha"] for r in results]
        self.assertTrue(any(s.startswith("cafef00d") for s in shas),
                        f"Expected sha starting with 'cafef00d' in {shas}")

    def test_file_history_filters_correctly(self):
        """file_history returns only commits that touched the specified file."""
        b, layer = _build_and_layer()

        for i in range(3):
            sha = f"abc{i:09d}"
            rec = CommitRecord(sha=sha, message=f"commit {i}", author="dev", date=f"2024-0{i+1}-01")
            target = "services/order_py/order_service.py" if i < 2 else "frontend/src/Checkout.tsx"
            rec.files.append((i + 1, 0, target))
            layer.commits[sha] = rec
            layer._add_commit_node(rec)
            layer._add_touches_edge(sha, target, i + 1, 0)

        history = layer.file_history("services/order_py/order_service.py")
        for h in history:
            self.assertIn("order_service", h["file"])

    def test_co_change_weight_same_commit(self):
        """co_change_weight is 1.0 if two files always change together."""
        b, layer = _build_and_layer()

        for i in range(3):
            sha = f"111{i:09d}"
            rec = CommitRecord(sha=sha, message=f"co-change {i}", author="dev", date="2024-01-01")
            rec.files.append((1, 0, "services/order_py/order_service.py"))
            rec.files.append((1, 0, "frontend/src/Checkout.tsx"))
            layer.commits[sha] = rec
            layer._add_commit_node(rec)

        w = layer.co_change_weight(
            "services/order_py/order_service.py",
            "frontend/src/Checkout.tsx"
        )
        self.assertAlmostEqual(w, 1.0, places=2)

    def test_co_change_weight_no_overlap(self):
        """co_change_weight is 0.0 if files never change together."""
        b, layer = _build_and_layer()

        sha_a = "aaaaaaaaaaaaa"
        rec_a = CommitRecord(sha=sha_a, message="a only", author="dev", date="2024-01-01")
        rec_a.files.append((1, 0, "file_a.py"))
        layer.commits[sha_a] = rec_a

        sha_b = "bbbbbbbbbbbbb"
        rec_b = CommitRecord(sha=sha_b, message="b only", author="dev", date="2024-01-02")
        rec_b.files.append((1, 0, "file_b.py"))
        layer.commits[sha_b] = rec_b

        w = layer.co_change_weight("file_a.py", "file_b.py")
        self.assertEqual(w, 0.0)

    def test_export_lineage_subgraph(self):
        """export_lineage_subgraph returns only Llineage nodes and TOUCHES edges."""
        b, layer = _build_and_layer()

        rec = CommitRecord(sha="fff000aaa111", message="test export", author="dev", date="2024-01-01")
        rec.files.append((2, 1, "services/order_py/order_service.py"))
        layer.commits["fff000aaa111"] = rec
        layer._add_commit_node(rec)
        layer._add_touches_edge("fff000aaa111", "services/order_py/order_service.py", 2, 1)

        sg = layer.export_lineage_subgraph()
        import networkx as nx
        self.assertIsInstance(sg, nx.DiGraph)
        for _, data in sg.nodes(data=True):
            # All nodes should be either commit or file nodes from lineage
            self.assertIn(data.get("layer"), ("Llineage", None))
        for _, _, data in sg.edges(data=True):
            self.assertEqual(data.get("relation"), "TOUCHES")


if __name__ == "__main__":
    unittest.main()
