"""Measurement correctness: attributes and paired bootstrap must not be conflated."""
import networkx as nx
import pytest

from bench.analyze_paired_study import bootstrap_paired_difference
from bench.paper_performance import graph_signature, full_graph_signature, semantic_graph_signature


def test_identical_topology_with_stale_lineage_metadata_is_not_full_equivalence():
    one=nx.MultiDiGraph()
    one.add_node("a.py:f", id="a.py:f", type="function", line_end=10)
    one.add_node("b.py:g", type="function")
    one.add_edge("a.py:f","b.py:g",key="call-1",relation="CALLS",
                 layer="Ldep", metadata={"confidence":0.9})
    two=one.copy()
    two.nodes["a.py:f"]["line_end"]=11
    assert graph_signature(one)==graph_signature(two)
    assert full_graph_signature(one)!=full_graph_signature(two)
    three=one.copy()
    three.edges["a.py:f","b.py:g","call-1"]["metadata"]={"confidence":0.1}
    assert graph_signature(one)==graph_signature(three)
    assert full_graph_signature(one)!=full_graph_signature(three)


def test_paired_bootstrap_is_seeded_and_preserves_cohort_alignment():
    a=[
      {"id":"q1","ranked_ids":["target","x"],"relevant_ids":["target"]},
      {"id":"q2","ranked_ids":["irrelevant","target"],"relevant_ids":["target"]}]
    b=[
      {"id":"q1","ranked_ids":["x","target"],"relevant_ids":["target"]},
      {"id":"q2","ranked_ids":["irrelevant","z"],"relevant_ids":["target"]}]
    first=bootstrap_paired_difference(a,b,seed=42,repetitions=200)
    assert first==bootstrap_paired_difference(a,b,seed=42,repetitions=200)
    assert first["left_minus_right_mrr"]==0.5
    assert first["n_queries"]==2
    with pytest.raises(ValueError,match="cohorts differ"):
        bootstrap_paired_difference(a,b[:1])
    wrong=[dict(x) for x in b]
    wrong[0]["relevant_ids"]=["not-the-target"]
    with pytest.raises(ValueError,match="Ground truth differs"):
        bootstrap_paired_difference(a,wrong)


def test_semantic_equality_ignores_only_ephemeral_counter_keys():
    original=nx.MultiDiGraph()
    original.add_node("caller", type="function")
    original.add_node("callee", type="function")
    original.add_edge("caller","callee",key="e10",relation="CALLS",
                      layer="Ldep",id_ctx="api.py")
    same=nx.MultiDiGraph()
    same.add_nodes_from(original.nodes(data=True))
    same.add_edge("caller","callee",key="e99",relation="CALLS",
                  layer="Ldep",id_ctx="api.py")
    assert semantic_graph_signature(original)==semantic_graph_signature(same)
    stable_a=nx.MultiDiGraph()
    stable_a.add_nodes_from(original.nodes(data=True))
    stable_a.add_edge("caller","callee",key="contract:a",relation="CONSUMES",
                      layer="Lcontract",id_ctx="api.py")
    stable_b=nx.MultiDiGraph()
    stable_b.add_nodes_from(original.nodes(data=True))
    stable_b.add_edge("caller","callee",key="contract:b",relation="CONSUMES",
                      layer="Lcontract",id_ctx="api.py")
    assert semantic_graph_signature(stable_a)!=semantic_graph_signature(stable_b)
