"""Objective and beam tests using only in-memory graphs and read-only GraphML."""

import math
from pathlib import Path

import networkx as nx
import pytest

from eg_pot import (CandidateStep, EGPOT, EGPOTConfig, PathState,
                    dominates, non_dominated_sort)


@pytest.fixture
def tiny():
    graph = nx.MultiDiGraph()
    for node in "abcdef":
        graph.add_node(node, name=f"shipping {node}", type="function")
    graph.nodes["c"]["type"] = "rpc_contract"
    for u, v, relation, layer in [
        ("a", "b", "CALLS", "Ldep"), ("b", "c", "CONSUMES", "Lcontract"),
        ("c", "d", "IMPLEMENTS", "Lcontract"), ("d", "e", "CALLS", "Ldep"),
        ("e", "f", "CALLS", "Ldep")]:
        graph.add_edge(u, v, key=0, relation=relation, layer=layer)
    return graph


def step(u="a", v="b", relation="CALLS", layer="Ldep"):
    return CandidateStep(u, v, relation, "out", 0, layer)


def root():
    return PathState(["a"], [], {"a": 0}, {}, {"a"})


def test_objectives_and_immutable_extension(tiny):
    engine = EGPOT(tiny)
    initial = root()
    first = initial.extend(step())
    assert initial == root()
    assert first.ordered_nodes == ["a", "b"]
    assert first.edges == [("a", "CALLS", "b")]
    assert first.hops_from_start == {"a": 0, "b": 1}
    assert first.relation_counts == {"CALLS": 1}
    assert first.visited == {"a", "b"}
    assert first.ordered_nodes is not initial.ordered_nodes
    assert first.edges is not initial.edges
    assert first.hops_from_start is not initial.hops_from_start
    assert first.relation_counts is not initial.relation_counts
    assert engine.hop_efficiency(2) == pytest.approx(0.64)
    assert engine.contract_consistency(step()) == 0.6
    assert engine.contract_consistency(step(v="c")) == 1.0
    assert engine.contract_consistency(step(layer="Lcontract")) == 1.0
    assert engine.semantic_relevance("shipping", "b") == engine.scorer.score("shipping", "b")
    assert engine.entropy_gain(initial, step()) == 0.0
    new_relation = step("b", "c", "CONSUMES", "Lcontract")
    gain = engine.entropy_gain(first, new_relation)
    assert gain == pytest.approx(math.log(2) / math.log(3))
    assert gain > engine.entropy_gain(first, step("b", "d")) == 0.0
    balanced = PathState(relation_counts={"CALLS": 1, "CONSUMES": 3})
    before = -(0.25 * math.log(0.25) + 0.75 * math.log(0.75))
    after = -(0.4 * math.log(0.4) + 0.6 * math.log(0.6))
    assert engine.entropy_gain(balanced, step()) == pytest.approx(
        (after - before) / math.log(3) / 2)
    for kind in ("service_contract", "http_endpoint", "topic_contract"):
        tiny.nodes["c"]["type"] = kind
        assert engine.contract_consistency(step(v="c")) == 1.0
    with pytest.raises(ValueError):
        first.extend(step())


def test_entropy_with_one_relation():
    graph = nx.MultiDiGraph()
    graph.add_edge("a", "b", relation="CALLS")
    assert EGPOT(graph).entropy_gain(root(), step()) == 0.0


def test_pareto_known_fronts_and_ties(tiny):
    vectors = [(1., 0., 1., 0.), (0., 1., 0., 1.),
               (0., 0., 0., 0.), (1., 1., 1., 1.), (1., 0., 1., 0.)]
    assert dominates(vectors[3], vectors[0])
    assert not dominates(vectors[0], vectors[1])
    assert not dominates(vectors[0], vectors[4])
    assert non_dominated_sort(vectors) == [[3], [0, 1, 4], [2]]
    assert non_dominated_sort([]) == []
    candidates = [step(v=n) for n in ("f", "b", "e", "d", "c")]
    engine = EGPOT(tiny)
    chosen = engine.select_top(candidates, vectors, 4)
    assert [s.to_node for s in chosen] == ["d", "b", "c", "f"]
    assert chosen == engine.select_top(candidates, vectors, 4)
    assert engine.select_top([], [], 2) == []
    assert engine.select_top(candidates, vectors, 0) == []


def test_weighted_sum_and_ablations(tiny):
    engine = EGPOT(tiny, EGPOTConfig(use_pareto=False, weights=(1., 0., 0., 0.)))
    candidates = [step(v="b"), step(v="c")]
    assert engine.select_top(candidates, [(1., 0., 0., 0.), (0., 1., 1., 1.)], 1) == [candidates[0]]
    assert engine.select_top(candidates[::-1], [(0.5,) * 4] * 2, 1) == [candidates[0]]
    state = root().extend(step())
    candidate = step("b", "d", "CONSUMES")
    normal = EGPOT(tiny).objective_vector("shipping", state, candidate)
    disabled = EGPOT(tiny, EGPOTConfig(use_contracts=False, use_entropy=False))
    vector = disabled.objective_vector("shipping", state, candidate)
    assert vector[:2] == normal[:2]
    assert normal[2] == 0.6 and normal[3] > 0
    assert vector[2:] == (1.0, 0.0)
    assert all(0 <= v <= 1 for v in normal + vector)


@pytest.mark.parametrize("weights", [(), (1, 0), (1, 1, 1, 1),
    (-0.1, 0.1, 0.5, 0.5), (float("nan"), 0, 0, 1),
    (float("inf"), 0, 0, 0), (True, 0, 0, 0), ("1", 0, 0, 0)])
def test_invalid_weights(weights):
    with pytest.raises(ValueError):
        EGPOTConfig(weights=weights)


def test_beam_budget_logs_dead_end_and_direction(tiny):
    engine = EGPOT(tiny, EGPOTConfig(node_budget=4, beam_width=2))
    result = engine.traverse("shipping", "a")
    assert len(result.visited) == len(result.ordered_path) == 4
    assert len(result.edges) == len(result.objective_log) == 3
    assert result == engine.traverse("shipping", "a")
    assert EGPOT(tiny, EGPOTConfig(node_budget=1)).traverse("query", "a").ordered_path == ["a"]
    assert len(EGPOT(tiny, EGPOTConfig(node_budget=20)).traverse("shipping", "a").visited) == 6
    backward = engine.traverse("shipping", "f")
    assert backward.edges[0] == ("f", "CALLS", "e")
    tiny.add_node("isolated")
    assert EGPOT(tiny).traverse("q", "isolated").ordered_path == ["isolated"]
    with pytest.raises(KeyError):
        engine.traverse("q", "missing")
    without_mcts = EGPOT(tiny, EGPOTConfig(use_mcts=False, node_budget=4, beam_width=2)).traverse("shipping", "a")
    assert without_mcts.ordered_path == result.ordered_path
    assert without_mcts.visited == result.visited


def test_union_retains_pruned_branches_and_caps_first_selection():
    graph = nx.MultiDiGraph()
    for node in ("root", "a", "b", "c", "d", "e", "f"):
        graph.add_node(node, name="shipping", type="function")
    for u, v in (("root", "a"), ("root", "b"), ("root", "c"),
                 ("b", "d"), ("b", "e"), ("b", "f")):
        graph.add_edge(u, v, relation="CALLS", layer="Ldep")
    # a is a dead end; c is pruned when all next-round slots go to b's children.
    result = EGPOT(graph, EGPOTConfig(node_budget=20, beam_width=3)).traverse("shipping", "root")
    assert result.visited == set(graph)
    assert set(result.ordered_path) < result.visited
    assert len(result.objective_log) == len(result.edges) == len(result.ordered_path) - 1
    # Round one selects a, b, c in ID order; a partial round must stop at b.
    capped = EGPOT(graph, EGPOTConfig(node_budget=3, beam_width=3)).traverse("shipping", "root")
    assert capped.visited == {"root", "a", "b"}
    assert set(capped.ordered_path) <= capped.visited
    assert capped == EGPOT(graph, EGPOTConfig(node_budget=3, beam_width=3)).traverse("shipping", "root")


def test_parallel_selections_count_unique_nodes_only():
    graph = nx.MultiDiGraph()
    for node in ("root", "a", "b"):
        graph.add_node(node, name="shipping")
    for key in range(3):
        graph.add_edge("root", "a", key=key, relation="CALLS", layer="Ldep")
    graph.add_edge("a", "b", relation="CALLS", layer="Ldep")
    result = EGPOT(graph, EGPOTConfig(node_budget=3, beam_width=3)).traverse("shipping", "root")
    assert result.visited == {"root", "a", "b"}


@pytest.fixture(scope="module")
def real_result():
    graph = nx.read_graphml(Path(__file__).resolve().parents[1] / "online_boutique_graph.graphml",
                           force_multigraph=True)
    starts = sorted(n for n, d in graph.nodes(data=True)
                    if d.get("repo") == "frontend" and d.get("type") == "function"
                    and "getCurrencies" in d.get("name", ""))
    assert starts == ["frontend/rpc.go:frontendServer.getCurrencies"]
    engine = EGPOT(graph, EGPOTConfig(node_budget=20))
    query = "which service supplies the available currency choices for display"
    first = engine.traverse(query, starts[0])
    second = engine.traverse(query, starts[0])
    return graph, first, second


def test_real_traversal_deterministic(real_result):
    _, first, second = real_result
    assert first == second
    assert len(first.visited) <= 20
    assert len(first.objective_log) == len(first.edges)


def test_real_contract_and_implementation_collected(real_result):
    _, first, _ = real_result
    targets = {"contract::CurrencyService.GetSupportedCurrencies",
               "currencyservice/server.js:getSupportedCurrencies"}
    assert targets <= first.visited
