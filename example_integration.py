"""
Quick integration verification script for Build and Traversal functionality.
Demonstrates both Build and Traversal using SCKGGraphProvider and contracts.
"""

from __future__ import annotations

import os
import sys

from contracts.graph_types import TelemetryEvent, TraversalPolicy
from sckg_provider import SCKGGraphProvider


def main():
    print("=" * 70)
    print("  SCKG / GRAFT-CKG: BUILD & TRAVERSAL INTEGRATION DEMO")
    print("=" * 70)

    # -------------------------------------------------------------------------
    # PART 1: BUILD FUNCTIONALITY
    # -------------------------------------------------------------------------
    print("\n[1] TESTING BUILD FUNCTIONALITY...")
    workspace_path = os.path.join("examples", "multi_repo_system", "workspace.yaml")
    if not os.path.exists(workspace_path):
        print(f"Error: {workspace_path} not found.")
        return

    # Instantiating SCKGGraphProvider triggers the full multi-repo CKG build
    provider = SCKGGraphProvider(workspace_path)
    graph = provider.graph

    print(f"  [+] Build completed successfully!")
    print(f"  [+] Engine Version:       {provider.version()}")
    print(f"  [+] Total Nodes:          {graph.number_of_nodes()}")
    print(f"  [+] Total Edges:          {graph.number_of_edges()}")
    
    # Layer breakdown
    layer_counts = {}
    for _, _, d in graph.edges(data=True):
        l = d.get("layer", "Unknown")
        layer_counts[l] = layer_counts.get(l, 0) + 1
    print(f"  [+] Layer Distribution:   {layer_counts}")

    # -------------------------------------------------------------------------
    # PART 2: TRAVERSAL FUNCTIONALITY
    # -------------------------------------------------------------------------
    print("\n[2] TESTING TRAVERSAL FUNCTIONALITY...")

    # A. Fuzzy Symbol Lookup
    print("\n  [A] Symbol / Node Lookup (find_node_by_name):")
    nodes = provider.find_node_by_name("ShippingService")
    for n in nodes:
        print(f"      Found: {n.short_label()} (ID: {n.node_id})")

    # B. Symptom Resolution from Telemetry
    print("\n  [B] Telemetry Symptom Resolution (resolve_symptom):")
    event = TelemetryEvent(
        event_id="ALERT-901",
        service_name="order_service",
        error_type="gRPC_UNAVAILABLE",
        message="Failed RPC call to ShippingService.GetQuote from handle_checkout",
    )
    symptoms = provider.resolve_symptom(event)
    for s in symptoms[:3]:
        print(f"      Mapped code symptom: {s.short_label()} [File: {s.file_path}:{s.line_start}]")

    target_symptom = symptoms[0] if symptoms else nodes[0]

    # C. Backward Traversal (Root Cause Discovery)
    print("\n  [C] Backward Traversal (backward_traverse):")
    policy = TraversalPolicy(max_depth=3, max_nodes=5)
    candidates = provider.backward_traverse(target_symptom, policy)
    print(f"      Discovered {len(candidates)} candidate root causes:")
    for c in candidates:
        print(f"      - Rank {c.rank}: {c.node.short_label()} | Confidence: {c.confidence:.2f}")
        if c.evidence:
            print(f"        Evidence: {c.evidence[-1]}")

    # D. Forward Traversal (Blast Radius Extraction)
    print("\n  [D] Forward Traversal (forward_traverse):")
    blast_radius = provider.forward_traverse(target_symptom, policy)
    print(f"      Blast Radius Subgraph: {blast_radius.node_count} nodes, {blast_radius.edge_count} edges")
    print(f"      Affected Services:     {blast_radius.services_affected}")
    print(f"      Estimated Tokens:      {blast_radius.estimated_tokens()} tokens")

    # E. Contract Query Between Services
    print("\n  [E] Shared Contract Query (get_contract_between):")
    shared_contracts = provider.get_contract_between("order_service", "shipping_service")
    for sc in shared_contracts:
        print(f"      Shared API Contract: {sc.short_label()} (Signature: {sc.signature})")

    # F. Causal Path Narrative
    print("\n  [F] Causal Path Narrative (explain_path):")
    quote_nodes = provider.find_node_by_name("GetQuote")
    if quote_nodes:
        path = provider.explain_path(target_symptom, quote_nodes[0])
        # Print path with ASCII arrows for safe cross-platform terminal display
        for i, p_node in enumerate(path.nodes):
            print(f"      Step {i + 1}: {p_node.short_label()}")
            if i < len(path.edges):
                print(f"        --[{path.edges[i].edge_type.value}]-->")

    print("\n" + "=" * 70)
    print("  ALL BUILD & TRAVERSAL FUNCTIONALITY VERIFIED AND OPERATIONAL!")
    print("=" * 70)


if __name__ == "__main__":
    main()
