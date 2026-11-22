import json

import numpy as np
import pytest

from bench import analyze_datahub_final as analysis
from bench import egpot_multi_eval as locked
from bench.datahub_protocol import settings


def label(link, variant, start, handler, pair):
    return {"id": f"{link}-{variant}", "link_id": link, "type": variant,
            "query": "synthetic prompt", "start_node": start, "module_pair": pair,
            "gold_nodes": [f"contract:{link}", handler],
            "gold_path": [start, f"contract:{link}", handler], "lookalike_ids": ["decoy"]}


@pytest.fixture
def published_record(tmp_path):
    labels = [
        label(link, kind, start, handler, pair)
        for link, start, handler, pair in (
            ("L1", "a", "one/A.java:A.first", "pair A"),
            ("L2", "a", "two/B.java:B.second", "pair A"),
            ("L3", "b", "one/A.java:A.third", "pair B"),
            ("L4", "c", "one/A.java:A.fourth", "pair B"),
        )
        for kind in ("explicit", "indirect")
    ]
    repo = locked.Repo(*(tmp_path / name for name in
                         ("graph", "graph-meta", "labels", "label-meta", "prereg")))
    repo.graph.write_bytes(b"synthetic graph bytes")
    repo.labels.write_text(json.dumps(labels), encoding="utf8")
    repo.preregistration.write_text("Status: FROZEN\n", encoding="utf8")
    graph_hash = locked.sha256(repo.graph)
    repo.provenance.write_text(json.dumps({
        "graphml_sha256": graph_hash,
        "links": [{"id": link, "status": "fully covered"} for link in ("L1", "L2", "L3", "L4")],
    }), encoding="utf8")
    repo.label_provenance.write_text(json.dumps({
        "graphml_sha256": graph_hash, "query_file_sha256": locked.sha256(repo.labels),
    }), encoding="utf8")
    configs = settings()
    jobs, aliases = locked.plan_locked(labels, configs)
    by_key = {job["key"]: job for job in jobs}
    rows, latencies = [], []
    for alias in aliases:
        job = by_key[alias["key"]]
        source = job["label"]
        method = job["method"]
        hit = int(method in (analysis.FULL, analysis.WIDE))
        returned = [source["start_node"], source["gold_nodes"][0],
                    source["gold_nodes"][1] if hit else "decoy"]
        rows.append({**{key: source[key] for key in ("id", "link_id", "type")},
                     **{key: alias[key] for key in ("experiment", "split", "seed")},
                     "node_budget": job["budget"], "method": method,
                     "returned_nodes": returned, "nodes_returned": len(returned),
                     "gold_found": source["gold_nodes"][:hit + 1],
                     "hit": hit, "gold_recall": (hit + 1) / 2, "precision": (hit + 1) / 3,
                     "path_coverage": (hit + 2) / 3, "ordered_path_match": hit,
                     "nodes_to_hit": 3 if hit else None, "precision_at_hit": 2 / 3 if hit else None})
        latencies.append({"job": alias["key"], "latency_s": 0.01})
    hashes = {**locked.verify_inputs(repo), "preregistration": locked.sha256(repo.preregistration)}
    payload = {
        "repo": "datahub", "split": "all", "schema": 2, "commit": "synthetic",
        "second_look": False, "previous_results": [], "configs": configs, "rows": rows,
        "deterministic_sha256": locked.digest(rows), "latencies": latencies,
        "identity": {**hashes, "verified_hashes": hashes, "commit": "synthetic",
                     "protocol_sha256": locked.digest(configs)},
    }
    path = tmp_path / "result.json"
    path.write_text(json.dumps(payload), encoding="utf8")
    return path, repo


def test_full_report_on_synthetic_locked_rows(published_record):
    path, repo = published_record
    result = analysis.analyze(path, repo=repo)
    assert result == analysis.analyze(path, repo=repo)
    assert [(r["id"], r["difference"], r["verdict"]) for r in result["confirmatory"]] == [
        ("C1", 1, "supported"), ("C2", 1, "supported"),
        ("C3", 0, "not supported"), ("C4", 1, "supported"),
    ]
    assert result["bootstrap"]["resamples"] == 10_000
    assert result["bootstrap"]["seed"] == 0
    assert result["bootstrap"]["confirmatory_tail_probability"] == 0.05 / 8
    assert all(r["clusters"] == 3 and r["confidence_level"] == 1 - 0.05 / 4
               for r in result["confirmatory"])
    assert all(r["clusters"] == 2 and r["confidence_level"] == 0.95
               and r["analysis_type"] == "exploratory" and "verdict" not in r
               for r in result["handler_class_sensitivity"])
    assert set(result["descriptive"]) == {"pooled", "pair A", "pair B"}
    pooled = result["descriptive"]["pooled"]
    assert all(row["vectors"] == 54 and row["below"] == 54 and row["pareto_hits"] == 8
               for row in pooled["weights"])
    assert next(row for row in pooled["compactness"] if row["left"] == analysis.FULL
                and row["right"] == analysis.WIDE)["both_hit_n"] == 8
    assert next(r for r in pooled["seed_spread"] if r["method"] == "mcts_standard")[
        "spread"]["nodes_to_hit"] == {"min": None, "median": None, "max": None, "defined_seeds": 0}
    assert result["lookalike_failure_analysis"]["failures"][0]["returned_lookalike_nodes"] == ["decoy"]


def test_reselect_baseline_and_weight_queries_inside_each_draw():
    first = label("L1", "explicit", "a", "one/A.java:A.first", "pair")
    second = label("L2", "explicit", "b", "one/A.java:A.second", "pair")
    third = label("L2", "indirect", "b", "one/A.java:A.second", "pair")

    def rows(hits, nodes_to_hit=3):
        return [{"id": lab["id"], "label": lab, "hit": hit,
                 "nodes_to_hit": nodes_to_hit if hit else None}
                for lab, hit in zip((first, second, third), hits, strict=True)]

    methods = {name: rows([0, 0, 0]) for name in analysis.BASELINES}
    methods.update({analysis.FULL: rows([0, 1, 1]), analysis.WIDE: rows([1, 1, 1]),
                    "bfs": rows([0, 1, 1]), "ppr": rows([1, 0, 0]),
                    "greedy_walk": rows([0, 1, 1], 2), "vector_topk": rows([0, 1, 1], 2),
                    "egpot_no_contracts_w4": rows([0, 0, 0])})
    c1, c2, c3, _ = analysis.paired_contrasts(
        {10: methods, 40: methods}, cluster_by=lambda lab: lab["start_node"])
    assert c1["observed_comparator"] == "greedy_walk"
    assert c1["interval"] == [-1, 0]  # ppr wins when only the first cluster is drawn
    assert c2["difference"] == pytest.approx(1 / 3)
    assert c3["difference"] == pytest.approx(-1 / 3)
    weights = analysis.cluster_weights([("DataHub", "a"), ("DataHub", "b"), ("DataHub", "b")])
    assert np.array_equal(weights[:, 1], weights[:, 2])


@pytest.mark.parametrize("changed", ["label", "preregistration", "digest"])
def test_refuses_changed_inputs_or_rows(published_record, changed):
    path, repo = published_record
    if changed == "label":
        with repo.labels.open("a", encoding="utf8") as stream:
            stream.write(" ")
    elif changed == "preregistration":
        with repo.preregistration.open("a", encoding="utf8") as stream:
            stream.write("Changed plan\n")
    else:
        data = json.loads(path.read_bytes())
        data["rows"][0]["returned_nodes"].reverse()
        path.write_text(json.dumps(data), encoding="utf8")
    with pytest.raises(ValueError, match="mismatch"):
        analysis.analyze(path, repo=repo)
