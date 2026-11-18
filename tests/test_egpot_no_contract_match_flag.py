import json
from io import StringIO
from pathlib import Path

import networkx as nx
import pytest

from bench import egpot_eval as ev


def test_repeatable_flag_preserves_traversal_and_withholds_contract_match(monkeypatch):
    graph = nx.MultiDiGraph()
    graph.add_node("contract", type="rpc_contract")
    graph.add_edge("start", "contract", relation="RETURNS_SCHEMA", layer="Lcontract")
    graph.add_edge("provider", "contract", relation="IMPLEMENTS", layer="Lcontract")
    rows = [
        {"id": f"{link}_{kind}", "link_id": link, "type": kind, "query": kind,
         "start_node": "start", "gold_nodes": ["contract", "provider"],
         "gold_path": ["start", "contract", "provider"]}
        for link in range(1, 16) for kind in ("explicit", "indirect")
    ]
    monkeypatch.setattr(nx, "read_graphml", lambda *args, **kwargs: graph)
    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: StringIO(json.dumps(rows)))

    def compare(dev, methods):
        assert dev == ev.split_by_link(rows)["dev"]
        engine = methods["egpot_full"].engine
        policy = engine.graph_view.edge_policy
        assert policy.no_contract_match_relations == frozenset({"RETURNS_SCHEMA", "IMPLEMENTS"})
        assert not policy.excluded_relations
        result = engine.traverse("query", "start")
        assert result.ordered_path == ["start", "contract", "provider"]
        assert [step["vector"][2] for step in result.objective_log] == [
            engine.config.contract_mismatch_penalty,
            engine.config.contract_mismatch_penalty,
        ]

    monkeypatch.setattr(ev, "run_comparison", compare)
    assert ev.main(["--mode", "comparison", "--no-contract-match-relation", "RETURNS_SCHEMA",
                    "--no-contract-match-relation", "IMPLEMENTS"]) == 0


@pytest.mark.parametrize("mode", [
    ["--mode", "comparison", "--split", "test", "--confirm-test"],
    ["--mode", "test-final"],
])
def test_contract_match_override_is_dev_only(mode, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("Held-out inputs or final result reservation were accessed")

    monkeypatch.setattr(nx, "read_graphml", forbidden)
    monkeypatch.setattr(ev, "_final_locks", forbidden)
    with pytest.raises(SystemExit) as exc:
        ev.main([*mode, "--no-contract-match-relation", "RETURNS_SCHEMA"])
    assert exc.value.code == 2
    assert "Non-legacy edge policies are DEV only" in capsys.readouterr().err
