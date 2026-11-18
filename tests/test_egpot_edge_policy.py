import json
import math
from dataclasses import replace
from io import StringIO
from pathlib import Path

import networkx as nx
import pytest

from bench import egpot_eval as ev
from eg_pot import CURRENT_V1, LEGACY, CandidateStep, EGPOT, EGPOTConfig, GraphView, QueryScorer


def test_legacy_preserves_ranking_and_entropy():
    graph = nx.MultiDiGraph()
    graph.add_node("contract", type="rpc_contract")
    graph.add_edge("start", "contract", relation="CONSUMES", layer="Lcontract")
    graph.add_edge("provider", "contract", relation="IMPLEMENTS", layer="Lcontract")
    graph.add_edge("unrelated", "field", relation="DECLARES_FIELD", layer="Lcontract")
    config = EGPOTConfig(node_budget=3, beam_width=1, use_mcts=False)

    explicit = EGPOT(graph, config, edge_policy=LEGACY).traverse("shipping", "start")
    assert explicit == EGPOT(graph, config).traverse("shipping", "start")
    assert explicit.visited_order == ["start", "contract", "provider"]
    assert explicit.objective_log[1]["vector"][3] == pytest.approx(math.log(2) / math.log(3))


def test_exclusion_controls_egpot_and_baseline_adjacency():
    graph = nx.MultiDiGraph()
    graph.add_edge("start", "excluded_out", relation="DECLARES_FIELD")
    graph.add_edge("excluded_in", "start", relation="EVALUATES")
    graph.add_edge("start", "allowed", relation="CALLS")
    view = GraphView(graph, edge_policy=CURRENT_V1)
    scorer = QueryScorer(view)

    assert [step[0] for step in view.neighbors("start")] == ["allowed"]
    assert view.neighbors("excluded_out") == []
    assert view.neighbors("excluded_in") == []
    assert EGPOT(graph, edge_policy=CURRENT_V1).traverse("query", "start").visited == {"start", "allowed"}

    methods = ev.make_comparison_retrievers(view, scorer)
    for name, method in methods.items():
        result = method.retrieve("query", "start", 4)
        assert not {relation for _, relation, _ in result.edges} & CURRENT_V1.excluded_relations, name
    for name in ("bfs", "greedy_walk", "scalar_beam", "mcts_standard", "egpot_full_mcts"):
        assert methods[name].retrieve("query", "start", 4).visited == {"start", "allowed"}
    assert set(methods["ppr"].move_graph.edges) == {("start", "allowed"), ("allowed", "start")}
    assert ("excluded_out",) in methods["community_graphrag"].partition
    assert ev.BFSNoChoke(view, scorer).retrieve("query", "start", 4).visited == {"start", "allowed"}
    assert ev.EGPOTRetriever(EGPOTConfig(), view, scorer, use_choke_point=False).retrieve(
        "query", "start", 4).visited == {"start", "allowed"}


@pytest.mark.parametrize("layer", ["Lcontract", "Ldep"])
def test_no_contract_match_overrides_layer_and_target_type(layer):
    graph = nx.MultiDiGraph()
    graph.add_node("rpc", type="rpc_contract")
    key = graph.add_edge("start", "rpc", relation="RETURNS_SCHEMA", layer=layer)
    step = CandidateStep("start", "rpc", "RETURNS_SCHEMA", "out", key, layer)

    legacy = EGPOT(graph)
    current = EGPOT(graph, edge_policy=CURRENT_V1)
    assert legacy.contract_consistency(step) == legacy.config.contract_match_score
    assert current.contract_consistency(step) == current.config.contract_mismatch_penalty
    assert current.traverse("query", "start").visited == {"start", "rpc"}


def test_entropy_uses_eligible_relation_types_only_when_enabled():
    graph = nx.MultiDiGraph()
    graph.add_edge("start", "one", relation="CALLS")
    graph.add_edge("one", "two", relation="IMPORTS")
    graph.add_edge("unrelated", "field", relation="DECLARES_FIELD")
    excluded = replace(LEGACY, excluded_relations=frozenset({"DECLARES_FIELD"}))
    filtered = replace(excluded, entropy_over_eligible_only=True)

    for policy, count in ((LEGACY, 3), (excluded, 3), (filtered, 2),
                          (replace(LEGACY, entropy_over_eligible_only=True), 3)):
        engine = EGPOT(graph, edge_policy=policy)
        view = engine.graph_view
        assert view.entropy_denominator() == pytest.approx(math.log(count))
        retriever = ev.EGPOTRetriever(EGPOTConfig(use_mcts=False), view, engine.scorer)
        result = retriever.engine.traverse("query", "start")
        assert result.objective_log[1]["vector"][3] == pytest.approx(math.log(2) / math.log(count))


@pytest.mark.parametrize("args", [
    ["--mode", "comparison", "--split", "test", "--confirm-test", "--edge-policy", "current_v1"],
    ["--mode", "comparison", "--split", "test", "--confirm-test", "--exclude-relation", "CALLS"],
    ["--mode", "test-final", "--edge-policy", "current_v1"],
])
def test_cli_rejects_nonlegacy_held_out_runs_before_loading_inputs(args, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("Held-out inputs or result lock were accessed")

    monkeypatch.setattr(nx, "read_graphml", forbidden)
    monkeypatch.setattr(ev, "_final_locks", forbidden)
    with pytest.raises(SystemExit) as exc:
        ev.main(args)
    assert exc.value.code == 2
    assert "Non-legacy edge policies are DEV only" in capsys.readouterr().err


def test_dev_cli_combines_named_policy_and_repeatable_exclusions(monkeypatch):
    graph = nx.MultiDiGraph()
    graph.add_edge("start", "answer", relation="CALLS")
    rows = [
        {"id": f"{link_id}_{kind}", "link_id": link_id, "type": kind, "query": kind,
         "start_node": "start", "gold_nodes": ["answer"], "gold_path": ["start", "answer"]}
        for link_id in range(1, 16) for kind in ("explicit", "indirect")
    ]
    monkeypatch.setattr(nx, "read_graphml", lambda *args, **kwargs: graph)
    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: StringIO(json.dumps(rows)))

    def comparison(dev, methods):
        assert dev == ev.split_by_link(rows)["dev"]
        assert methods["bfs"].graph_view.edge_policy == replace(
            CURRENT_V1, excluded_relations=CURRENT_V1.excluded_relations | {"CALLS", "USES"})
        assert methods["bfs"].retrieve("query", "start", 5).visited == {"start"}

    monkeypatch.setattr(ev, "run_comparison", comparison)
    assert ev.main(["--mode", "comparison", "--edge-policy", "current_v1",
                    "--exclude-relation", "CALLS", "--exclude-relation", "USES"]) == 0
