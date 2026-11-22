"""Analysis checks on synthetic locked records. No graph is parsed or searched."""
from dataclasses import replace
import json

import numpy as np
import pytest

from bench import analyze_dsb_final as analysis
from bench import egpot_multi_eval as locked
from bench.egpot_eval import FINAL_METHODS


def metric(hit, *, nodes_to_hit=3):
    return {"hit": hit, "gold_recall": float(hit), "precision": hit / 4,
            "path_coverage": (1 + hit) / 2, "ordered_path_match": hit,
            "nodes_returned": 4, "nodes_to_hit": nodes_to_hit if hit else None,
            "precision_at_hit": 1 / nodes_to_hit if hit else None, "latency_s": 0.1 + hit}


def test_descriptive_means_and_hits_only_compactness():
    a, b = [metric(1), metric(1, nodes_to_hit=5), metric(0)], [
        metric(0), metric(1, nodes_to_hit=4), metric(1)]
    result = analysis.summarize(a)
    assert result == pytest.approx({"n": 3, "hit_count": 2, "hit": 2 / 3, "gold_recall": 2 / 3,
        "precision": 1 / 6, "path_coverage": 5 / 6, "ordered_path_match": 2 / 3,
        "nodes_returned": 4, "nodes_to_hit": 4, "precision_at_hit": (1 / 3 + 1 / 5) / 2,
        "latency_s": 2.3 / 3})
    assert analysis.summarize([metric(0)])["precision_at_hit"] is None
    assert analysis.compactness(a, b) == {
        "left_hits": 2, "right_hits": 2, "left_hits_only": 4, "right_hits_only": 3.5,
        "both_hit_n": 1, "paired_left": 5, "paired_right": 4, "paired_difference": 1}
    assert analysis.compactness([metric(1)], [metric(0)])["paired_difference"] is None


def test_bootstrap_identical_and_always_winning_methods_are_deterministic():
    methods = {analysis.FULL: [metric(1)] * 2, "same": [metric(1)] * 2, "loser": [metric(0)] * 2}
    args = (methods, [("social", "x"), ("social", "y")],
            [(analysis.FULL, "same"), (analysis.FULL, "loser")], ["same", "loser"])
    first = analysis.bootstrap(*args, seed=0)
    assert first == analysis.bootstrap(*args, seed=0)
    for name in ("hit_rate", "mean_recall"):
        assert first[0][name] == {"difference": 0, "interval": [0, 0],
                                  "analysis_type": "exploratory", "confidence_level": 0.95}
        assert first[1][name]["difference"] == 1
        assert first[1][name]["interval"] == [1, 1]


def test_cluster_resampling_ties_queries_and_stratifies_by_app():
    keys = [("social", "shared"), ("social", "shared"), ("social", "other"),
            ("media", "shared"), ("media", "third"), ("media", "third"), ("media", "fourth")]
    draws = analysis.cluster_weights(keys, resamples=200)
    assert np.array_equal(draws[:, 0], draws[:, 1])
    assert np.array_equal(draws[:, 4], draws[:, 5])
    assert np.all(draws[:, [0, 2]].sum(axis=1) == 2)
    assert np.all(draws[:, [3, 4, 6]].sum(axis=1) == 3)
    assert np.any(draws[:, 0] != draws[:, 3])
    assert len(np.unique(draws.sum(axis=1))) > 1  # resample clusters, then weight by query
    methods = {analysis.FULL: [metric(1)] * 3 + [metric(0)] * 4,
               "baseline": [metric(0)] * 7}
    contrast, _ = analysis.bootstrap(methods, keys, [(analysis.FULL, "baseline")], ["baseline"])
    assert contrast["hit_rate"]["difference"] == pytest.approx(3 / 7)
    assert contrast["hit_rate"]["interval"][0] > 0
    assert contrast["hit_rate"]["interval"][1] < 1


def test_strongest_is_reselected_in_each_draw_using_metric_then_size_then_name():
    methods = {analysis.FULL: [metric(1), metric(1)], "a": [metric(1), metric(0)],
               "b": [metric(0), metric(1, nodes_to_hit=2)]}
    fixed, adaptive = analysis.bootstrap(methods, [("social", "a"), ("social", "b")],
                                         [(analysis.FULL, "b")], ["a", "b"])
    assert adaptive["hit_rate"]["observed_baseline"] == "b"  # equal hits, lower nodes to hit
    assert adaptive["hit_rate"]["difference"] == 0.5
    assert adaptive["hit_rate"]["interval"] == [0, 0.5]
    assert fixed["hit_rate"]["interval"] == [0, 1]
    selected = analysis.strongest_baseline(np.array([[1, 2], [2, 2], [2, 2]]),
                                            np.array([[1, 9], [4, 3], [4, 4]]))
    assert selected.tolist() == [1, 1, 0]


def test_recall_uses_its_own_strongest_baseline_and_reselects_it():
    methods = {analysis.FULL: [metric(1)] * 3,
               "a": [metric(1), metric(1), metric(0)],
               "b": [{**metric(0), "gold_recall": 0.75}] * 3}
    fixed, adaptive = analysis.bootstrap(methods, [("social", str(i)) for i in range(3)],
                                         [(analysis.FULL, "b")], ["a", "b"])
    assert adaptive["hit_rate"]["observed_baseline"] == "a"
    assert adaptive["mean_recall"]["observed_baseline"] == "b"
    assert adaptive["mean_recall"]["difference"] == 0.25
    assert adaptive["mean_recall"]["interval"] == [0, 0.25]
    assert fixed["mean_recall"]["interval"] == [0.25, 0.25]


def test_bonferroni_tails_only_apply_to_confirmatory_hit_rate(monkeypatch):
    draws = np.array([[2, 0]] * 10 + [[0, 2]] * 10 + [[1, 1]] * 980)
    monkeypatch.setattr(analysis, "cluster_weights", lambda *args, **kwargs: draws)
    ablation = "egpot_no_pareto"
    methods = {analysis.FULL: [metric(1), metric(0)], ablation: [metric(0)] * 2,
               "other": [metric(0)] * 2}
    adjusted, exploratory, _ = analysis.bootstrap(
        methods, [("a", "x"), ("a", "y")], [(analysis.FULL, ablation), (analysis.FULL, "other")],
        ["other"], confirmatory=True, resamples=1000)
    assert adjusted["hit_rate"] == {"difference": 0.5, "interval": [0, 1],
                                    "confidence_level": 1 - 0.05 / 7, "analysis_type": "confirmatory"}
    for effect in (adjusted["mean_recall"], exploratory["hit_rate"]):
        assert effect == {"difference": 0.5, "interval": [0.5, 0.5],
                          "confidence_level": 0.95, "analysis_type": "exploratory"}


def write(path, value):
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


@pytest.fixture
def synthetic(tmp_path):
    def spec(budgets, seed=0):
        return {"class": "Synthetic", "config": {"seed": seed},
                "choke_point": True, "budgets": list(budgets)}

    configs = {
        # Intentionally append tiebreak out of alphabetical order before serialization.
        "main": {name: spec((10, 20, 40)) for name in (*FINAL_METHODS, "egpot_full_tiebreak")},
        "choke": {off: spec((20, 40)) for _, off in analysis.CHOKE_PAIRS if off not in FINAL_METHODS},
        "seeds": {name: {str(seed): spec((20, 40), seed) for seed in range(6)}
                  for name in ("egpot_full_mcts", "egpot_full_tiebreak", "egpot_no_pareto_mcts",
                               "mcts_standard", "mcts_standard_no_choke")},
        "weights": {name: spec((10, 20)) for name in locked.weight_experiment_vectors()},
        "pareto_reference": spec((10, 20)),
    }
    prereg = tmp_path / "preregistration.md"
    prereg.write_text("Synthetic preregistration", encoding="utf-8")
    registry, paths = {}, []
    for app in locked.DSB_DATASETS:
        repo = locked.Repo(tmp_path / (app + ".graphml"), tmp_path / (app + ".graph.provenance.json"),
                           tmp_path / (app + ".labels.json"), tmp_path / (app + ".labels.provenance.json"),
                           prereg)
        registry[app] = repo
        repo.graph.write_text("bytes for hashing only", encoding="utf-8")
        labels = [{"id": f"q{i}", "link_id": f"link{i}", "type": kind, "query": "synthetic",
                   "start_node": "root", "gold_nodes": ["answer"], "gold_path": ["root", "answer"],
                   "lookalike_nodes": lookalikes}
                  for i, (kind, lookalikes) in enumerate(
                      (("explicit", ["root"]), ("indirect", ["also", "absent", "maybe"]),
                       ("explicit", ["absent"])))]
        write(repo.labels, labels)
        graph_hash = locked.sha256(repo.graph)
        label_hash = locked.sha256(repo.labels)
        write(repo.provenance, {"graphml_sha256": graph_hash})
        write(repo.label_provenance, {"graphml_sha256": graph_hash, "query_file_sha256": label_hash})
        jobs, aliases = locked.plan_locked(labels, configs)
        by_key = {job["key"]: job for job in jobs}
        rows, latencies = [], []
        for alias in aliases:
            job = by_key[alias["key"]]
            label = job["label"]
            hit = int(job["method"] in {"egpot_full", "egpot_no_entropy"} and label["id"] == "q0")
            row = metric(hit)
            returned = (["root", "maybe", "also", "filler"] if label["id"] == "q1" else
                        ["root", "filler", "answer" if hit else "extra", "last"])
            latencies.append({"job": alias["key"], "latency_s": row.pop("latency_s")})
            rows.append({**row, **{key: label[key] for key in ("id", "link_id", "type")},
                         **{key: alias[key] for key in ("experiment", "split", "seed")},
                         "method": job["method"], "node_budget": job["budget"],
                         "gold_found": ["answer"] if hit else [], "returned_nodes": returned})
        path = tmp_path / (app + ".result.json")
        write(path, {"schema": locked.DSB_RESULT_SCHEMA, "repo": app, "split": "all", "commit": "fake",
                  "identity": {"commit": "fake", "graph": graph_hash, "labels": label_hash,
                               "protocol_sha256": locked.digest(configs),
                               "verified_hashes": {"graph": graph_hash, "labels": label_hash,
                                                    "preregistration": locked.sha256(prereg)}},
                  "configs": configs, "rows": rows, "latencies": latencies,
                  "deterministic_sha256": locked.digest(rows)})
        paths.append(path)
    return paths, registry


def test_end_to_end_synthetic_report(synthetic):
    paths, registry = synthetic
    report = analysis.analyze(*paths, registry=registry)
    assert report["bootstrap"]["seed"] == 0
    assert report["bootstrap"]["resamples"] == 10_000
    assert report["bootstrap"]["confirmatory_tail_probability"] == 0.05 / 14
    assert report["primary"] == {"method": analysis.FULL, "scope": "pooled", "budget": 40,
                                 "metric": "hit_count", "rate_field": "hit"}
    primary, exploratory = report["claims"][:7], report["claims"][7:]
    assert [row["id"] for row in primary] == [f"C{i}" for i in range(1, 8)]
    assert [(r["left"], r["right"]) for r in primary] == [
        ("egpot_full", "strongest_baseline"), ("egpot_full", "egpot_no_pareto"),
        ("egpot_full", "egpot_no_entropy"), ("egpot_full", "egpot_no_contracts"),
        ("egpot_full", "egpot_no_choke_point"), ("egpot_full_mcts", "egpot_full"),
        ("egpot_full_tiebreak", "egpot_full")]
    assert all(r["scope"] == "pooled" and r["budget"] == 40 and r["metric"] == "hit_rate"
               and r["analysis_type"] == "confirmatory" for r in primary)
    assert [r["verdict"] for r in primary] == [
        "supported", "supported", "not supported", "supported", "supported",
        "significantly worse", "significantly worse"]
    assert all(r["analysis_type"] == "exploratory" and r["confidence_level"] == 0.95
               and "verdict" not in r for r in exploratory)
    assert any((r["left"], r["right"]) == ("egpot_no_pareto_mcts", "egpot_no_pareto")
               for r in exploratory)
    for name, n in (("dsb_social", 3), ("dsb_media", 3), ("pooled", 6)):
        tables = report["tables"][name]
        assert len(tables["descriptive"]) == 48
        full40 = next(r for r in tables["descriptive"] if r["method"] == analysis.FULL and r["budget"] == 40)
        assert full40["n"] == n and full40["hit_count"] == n // 3
        assert full40["latency_s"] == pytest.approx(1.3 / 3)
        assert len(tables["seeds"]) == 10
        assert all(r["primary_seed"] == 0 and r["metrics"]["hit"]["defined_seeds"] == 6
                   for r in tables["seeds"])
        assert all(r["vectors"] == r["below"] == 54 for r in tables["weights"])
        assert len(tables["choke"]) == 14
    assert {r["id"]: r["lookalike_returned"] for r in report["failures"] if r["method"] == "bfs"} == {
        "q0": True, "q1": True, "q2": False}
    assert {r["id"]: r["returned_lookalike_nodes"] for r in report["failures"] if r["method"] == "bfs"} == {
        "q0": ["root"], "q1": ["maybe", "also"], "q2": []}
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize("which,match", [
    ("graph", "Graph SHA256 mismatch"), ("labels", "Labels SHA256 mismatch"),
    ("preregistration", "preregistration hash mismatch")])
def test_refuses_tampered_inputs(synthetic, which, match):
    paths, registry = synthetic
    getattr(registry["dsb_social"], which).write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        analysis.analyze(*paths, registry=registry)


def test_old_schema_is_rejected_before_reading_inputs(synthetic, monkeypatch):
    paths, registry = synthetic
    write(paths[0], {"schema": 1, "repo": "dsb_social", "split": "all"})
    monkeypatch.setattr(locked, "verify_inputs", lambda *args: pytest.fail("read benchmark inputs"))
    with pytest.raises(ValueError, match="schema 2 with ordered returned_nodes is required"):
        analysis.analyze(*paths, registry=registry)


def test_schema_two_requires_returned_nodes_on_every_row(synthetic):
    paths, registry = synthetic
    record = locked.read_json(paths[0])
    del record["rows"][0]["returned_nodes"]
    record["deterministic_sha256"] = locked.digest(record["rows"])
    write(paths[0], record)
    with pytest.raises(ValueError, match="requires an ordered returned_nodes list"):
        analysis.analyze(*paths, registry=registry)


def test_reordering_returned_nodes_invalidates_the_digest(synthetic):
    paths, registry = synthetic
    record = locked.read_json(paths[0])
    record["rows"][0]["returned_nodes"].reverse()
    write(paths[0], record)
    with pytest.raises(ValueError, match="row digest mismatch"):
        analysis.analyze(*paths, registry=registry)


@pytest.mark.parametrize("modified,tag", [
    ("thrift_bindings.py", locked.DSB_BUILDER_TAG), ("eg_pot.py", locked.DSB_EGPOT_TAG)])
def test_locked_preflight_refuses_frozen_code_changes_before_inputs(tmp_path, monkeypatch, modified, tag):
    prereg = tmp_path / "preregistration.md"
    prereg.touch()
    repo = replace(locked.REGISTRY["dsb_social"], preregistration=prereg)
    head = "a" * 40
    expected_refs = {f"refs/tags/{name}^{{commit}}": pin for name, pin in (
        locked.DSB_BUILDER_TAG, locked.DSB_EGPOT_TAG)}

    def fake_git(*args, root):
        if args[0] in {"status", "ls-files"}:
            return ""
        if args == ("rev-parse", "HEAD"):
            return head
        if args[:2] == ("rev-parse", "--verify"):
            return expected_refs[args[2]]
        assert args[0] == "diff"
        pin, commit = args[5:7]
        assert commit == head
        paths = args[8:]
        assert paths == (locked.DSB_BUILDER_PATHS if pin == locked.DSB_BUILDER_TAG[1]
                         else ("eg_pot.py",))
        return modified if pin == tag[1] else ""

    monkeypatch.setattr(locked, "git", fake_git)
    monkeypatch.setattr(locked, "verify_inputs", lambda *args: pytest.fail("read benchmark inputs"))
    with pytest.raises(ValueError, match=tag[0]):
        locked.locked_preflight("dsb_social", repo, tmp_path, root=tmp_path)
