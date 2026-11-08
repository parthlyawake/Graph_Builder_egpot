"""Locked final-mode plumbing only: mocked git and tiny synthetic data.

No production labels are opened and no real experiment retriever is run.
"""
import hashlib
import json
import subprocess
from collections import Counter

import networkx as nx
import pytest

from bench import egpot_eval as ev

COMMIT = "12345678" + "a" * 32
COMMAND = ["--mode","test-final","--split","test","--confirm-test"]


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(ev,"ROOT",tmp_path)
    state = {"dirty":"","commands":[],"loads":0}
    def git(command, **kwargs):
        assert kwargs["cwd"] == tmp_path
        assert kwargs["check"] and kwargs["capture_output"] and kwargs["text"]
        state["commands"].append(command)
        if command == ["git","status","--porcelain"]:
            return subprocess.CompletedProcess(command,0,stdout=state["dirty"])
        assert command == ["git","rev-parse","HEAD"]
        return subprocess.CompletedProcess(command,0,stdout=COMMIT+"\n")
    def forbidden_loader(*args):
        state["loads"] += 1
        raise AssertionError("input loader must not run in a refused invocation")
    monkeypatch.setattr(ev.subprocess,"run",git)
    monkeypatch.setattr(ev,"_load_final_inputs",forbidden_loader)
    return state


def previous(tmp_path, name="test_final_older.json"):
    path = tmp_path/"bench/results"/name
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text('{"prior":true}',encoding="utf-8")
    return path


def test_dirty_tree_refuses_before_loading(isolated, tmp_path, capsys):
    isolated["dirty"] = " M bench/egpot_eval.py\n?? untracked.txt\n"
    with pytest.raises(SystemExit) as error:
        ev.main(COMMAND)
    assert error.value.code == 2
    message = capsys.readouterr().err
    assert "clean git tree" in message and "bench/egpot_eval.py" in message and "untracked.txt" in message
    assert isolated["loads"] == 0
    assert isolated["commands"] == [["git","status","--porcelain"]]
    assert not (tmp_path/"bench/results").exists()


@pytest.mark.parametrize("arguments", [
    ["--mode","test-final","--split","test"],
    ["--mode","test-final","--confirm-test"],
    ["--mode","test-final"],
])
def test_requires_both_test_and_confirmation(arguments, isolated, capsys):
    with pytest.raises(SystemExit):
        ev.main(arguments)
    assert "BOTH --split test and --confirm-test" in capsys.readouterr().err
    assert isolated["loads"] == 0 and isolated["commands"] == []


def test_second_run_refuses_and_names_suffix(isolated, tmp_path, capsys):
    old = previous(tmp_path)
    with pytest.raises(SystemExit):
        ev.main(COMMAND)
    message = capsys.readouterr().err
    assert old.name in message and "--acknowledge-second-look" in message and "_secondlook.json" in message
    assert isolated["loads"] == 0 and old.read_text() == '{"prior":true}'
    assert len(list(old.parent.glob("*.json"))) == 1


def synthetic_run(monkeypatch, isolated):
    graph = nx.MultiDiGraph()
    graph.add_nodes_from((n,{"name":n,"type":"function"}) for n in ("start","rpc","handler"))
    graph.add_edge("start","rpc",relation="CONSUMES",layer="Lcontract")
    labels = [{"id":f"synthetic_{link}_{kind}","link_id":link,"type":kind,"query":kind+f" question {link}",
        "start_node":"start","gold_nodes":["rpc","handler"],"gold_path":["start","rpc","handler"]}
        for link in range(1,16) for kind in ("explicit","indirect")]
    def load(*args):
        isolated["loads"] += 1
        return graph,labels
    monkeypatch.setattr(ev,"_load_final_inputs",load)
    class Fake:
        def __init__(self, view, config=None, seed=0):
            self.graph_view,self.seed = view,seed
            if config is not None:
                self.config = config
        def retrieve(self, query, start_node, node_budget):
            assert start_node == "start" and node_budget in (10,20,40)
            ordered = [start_node,"rpc"] + (["handler"] if query.startswith("explicit") else [])
            isolated["calls"] = isolated.get("calls",0)+1
            return ev.RetrievalResult(set(ordered),list(ordered),isolated["calls"]*.000001,list(ordered))
    def engines(view,scorer,ids):
        result = {}
        for name in ev.FINAL_METHODS:
            cfg = None
            off = name == "egpot_no_choke_point"
            if name.startswith("egpot_"):
                cfg = ev.EGPOTConfig(use_mcts=name.endswith("_mcts"),use_pareto="no_pareto" not in name,
                    use_entropy=name!="egpot_no_entropy",use_contracts=name!="egpot_no_contracts")
            result[name] = Fake(ev.GraphView(graph,use_choke_point=False) if off else view,cfg)
        for _,name in ev.CHOKE_PAIRS:
            if name.endswith("_no_choke"):
                result[name] = Fake(ev.GraphView(graph,use_choke_point=False))
        return result
    monkeypatch.setattr(ev,"_final_methods",engines)
    monkeypatch.setattr(ev,"_final_seed_method",lambda name,seed,view,scorer,ids:
        Fake(view, None if name=="mcts_standard" else ev.EGPOTConfig(seed=seed,use_mcts=True,
             use_pareto=name!="egpot_no_pareto_mcts"),seed))
    monkeypatch.setattr(ev,"EGPOTRetriever",lambda config,view,scorer:Fake(view,config))
    return labels


def test_synthetic_complete_record_and_experiment_matrix(monkeypatch, isolated, tmp_path, capsys):
    labels = synthetic_run(monkeypatch,isolated)
    assert ev.main(COMMAND) == 0
    path = tmp_path/"bench/results/test_final_12345678.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    assert {"commit","configs","rows","summary","versions","utc_timestamp"} <= record.keys()
    assert record["commit"] == COMMIT and record["status"] == "completed"
    assert set(record["versions"]) == {"python","networkx","scikit-learn","numpy"}
    assert record["utc_timestamp"].endswith("+00:00")
    assert record["split_links"] == {k:sorted({r["link_id"] for r in v}) for k,v in ev.split_by_link(labels).items()}
    assert Counter(r["experiment"] for r in record["rows"]) == {
        "main":1350,"choke":168,"seeds":420,"weights":1540,"pareto_reference":28}
    assert {r["split"] for r in record["rows"] if r["experiment"] != "main"} == {"test"}
    assert len(record["configs"]["weights"]) == 55
    assert set(record["configs"]["main"]) == set(ev.FINAL_METHODS)
    assert record["configs"]["protocol"]["seeds"] == list(range(5))
    for method in ev.STOCHASTIC_METHODS:
        assert set(record["configs"]["seeds"][method]) == {str(i) for i in range(5)}
    config = record["configs"]["main"]["egpot_full"]["effective_configs"]["10"]
    assert config == json.loads(json.dumps(ev.asdict(ev.EGPOTConfig(use_mcts=False,node_budget=10))))
    assert all("latency_s" in r for r in record["rows"])
    assert len(record["summary"]["dev_vs_test"]) == 45
    assert len(record["summary"]["weight_distribution"]) == 6
    assert all(s["vectors"] == 54 for s in record["summary"]["weight_distribution"])
    assert len(record["summary"]["test_misses_budget20"]) == 21
    assert all(r["missing_gold_nodes"] == ["handler"] for r in record["summary"]["test_misses_budget20"])
    assert all(r["minimum_budget_90_percent"] is None for r in record["summary"]["test_90_percent_thresholds"])
    output = capsys.readouterr().out
    assert output.index("LOCKED FULL CONFIGS") < output.index("DEV budget 10")
    assert "7/14" in output and "8/16" in output and "not tuning" in output
    assert isolated["loads"] == 1
    assert isolated["commands"] == [["git","status","--porcelain"],["git","rev-parse","HEAD"]]


def test_acknowledged_second_look_uses_distinct_names(monkeypatch, isolated, tmp_path, capsys):
    old = previous(tmp_path,"test_final_12345678.json")
    synthetic_run(monkeypatch,isolated)
    args = [*COMMAND,"--acknowledge-second-look"]
    assert ev.main(args) == 0
    assert ev.main(args) == 0
    paths = sorted(old.parent.glob("*.json"))
    assert {p.name for p in paths} == {old.name,"test_final_12345678_secondlook.json","test_final_12345678_2_secondlook.json"}
    assert old.read_text() == '{"prior":true}'
    assert "THE TEST SPLIT HAS BEEN LOOKED AT BEFORE" in capsys.readouterr().out


def test_failed_look_remains_locked_before_retry(monkeypatch, isolated, tmp_path, capsys):
    def broken(*args):
        isolated["loads"] += 1
        raise ValueError("synthetic loader failure")
    monkeypatch.setattr(ev,"_load_final_inputs",broken)
    with pytest.raises(SystemExit):
        ev.main(COMMAND)
    path = tmp_path/"bench/results/test_final_12345678.json"
    assert json.loads(path.read_text())["status"] == "failed"
    with pytest.raises(SystemExit):
        ev.main(COMMAND)
    assert isolated["loads"] == 1
    assert "_secondlook" in capsys.readouterr().err


def test_synthetic_determinism_excludes_latency(monkeypatch, isolated, tmp_path, capsys):
    synthetic_run(monkeypatch,isolated)
    assert ev.main(COMMAND) == 0
    first = json.loads((tmp_path/"bench/results/test_final_12345678.json").read_text())
    assert ev.main([*COMMAND,"--acknowledge-second-look"]) == 0
    second = json.loads((tmp_path/"bench/results/test_final_12345678_secondlook.json").read_text())
    assert first["rows"][0]["latency_s"] != second["rows"][0]["latency_s"]
    assert first["deterministic_sha256"] == second["deterministic_sha256"]
    assert ev.final_deterministic_content(first) == ev.final_deterministic_content(second)
    actual = hashlib.sha256(json.dumps(ev.final_deterministic_content(first),sort_keys=True,
        separators=(",",":"),allow_nan=False).encode()).hexdigest()
    assert actual == first["deterministic_sha256"]
    capsys.readouterr()


def test_reservation_collision_precedes_loader(monkeypatch, isolated, tmp_path, capsys):
    original = ev._final_locks
    def raced(args):
        result = original(args)
        path = result[1]
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text("reserved elsewhere")
        return result
    monkeypatch.setattr(ev,"_final_locks",raced)
    with pytest.raises(SystemExit):
        ev.main(COMMAND)
    assert isolated["loads"] == 0
    assert "reserved concurrently" in capsys.readouterr().err


def test_actual_registry_uses_unchanged_defaults_on_tiny_graph():
    graph = nx.MultiDiGraph()
    graph.add_node("s",type="function",name="tiny start")
    graph.add_node("t",type="rpc_contract",name="tiny target")
    graph.add_edge("s","t",relation="CONSUMES",layer="Lcontract")
    view = ev.GraphView(graph)
    scorer = ev.QueryScorer(view)
    methods = ev._final_methods(view,scorer,{})
    assert set(ev.FINAL_METHODS) <= methods.keys()
    assert methods["egpot_full"].config == ev.EGPOTConfig(use_mcts=False)
    assert methods["egpot_full_mcts"].config == ev.EGPOTConfig(use_mcts=True)
    assert methods["egpot_no_pareto_mcts"].config == ev.EGPOTConfig(use_mcts=True,use_pareto=False)
    assert methods["egpot_no_entropy"].config == ev.EGPOTConfig(use_mcts=False,use_entropy=False)
    assert methods["egpot_no_contracts"].config == ev.EGPOTConfig(use_mcts=False,use_contracts=False)
    assert not methods["egpot_no_choke_point"].graph_view.use_choke_point
    assert methods["vector_bfs_k2"].k == 2
    for normal,off in ev.CHOKE_PAIRS:
        assert methods[normal].graph_view.use_choke_point
        assert not methods[off].graph_view.use_choke_point
    for seed in range(5):
        for method in ev.STOCHASTIC_METHODS:
            engine = ev._final_seed_method(method,seed,view,scorer,{})
            assert (engine.seed if method=="mcts_standard" else engine.config.seed) == seed
