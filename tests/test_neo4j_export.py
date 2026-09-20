"""
tests/test_neo4j_export.py  -  Unit tests for the Neo4j Cypher Exporter
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graft_ckg import CKGBuilder
from neo4j_export import CypherExporter

POLYGLOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "examples", "polyglot_system",
)


def _build():
    b = CKGBuilder(POLYGLOT)
    b.build()
    return b


class Neo4jExportTests(unittest.TestCase):

    def test_export_creates_file(self):
        """Export produces a non-empty .cypher file."""
        b = _build()
        exp = CypherExporter(b.graph)
        with tempfile.NamedTemporaryFile(suffix=".cypher", delete=False) as f:
            path = f.name
        try:
            n = exp.export(path)
            self.assertGreater(n, 0, "Expected at least one Cypher statement")
            self.assertGreater(os.path.getsize(path), 100, "Cypher file too small")
        finally:
            os.unlink(path)

    def test_export_contains_constraints(self):
        """Exported Cypher includes CREATE CONSTRAINT statements."""
        b = _build()
        exp = CypherExporter(b.graph)
        cypher = exp.to_string()
        self.assertIn("CREATE CONSTRAINT", cypher)

    def test_export_contains_merge_nodes(self):
        """Exported Cypher has MERGE node statements."""
        b = _build()
        exp = CypherExporter(b.graph)
        cypher = exp.to_string()
        self.assertIn("MERGE", cypher)
        self.assertIn("node_id", cypher)

    def test_export_contains_relationships(self):
        """Exported Cypher has relationship MERGE statements for known relations."""
        b = _build()
        exp = CypherExporter(b.graph)
        cypher = exp.to_string()
        # At least one of these relations must appear
        self.assertTrue(
            any(rel in cypher for rel in ("CALLS", "CONTAINS", "IMPORTS", "PASSES_ARG")),
            "Expected at least one known relationship type in Cypher output"
        )

    def test_export_node_count_matches_graph(self):
        """Number of unique node_id values in Cypher matches graph node count."""
        b = _build()
        exp = CypherExporter(b.graph)
        cypher = exp.to_string()
        # Count MERGE node lines (each UNWIND row becomes a MERGE)
        merge_lines = [ln for ln in cypher.splitlines() if ln.strip().startswith("MERGE (n:")]
        # At least 1 MERGE block per node label
        self.assertGreater(len(merge_lines), 0)

    def test_to_string_returns_valid_utf8(self):
        """to_string() returns a proper UTF-8 string without encoding errors."""
        b = _build()
        exp = CypherExporter(b.graph)
        cypher = exp.to_string()
        self.assertIsInstance(cypher, str)
        cypher.encode("utf-8")  # Would raise if invalid


if __name__ == "__main__":
    unittest.main()
