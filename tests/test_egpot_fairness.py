"""Fairness variants and seed checks using in-memory graphs only."""
import networkx as nx
import pytest

from bench.egpot_eval import (CHOKE_PAIRS, STOCHASTIC_METHODS, StandardMCTS,
                             make_fairness_retrievers, matched_node_budget, main)
from eg_pot import GraphView, QueryScorer


def choke_fixture():
    graph = nx.MultiDiGraph()
    for node, name, kind in [("r", "currency target", "rpc_contract"),
                             ("a", "currency target alpha", "function"),
                             ("b", "currency target beta", "function"),
                             ("p", "parentonly", "service_contract"),
                             ("other", "postal delivery", "rpc_contract"),
                             ("q", "email sender", "function")]:
        graph.add_node(node, name=name, type=kind)
    graph.add_edge("r", "a", relation="CALLS")
    graph.add_edge("r", "b", relation="CALLS")
    graph.add_edge("p", "r", relation="DEFINES_RPC")
    graph.add_edge("p", "other", relation="DEFINES_RPC")
    graph.add_edge("p", "q", relation="DEFINES")
    view = GraphView(graph)
    return view, QueryScorer(view)


@pytest.mark.parametrize("normal,off", CHOKE_PAIRS)
def test_choke_variants_change_only_adjacency_and_affect_retrieval(normal, off):
    view, scorer = choke_fixture()
    methods = make_fairness_retrievers(view, scorer)
    assert methods[normal].graph_view.use_choke_point
    assert not methods[off].graph_view.use_choke_point
    assert methods[normal].scorer is methods[off].scorer is scorer
    assert not any(n == "p" for n, _, _, _ in methods[normal].graph_view.neighbors("r"))
    assert any(n == "p" for n, _, _, _ in methods[off].graph_view.neighbors("r"))
    query = "parentonly" if normal == "greedy_walk" else "currency target"
    budget = 3 if normal == "ppr" else 6
    a = methods[normal].retrieve(query, "r", budget)
    b = methods[off].retrieve(query, "r", budget)
    assert a.discovery_order != b.discovery_order
    repeated = methods[off].retrieve(query, "r", budget)
    assert b.discovery_order == repeated.discovery_order
    for result in (a, b):
        assert result.discovery_order[0] == "r"
        assert len(result.visited) <= budget
        assert set(result.discovery_order) == result.visited
    if normal == "ppr":
        assert methods[normal].scores("r")["p"] == pytest.approx(0, abs=1e-10)
        assert methods[off].scores("r")["p"] > 0


def test_off_variants_share_one_view_and_defaults_stay_on():
    view, scorer = choke_fixture()
    methods = make_fairness_retrievers(view, scorer)
    assert len({id(methods[off].graph_view) for _, off in CHOKE_PAIRS}) == 1
    assert view.use_choke_point and scorer.graph_view is view


def test_stochastic_seed_changes_simulations_and_reproduces_results():
    graph = nx.MultiDiGraph()
    graph.add_node("s", name="root", type="function")
    for i in range(7):
        branch = f"branch{i}"
        graph.add_node(branch, name="currency branch", type="function")
        graph.add_edge("s", branch, relation="CALLS")
        for j in range(4):
            leaf = f"leaf{i}_{j}"
            graph.add_node(leaf, name="currency rate" if j % 2 else "postal parcel", type="function")
            graph.add_edge(branch, leaf, relation="CALLS")
    view = GraphView(graph)
    scorer = QueryScorer(view)
    profiles, results = [], []
    for seed in (0, 1, 0):
        engine = StandardMCTS(view, scorer, seed=seed, query_ids={("currency", "s"): "query-id"})
        result = engine.retrieve("currency", "s", 15)
        profiles.append([(n.path, n.visits, n.reward) for n in engine.last_tree])
        results.append((result.discovery_order, result.ordered_path))
    assert profiles[0] != profiles[1]
    assert profiles[0] == profiles[2]
    assert results[0] == results[2]


def test_deterministic_methods_ignore_registry_seed_argument():
    view, scorer = choke_fixture()
    one = make_fairness_retrievers(view, scorer, seed=0)
    two = make_fairness_retrievers(view, scorer, seed=4)
    for name in one:
        if name in STOCHASTIC_METHODS or name == "mcts_standard_no_choke":
            continue
        a = one[name].retrieve("currency target", "r", 6)
        b = two[name].retrieve("currency target", "r", 6)
        assert a.visited == b.visited, name
        assert a.discovery_order == b.discovery_order, name
        assert a.ordered_path == b.ordered_path, name
    assert one["egpot_full"].config == two["egpot_full"].config
    assert two["egpot_full_mcts"].config.seed == 4
    assert two["egpot_no_pareto_mcts"].config.seed == 4
    assert two["mcts_standard"].seed == 4


@pytest.mark.parametrize("nodes,expected", [([14, 15], 14), ([15, 16], 16), ([14, 16, 15, 14], 15)])
def test_matching_budget_uses_round_mean_nodes(nodes, expected):
    records = [{"method": "egpot_full", "node_budget": 40, "nodes_returned": n} for n in nodes]
    records.extend([{"method": "bfs", "node_budget": 40, "nodes_returned": 100},
                    {"method": "egpot_full", "node_budget": 20, "nodes_returned": 1}])
    assert matched_node_budget(records) == expected


def test_matching_requires_reference_and_fairness_refuses_test_split():
    with pytest.raises(ValueError, match="budget 40"):
        matched_node_budget([])
    with pytest.raises(SystemExit):
        main(["--mode", "fairness", "--split", "test", "--confirm-test"])
