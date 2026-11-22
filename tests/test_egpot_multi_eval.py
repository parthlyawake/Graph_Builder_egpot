"""Only synthetic graphs/labels; never run the Train benchmark or OB test split."""
from dataclasses import asdict, replace
import json
from pathlib import Path

import networkx as nx
import pytest

from bench import egpot_multi_eval as multi
from eg_pot import EGPOTConfig


def write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def tiny(tmp_path):
    graph = nx.MultiDiGraph()
    for node in ("s", "a", "b", "handler", "contract"):
        graph.add_node(node, type="http_endpoint" if node == "contract" else "function",
                       name="inventory available " + node, file="example.py", code="return available things")
    graph.add_edge("s", "a", relation="CALLS", layer="Ldep")
    graph.add_edge("a", "b", relation="CALLS", layer="Ldep")
    graph.add_edge("s", "handler", relation="HTTP_CALLS", layer="Ldep")
    graph.add_edge("handler", "contract", relation="IMPLEMENTS", layer="Lcontract")
    gp, lp = tmp_path / "graph.graphml", tmp_path / "labels.json"
    nx.write_graphml(graph, gp)
    labels = [{"id": f"q{i}", "link_id": i, "type": "explicit" if i == 1 else "indirect",
               "query": "available inventory " + str(i), "start_node": "s",
               "gold_nodes": ["contract", "handler"], "gold_path": ["s", "handler", "contract"]}
              for i in (1, 2)]
    write(lp, labels)
    provenance, label_prov = tmp_path / "graph.provenance.json", tmp_path / "labels.provenance.json"
    write(provenance, {"graphml_sha256": multi.sha256(gp)})
    write(label_prov, {"query_file_sha256": multi.sha256(lp), "graphml_sha256": multi.sha256(gp)})
    prereg = tmp_path / "preregistration.md"
    prereg.write_text("Synthetic preregistration", encoding="utf-8")
    repo = multi.Repo(gp, provenance, lp, label_prov, prereg)
    config = {"class": "EGPOTRetriever", "config": asdict(EGPOTConfig(use_mcts=False)),
              "choke_point": True, "budgets": [3, 5]}
    bfs = {"class": "BFS", "config": {"order": "breadth-first deterministic GraphView.neighbors"},
           "choke_point": True, "budgets": [3, 5]}
    mcts = {**config, "config": asdict(EGPOTConfig(use_mcts=True, mcts_rollouts=2, rollout_depth=1))}
    configs = {"main": {"egpot_full": config, "bfs": bfs, "egpot_full_mcts": mcts},
               "choke": {}, "seeds": {}, "weights": {}, "pareto_reference": config, "protocol": {}}
    return repo, labels, configs


def clean_git(*args, **kwargs):
    if args[:2] == ("status", "--porcelain"):
        return ""
    if args[:2] == ("ls-files", "--error-unmatch"):
        return str(args[-1])
    return "a" * 40


def test_registry():
    assert set(multi.REGISTRY) == {"online_boutique", "train_ticket", "dsb_social", "dsb_media"}
    assert multi.REGISTRY["train_ticket"].preregistration.name == "preregistration_train_ticket.md"


def test_hash_checks(tiny):
    repo, _, _ = tiny
    assert multi.verify_inputs(repo) == {"graph": multi.sha256(repo.graph), "labels": multi.sha256(repo.labels)}


@pytest.mark.parametrize("which", ["graph", "labels"])
def test_hash_mismatch(tiny, which):
    repo, _, _ = tiny
    getattr(repo, which).write_bytes(b"modified")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        multi.verify_inputs(repo)


def test_missing_provenance_refuses(tiny):
    repo, _, _ = tiny
    with pytest.raises(ValueError, match="Missing frozen graph provenance"):
        multi.verify_inputs(replace(repo, provenance=repo.provenance.with_name("absent.json")))


def test_dirty_refuses_before_inputs(tiny, monkeypatch, tmp_path):
    repo, _, _ = tiny
    monkeypatch.setattr(multi, "git", lambda *a, **k: " M dirty.py")
    monkeypatch.setattr(multi, "verify_inputs", lambda *a, **k: pytest.fail("input loader called before lock"))
    with pytest.raises(ValueError, match="dirty.py"):
        multi.locked_preflight("train_ticket", repo, tmp_path)


def test_missing_preregistration(tiny, monkeypatch, tmp_path):
    repo, _, _ = tiny
    monkeypatch.setattr(multi, "git", clean_git)
    with pytest.raises(ValueError, match="Missing Train-Ticket preregistration"):
        multi.locked_preflight("train_ticket", replace(repo, preregistration=None), tmp_path)


def test_untracked_preregistration(tiny, monkeypatch, tmp_path):
    repo, _, _ = tiny
    def fake(*args, **kwargs):
        if args[0] == "ls-files":
            raise multi.subprocess.CalledProcessError(1, "git")
        return clean_git(*args, **kwargs)
    monkeypatch.setattr(multi, "git", fake)
    with pytest.raises(ValueError, match="must be tracked"):
        multi.locked_preflight("train_ticket", repo, tmp_path)


def test_second_run_guard_and_distinct_path(tiny, monkeypatch, tmp_path):
    repo, _, _ = tiny
    monkeypatch.setattr(multi, "git", clean_git)
    first = tmp_path / ("train_ticket_final_" + "a" * 8 + ".json")
    first.write_text("{}")
    with pytest.raises(ValueError, match="secondlook"):
        multi.locked_preflight("train_ticket", repo, tmp_path)
    _, _, second, _ = multi.locked_preflight("train_ticket", repo, tmp_path, acknowledge=True)
    assert second != first and second.stem.endswith("_secondlook")


def test_publish_is_complete_exclusive_and_only_consumption(tmp_path):
    destination = tmp_path / "final.json"
    assert not destination.exists()
    multi.publish(destination, {"rows": [1], "latencies": [2]})
    assert multi.read_json(destination)["rows"] == [1]
    with pytest.raises(FileExistsError):
        multi.publish(destination, {"rows": []})
    assert multi.read_json(destination)["rows"] == [1]


@pytest.fixture(scope="module")
def executions(tmp_path_factory):
    # Build fixture data independently so multiprocessing sees real tiny files.
    root = tmp_path_factory.mktemp("multi-workers")
    graph = nx.MultiDiGraph()
    for n in ("s", "a", "b"):
        graph.add_node(n, type="function", name="available " + n, file="tiny.py")
    graph.add_edge("s", "a", relation="CALLS", layer="Ldep")
    graph.add_edge("a", "b", relation="CALLS", layer="Ldep")
    path = root / "tiny.graphml"
    nx.write_graphml(graph, path)
    spec = {"class": "BFS", "config": {"order": "breadth-first deterministic GraphView.neighbors"},
            "choke_point": True}
    labels = [{"id": str(i), "link_id": i, "type": "explicit", "query": "available",
               "start_node": "s", "gold_nodes": ["b"], "gold_path": ["s", "a", "b"]} for i in (1, 2)]
    jobs = [multi.job("bfs", spec, 3, row) for row in labels]
    identity = {"commit": "synthetic", "graph": multi.sha256(path)}
    one = multi.run_jobs(path, jobs, root / "one", identity, workers=1)
    two = multi.run_jobs(path, jobs, root / "two", identity, workers=2)
    return root, path, jobs, identity, one, two


def test_worker_determinism(executions):
    *_, one, two = executions
    assert {k: v["deterministic"] for k, v in one.items()} == {k: v["deterministic"] for k, v in two.items()}
    assert all("latency_s" not in r["deterministic"] for r in one.values())


def test_completed_checkpoint_resume_no_jobs(executions, monkeypatch):
    root, path, jobs, identity, one, _ = executions
    monkeypatch.setattr(multi, "ProcessPoolExecutor", lambda **k: pytest.fail("completed jobs rerun"))
    assert multi.run_jobs(path, jobs, root / "one", identity, workers=4, resume=True) == one


def test_partial_checkpoint_resume(executions):
    root, path, jobs, identity, one, _ = executions
    partial = root / "partial"
    partial.mkdir()
    multi.atomic_json(partial / "manifest.json", {"identity": identity,
        "jobs_sha256": multi.digest(sorted(j["key"] for j in jobs))})
    key = jobs[0]["key"]
    multi.atomic_json(partial / (key + ".json"), {"key": key,
        "identity_sha256": multi.digest(identity), "result": one[key]})
    resumed = multi.run_jobs(path, jobs, partial, identity, workers=1, resume=True)
    assert {k: v["deterministic"] for k, v in resumed.items()} == {k: v["deterministic"] for k, v in one.items()}


def test_checkpoint_changed_identity_refused(executions):
    root, path, jobs, identity, *_ = executions
    with pytest.raises(ValueError, match="Resume refused"):
        multi.run_jobs(path, jobs, root / "one", {**identity, "commit": "changed"}, resume=True)


def test_checkpoint_requires_explicit_resume(executions):
    root, path, jobs, identity, *_ = executions
    with pytest.raises(ValueError, match="pass --resume"):
        multi.run_jobs(path, jobs, root / "one", identity)


def test_locked_plan_uses_record_budgets_and_whole_set(tiny):
    _, labels, configs = tiny
    jobs, aliases = multi.plan_locked(labels, configs)
    assert {j["budget"] for j in jobs} == {3, 5}
    assert {j["label"]["id"] for j in jobs} == {"q1", "q2"}
    assert all(a["split"] == "all" for a in aliases)
    assert len(aliases) > len(jobs)  # Pareto reference reuses full retrieval jobs


def test_synthetic_locked_payload(tiny, monkeypatch, tmp_path):
    repo, labels, configs = tiny
    monkeypatch.setattr(multi, "locked_preflight", lambda *a, **k: ("a"*40, multi.verify_inputs(repo), tmp_path/"result.json", []))
    monkeypatch.setattr(multi, "input_identity", lambda *a, **k: {"commit": "a"*40, "graph": multi.sha256(repo.graph)})
    repo = replace(repo, preregistration=None)
    payload = multi.run_locked("synthetic", configs, workers=1, checkpoint=tmp_path/"jobs",
                              registry={"synthetic": repo}, output_dir=tmp_path)
    assert {"commit", "identity", "configs", "rows", "summary", "latencies", "worker_count"} <= payload.keys()
    assert all("latency_s" not in row for row in payload["rows"])
    assert len(payload["rows"]) == len(multi.plan_locked(labels, configs)[1])
    assert payload["schema"] == 1
    assert all("returned_nodes" not in row for row in payload["rows"])


def test_dsb_publishes_discovery_order_in_every_deterministic_row(tiny, monkeypatch, tmp_path):
    repo, _, configs = tiny
    configs["main"]["vector_topk"] = configs["main"]["bfs"]
    configs["seeds"] = {"egpot_full_mcts": {"0": configs["main"]["egpot_full_mcts"]}}
    configs["weights"] = {"equal": configs["main"]["egpot_full"]}
    configs["choke"] = {"bfs_no_choke": configs["main"]["bfs"]}
    target = tmp_path / "result.json"
    hashes = {**multi.verify_inputs(repo), "preregistration": multi.sha256(repo.preregistration)}
    monkeypatch.setattr(multi, "locked_preflight", lambda *a, **k: ("a" * 40, hashes, target, []))
    monkeypatch.setattr(multi, "input_identity", lambda *a, **k: {"commit": "a" * 40})
    monkeypatch.setattr(multi, "load_settings", lambda: {})
    monkeypatch.setattr(multi, "dsb_settings", lambda _: configs)
    monkeypatch.setattr(multi, "_ENGINES", {})

    class Stub:
        discovery = ["s", "handler", "contract"]

        def retrieve(self, *, query, start_node, node_budget):
            assert start_node == "s" and query.startswith("available inventory")
            return multi.frozen.RetrievalResult(set(self.discovery), ["s", "contract"], 0.01,
                                               self.discovery)

    class StubVectorTopK(Stub, multi.VectorTopK):
        discovery = ["handler", "s", "contract"]

        def __init__(self):
            pass

    monkeypatch.setattr(multi, "make_engine", lambda method, _: (
        StubVectorTopK() if method == "vector_topk" else Stub()))

    def run_jobs(graph, jobs, checkpoint, identity, *, include_returned_nodes, **kwargs):
        assert include_returned_nodes is True
        return dict(multi.execute_job(job, include_returned_nodes=include_returned_nodes)
                    for job in jobs)

    monkeypatch.setattr(multi, "run_jobs", run_jobs)
    payload = multi.run_locked("dsb_social", None, registry={"dsb_social": repo},
                               output_dir=tmp_path, workers=1, checkpoint=tmp_path / "jobs")
    published = multi.read_json(target)
    assert multi.canonical(published) == multi.canonical(payload)
    assert published["schema"] == multi.DSB_RESULT_SCHEMA == 2
    assert {row["experiment"] for row in published["rows"]} == {
        "main", "seeds", "weights", "choke", "pareto_reference"}
    for row in published["rows"]:
        expected = StubVectorTopK.discovery if row["method"] == "vector_topk" else Stub.discovery
        assert row["returned_nodes"] == expected
        assert "latency_s" not in row
    assert all("retrieve" not in vars(engine) for engine in multi._ENGINES.values())
    assert published["deterministic_sha256"] == multi.digest(published["rows"])
    published["rows"][0]["returned_nodes"].reverse()
    assert published["deterministic_sha256"] != multi.digest(published["rows"])


def test_metrics_and_split_are_original_imports():
    from bench import egpot_eval
    assert multi.metrics is egpot_eval.metrics
    assert multi.split_by_link is egpot_eval.split_by_link
    assert multi.ablation_configs is egpot_eval.ablation_configs
