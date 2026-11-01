"""
Acceptance regression tests for Group 3 defect report (D1 - D7).
Validates symptom resolution, backward traversal candidate ranking,
test node filtering, path explanation, and strict node detail lookups.
"""

from __future__ import annotations

import os
import tempfile
import textwrap
from pathlib import Path
import pytest

from contracts.sckg_provider import SCKGGraphProvider
from contracts.graph_types import TelemetryEvent, TraversalPolicy


@pytest.fixture(scope="module")
def shop_fixture():
    files = {
        "discounts.py": 'def discount_rate(customer):\n    return 0.1 if customer == "vip" else 0.0\n',
        "pricing.py": (
            "from discounts import discount_rate\n\n\n"
            "def compute_total(prices, customer):\n"
            "    subtotal = sum(prices)\n"
            "    return round(subtotal * (1 + discount_rate(customer)), 2)\n"
        ),
        "test_pricing.py": (
            "from pricing import compute_total\n\n\n"
            "def test_vip_total():\n"
            '    assert compute_total([10, 20], "vip") == 27.0\n\n\n'
            "def test_regular_total():\n"
            '    assert compute_total([10, 20], "regular") == 30.0\n'
        ),
    }
    tmp = Path(tempfile.mkdtemp())
    (tmp / "shop").mkdir()
    for name, text in files.items():
        (tmp / "shop" / name).write_text(text, encoding="utf-8", newline="\n")
    (tmp / "workspace.yaml").write_text(
        textwrap.dedent("""\
        name: "repro"
        version: "1.0"
        repositories:
          - id: "shop"
            path: "./shop"
        """),
        encoding="utf-8",
    )
    provider = SCKGGraphProvider(str(tmp / "workspace.yaml"))
    return provider


def test_d5_resolve_symptom_exact_function(shop_fixture):
    """D5: resolve_symptom returns exactly one node, shop/pricing.py:compute_total."""
    event = TelemetryEvent(
        service_name="shop",
        message="AssertionError: assert 33.0 == 27.0",
        stack_trace='File "pricing.py", line 6, in compute_total',
    )
    symptoms = shop_fixture.resolve_symptom(event)
    assert len(symptoms) == 1
    assert symptoms[0].node_id == "shop/pricing.py:compute_total"


def test_d1_d2_backward_traverse_candidates(shop_fixture):
    """D1 & D2: backward_traverse returns compute_total first (conf 1.0), with discount_rate next."""
    event = TelemetryEvent(
        service_name="shop",
        message="AssertionError: assert 33.0 == 27.0",
        stack_trace='File "pricing.py", line 6, in compute_total',
    )
    symptoms = shop_fixture.resolve_symptom(event)
    candidates = shop_fixture.backward_traverse(symptoms[0], TraversalPolicy())
    assert len(candidates) >= 2
    assert candidates[0].node.node_id == "shop/pricing.py:compute_total"
    assert candidates[0].confidence == 1.0
    assert candidates[1].node.node_id == "shop/discounts.py:discount_rate"
    assert candidates[1].confidence == 0.9


def test_d3_no_tests_or_container_nodes_in_candidates(shop_fixture):
    """D3: No candidate is from test_pricing.py, and none has type file, module, variable, or return."""
    event = TelemetryEvent(
        service_name="shop",
        message="AssertionError: assert 33.0 == 27.0",
        stack_trace='File "pricing.py", line 6, in compute_total',
    )
    symptoms = shop_fixture.resolve_symptom(event)
    candidates = shop_fixture.backward_traverse(symptoms[0], TraversalPolicy())
    for c in candidates:
        assert "test_pricing.py" not in (c.node.file_path or "")
        assert c.node.metadata.get("raw_type") not in ("file", "module", "variable", "return")


def test_d4_deterministic_ranking(shop_fixture):
    """D4: Multiple runs produce identical candidate ranking."""
    event = TelemetryEvent(
        service_name="shop",
        message="AssertionError: assert 33.0 == 27.0",
        stack_trace='File "pricing.py", line 6, in compute_total',
    )
    symptoms = shop_fixture.resolve_symptom(event)
    run1 = shop_fixture.backward_traverse(symptoms[0], TraversalPolicy())
    run2 = shop_fixture.backward_traverse(symptoms[0], TraversalPolicy())
    assert [c.node.node_id for c in run1] == [c.node.node_id for c in run2]
    assert [c.confidence for c in run1] == [c.confidence for c in run2]


def test_d6_explain_path_relation_preservation(shop_fixture):
    """D6: explain_path returns compute_total --[CALLS]--> discount_rate with raw_relation=CALLS."""
    event = TelemetryEvent(
        service_name="shop",
        message="AssertionError: assert 33.0 == 27.0",
        stack_trace='File "pricing.py", line 6, in compute_total',
    )
    symptoms = shop_fixture.resolve_symptom(event)
    candidates = shop_fixture.backward_traverse(symptoms[0], TraversalPolicy())
    fn = symptoms[0]
    discount_node = candidates[1].node
    path = shop_fixture.explain_path(fn, discount_node)
    assert len(path.edges) == 1
    edge = path.edges[0]
    assert edge.source_id == "shop/pricing.py:compute_total"
    assert edge.target_id == "shop/discounts.py:discount_rate"
    assert edge.edge_type.value == "calls"
    assert edge.metadata.get("raw_relation") == "CALLS"


def test_d7_get_node_detail_exact_id_only():
    """D7: get_node_detail accepts exact IDs only and raises KeyError on fuzzy names."""
    target = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "examples",
        "multi_repo_system",
        "workspace.yaml",
    )
    multi_p = SCKGGraphProvider(target)
    with pytest.raises(KeyError):
        multi_p.get_node_detail("process")
