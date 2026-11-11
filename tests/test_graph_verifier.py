"""
Unit and Integration Tests for SCKG Graph Verifier
==================================================
Tests both the positive assertion suite against multi-repo workspaces
and the failure-detection invariants against synthetically corrupted graphs.
"""

import os
import sys
import unittest
import networkx as nx

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graph_verifier import SCKGGraphVerifier, VerificationReport, CheckResult
from multi_repo import WorkspaceCKGBuilder


class TestSCKGGraphVerifier(unittest.TestCase):

    def setUp(self):
        self.root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.fixture_ws = os.path.join(self.root_dir, "examples", "multi_repo_system", "workspace.yaml")
        self.boutique_ws = os.path.join(self.root_dir, "repos", "online-boutique", "workspace.yaml")

    def test_verifier_on_fixture_workspace(self):
        """Verifier passes cleanly on showcase multi_repo_system fixture."""
        if not os.path.isfile(self.fixture_ws):
            self.skipTest("Showcase fixture workspace.yaml not found.")

        verifier = SCKGGraphVerifier(workspace_path=self.fixture_ws)
        report = verifier.verify_all()

        self.assertTrue(report.passed, f"Fixture workspace failed verification:\n{report.summary_table()}")
        self.assertEqual(report.fail_count, 0)
        self.assertGreater(report.pass_count, 5)

    def test_verifier_detects_dangling_edge(self):
        """Invariant: graph verifier flags dangling edges where source or target is missing."""
        if not os.path.isfile(self.fixture_ws):
            self.skipTest("Showcase fixture workspace.yaml not found.")

        verifier = SCKGGraphVerifier(workspace_path=self.fixture_ws)
        # Corrupt the graph by adding an edge targeting a nonexistent node
        verifier.graph.add_edge("nonexistent_source_node", "contract::ShippingService", layer="Ldep", relation="CALLS")

        report = verifier.verify_all()
        self.assertFalse(report.passed)
        dangling_check = next(c for c in report.checks if "Zero Dangling Edges" in c.name)
        self.assertEqual(dangling_check.status, "FAIL")
        self.assertIn("nonexistent_source_node", str(dangling_check.details))

    def test_verifier_detects_orphan_contract_without_implements(self):
        """Invariant: graph verifier flags canonical RPC contracts that have zero producer handlers."""
        if not os.path.isfile(self.fixture_ws):
            self.skipTest("Showcase fixture workspace.yaml not found.")

        verifier = SCKGGraphVerifier(workspace_path=self.fixture_ws)
        # Add an orphan RPC contract node with no IMPLEMENTS edge
        orphan_rpc = "contract::FakeInventoryService.CheckStock"
        verifier.graph.add_node(orphan_rpc, type="contract", layer="Lcontract")

        report = verifier.verify_all()
        self.assertFalse(report.passed)
        producer_check = next(c for c in report.checks if "Producer Binding" in c.name)
        self.assertEqual(producer_check.status, "FAIL")
        self.assertIn(orphan_rpc, str(producer_check.details))

    def test_verifier_detects_invalid_consumer_target(self):
        """Invariant: graph verifier flags CONSUMES edges that target non-canonical contract nodes."""
        if not os.path.isfile(self.fixture_ws):
            self.skipTest("Showcase fixture workspace.yaml not found.")

        verifier = SCKGGraphVerifier(workspace_path=self.fixture_ws)
        # Add a CONSUMES edge pointing to a raw function node instead of contract::
        verifier.graph.add_node("raw_target_function", type="function", layer="Ldep")
        verifier.graph.add_edge("caller_node", "raw_target_function", layer="Lcontract", relation="CONSUMES")
        verifier.graph.add_node("caller_node", type="function", layer="Ldep")

        report = verifier.verify_all()
        self.assertFalse(report.passed)
        consumer_check = next(c for c in report.checks if "Consumer Target Integrity" in c.name)
        self.assertEqual(consumer_check.status, "FAIL")

    def test_verifier_passes_on_online_boutique_full_system(self):
        """Verification proof: Google Online Boutique graph build is 100% resolved and verified."""
        if not os.path.isfile(self.boutique_ws):
            self.skipTest("Online Boutique workspace.yaml not found.")

        verifier = SCKGGraphVerifier(workspace_path=self.boutique_ws)
        report = verifier.verify_all(strict=True)

        self.assertTrue(report.passed, f"Online Boutique graph verification failed:\n{report.summary_table()}")
        self.assertEqual(report.fail_count, 0)
        self.assertEqual(report.warn_count, 0)
        self.assertEqual(report.pass_count, 9)

        # Confirm all 15 RPC contracts in Online Boutique have producers
        proto_rpcs = [
            "contract::CartService.AddItem",
            "contract::CartService.GetCart",
            "contract::CartService.EmptyCart",
            "contract::RecommendationService.ListRecommendations",
            "contract::ProductCatalogService.ListProducts",
            "contract::ProductCatalogService.GetProduct",
            "contract::ProductCatalogService.SearchProducts",
            "contract::ShippingService.GetQuote",
            "contract::ShippingService.ShipOrder",
            "contract::CurrencyService.GetSupportedCurrencies",
            "contract::CurrencyService.Convert",
            "contract::PaymentService.Charge",
            "contract::EmailService.SendOrderConfirmation",
            "contract::CheckoutService.PlaceOrder",
            "contract::AdService.GetAds",
        ]
        for rpc in proto_rpcs:
            self.assertIn(rpc, verifier.graph.nodes, f"Missing RPC contract node: {rpc}")
            impls = [u for u, v, d in verifier.graph.in_edges(rpc, data=True) if d.get("relation") == "IMPLEMENTS"]
            self.assertGreaterEqual(len(impls), 1, f"RPC {rpc} has no concrete IMPLEMENTS handlers!")


if __name__ == "__main__":
    unittest.main()
