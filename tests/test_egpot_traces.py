"""Trace non-interference, schema integrity and deterministic export regressions."""

import json
from pathlib import Path

import networkx as nx
import pytest

from bench.egpot_eval import BFS, GreedyWalk, VectorTopK, make_ablations, split_by_link
from bench.export_traces import build_export, json_bytes, main, write_export
from eg_pot import EGPOT, EGPOTConfig, GraphView, QueryScorer


ROOT = Path(__file__).resolve().parents[1]
METHOD_NAMES = tuple(make for make in (
    "full(no MCTS/no_mcts_rollout)", "no_pareto(no MCTS)", "no_entropy(no MCTS)",
    "no_contracts(no MCTS)", "no_choke_point(no MCTS)", "full(MCTS)",
    "no_pareto(MCTS)", "no_entropy(MCTS)", "no_contracts(MCTS)", "no_choke_point(MCTS)",
    "VectorTopK", "BFS", "GreedyWalk"))


def no_gold_fields(value):
    if isinstance(value, dict):
        assert all(not key.startswith("gold") and key != "accepted_alternatives" for key in value)
        for item in value.values():
            no_gold_fields(item)
    elif isinstance(value, list):
        for item in value:
            no_gold_fields(item)


def validate_steps(trace, result, budget):
    assert trace["final"]["visited_order"] == result.discovery_order
    assert trace["final"]["ordered_path"] == result.ordered_path
    assert trace["final"]["edges"] == [list(edge) for edge in result.edges]
    previous = 1
    for step in trace["steps"]:
        if step["kind"] != "egpot_round":
            continue
        assert previous <= step["collected_size_after"] <= budget
        previous = step["collected_size_after"]
        candidates = step["candidates"]
        assert len(candidates) <= 60
        assert step["candidates_total"] - step["candidates_truncated"] == len(candidates)
        indices = set(range(len(candidates)))
        assert {row["idx"] for row in candidates} == indices
        assert set(step["selected"]) <= indices
        assert set(step["selected"]) == {row["idx"] for row in candidates if row["selected"]}
        flattened = [idx for front in step["fronts"] for idx in front]
        assert sorted(flattened) == sorted(indices)
        for row in candidates:
            assert row["idx"] in step["fronts"][row["front_index"]]
            if row["selected"]:
                assert row["to_node"] in result.visited
            for name in ("immediate_vector", "lookahead_vector", "final_vector"):
                vector = row[name]
                if vector is not None:
                    assert len(vector) == 4 and all(0 <= x <= 1 for x in vector)
            rollouts = row["rollouts"]
            if rollouts is not None:
                assert len(rollouts["samples"]) == min(3, rollouts["count"])
                for sample in rollouts["samples"]:
                    assert sample["nodes"][0] == row["to_node"]
                    assert len(sample["return_vector"]) == 4
                    assert all(0 <= x <= 1 for x in sample["return_vector"])
    if trace["steps"] and trace["steps"][0]["kind"] == "egpot_round":
        assert trace["steps"][-1]["kind"] == "stop"
        assert trace["steps"][-1]["reason"] in {"budget", "beam_exhausted", "no_candidates"}
    no_gold_fields(trace)
    json.loads(json.dumps(trace, allow_nan=False))


@pytest.fixture(scope="module")
def real():
    graph = nx.read_graphml(ROOT / "bench/results/online_boutique_graph_fresh.graphml", force_multigraph=True)
    rows = json.loads((ROOT / "bench/labels/online_boutique_egpot_queries.json").read_text(encoding="utf-8"))
    wanted = {"ob01_explicit", "ob04_indirect", "ob05_explicit", "ob09_indirect", "ob11_explicit", "ob13_indirect"}
    tasks = [r for r in split_by_link(rows)["dev"] if r["id"] in wanted]
    assert len(tasks) == 6
    view = GraphView(graph)
    scorer = QueryScorer(view)
    methods = make_ablations(view, scorer)
    methods.update(VectorTopK=VectorTopK(view, scorer), BFS=BFS(view, scorer), GreedyWalk=GreedyWalk(view, scorer))
    return graph, rows, tasks, methods


@pytest.mark.parametrize("method", METHOD_NAMES)
def test_trace_never_changes_results_on_six_dev_queries(real, method):
    _, _, tasks, methods = real
    for row in tasks:
        retriever = methods[method]
        plain = retriever.retrieve(row["query"], row["start_node"], 20)
        trace = {}
        traced = retriever.retrieve(row["query"], row["start_node"], 20, trace=trace)
        assert plain.visited == traced.visited
        assert plain.discovery_order == traced.discovery_order
        assert plain.ordered_path == traced.ordered_path
        assert plain.edges == traced.edges
        validate_steps(trace, traced, 20)


def test_direct_egpot_pathresult_is_identical(real):
    graph, _, tasks, _ = real
    row = tasks[0]
    engine = EGPOT(graph, EGPOTConfig(use_mcts=False, node_budget=20))
    plain = engine.traverse(row["query"], row["start_node"])
    trace = {}
    assert engine.traverse(row["query"], row["start_node"], trace=trace) == plain
    assert trace["final"]["visited_order"] == plain.visited_order


def test_candidate_truncation_keeps_selections_and_remaps_fronts():
    graph = nx.MultiDiGraph()
    graph.add_node("start", name="start", type="function")
    for i in range(100):
        node = f"node{i:03d}"
        graph.add_node(node, name="currency", type="function")
        graph.add_edge("start", node, relation="CALLS", layer="Ldep")
    engine = EGPOT(graph, EGPOTConfig(use_mcts=False, node_budget=3))
    trace = {}
    result = engine.traverse("currency", "start", trace=trace)
    first = trace["steps"][0]
    assert first["candidates_total"] == 100
    assert len(first["candidates"]) == 60 and first["candidates_truncated"] == 40
    assert len(first["selected"]) == 2  # partial final round respects budget
    assert all(first["candidates"][i]["to_node"] in result.visited for i in first["selected"])
    assert first["collected_size_after"] == 3
    assert trace["steps"][-1] == {"kind": "stop", "reason": "budget"}


@pytest.mark.parametrize("budget, reason", [(1, "budget"), (20, "no_candidates")])
def test_isolated_stop_reasons(budget, reason):
    graph = nx.MultiDiGraph()
    graph.add_node("alone")
    trace = {}
    result = EGPOT(graph, EGPOTConfig(node_budget=budget)).traverse("q", "alone", trace=trace)
    assert result.visited_order == ["alone"]
    assert trace["steps"][-1] == {"kind": "stop", "reason": reason}


def test_two_export_runs_are_byte_identical_and_json_valid(real, tmp_path):
    graph, rows, _, _ = real
    kwargs = dict(method_names=("egpot_full", "bfs", "vector_topk", "greedy_walk"),
                  budgets=(3,), query_ids=("ob01_explicit",))
    first, summary = build_export(graph, rows, **kwargs)
    second, _ = build_export(graph, rows, **kwargs)
    assert first == second
    assert summary["trace_files"] == 4
    write_export(first, tmp_path / "first")
    write_export(second, tmp_path / "second")
    for relative, expected in first.items():
        assert (tmp_path / "first" / relative).read_bytes() == (tmp_path / "second" / relative).read_bytes() == expected
        data = json.loads(expected)
        if relative == "traces_index.json":
            assert all(item["hit"] in (0, 1) for item in data)
        else:
            assert data["schema"] == 1 and data["split"] == "dev"
            assert data["config"] == {} or data["config"]["node_budget"] == 3
            assert "latency_s" not in expected.decode()
            no_gold_fields(data)
    assert json_bytes({"x": 0.123456789}) == b'{"x":0.123457}\n'


def test_mcts_export_bytes_repeat_and_samples_match(real):
    graph, rows, _, _ = real
    kwargs = dict(method_names=("egpot_full_mcts",), budgets=(2,), query_ids=("ob01_explicit",))
    first, _ = build_export(graph, rows, **kwargs)
    second, _ = build_export(graph, rows, **kwargs)
    assert first == second


def test_export_size_preflight_stops_before_writes(real, tmp_path):
    graph, rows, _, _ = real
    with pytest.raises(ValueError, match="STOP before writing"):
        files, _ = build_export(graph, rows, method_names=("bfs",), budgets=(2,),
                                query_ids=("ob01_explicit",), max_bytes=1)
        write_export(files, tmp_path / "must_not_exist")
    assert not (tmp_path / "must_not_exist").exists()


@pytest.mark.parametrize("args", [["--include-test"], ["--confirm-test"]])
def test_export_test_guard_before_loading(args, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("guard must run before loading")
    monkeypatch.setattr(nx, "read_graphml", forbidden)
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2
    with pytest.raises(AssertionError, match="guard must run"):
        main(["--include-test", "--confirm-test"])


def test_test_query_cannot_be_requested_without_both_flags(real):
    graph, rows, _, _ = real
    test_id = split_by_link(rows)["test"][0]["id"]
    with pytest.raises(ValueError, match="guarded test"):
        build_export(graph, rows, method_names=("bfs",), budgets=(1,), query_ids=(test_id,))
