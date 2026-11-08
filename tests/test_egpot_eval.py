"""In-memory evaluation tests; no fixture or result files are written."""

import hashlib
import inspect

import networkx as nx
import pytest

from bench.egpot_eval import (BFS, EGPOTRetriever, GreedyWalk, RetrievalResult,
                             VectorTopK, evaluate, main, make_retrievers, metrics,
                             ordered_path_match, split_by_link, nodes_to_hit, summarize,
                             ablation_configs, make_ablations, run_budget_sweep, FULL_MCTS, FULL_PLAIN)
from eg_pot import EGPOT, EGPOTConfig, GraphView, QueryScorer


def test_exact_metrics_no_substring_or_alternative_credit():
    result = RetrievalResult({"start", "gold:suffix", "alternative"}, ["start", "gold:suffix"],
                             0.125, ["start", "gold:suffix", "alternative"])
    values = metrics(result, ["gold"], ["start", "gold"])
    assert values == {"gold_recall": 0., "precision": 0., "hit": 0,
                      "path_coverage": 0.5, "ordered_path_match": 0,
                      "nodes_returned": 3, "latency_s": 0.125,
                      "nodes_to_hit": None, "precision_at_hit": None}
    partial = metrics(RetrievalResult({"a", "x"}, ["a", "x"], 0., ["a", "x"]), ["a", "b"], ["s", "a", "b"])
    assert partial["gold_recall"] == 0.5 and partial["precision"] == 0.5
    assert partial["path_coverage"] == pytest.approx(1 / 3)
    assert partial["hit"] == 0


def test_path_coverage_separate_from_ordered_match():
    result = RetrievalResult({"s", "c", "h"}, ["s", "h", "c"], 0., ["s", "h", "c"])
    values = metrics(result, ["c", "h"], ["s", "c", "h"])
    assert values["gold_recall"] == values["hit"] == values["path_coverage"] == 1
    assert values["precision"] == pytest.approx(2 / 3)  # start is returned, but is not gold
    assert values["ordered_path_match"] == 0
    assert ordered_path_match(["s", "noise", "c", "extra", "h"], ["s", "c", "h"]) == 1
    assert ordered_path_match(["s", "c"], ["s", "c", "h"]) == 0


def test_empty_visited_and_invalid_gold():
    assert metrics(RetrievalResult(set(), [], 0., []), ["a"], ["a"])["precision"] == 0
    with pytest.raises(ValueError):
        metrics(RetrievalResult(set(), [], 0., []), [], ["a"])


def labels():
    return [{"id": f"ob{link:02d}_{kind}", "link_id": link, "type": kind,
             "query": "currency", "start_node": "s", "gold_nodes": ["c", "h"],
             "gold_path": ["s", "c", "h"], "accepted_alternatives": ["alternative"]}
            for link in range(1, 16) for kind in ("explicit", "indirect")]


def test_split_deterministic_disjoint_and_link_paired():
    rows = labels()
    splits = split_by_link(rows)
    dev = {r["link_id"] for r in splits["dev"]}
    test = {r["link_id"] for r in splits["test"]}
    ranked = sorted(range(1, 16), key=lambda n: hashlib.sha256(str(n).encode()).hexdigest())
    assert dev == set(ranked[::2]) and test == set(ranked[1::2])
    assert len(dev) == 8 and len(test) == 7
    assert not dev & test and dev | test == set(range(1, 16))
    assert len(splits["dev"]) == 16 and len(splits["test"]) == 14
    reversed_splits = split_by_link(rows[::-1])
    for split in splits:
        assert {r["id"] for r in splits[split]} == {r["id"] for r in reversed_splits[split]}
        for link in {r["link_id"] for r in splits[split]}:
            assert {r["type"] for r in splits[split] if r["link_id"] == link} == {"explicit", "indirect"}


@pytest.fixture
def shared():
    graph = nx.MultiDiGraph()
    for node, kind in (("s", "function"), ("c", "rpc_contract"), ("h", "function"),
                       ("parent", "service_contract"), ("x", "function")):
        graph.add_node(node, name="currency" if node != "s" else "start", type=kind)
    graph.add_edge("s", "c", relation="CONSUMES", layer="Lcontract")
    graph.add_edge("h", "c", relation="IMPLEMENTS", layer="Lcontract")
    graph.add_edge("parent", "c", relation="DEFINES_RPC", layer="Lcontract")
    graph.add_edge("h", "x", relation="CALLS", layer="Ldep")
    view = GraphView(graph)
    return view, QueryScorer(view)


@pytest.mark.parametrize("budget", [1, 2, 3, 20])
def test_retrievers_share_scorer_respect_budget_and_repeat(shared, budget):
    view, scorer = shared
    for retriever in make_retrievers(view, scorer).values():
        assert retriever.scorer is scorer and retriever.graph_view is view
        first = retriever.retrieve("currency", "s", budget)
        second = retriever.retrieve("currency", "s", budget)
        assert first.visited == second.visited and first.ordered_path == second.ordered_path
        assert first.discovery_order == second.discovery_order
        assert set(first.discovery_order) == first.visited
        assert len(first.discovery_order) == len(first.visited)
        if not isinstance(retriever, VectorTopK):
            assert first.discovery_order[0] == "s"
        assert "s" in first.visited and len(first.visited) <= budget
        assert set(first.ordered_path) <= first.visited
        assert first.latency_s >= 0
        if budget == 1:
            assert first.visited == {"s"}
    for cls in (EGPOTRetriever, VectorTopK, BFS, GreedyWalk):
        assert not any(name.startswith("gold") for name in inspect.signature(cls.retrieve).parameters)


def test_no_extra_scorer_fit_when_building_retrievers(shared, monkeypatch):
    view, scorer = shared

    def forbidden(*args, **kwargs):
        raise AssertionError("QueryScorer must be fitted only once")

    monkeypatch.setattr(QueryScorer, "__init__", forbidden)
    methods = make_retrievers(view, scorer)
    for method in methods.values():
        method.retrieve("currency", "s", 3)


def test_graph_methods_obey_rpc_choke_point(shared):
    view, scorer = shared
    assert ("parent", "DEFINES_RPC", "in", 0) not in view.neighbors("c")
    for name, method in make_retrievers(view, scorer).items():
        if name != "VectorTopK":
            assert "parent" not in method.retrieve("currency", "c", 20).visited


def test_harness_passes_identical_starts_and_no_gold_fields():
    calls = []

    class Spy:
        def retrieve(self, query, start_node, node_budget):
            calls.append((query, start_node, node_budget))
            return RetrievalResult({start_node}, [start_node], 0., [start_node])

    row = labels()[0]
    records = evaluate([row], {"one": Spy(), "two": Spy()}, 2)
    assert calls == [("currency", "s", 2)] * 2
    assert all(r["gold_recall"] == 0 for r in records)


def test_harness_rejects_missing_start_or_excess_budget():
    class Bad:
        def retrieve(self, query, start_node, node_budget):
            return RetrievalResult({"c", "h"}, ["c", "h"], 0., ["c", "h"])

    with pytest.raises(ValueError, match="start-node/budget"):
        evaluate(labels()[:1], {"bad": Bad()}, 1)


def test_test_split_guard_runs_before_reading_files(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("guard must precede graph loading")

    monkeypatch.setattr(nx, "read_graphml", forbidden)
    with pytest.raises(SystemExit) as error:
        main(["--split", "test"])
    assert error.value.code == 2
    assert "requires --confirm-test" in capsys.readouterr().err
    # Confirmation passes the guard. Stop at the loader to avoid test evaluation.
    with pytest.raises(AssertionError, match="guard must precede"):
        main(["--split", "test", "--confirm-test"])


def test_invalid_budget_and_disabled_choke_point(shared):
    view, scorer = shared
    with pytest.raises(ValueError):
        BFS(view, scorer).retrieve("query", "s", 0)
    with pytest.raises(KeyError):
        BFS(view, scorer).retrieve("query", "missing", 1)
    disabled = GraphView(view.graph, use_choke_point=False)
    with pytest.raises(ValueError, match="choke-point"):
        BFS(disabled, QueryScorer(disabled))


def test_nodes_to_hit_and_size_fair_precision():
    order = ["s", "x", "gold1", "a", "b", "c", "gold2", "tail"]
    assert nodes_to_hit(order, ["gold1", "gold2"]) == 7
    assert nodes_to_hit(order, ["gold2", "gold1"]) == 7
    assert nodes_to_hit(order, ["gold1", "missing"]) is None
    assert nodes_to_hit(["gold1-lookalike"], ["gold1"]) is None
    values = metrics(RetrievalResult(set(order), order, 0., order),
                     ["gold1", "gold2"], ["s", "gold1", "gold2"])
    assert values["nodes_to_hit"] == 7
    assert values["precision_at_hit"] == pytest.approx(2 / 7)
    miss = metrics(RetrievalResult({"s"}, ["s"], 0., ["s"]),
                   ["gold1", "gold2"], ["s", "gold1", "gold2"])
    summary = summarize([values, miss])
    assert summary["hit_count"] == 1
    assert summary["nodes_to_hit"] == 7
    assert summary["precision_at_hit"] == pytest.approx(2 / 7)
    assert summarize([miss])["nodes_to_hit"] is None
    assert summarize([miss])["precision_at_hit"] is None


@pytest.mark.parametrize("mcts", [False, True])
def test_egpot_exposes_existing_selection_order(shared, mcts):
    view, _ = shared
    engine = EGPOT(view.graph, EGPOTConfig(use_mcts=mcts, node_budget=3))
    result = engine.traverse("currency", "s")
    assert result.visited_order[0] == "s"
    assert set(result.visited_order) == result.visited
    assert len(result.visited_order) == len(result.visited)
    assert result.visited_order == engine.traverse("currency", "s").visited_order


def test_vector_discovery_is_ranked_including_forced_start(shared):
    view, scorer = shared
    result = VectorTopK(view, scorer).retrieve("currency", "s", 3)
    assert result.discovery_order[-1] == "s"
    assert set(result.discovery_order) == result.visited
    scores = scorer.score_many("currency", result.visited)
    assert result.discovery_order == sorted(result.visited, key=lambda n: (-scores[n], n))


def test_ablation_configs_are_distinct_and_share_fitted_scorer(shared):
    specs = ablation_configs()
    assert len(specs) == 10
    assert specs[FULL_PLAIN].config.use_mcts is False
    assert specs[FULL_MCTS].config.use_mcts is True
    assert sum("no_mcts_rollout" in name for name in specs) == 1
    for suffix, mcts in (("no MCTS", False), ("MCTS", True)):
        for component in ("pareto", "entropy", "contracts"):
            spec = specs[f"no_{component}({suffix})"]
            assert not getattr(spec.config, f"use_{component}")
            assert spec.config.use_mcts == mcts and spec.config.seed == 0
            assert spec.config != specs[FULL_MCTS if mcts else FULL_PLAIN].config
        assert specs[f"no_choke_point({suffix})"].use_choke_point is False
    view, scorer = shared
    for name, method in make_ablations(view, scorer).items():
        assert method.scorer is scorer
        assert method.graph_view.graph is view.graph
        assert method.graph_view.use_choke_point == specs[name].use_choke_point


def test_budget_sweep_respects_all_budgets(shared):
    view, scorer = shared
    all_methods = make_ablations(view, scorer)
    methods = {FULL_PLAIN: all_methods[FULL_PLAIN], FULL_MCTS: all_methods[FULL_MCTS],
               "VectorTopK": VectorTopK(view, scorer), "BFS": BFS(view, scorer)}
    records = run_budget_sweep(labels()[:2], methods, budgets=(20, 40, 60, 100, 200))
    assert len(records) == 2 * 4 * 5
    assert all(r["nodes_returned"] <= r["node_budget"] for r in records)


def test_sweep_mcts_200_guard_uses_measured_prior_timings(shared):
    view, scorer = shared
    method = make_ablations(view, scorer)[FULL_MCTS]
    rows = labels()[:1]
    cached = {(FULL_MCTS, 100): [{"id": "x", "method": FULL_MCTS, "node_budget": 100,
                                "latency_s": 500.0}]}
    results = run_budget_sweep(rows, {FULL_MCTS: method}, cached=cached, budgets=(100, 200))
    assert len(results) == 1 and results[0]["node_budget"] == 100
