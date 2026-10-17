"""
Tests for SCKGGraphProvider implementing the GraphProvider contract interface.
"""

from __future__ import annotations

import os
import pytest

from contracts.graph_provider import GraphProvider
from contracts.graph_types import (
    CandidateRootCause,
    CausalPath,
    CodeNode,
    EdgeType,
    InducedSubgraph,
    Language,
    NodeType,
    TelemetryEvent,
    TraversalPolicy,
    TypedEdge,
)
from sckg_provider import SCKGGraphProvider


@pytest.fixture(scope="module")
def polyglot_provider():
    target = os.path.join(os.path.dirname(os.path.dirname(__file__)), "examples", "polyglot_system")
    return SCKGGraphProvider(target)


@pytest.fixture(scope="module")
def multi_repo_provider():
    target = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "examples",
        "multi_repo_system",
        "workspace.yaml",
    )
    return SCKGGraphProvider(target)


def test_interface_compliance(polyglot_provider):
    """Ensure SCKGGraphProvider is an instance of GraphProvider ABC."""
    assert isinstance(polyglot_provider, GraphProvider)
    assert isinstance(polyglot_provider.version(), str)
    assert "GRAFT-CKG" in polyglot_provider.version()


def test_find_node_by_name(polyglot_provider):
    """Test lookup of nodes by name with and without file paths."""
    matches = polyglot_provider.find_node_by_name("ShippingService")
    assert len(matches) > 0
    node = matches[0]
    assert isinstance(node, CodeNode)
    assert node.node_type == NodeType.CONTRACT
    assert node.name == "ShippingService"


def test_get_node_detail(polyglot_provider):
    """Test fetching node details for a valid node ID."""
    nodes = polyglot_provider.find_node_by_name("ShippingService")
    assert len(nodes) > 0
    detail = polyglot_provider.get_node_detail(nodes[0].node_id)
    assert isinstance(detail, CodeNode)
    assert detail.node_id == nodes[0].node_id
    assert detail.name == "ShippingService"


def test_get_node_detail_invalid(polyglot_provider):
    """Test fetching an invalid node ID raises KeyError."""
    with pytest.raises(KeyError):
        polyglot_provider.get_node_detail("non_existent_node_id_9999")


def test_resolve_symptom_with_message(polyglot_provider):
    """Test symptom resolution from a telemetry message."""
    event = TelemetryEvent(
        event_id="evt-001",
        service_name="frontend",
        error_type="gRPC_UNIMPLEMENTED",
        message="Failure calling ShippingService.GetQuote",
    )
    resolved = polyglot_provider.resolve_symptom(event)
    assert len(resolved) > 0
    assert any("GetQuote" in n.name or "ShippingService" in n.name for n in resolved)


def test_resolve_symptom_with_stacktrace(polyglot_provider):
    """Test symptom resolution from a stack trace string."""
    trace = """Traceback (most recent call last):
  File "order_service.py", line 15, in process_order
    res = client.GetQuote()
"""
    event = TelemetryEvent(
        event_id="evt-002",
        service_name="order_service",
        error_type="RUNTIME_ERROR",
        message="RPC call failed",
        stack_trace=trace,
    )
    resolved = polyglot_provider.resolve_symptom(event)
    assert isinstance(resolved, list)


def test_backward_traverse(polyglot_provider):
    """Test backward traversal to find ranked candidate root causes."""
    nodes = polyglot_provider.find_node_by_name("ShippingService")
    assert len(nodes) > 0
    policy = TraversalPolicy(max_depth=3, max_nodes=20)
    candidates = polyglot_provider.backward_traverse(nodes[0], policy)
    assert isinstance(candidates, list)
    for c in candidates:
        assert isinstance(c, CandidateRootCause)
        assert 0.0 <= c.confidence <= 1.0
        assert c.rank > 0
        assert isinstance(c.evidence, list)


def test_forward_traverse(polyglot_provider):
    """Test forward traversal to build blast-radius induced subgraph."""
    nodes = polyglot_provider.find_node_by_name("ShippingService")
    assert len(nodes) > 0
    policy = TraversalPolicy(max_depth=2, max_nodes=30)
    subgraph = polyglot_provider.forward_traverse(nodes[0], policy)
    assert isinstance(subgraph, InducedSubgraph)
    assert subgraph.node_count > 0
    assert isinstance(subgraph.to_prompt_context(), str)
    assert isinstance(subgraph.to_prompt_context("signatures_only"), str)
    assert isinstance(subgraph.to_prompt_context("narrative"), str)
    assert subgraph.estimated_tokens() > 0


def test_explain_path(multi_repo_provider):
    """Test causal path construction between two interconnected nodes."""
    src_node = multi_repo_provider.get_node_detail("order_service/order_service.py:App.post")
    dst_node = multi_repo_provider.get_node_detail("contract::ShippingService.GetQuote")
    path = multi_repo_provider.explain_path(src_node, dst_node)
    assert isinstance(path, CausalPath)
    assert len(path.nodes) >= 2
    narrative = path.to_narrative()
    assert "Step 1" in narrative


def test_get_contract_between(multi_repo_provider):
    """Test finding shared contracts between two microservices."""
    contracts = multi_repo_provider.get_contract_between("order_service", "shipping_service")
    assert len(contracts) > 0
    for c in contracts:
        assert isinstance(c, CodeNode)
        assert c.node_type == NodeType.CONTRACT
