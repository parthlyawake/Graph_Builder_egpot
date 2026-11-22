from dataclasses import asdict
from types import SimpleNamespace

import networkx as nx
import pytest

from bench import egpot_multi_eval as locked
from eg_pot import EGPOTConfig, GraphView, QueryScorer


def specs():
    base = {"class": "EGPOTRetriever", "choke_point": True, "budgets": [10, 20, 40],
            "config": asdict(EGPOTConfig(use_mcts=False))}
    tiebreak = {**base, "config": {**base["config"], "use_mcts": True, "lookahead_mode": "tiebreak"}}
    return {"main": {"egpot_full": base,
                     "egpot_no_pareto": {**base, "config": {**base["config"], "use_pareto": False}},
                     "egpot_full_tiebreak": tiebreak, "egpot_full_mcts": base},
            "seeds": {"egpot_full_tiebreak": {
                str(seed): {**tiebreak, "budgets": [20, 40],
                            "config": {**tiebreak["config"], "seed": seed}}
                for seed in range(6)}},
            "edge_policy": {}}


def toy_label():
    return {"id": "q", "link_id": "toy", "type": "explicit", "query": "find target",
            "start_node": "start", "gold_nodes": ["target"], "gold_path": ["start", "target"]}


def test_width12_specs_keep_original_untouched_and_scope_methods():
    original = specs()
    configs = locked.width12_settings(original)
    assert set(configs["main"]) == {m + "_w12" for m in locked.WIDTH12_METHODS}
    assert set(configs["seeds"]["egpot_full_tiebreak_w12"]) == set(map(str, range(6)))
    assert not configs["choke"] and not configs["weights"]
    jobs, _ = locked.plan_locked([toy_label()], configs)
    for task in jobs:
        assert task["spec"]["config"]["beam_width"] == 12
    assert original["main"]["egpot_full"]["config"]["beam_width"] == 4


def test_worker_records_effective_width_and_ordered_nodes(monkeypatch):
    graph = nx.MultiDiGraph()
    graph.add_node("start", name="origin")
    graph.add_node("target", name="target")
    graph.add_edge("start", "target", relation="CALLS")
    view = GraphView(graph)
    monkeypatch.setattr(locked, "_VIEW", view)
    monkeypatch.setattr(locked, "_SCORER", QueryScorer(view))
    monkeypatch.setattr(locked, "_ENGINES", {})
    method = "egpot_full_w12"
    spec = locked.width12_settings(specs())["main"][method]
    task = locked.job(method, spec, 10, toy_label())
    key, result = locked.execute_job(task, include_returned_nodes=True, width12=True)
    assert key == task["key"]
    row = result["deterministic"]
    assert row["beam_width"] == 12 and row["returned_nodes"] == ["start", "target"]
    for bad in ({**row, "beam_width": 4}, {**row, "method": "egpot_full"}):
        with pytest.raises(ValueError, match="width-12"):
            locked.verify_width12_row(bad, task)
    task["spec"]["config"]["beam_width"] = 4
    with pytest.raises(ValueError, match="width-12"):
        locked.verify_width12_row(row, task)


@pytest.mark.parametrize("method", locked.WIDTH12_METHODS)
def test_worker_does_not_expose_label_fields_to_retriever(monkeypatch, method):
    class Spy:
        config = SimpleNamespace(beam_width=12)

        def retrieve(self, *, query, start_node, node_budget):
            assert (query, start_node, node_budget) == ("find target", "start", 10)
            return SimpleNamespace(discovery_order=["start", "target"], visited={"start", "target"},
                                   ordered_path=["start", "target"], latency_s=0.0)

    monkeypatch.setattr(locked, "_ENGINES", {})
    monkeypatch.setattr(locked, "make_engine", lambda *args: Spy())
    name = method + "_w12"
    task = locked.job(name, locked.width12_settings(specs())["main"][name], 10, toy_label())
    _, result = locked.execute_job(task, include_returned_nodes=True, width12=True)
    assert result["deterministic"]["hit"] == 1
