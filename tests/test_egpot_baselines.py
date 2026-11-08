"""In-memory baseline checks; no benchmark/result files are written."""
import inspect

import networkx as nx
import pytest

from bench.egpot_eval import (CommunityGraphRAG, PersonalizedPageRank, ScalarBeam,
                             StandardMCTS, VectorBFS, NEW_BASELINES,
                             make_comparison_retrievers, main)
from eg_pot import GraphView, QueryScorer


def fixture():
    graph = nx.MultiDiGraph()
    for node, name in [("s", "client"), ("a", "currency exchange"), ("b", "postal parcel"),
                       ("c", "currency conversion"), ("d", "currency rate"), ("e", "email sender"),
                       ("f", "payment card"), ("g", "warehouse product")]:
        graph.add_node(node, type="function", name=name)
    for u, v in [("s", "a"), ("s", "b"), ("a", "c"), ("c", "d"),
                 ("d", "e"), ("e", "f"), ("f", "g")]:
        graph.add_edge(u, v, relation="CALLS", layer="Ldep")
    view = GraphView(graph)
    return graph, view, QueryScorer(view)


def build(name, view, scorer):
    if name.startswith("vector_bfs_k"):
        return VectorBFS(view, scorer, int(name[-1]))
    return {"ppr": PersonalizedPageRank, "scalar_beam": ScalarBeam,
            "community_graphrag": CommunityGraphRAG, "mcts_standard": StandardMCTS}[name](view, scorer)


@pytest.mark.parametrize("method", NEW_BASELINES)
@pytest.mark.parametrize("budget", [1, 4, 20])
def test_budget_start_discovery_determinism_and_no_gold(method, budget):
    graph, view, scorer = fixture()
    retriever = build(method, view, scorer)
    first = retriever.retrieve("currency", "s", budget)
    second = retriever.retrieve("currency", "s", budget)
    assert first.visited == second.visited
    assert first.ordered_path == second.ordered_path
    assert first.discovery_order == second.discovery_order
    assert first.edges == second.edges
    assert 1 <= len(first.visited) <= budget
    assert first.discovery_order[0] == "s"
    assert set(first.discovery_order) == first.visited
    assert len(first.discovery_order) == len(first.visited)
    assert first.visited <= set(graph)
    assert set(first.ordered_path) <= first.visited
    assert not any(name.startswith("gold") for name in inspect.signature(retriever.retrieve).parameters)


def test_vector_bfs_depth_sets_are_nested_before_budget_exhaustion():
    graph, view, scorer = fixture()
    previous = set()
    for k in (2, 3, 4, 5):
        result = VectorBFS(view, scorer, k).retrieve("currency", "s", 100)
        assert previous <= result.visited
        assert len(result.visited) < 100
        previous = result.visited
    scores = scorer.score_many("currency", scorer.node_ids)
    seeds = list(dict.fromkeys(["s", *sorted(scores, key=lambda n: (-scores[n], str(n)))[:3]]))
    result = VectorBFS(view, scorer, 2).retrieve("currency", "s", 100)
    assert result.discovery_order[:len(seeds)] == seeds
    expected = set(seeds)
    frontier = set(seeds)
    for _ in range(2):
        frontier = {v for u in frontier for v, _, _, _ in view.neighbors(u)} - expected
        expected |= frontier
    assert result.visited == expected


def test_ppr_probability_mass_and_choke_point():
    graph, view, scorer = fixture()
    ppr = PersonalizedPageRank(view, scorer)
    scores = ppr.scores("s")
    assert all(score >= 0 for score in scores.values())
    assert sum(scores.values()) == pytest.approx(1.0)
    assert ppr.retrieve("ignored", "s", 4).discovery_order[0] == "s"
    assert ppr.retrieve("different ignored query", "s", 4).discovery_order == ppr.retrieve("", "s", 4).discovery_order
    graph.add_node("service", name="service", type="service_contract")
    graph.add_node("rpc", name="rpc", type="rpc_contract")
    graph.add_edge("service", "rpc", relation="DEFINES_RPC")
    new_view = GraphView(graph)
    moves = PersonalizedPageRank(new_view, QueryScorer(new_view)).move_graph
    assert moves.has_edge("service", "rpc")
    assert not moves.has_edge("rpc", "service")


def test_community_missing_louvain_fails_even_if_cached(monkeypatch):
    _, view, scorer = fixture()
    CommunityGraphRAG(view, scorer)
    monkeypatch.setattr(nx.community, "louvain_communities", None)
    with pytest.raises(ImportError, match="louvain"):
        CommunityGraphRAG(view, scorer)


def test_community_partition_reproducible_and_cached(monkeypatch):
    _, view, scorer = fixture()
    first = CommunityGraphRAG(view, scorer)
    original = nx.community.louvain_communities
    calls = []
    def wrapped(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)
    monkeypatch.setattr(nx.community, "louvain_communities", wrapped)
    second = CommunityGraphRAG(view, scorer)
    assert first.partition == second.partition
    assert not calls
    # A separate graph forces an independent seeded partition computation.
    copied = GraphView(view.graph.copy())
    third = CommunityGraphRAG(copied, QueryScorer(copied))
    assert third.partition == first.partition
    assert calls[0]["seed"] == 0
    assert calls[0]["resolution"] == 1.0


def test_scalar_beam_best_path_prefers_relevance():
    graph = nx.MultiDiGraph()
    for node, name in [("s", "client"), ("a", "postal parcel"), ("z", "currency exchange")]:
        graph.add_node(node, name=name, type="function")
    graph.add_edge("s", "a", relation="CALLS")
    graph.add_edge("s", "z", relation="CALLS")
    view = GraphView(graph)
    result = ScalarBeam(view, QueryScorer(view)).retrieve("currency", "s", 2)
    assert result.ordered_path == ["s", "z"]
    assert result.visited == {"s", "z"}


def test_mcts_query_id_seed_and_tree_are_deterministic():
    graph, view, scorer = fixture()
    one = StandardMCTS(view, scorer, query_ids={("currency", "s"): "q1"})
    two = StandardMCTS(view, scorer, query_ids={("currency", "s"): "q1"})
    a = one.retrieve("currency", "s", 100)
    b = two.retrieve("currency", "s", 100)
    assert a.discovery_order == b.discovery_order
    assert one.last_tree[0].visits == 300
    assert len(one.last_tree) <= 301
    assert [(n.node, n.path, n.visits, n.reward) for n in one.last_tree] == [
        (n.node, n.path, n.visits, n.reward) for n in two.last_tree]
    assert all(n.node in graph and set(n.path) <= set(graph) for n in one.last_tree)
    assert all(len(n.path) == len(set(n.path)) for n in one.last_tree)
    assert a.visited == {n.node for n in one.last_tree}


def test_registry_and_test_split_guard():
    _, view, scorer = fixture()
    registry = make_comparison_retrievers(view, scorer)
    assert set(NEW_BASELINES) <= set(registry)
    assert len(registry) == 14
    with pytest.raises(SystemExit):
        main(["--mode", "comparison", "--split", "test"])
