from types import SimpleNamespace

import networkx as nx
import pytest

from bench import egpot_test_splits as run


@pytest.fixture
def toy_root(tmp_path, monkeypatch):
    def git(*args, root=None):
        if args[:2] == ("tag", "--list"):
            return ""
        if args[0] == "rev-parse":
            return run.FREEZE
        if args[0] == "status":
            return " M eg_pot.py"
        return ""

    monkeypatch.setattr(run.locked, "git", git)
    (tmp_path / "bench/results").mkdir(parents=True)
    return tmp_path


def test_refuses_missing_plan(toy_root):
    with pytest.raises(ValueError, match="Missing test-split preregistration"):
        run.preflight("online_boutique", acknowledge=True, root=toy_root)


def test_refuses_second_attempt_even_if_incomplete(toy_root):
    path = toy_root / "bench/results" / run.result_name("online_boutique")
    run.reserve(path, {"commit": "fake"})
    with pytest.raises(ValueError, match="already consumed"):
        run.preflight("online_boutique", acknowledge=True, root=toy_root)
    with pytest.raises(ValueError, match="already consumed"):
        run.reserve(path, {})


def test_refuses_dirty_tree(toy_root):
    (toy_root / run.PLAN).write_text("toy plan", encoding="utf-8")
    with pytest.raises(ValueError, match="clean Git tree"):
        run.preflight("online_boutique", acknowledge=True, root=toy_root)


def test_no_label_fields_reach_any_method_and_registry_is_executable(monkeypatch):
    graph = nx.MultiDiGraph()
    graph.add_node("start", name="start")
    graph.add_node("target", name="target")
    graph.add_edge("start", "target", relation="HTTP_CALLS")
    configs = run.configs_for(graph)
    label = {"id": "q", "link_id": 2, "type": "explicit", "query": "target",
             "start_node": "start", "gold_nodes": ["target"], "gold_path": ["start", "target"],
             "path_relations": ["HTTP_CALLS->"], "accepted_alternatives": ["private"]}
    assert run.coverage(graph, [label]) == ([label], [], {"q": 1})
    jobs, _ = run.locked.plan_locked([label], configs)
    assert {task["method"] for task in jobs} == set(run.EGPOT + run.BASELINES) | set(dict(run.CHOKE).values())
    monkeypatch.setattr(run.locked, "_VIEW", run.GraphView(graph, edge_policy=run.locked.DSB_EDGE_POLICY))
    monkeypatch.setattr(run.locked, "_SCORER", run.QueryScorer(run.locked._VIEW))
    monkeypatch.setattr(run.locked, "_ENGINES", {})
    for task in jobs:
        engine = run.locked.make_engine(task["method"], task["spec"])
        if type(engine).__name__ != "StandardMCTS":
            run.locked.evaluate_locked_job(task, engine, include_returned_nodes=True)

    class Spy:
        def retrieve(self, *, query, start_node, node_budget):
            assert (query, start_node) == ("target", "start")
            return SimpleNamespace(discovery_order=["start", "target"], visited={"start", "target"},
                                   ordered_path=["start", "target"], latency_s=0.0)

    monkeypatch.setattr(run.locked, "make_engine", lambda *args: Spy())
    for task in jobs:
        assert "accepted_alternatives" not in task["label"]
        _, result = run.execute_test_job(task)
        assert result["deterministic"]["returned_nodes"] == ["start", "target"]
