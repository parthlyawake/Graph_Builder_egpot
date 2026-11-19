"""Synthetic tests for the post-hoc exploratory distance report."""
from copy import deepcopy

import networkx as nx
import numpy as np

from bench import analyze_dsb_distance as analysis
from bench import egpot_eval
from bench import egpot_multi_eval as locked


def toy_graph():
    graph = nx.MultiDiGraph()
    graph.add_edge("start", "contract", relation="CONSUMES")
    graph.add_edge("start", "contract", relation="PASSES_ARG")
    graph.add_edge("handler", "contract", relation="IMPLEMENTS")
    graph.add_edge("tail", "handler")
    return graph


def test_distance_reports_raw_arrows_separately_from_the_labelled_walk():
    graph = toy_graph()
    view = graph.to_undirected(as_view=True)
    facts = analysis.distance_facts(graph, view, "start", "contract", "handler")
    assert facts["undirected_hops"] == [1, 2]
    assert facts["forward_graph_hops"] == [1, None]
    assert facts["gold_structure_forward_hops"] == [1, None]
    assert facts["gold_structure_walk_hops"] == [1, 2]
    assert facts["gold_depth"] == 2
    assert facts["forward_graph_depth"] is None
    assert facts["start_degree"] == 2 and facts["start_unique_neighbors"] == 1
    assert facts["contract_degree"] == 3 and facts["contract_unique_neighbors"] == 2
    assert facts["within_two_hops"] == 3
    graph.add_edge("start", "handler", relation="SEMANTIC_SIMILAR")
    facts = analysis.distance_facts(graph, view, "start", "contract", "handler")
    assert facts["undirected_hops"] == facts["forward_graph_hops"] == [1, 1]
    assert facts["gold_depth"] == 1
    assert facts["gold_structure_walk_hops"] == [1, 2]


def test_bucket_assigns_maximum_or_unreachable():
    rows = [{"id": f"q{i}", "gold_depth": analysis.gold_depth(values)}
            for i, values in enumerate(([1, 2], [2, 2], [1, 1], [None, 1]))]
    assert [(depth, [q["id"] for q in cohort]) for depth, cohort in analysis.depth_buckets(rows)] == [
        (1, ["q2"]), (2, ["q0", "q1"]), (None, ["q3"])]


def saved_rows(label, *, rows_per_cohort=1):
    for budget in analysis.BUDGETS:
        for method in analysis.METHODS:
            visited = ["start", "contract", "handler"] if method == "ppr" else ["start", "contract", "tail"]
            for i in range(rows_per_cohort):
                query = {**label, "id": f"q{i}"}
                record = {"id": query["id"], "label": query, "method": method,
                          "node_budget": budget, "hit": int(method == "ppr"),
                          "returned_nodes": visited}
                yield {**record, "seed": 0, "experiment": "main"}
                if budget in (20, 40) and method == "egpot_full_mcts":
                    for seed in range(6):
                        yield {**record, "hit": int(seed >= 3), "seed": seed, "experiment": "seeds"}


def test_describing_gold_does_not_call_any_retrieval_method_or_change_saved_rows(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("post-hoc analysis attempted retrieval")

    for module, name in ((locked, "run_jobs"), (locked, "execute_job"), (egpot_eval, "evaluate")):
        monkeypatch.setattr(module, name, forbidden)
    for model in ("EGPOTRetriever", "VectorTopK", "BFS", "PersonalizedPageRank", "StandardMCTS"):
        monkeypatch.setattr(getattr(egpot_eval, model), "retrieve", forbidden)

    label = {"id": "q", "link_id": "toy", "type": "explicit", "start_node": "start",
             "contract_node": "contract", "handler_node": "handler", "query": "synthetic"}
    rows = list(saved_rows(label))
    original = deepcopy(rows)
    queries, misses, _ = analysis.describe_app("toy", toy_graph(), rows)
    assert rows == original
    assert queries[0]["main_hits"][40]["ppr"] == 1
    assert queries[0]["ppr_ranks"][40] == [2, 3]
    assert [(m["missing_gold_role"], m["nearest_returned_node"], m["nearest_rank"], m["nearest_hops"])
            for m in misses] == [("handler", "contract", 2, 1)]
    assert misses[0]["frontier_or_pruned"].startswith("undetermined")
    graph = toy_graph()
    graph.add_edge("start", "handler", relation="SEMANTIC_SIMILAR")
    _, root_misses, _ = analysis.describe_app("toy", graph, rows)
    assert root_misses[0]["frontier_or_pruned"] == "pruned at root"

    root_only_rows = [
        {**row, "returned_nodes": ["start"]} if row["method"] == "egpot_full" else row
        for row in rows
    ]
    _, frontier_misses, _ = analysis.describe_app("toy", toy_graph(), root_only_rows)
    assert {miss["missing_gold_role"]: miss["frontier_or_pruned"] for miss in frontier_misses} == {
        "contract": "pruned at root", "handler": "beyond returned frontier"}
    stats = analysis.bucket_statistics(queries)
    assert all(row["egpot_full_minus_ppr"] is None for row in stats)
    assert stats[2]["hits"]["egpot_full_mcts"] == {"seed_0_hits": 0, "median_hits": 0.5}


def test_bootstrap_uses_only_eligible_buckets_and_saved_seed_zero_hits(monkeypatch):
    label = {"link_id": "toy", "type": "indirect", "start_node": "start",
             "contract_node": "contract", "handler_node": "handler"}
    queries, _, _ = analysis.describe_app("toy", toy_graph(), list(saved_rows(label, rows_per_cohort=8)))
    calls = []

    def weights(starts, *, resamples, seed):
        calls.append((starts, resamples, seed))
        return np.ones((2, len(starts)), dtype=int)

    monkeypatch.setattr(analysis, "cluster_weights", weights)
    assert all(row["egpot_full_minus_ppr"] is None for row in analysis.bucket_statistics(queries[:7]))
    for row in analysis.bucket_statistics(queries):
        assert row["egpot_full_minus_ppr"] == {
            "analysis_type": "post-hoc exploratory", "difference": -1, "interval_95": [-1, -1]}
    assert calls == [([("toy", "start")] * 8, 10_000, 0)]
