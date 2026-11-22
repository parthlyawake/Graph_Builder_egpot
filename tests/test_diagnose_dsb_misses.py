from types import SimpleNamespace

import networkx as nx
import pytest

from bench import diagnose_dsb_misses as diagnosis
from eg_pot import EdgePolicy, GraphView


def test_replay_aborts_on_order_mismatch_without_requesting_trace():
    calls = []

    class Retriever:
        def retrieve(self, **request):
            calls.append(request)
            return SimpleNamespace(discovery_order=["root", "b", "a"])

    label = {"query": "toy", "start_node": "root"}
    rows = [{"id": "q1", "label": label, "returned_nodes": ["root", "a", "b"]},
            {"id": "q2", "label": label, "returned_nodes": ["root", "b", "a"]}]
    with pytest.raises(ValueError, match="q1: replay differs at returned rank 2"):
        diagnosis.verify_replays({"toy": {"rows": rows, "retriever": Retriever()}})
    assert len(calls) == 1
    assert calls[0]["trace"] is None


def test_classification_and_eligibility_on_toy_graph():
    graph = nx.MultiDiGraph()
    graph.add_node("contract", type="rpc_contract")
    graph.add_edge("root", "contract", relation="CONSUMES")
    graph.add_edge("handler", "contract", relation="IMPLEMENTS")
    graph.add_edge("service", "contract", relation="DEFINES_RPC")
    graph.add_edge("root", "excluded", relation="SEMANTIC_SIMILAR")
    view = GraphView(graph, edge_policy=EdgePolicy(frozenset({"SEMANTIC_SIMILAR"}),
                                                  frozenset({"IMPLEMENTS"}), False))
    label = {"start_node": "root", "contract_node": "contract", "handler_node": "handler"}
    walk = diagnosis.gold_walk(view, label)
    assert walk[1][0]["eligible"] and walk[1][0]["contract_match_withheld"]
    assert diagnosis.edge_options(view, "contract", "service")[0]["rule"] == (
        "incoming DEFINES_RPC at rpc_contract")
    assert diagnosis.edge_options(view, "root", "excluded")[0]["rule"] == "relation excluded"
    eligible = nx.DiGraph()
    eligible.add_nodes_from(graph)
    eligible.add_edges_from((node, neighbor) for node in graph for neighbor, *_ in view.neighbors(node))
    trace = {"rounds": [{"round": 1, "candidates": [{"to_node": "contract"}], "width_order": []}]}
    for target, expected in (("contract", "a"), ("service", "b"), ("handler", "c")):
        path = diagnosis.shortest_path(view, label, target, walk)
        assert diagnosis.classify(target, trace, eligible, "root", {"root"}, path)[0] == expected
    trace["rounds"][0]["width_order"] = [0]
    assert diagnosis.classify("contract", trace, eligible, "root", {"root"}, None)[0] == "d"


def test_retrieval_boundary_does_not_read_gold_or_any_label_metadata():
    class RestrictedLabel(dict):
        def __getitem__(self, field):
            assert field in {"query", "start_node"}
            return super().__getitem__(field)

    class Retriever:
        def retrieve(self, *, query, start_node, node_budget, trace):
            assert (query, start_node, node_budget, trace) == ("question", "root", 40, None)
            return SimpleNamespace(discovery_order=["root"])

    label = RestrictedLabel(query="question", start_node="root", gold_nodes=["secret"],
                            link_id="secret", type="indirect", handler_node="secret")
    assert diagnosis.retrieve(Retriever(), label) == ["root"]
