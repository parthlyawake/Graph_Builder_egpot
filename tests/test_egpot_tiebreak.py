"""Synthetic checks for the opt-in bucketed lookahead ranking."""

from dataclasses import asdict, replace
import hashlib
from io import StringIO
import json
from pathlib import Path

import networkx as nx
import pytest

from bench import egpot_eval as ev
from eg_pot import EGPOT, EGPOTConfig


@pytest.fixture
def branching_graph():
    graph = nx.MultiDiGraph()
    graph.add_edges_from([("root", "a"), ("root", "b"), ("a", "end"),
                          ("b", "end"), ("a", "other"), ("end", "tail")],
                         relation="CALLS", layer="Ldep")
    graph.add_edge("b", "other", relation="IMPORTS", layer="Ldep")
    for node in graph:
        graph.nodes[node]["name"] = "currency handler" if node in {"a", "tail", "other"} else node
    return graph


def result_bytes(engine):
    trace = {}
    result = asdict(engine.traverse("currency", "root", trace=trace))
    result["visited"] = sorted(result["visited"])
    return json.dumps({"result": result, "trace": trace}, sort_keys=True,
                      separators=(",", ":")).encode()


def test_blend_matches_frozen_result_and_trace(branching_graph):
    settings = dict(beam_width=2, node_budget=5, seed=7)
    explicit = result_bytes(EGPOT(branching_graph, EGPOTConfig(lookahead_mode="blend", **settings)))
    assert result_bytes(EGPOT(branching_graph, EGPOTConfig(**settings))) == explicit
    # Captured on the same fixture at egpot-bench-builder-v1.
    assert hashlib.sha256(explicit).hexdigest() == (
        "274da6752a66d9d28793ace295142c14c8be2a2e6db82a2b1464818eb64b9653"
    )


@pytest.fixture
def ranked_pair(monkeypatch):
    graph = nx.MultiDiGraph()
    graph.add_edges_from([("root", "a"), ("root", "z")], relation="CALLS", layer="Ldep")

    def run(a, z, a_return, z_return, *, mode="tiebreak"):
        engine = EGPOT(graph, EGPOTConfig(lookahead_mode=mode, lookahead_weight=0,
                                          node_budget=2, beam_width=1))
        immediate = {"a": a, "z": z}
        returns = {"a": a_return, "z": z_return}
        monkeypatch.setattr(engine, "objective_vector",
                            lambda query, state, step: immediate[step.to_node])
        monkeypatch.setattr(engine, "lookahead_vector",
                            lambda query, state, step, trace=None: returns[step.to_node])
        trace = {}
        result = engine.traverse("query", "root", trace=trace)
        candidates = {row["to_node"]: row for row in trace["steps"][0]["candidates"]}
        return result, candidates, trace

    return run


def test_equal_returns_match_plain_when_immediate_means_tie(ranked_pair):
    args = ((0.25, 0.75, 0.5, 0.5), (0.75, 0.25, 0.5, 0.5), (0.4,) * 4, (0.4,) * 4)
    tiebreak, _, tiebreak_trace = ranked_pair(*args)
    plain, _, plain_trace = ranked_pair(*args, mode="blend")
    assert tiebreak == plain
    assert tiebreak_trace == plain_trace
    assert tiebreak.visited_order == ["root", "a"]


def test_higher_bucket_beats_larger_rollout_on_same_front(ranked_pair):
    result, rows, _ = ranked_pair((0.5, 0.4, 0.5, 0.5), (0.4, 0.7, 0.5, 0.5), (1.,) * 4, (0.,) * 4)
    assert rows["a"]["front_index"] == rows["z"]["front_index"] == 0
    assert result.visited_order == ["root", "z"]


def test_same_bucket_orders_by_mean_rollout(ranked_pair):
    a, z = (0.51, 0.5, 0.5, 0.5), (0.5, 0.52, 0.5, 0.5)
    a_return, z_return = (1., 0., 0., 0.), (0., 1., 1., 1.)
    result, rows, _ = ranked_pair(a, z, a_return, z_return)
    assert result.visited_order == ["root", "z"]
    assert rows["z"]["lookahead_vector"] == list(z_return)
    assert rows["z"]["final_vector"] == rows["z"]["immediate_vector"] == list(z)
    result, _, _ = ranked_pair(a, z, z_return, a_return)
    assert result.visited_order == ["root", "a"]


def test_same_bucket_and_equal_rollouts_match_plain_at_different_means(ranked_pair):
    args = ((0.51, 0.5, 0.5, 0.5), (0.5, 0.52, 0.5, 0.5), (0.,) * 4, (0.,) * 4)
    tiebreak, rows, tiebreak_trace = ranked_pair(*args)
    plain, _, plain_trace = ranked_pair(*args, mode="blend")
    assert rows["a"]["front_index"] == rows["z"]["front_index"] == 0
    assert tiebreak == plain
    assert tiebreak_trace == plain_trace
    assert tiebreak.visited_order == ["root", "z"]


def test_within_bucket_rollout_beats_exact_mean_and_node_id(ranked_pair):
    args = ((0.5, 0.53, 0.5, 0.5), (0.51, 0.5, 0.5, 0.5), (0.2,) * 4, (0.8,) * 4)
    tiebreak, rows, _ = ranked_pair(*args)
    plain, _, _ = ranked_pair(*args, mode="blend")
    assert rows["a"]["front_index"] == rows["z"]["front_index"] == 0
    assert plain.visited_order == ["root", "a"]
    assert tiebreak.visited_order == ["root", "z"]


@pytest.mark.parametrize("a_return,z_return", [((1.,) * 4, (0.,) * 4), ((0.,) * 4, (1.,) * 4)])
def test_rollouts_cannot_move_candidates_between_fronts(ranked_pair, a_return, z_return):
    result, rows, _ = ranked_pair((0.5,) * 4, (0.503,) * 4, a_return, z_return)
    assert {node: row["front_index"] for node, row in rows.items()} == {"a": 1, "z": 0}
    assert result.visited_order == ["root", "z"]


def test_seeded_tiebreak_result_and_trace_are_deterministic(branching_graph):
    config = EGPOTConfig(lookahead_mode="tiebreak", seed=7, node_budget=5, beam_width=2)
    first = result_bytes(EGPOT(branching_graph, config))
    assert first == result_bytes(EGPOT(branching_graph, config))
    candidates = json.loads(first)["trace"]["steps"][0]["candidates"]
    assert all(row["rollouts"]["count"] == 16 for row in candidates)
    assert any(any(row["lookahead_vector"]) for row in candidates)


def test_equal_returns_match_plain_over_multiple_rounds(branching_graph, monkeypatch):
    config = EGPOTConfig(node_budget=5, beam_width=2, lookahead_weight=0)
    tiebreak = EGPOT(branching_graph, replace(config, lookahead_mode="tiebreak"))
    monkeypatch.setattr(tiebreak, "lookahead_vector",
                        lambda query, state, step, trace=None: (0.5,) * 4)
    assert result_bytes(tiebreak) == result_bytes(EGPOT(branching_graph, config))


def test_comparison_cli_opts_in_at_both_budgets(branching_graph, monkeypatch, capsys):
    rows = [
        {"id": f"{link}_{kind}", "link_id": link, "type": kind, "query": "currency",
         "start_node": "root", "gold_nodes": ["a"], "gold_path": ["root", "a"]}
        for link in range(1, 16) for kind in ("explicit", "indirect")
    ]
    monkeypatch.setattr(nx, "read_graphml", lambda *args, **kwargs: branching_graph)
    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: StringIO(json.dumps(rows)))
    view = ev.GraphView(branching_graph)
    assert ev.TIEBREAK_METHOD not in ev.make_comparison_retrievers(view, ev.QueryScorer(view))
    assert ev.main(["--mode", "comparison", "--methods", ev.TIEBREAK_METHOD]) == 0
    output = capsys.readouterr().out
    for budget in (20, 40):
        assert f"RUN method={ev.TIEBREAK_METHOD} budget={budget} queries=16" in output
    assert "RUN method=egpot_full_mcts" not in output


def test_tiebreak_refuses_test_split_before_loading(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("Held-out inputs were accessed")

    monkeypatch.setattr(nx, "read_graphml", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    with pytest.raises(SystemExit) as exc:
        ev.main(["--mode", "comparison", "--methods", ev.TIEBREAK_METHOD,
                 "--split", "test", "--confirm-test"])
    assert exc.value.code == 2
    assert f"{ev.TIEBREAK_METHOD} is DEV only" in capsys.readouterr().err


def test_rejects_unknown_lookahead_mode():
    with pytest.raises(ValueError, match="lookahead_mode"):
        EGPOTConfig(lookahead_mode="other")
