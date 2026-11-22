"""One reserved, preregistered exploratory second look per historical test cohort."""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys

import networkx as nx

from bench import egpot_eval as ev, egpot_multi_eval as locked, egpot_width_sweep_dev as dev
from bench.analyze_dsb_distance import gold_depth
from eg_pot import EGPOTConfig, GraphView, QueryScorer

ROOT = locked.ROOT
RESULTS = ROOT / "bench/results"
PLAN = Path("bench/preregistration_test_splits.md")
FREEZE_TAG = "egpot-test-prereg-v1"
FREEZE = "04a4c985b6e681e4dcfff98c113aedf58ce75e99"
RESULT_TAG = "egpot-test-locked-v1"
STATUS = "second look, exploratory"
DEV_INPUT_SHA256 = "c613d19b4bf102940d259296222e822136bc07750fb762fd72cd3ee639b3cf7d"
PRIOR = {
    "online_boutique": ("test_final_41d61e11.json",
                        "125ceb6af5f11955d0161d83eed806c2d5f2f200976c83071cdfd17bd47934db"),
    "train_ticket": ("train_ticket_final_0545478c.json",
                     "9a893d884f3af3f38459772f6bc8b8dc41b25fcb933e6336c7ecf61804811373"),
}
TEST_LINKS = (2, 3, 6, 7, 8, 10, 12)
BUDGETS = (10, 20, 40)
FULL = "egpot_full_w4"
EGPOT = (
    "egpot_full_w4", "egpot_full_w12", "egpot_no_pareto_w4", "egpot_no_pareto_w12",
    "egpot_full_tiebreak_w4", "egpot_full_tiebreak_w12", "egpot_full_mcts_w4",
    "egpot_no_entropy_w4", "egpot_no_contracts_w4", "egpot_no_choke_point_w4",
)
BASELINES = ("vector_topk", "bfs", "greedy_walk", *(f"vector_bfs_k{k}" for k in range(2, 6)),
             "ppr", "scalar_beam", "community_graphrag", "mcts_standard")
CHOKE = tuple((on, off) for on, off in ev.CHOKE_PAIRS if off.endswith("_no_choke"))
SEEDED = ("egpot_full_tiebreak_w4", "egpot_full_tiebreak_w12", "egpot_full_mcts_w4",
          "mcts_standard", "mcts_standard_no_choke")


def result_name(app):
    return f"test_splits_{app}_secondlook.json"


def preflight(app, *, acknowledge, root=ROOT):
    if not acknowledge or app not in PRIOR:
        raise ValueError("Explicit second-look acknowledgement and a registered dataset are required")
    output_dir = root / "bench/results"
    output = output_dir / result_name(app)
    if output.exists() or locked.git("tag", "--list", RESULT_TAG, root=root):
        raise ValueError(f"Attempt already consumed for {app}")
    if not (root / PLAN).is_file():
        raise ValueError("Missing test-split preregistration")
    try:
        locked.git("ls-files", "--error-unmatch", PLAN.as_posix(), root=root)
        tag_commit = locked.git("rev-parse", f"{FREEZE_TAG}^{{commit}}", root=root)
    except subprocess.CalledProcessError as exc:
        raise ValueError("A tracked and tagged preregistration is required") from exc
    commit = locked.git("rev-parse", "HEAD", root=root)
    if (tag_commit != FREEZE or locked.git("diff", "--name-only", FREEZE, commit, "--",
                                          PLAN.as_posix(), root=root)):
        raise ValueError("Preregistration differs from the frozen protocol")
    sibling = next(name for name in PRIOR if name != app)
    sibling_path = output_dir / result_name(sibling)
    permitted = f"?? bench/results/{sibling_path.name}"
    changes = locked.git("status", "--porcelain", "--untracked-files=all", root=root).splitlines()
    if any(line != permitted for line in changes):
        raise ValueError("Locked test run requires a clean Git tree")
    if permitted in changes:
        record = locked.read_json(sibling_path)
        if (record.get("status"), record.get("commit")) != ("complete", commit):
            raise ValueError("Unexpected sibling attempt in the working tree")
    locked.verify_dsb_frozen_code(commit, root=root)
    if locked.git("diff", "--name-only", "egpot-dsb-locked-v1", commit, "--", "eg_pot.py", root=root):
        raise ValueError("Engine differs from the frozen DeathStarBench locked tag")
    if locked.sha256(root / "bench/results" / dev.OUTPUT.name) != DEV_INPUT_SHA256:
        raise ValueError("Pinned workspace configuration capture hash mismatch")
    return commit, output


def load_test_labels(path, expected_hash):
    """Scan only split markers before decoding selected whole-link rows."""
    import hashlib
    import re

    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_hash:
        raise ValueError("Frozen test label file hash mismatch")
    selected = []
    for record in re.findall(rb"(?ms)^  \{\r?\n.*?^  \}(?=,?\r?$)", raw):
        match = re.search(rb'(?m)^    "link_id": (\d+),\r?$', record)
        if match is None:
            raise ValueError("Malformed label link marker")
        if int(match[1]) in TEST_LINKS:
            selected.append(json.loads(record))
    expected = {(link, kind) for link in TEST_LINKS for kind in ("explicit", "indirect")}
    if (len(selected) != 14 or len({row["id"] for row in selected}) != 14
            or {(row["link_id"], row["type"]) for row in selected} != expected):
        raise ValueError("Expected exactly two labelled queries per frozen test link")
    return selected


def coverage(graph, labels):
    covered, excluded, depths = [], [], {}
    view = graph.to_undirected(as_view=True)
    for label in labels:
        path = label["gold_path"]
        relations = label["path_relations"]
        error = []
        missing = {label["start_node"], *path, *label["gold_nodes"]} - graph.nodes
        if missing:
            error.extend({"missing_node": node} for node in sorted(missing))
        if len(relations) != len(path) - 1:
            raise ValueError(f"Malformed gold path for {label['id']}")
        for u, v, relation in zip(path, path[1:], relations):
            if relation.startswith("<-"):
                src, dst, name = v, u, relation[2:]
            elif relation.endswith("->"):
                src, dst, name = u, v, relation[:-2]
            else:
                raise ValueError(f"Unspecified gold path direction for {label['id']}")
            if not any(d.get("relation") == name for d in graph.get_edge_data(src, dst, default={}).values()):
                error.append({"source": src, "target": dst, "missing_relation": name})
        if error:
            excluded.append({**{k: label[k] for k in ("id", "link_id", "type")}, "failures": error})
        else:
            covered.append(label)
            distances = nx.single_source_shortest_path_length(view, label["start_node"])
            depths[label["id"]] = gold_depth([distances.get(n) for n in label["gold_nodes"]])
    return covered, excluded, depths


def configs_for(graph):
    view = GraphView(graph, edge_policy=locked.DSB_EDGE_POLICY)
    scorer = QueryScorer(view)
    main = {}
    for name in EGPOT:
        base, width = name.rsplit("_w", 1)
        config = EGPOTConfig(beam_width=int(width), use_pareto=base != "egpot_no_pareto",
                             use_mcts=base in ("egpot_full_mcts", "egpot_full_tiebreak"),
                             use_entropy=base != "egpot_no_entropy", use_contracts=base != "egpot_no_contracts",
                             lookahead_mode="tiebreak" if base == "egpot_full_tiebreak" else "blend")
        engine = ev.EGPOTRetriever(config, view, scorer, use_choke_point=base != "egpot_no_choke_point")
        main[name] = ev._final_config(name, engine, BUDGETS)
    for name, engine in ev.make_comparison_retrievers(view, scorer, method_names=BASELINES).items():
        if isinstance(engine, ev.VectorBFS):
            spec = ev._final_config("vector_bfs_k2", engine, BUDGETS)
            spec["config"]["k"] = engine.k
        else:
            spec = ev._final_config(name, engine, BUDGETS)
        main[name] = spec
    fairness = ev.make_fairness_retrievers(view, scorer)
    choke = {off: ev._final_config(off, fairness[off], (20, 40)) for _, off in CHOKE}
    seeds = {}
    for name in SEEDED:
        spec = (main | choke)[name]
        seeds[name] = {str(seed): locked._override_config(spec, seed=seed) for seed in range(6)}
    policy = locked.DSB_EDGE_POLICY
    return {"main": main, "choke": choke, "seeds": seeds, "weights": {},
            "edge_policy": {"excluded_relations": sorted(policy.excluded_relations),
                            "no_contract_match_relations": sorted(policy.no_contract_match_relations),
                            "entropy_over_eligible_only": policy.entropy_over_eligible_only}}


def setup_worker(graph):
    sys.addaudithook(dev.guard)
    locked._VIEW = GraphView(graph, edge_policy=locked.DSB_EDGE_POLICY)
    locked._SCORER = QueryScorer(locked._VIEW)
    locked._ENGINES = {}


def execute_test_job(task):
    key, result = locked.execute_job(task, include_returned_nodes=True)
    config = task["spec"]["config"]
    width = config.get("beam_width") if task["spec"]["class"] == "EGPOTRetriever" else None
    if task["method"] in EGPOT and width != int(task["method"].rsplit("_w", 1)[1]):
        raise ValueError("Method ID conflicts with beam width")
    result["deterministic"]["beam_width"] = width
    return key, result


def run_workers(graph, jobs, workers):
    output = {}
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=workers, mp_context=context, initializer=setup_worker,
                             initargs=(graph,)) as pool:
        tasks = [pool.submit(execute_test_job, task) for task in jobs]
        for i, future in enumerate(as_completed(tasks), 1):
            key, result = future.result()
            output[key] = result
            if i % 200 == 0 or i == len(tasks):
                print(f"TEST SECOND LOOK {i}/{len(tasks)} jobs", flush=True)
    return output


def reserve(path, header):
    try:
        with path.open("x", encoding="utf-8") as stream:
            json.dump({**header, "status": "reserved"}, stream, sort_keys=True)
    except FileExistsError as exc:
        raise ValueError("Attempt already consumed") from exc


def run(app, *, workers, acknowledge):
    commit, path = preflight(app, acknowledge=acknowledge)
    if workers < 1 or os.environ.get("PYTHONHASHSEED") != "0" or not sys.dont_write_bytecode:
        raise ValueError("Requires positive worker count, PYTHONHASHSEED=0 and python -B")
    reference = locked.read_json(dev.OUTPUT)["datasets"][app]
    source, revision = dev.SOURCES[app]
    git_prefix = ["git", "-c", f"safe.directory={source.as_posix()}", "-C", str(source)]
    if (subprocess.check_output([*git_prefix, "rev-parse", "HEAD"], text=True).strip() != revision
            or subprocess.check_output([*git_prefix, "status", "--porcelain"], text=True).strip()
            or revision != reference["source_revision"]):
        raise ValueError("Source workspace is not clean at the frozen revision")
    labels_path = locked.REGISTRY[app].labels
    guarded = False

    def audit(event, args):
        if guarded:
            dev.guard(event, args)

    sys.addaudithook(audit)
    guarded = True
    try:
        graph, graph_hash = dev.build(app, reference["workspace"])
        if graph_hash != reference["graphml_sha256"]:
            raise ValueError("In-memory GraphML SHA-256 differs from the freeze")
        labels = load_test_labels(labels_path, reference["label_file_sha256"])
        included, excluded, depths = coverage(graph, labels)
        if not included:
            raise ValueError("No covered test queries")
        configs = configs_for(graph)
    finally:
        guarded = False
    hashes = {"graph": graph_hash, "labels": reference["label_file_sha256"],
              "preregistration": locked.sha256(ROOT / PLAN), "dev_workspace": DEV_INPUT_SHA256,
              "protocol": locked.digest(configs)}
    header = {"schema": 2, "repo": app, "split": "test", "commit": commit, "analysis_type": STATUS,
              "second_look": True, "acknowledge_second_look": acknowledge, "preregistration_commit": FREEZE,
              "test_links": TEST_LINKS, "source_revision": revision, "verified_hashes": hashes,
              "frozen_code": {"engine": locked.DSB_EGPOT_TAG[1], "builder": locked.DSB_BUILDER_TAG[1]},
              "prior_record": dict(zip(("file", "sha256"), PRIOR[app], strict=True))}
    jobs, aliases = locked.plan_locked(included, configs)
    reserve(path, header)
    print(f"{STATUS}: {app}, {len(included)} covered, {len(excluded)} excluded, {len(jobs)} jobs", flush=True)
    results = run_workers(graph, jobs, workers)
    rows, latencies = [], []
    for alias in aliases:
        key = alias["key"]
        result = results[key]
        rows.append({**result["deterministic"], "split": "test", "seed": alias["seed"],
                     "experiment": alias["experiment"]})
        latencies.append({"job": key, "latency_s": result["latency_s"]})
    if (locked.git("rev-parse", "HEAD") != commit or locked.sha256(ROOT / PLAN) != hashes["preregistration"]
            or locked.sha256(labels_path) != hashes["labels"]
            or locked.sha256(dev.OUTPUT) != hashes["dev_workspace"]):
        raise ValueError("Frozen inputs changed during the reserved attempt")
    allowed = {f"?? bench/results/{result_name(name)}" for name in PRIOR}
    if set(locked.git("status", "--porcelain", "--untracked-files=all").splitlines()) - allowed:
        raise ValueError("Git tree changed during the reserved attempt")
    payload = {**header, "status": "complete", "configs": configs, "covered_ids": sorted(depths),
               "coverage_exclusions": excluded, "gold_depths": depths, "rows": rows, "latencies": latencies,
               "deterministic_sha256": locked.digest(rows), "worker_count": workers,
               "utc_timestamp": datetime.now(timezone.utc).isoformat()}
    locked.atomic_json(path, payload)
    print(f"LOCKED SECOND LOOK RESULT: {path}", flush=True)
    return payload
