import hashlib
import json
from dataclasses import asdict

import networkx as nx
import pytest

from eg_pot import EGPOT, EGPOTConfig


@pytest.mark.parametrize("with_trace", [False, True])
def test_shared_tip_extension_uses_the_path_that_scored_it(monkeypatch, with_trace):
    graph = nx.MultiDiGraph()
    graph.add_edges_from([("root", "a"), ("root", "b"), ("a", "tip"),
                          ("b", "tip"), ("tip", "finish")], relation="CALLS", layer="Ldep")
    engine = EGPOT(graph, EGPOTConfig(beam_width=2, node_budget=5))
    finish_steps = []

    def score(query, state, step, trace=None):
        value = 0.5 if step.to_node in {"a", "b", "tip"} and state.ordered_nodes[-1] != "tip" else 0.0
        if step.to_node == "finish":
            finish_steps.append(step)
            value = 1.0 if state.ordered_nodes[1] == "a" else 0.25
        vector = (value,) * 4
        if trace is not None:
            trace["final_vector"] = list(vector)
        return vector

    monkeypatch.setattr(engine, "candidate_vector", score)
    trace = {} if with_trace else None
    result = engine.traverse("query", "root", trace=trace)

    assert len(finish_steps) == 2 and finish_steps[0] is finish_steps[1]
    assert result.ordered_path == ["root", "a", "tip", "finish"]
    assert result.objective_log[-1]["vector"] == (1.0,) * 4
    if with_trace:
        final_round = trace["steps"][-2]
        selected = final_round["candidates"][final_round["selected"][0]]
        parent = next(row for row in final_round["beam_before"] if row["state_id"] == selected["state_id"])
        assert parent["nodes"] == result.ordered_path[:-1]


def test_unique_tips_match_pre_fix_result_and_trace_bytes():
    graph = nx.MultiDiGraph()
    graph.add_edges_from([("start", "first"), ("first", "second")], relation="CALLS", layer="Ldep")
    trace = {}
    result = asdict(EGPOT(graph).traverse("unrelated", "start", trace=trace))
    result["visited"] = sorted(result["visited"])
    encoded = json.dumps({"result": result, "trace": trace}, sort_keys=True, separators=(",", ":"))

    # Snapshot of the default result and trace on this graph before the origin fix.
    assert hashlib.sha256(encoded.encode()).hexdigest() == (
        "5d30455348f6e87a1ae5de0bb81d063130ca509134e6cdb771200d7a83e9642f"
    )
