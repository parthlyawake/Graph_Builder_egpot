"""In-memory foundation tests; the saved graph is opened read-only."""

from pathlib import Path
import random

import networkx as nx
import pytest

from eg_pot import EGPOT, EGPOTConfig, GraphView, PathResult, QueryScorer, normalize_text


@pytest.mark.parametrize("text, expected", [
    ("GetSupportedCurrencies", "get supported currency"),
    ("frontendServer.getCurrencies", "frontend server get currency"),
    ("convert_currency", "convert currency"),
    ("HTTPServer42::getCurrencies/v2.api_calls", "http server 42 get currency v 2 api call"),
    ("currencies currency choices cats bus gas", "currency currency choice cat bus gas"),
    ("", ""),
])
def test_normalize_text(text, expected):
    assert normalize_text(text) == expected
    assert normalize_text(text) == normalize_text(text)


def test_node_and_query_share_normalization():
    graph = nx.MultiDiGraph()
    graph.add_node("rpc", name="GetSupportedCurrencies")
    graph.add_node("unrelated", name="SendEmail")
    first = QueryScorer(GraphView(graph))
    second = QueryScorer(GraphView(graph))
    queries = ("GetSupportedCurrencies", "get_supported_currencies", "get supported currency")
    scores = [first.score(query, "rpc") for query in queries]
    assert scores == pytest.approx([1.0] * len(queries))
    assert first.score("currency", "rpc") > first.score("currency", "unrelated")
    for query in queries:
        values = first.score_many(query, graph.nodes)
        assert values == second.score_many(query, graph.nodes)
        assert all(0 <= value <= 1 for value in values.values())


@pytest.fixture(scope="module")
def graph():
    path = Path(__file__).resolve().parents[1] / "online_boutique_graph.graphml"
    return nx.read_graphml(path, force_multigraph=True)


def test_graphml_metadata_and_deterministic_neighbors(graph):
    view = GraphView(graph)
    assert isinstance(graph, nx.MultiDiGraph)
    for u, v, key in graph.edges(keys=True):
        meta = view.edge_meta(u, v, key)
        assert type(meta["c_type"]) is float
        assert type(meta["f_call"]) is float
        assert type(meta["d_scope"]) is int
        assert type(meta["id_ctx"]) is str
    for node in graph:
        assert view.neighbors(node) == view.neighbors(node)


def test_rpc_choke_point(graph):
    u, rpc, key = next((u, v, k) for u, v, k, d in graph.edges(keys=True, data=True)
                       if d.get("relation") == "DEFINES_RPC"
                       and graph.nodes[v].get("type") == "rpc_contract")
    blocked = GraphView(graph).neighbors(rpc)
    restored = GraphView(graph, use_choke_point=False).neighbors(rpc)
    assert (u, "DEFINES_RPC", "in", key) not in blocked
    assert (u, "DEFINES_RPC", "in", key) in restored
    assert (rpc, "DEFINES_RPC", "out", key) in GraphView(graph).neighbors(u)
    removed = set(restored) - set(blocked)
    assert removed and all(rel == "DEFINES_RPC" and direction == "in"
                           for _, rel, direction, _ in removed)


def test_metadata_strings_defaults_and_parallel_edges():
    graph = nx.MultiDiGraph()
    graph.add_node("a", type="function")
    graph.add_node("b", type="service_contract")
    graph.add_edge("a", "b", key="z", relation="CALLS",
                   c_type="0.4", f_call="3.0", d_scope="2", id_ctx=7)
    graph.add_edge("a", "b", key="a", relation="DEFINES_RPC")
    graph.add_edge("b", "a", key=1, metadata="{'c_type': 0.2, 'f_call': 4}")
    view = GraphView(graph)
    assert view.edge_meta("a", "b", "z") == {
        "c_type": 0.4, "f_call": 3.0, "d_scope": 2, "id_ctx": "7"}
    assert view.edge_meta("a", "b", "a") == {
        "c_type": 1.0, "f_call": 1.0, "d_scope": 0, "id_ctx": ""}
    assert view.edge_meta("b", "a", 1)["c_type"] == 0.2
    assert len(view.neighbors("a")) == 3
    # Incoming DEFINES_RPC is retained when the current node is not an RPC.
    assert ("a", "DEFINES_RPC", "in", "a") in view.neighbors("b")
    reordered = nx.MultiDiGraph()
    reordered.add_nodes_from(graph.nodes(data=True))
    for u, v, key, data in reversed(list(graph.edges(keys=True, data=True))):
        reordered.add_edge(u, v, key=key, **data)
    assert view.neighbors("a") == GraphView(reordered).neighbors("a")


def test_query_scorer_real_graph(graph):
    view = GraphView(graph)
    first, second = QueryScorer(view), QueryScorer(view)
    query = "where is GetSupportedCurrencies implemented"
    rpc = next(n for n in graph if view.node_type(n) == "rpc_contract"
               and graph.nodes[n].get("name") == "GetSupportedCurrencies")
    unrelated = random.Random(0).choice(sorted(
        n for n in graph if "currency" not in view.node_text(n).lower()
        and "supported" not in view.node_text(n).lower()))
    scores = first.score_many(query, graph.nodes)
    assert all(0.0 <= value <= 1.0 for value in scores.values())
    assert scores[rpc] > scores[unrelated]
    assert scores == second.score_many(query, graph.nodes)
    vector = first._query_vectors[query]
    matrix = first.matrix
    assert first.score(query, rpc) == scores[rpc]
    assert first._query_vectors[query] is vector
    assert first.matrix is matrix


def test_empty_vocabulary_and_unknown_query():
    assert QueryScorer(GraphView(nx.MultiDiGraph())).score_many("query", []) == {}
    graph = nx.MultiDiGraph()
    graph.add_node("blank", name="the and")
    assert QueryScorer(GraphView(graph)).score("query", "blank") == 0.0
    graph.add_node("code", name="shipping")
    scorer = QueryScorer(GraphView(graph))
    assert scorer.score("zzzzunknownword", "code") == 0.0
    with pytest.raises(KeyError):
        scorer.score("query", "missing")


@pytest.mark.parametrize("kwargs", [
    {"node_budget": 0}, {"node_budget": True}, {"beam_width": -1},
    {"mcts_rollouts": 1.5}, {"rollout_depth": 0}, {"hop_gamma": -0.1},
    {"hop_gamma": 1.1}, {"hop_gamma": float("nan")},
    {"contract_match_score": float("inf")}, {"contract_match_score": "1"},
    {"contract_mismatch_penalty": -1},
    {"contract_match_score": 0.2, "contract_mismatch_penalty": 0.6},
    {"seed": -1}, {"seed": False}, {"use_pareto": 1},
    {"use_entropy": None}, {"use_contracts": "yes"}, {"use_mcts": 0},
])
def test_config_validation(kwargs):
    with pytest.raises(ValueError):
        EGPOTConfig(**kwargs)


def test_defaults_result_and_single_node_traversal():
    config = EGPOTConfig()
    assert (config.node_budget, config.beam_width, config.mcts_rollouts,
            config.rollout_depth, config.hop_gamma, config.contract_match_score,
            config.contract_mismatch_penalty, config.seed) == (40, 4, 16, 3, 0.8, 1.0, 0.6, 0)
    assert all((config.use_pareto, config.use_entropy, config.use_contracts, config.use_mcts))
    result = PathResult()
    result.visited.add("a")
    assert PathResult().visited == set()
    assert result.objective_log == []
    graph = nx.MultiDiGraph()
    graph.add_node("a")
    engine = EGPOT(graph, config)
    assert engine.config is config
    traversed = engine.traverse("query", "a")
    assert traversed.ordered_path == ["a"]
    assert traversed.visited == {"a"}
    assert traversed.edges == traversed.objective_log == []
