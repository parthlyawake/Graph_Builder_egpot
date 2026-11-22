"""Run the frozen DataHub methods on the Suite 2 input and retain raw discovery orders."""

import argparse
import json
import math
import sys
from pathlib import Path
from unittest.mock import patch

from bench import egpot_multi_eval as runner
from bench.datahub_protocol import settings
from bench.egpot_width_sweep_dev import guard

ROOT = Path(__file__).resolve().parents[1]
FREEZE = "ad7c5516eb672da706a8ae9329fe32fee4192bba"
TAG = "egpot-suite2-prereg-v1"
PROTOCOL = "8f5e6aa3715a3a26ca15724278f624297252fad00593f1b3130459634eefda2d"
INPUTS = {
    "bench/labels_draft/suite2_exploratory_manifest.md": "4aa894680781a9b5b48635020a3b5a77e6321bfbcc5a3d57e6390be515f75fa0",
    "bench/suite2_queries.json": "92030da2c50e38b4ec31b22eba29f50ab3aa133205c997b42f7a2db34bfe10ec",
    "bench/preregistration_suite2.md": "83d8fdd6a2fb505ea8d2339f957c200f2aa235a90fe97aa8b3fb4ad36756d013",
    "bench/results/datahub_graph_v3.graphml": "041015fba8ab3baa7cc883955fcc700e344839b50d72359e072b2bcf43ebfeb0",
    "bench/results/dsb_social_graph.graphml": "7a9a9b9941edd62ae8ca78c556ca5361e3a22fd583c2ce61b26833dcb8d00ae9",
    "bench/results/dsb_media_graph.graphml": "96868d204874b6c2bbbba6c3b0399b45b74857f61e472b0ef19ef7ea23efb671",
}
PHASES = {
    "dsb_social": ("DSB Social", "bench/results/dsb_social_graph.graphml", 2034),
    "dsb_media": ("DSB Media", "bench/results/dsb_media_graph.graphml", 4068),
    "datahub": ("DataHub", "bench/results/datahub_graph_v3.graphml", 6780),
}
RESULT_KEY = ("link_id", "wording", "budget", "method", "seed")
UNMODIFIED = (
    "eg_pot.py", "bench/egpot_eval.py", "bench/egpot_multi_eval.py", "bench/egpot_test_splits.py",
    "bench/datahub_protocol.py", "bench/analyze_suite2.py",
)


def verify_frozen():
    if runner.git("rev-parse", f"{TAG}^{{commit}}") != FREEZE:
        raise ValueError("Suite 2 freeze tag does not match its commit")
    head = runner.git("rev-parse", "HEAD")
    if runner.git("diff", "--name-only", TAG, head, "--", *UNMODIFIED):
        raise ValueError("Frozen method or scoring code has changed")
    # The supervisor appends operational events between attempts.
    dirty = set(runner.git("diff", "--name-only", "HEAD").splitlines())
    if (dirty - {"bench/results/suite2_deviations_ad7c5516.jsonl"}
            or runner.git("diff", "--cached", "--name-only")):
        raise ValueError("Tracked checkout is dirty")
    hashes = {name: runner.sha256(ROOT / name) for name in INPUTS}
    if hashes != INPUTS:
        raise ValueError("Suite 2 frozen input hashes differ")
    configs = settings()
    if runner.digest(configs) != PROTOCOL:
        raise ValueError("Method configuration hash differs from locked DataHub")
    return head, configs, hashes


def plan(phase, config, queries):
    repo, _, expected = PHASES[phase]
    variants = {(method, 0): spec for section in ("main", "choke", "weights")
                for method, spec in config[section].items()}
    for method, seeds in config["seeds"].items():
        for seed, spec in seeds.items():
            variants[method, int(seed)] = spec

    jobs = []
    for (method, seed), spec in variants.items():
        for case in queries:
            if case["repo"] != repo:
                continue
            for wording in ("explicit", "indirect"):
                for budget in case["budgets"]:
                    effective = runner.spec_at(spec, budget)
                    if "effective_configs" in spec and str(budget) not in spec["effective_configs"]:
                        effective = {
                            **effective, "config": {**effective["config"], "node_budget": budget}
                        }
                    task = {
                        "link_id": case["link_id"], "wording": wording, "budget": budget,
                        "method": method, "seed": seed, "spec": effective,
                        "label": {"id": f"{case['link_id']}_{wording}", "start_node": case["start_id"],
                                  "query": case[f"{wording}_query"]},
                    }
                    jobs.append({**task, "key": runner.digest(task)})
    keys = {tuple(task[field] for field in RESULT_KEY) for task in jobs}
    if len(jobs) != expected or len(keys) != expected:
        raise ValueError(f"{phase}: unexpected job count or duplicate identities")
    return jobs


_initialize = runner.initialize_worker


def initialize_worker(graph, edge_policy, datahub):
    if not datahub:
        sys.addaudithook(guard)
    _initialize(graph, edge_policy, datahub)


def execute_job(task, *, include_returned_nodes=True, datahub=False):
    key = runner.digest({"method": task["method"], "spec": task["spec"]})
    if key not in runner._ENGINES:
        runner._ENGINES[key] = runner.make_engine(task["method"], task["spec"])
    engine = runner._ENGINES[key]
    label = task["label"]
    if isinstance(engine, runner.StandardMCTS):
        engine.query_ids = {(label["query"], label["start_node"]): label["id"]}
    result = engine.retrieve(query=label["query"], start_node=label["start_node"],
                             node_budget=task["budget"])
    visited = result.visited
    discovery = list(result.discovery_order)
    if (label["start_node"] not in visited or len(visited) > task["budget"]
            or len(discovery) != len(visited) or set(discovery) != visited
            or not set(result.ordered_path) <= visited
            or (not isinstance(engine, runner.frozen.VectorTopK)
                and discovery[0] != label["start_node"])
            or not math.isfinite(result.latency_s) or result.latency_s < 0):
        raise ValueError(f"{task['method']} violated the locked result invariants")
    row = {field: task[field] for field in RESULT_KEY}
    row["returned_nodes"] = discovery
    return task["key"], {"deterministic": row, "latency_s": result.latency_s}


def run(phase, workers, checkpoint, resume, output, pool=None):
    head, configs, hashes = verify_frozen()
    queries = runner.read_json(ROOT / "bench/suite2_queries.json")
    jobs = plan(phase, configs, queries)
    if output.exists():
        raise FileExistsError(output)
    identity = {"commit": head, "preregistration": FREEZE, "phase": phase,
                "inputs": hashes, "protocol_sha256": PROTOCOL}
    print(f"SUITE2 {phase} workers={workers} calls={len(jobs)} resume={resume}", flush=True)
    with patch.object(runner, "execute_job", execute_job), patch.object(
        runner, "initialize_worker", initialize_worker
    ), patch.object(runner, "ProcessPoolExecutor", pool or runner.ProcessPoolExecutor):
        results = runner.run_jobs(
            ROOT / PHASES[phase][1], jobs, checkpoint, identity, workers=workers, resume=resume,
            edge_policy=runner.DSB_EDGE_POLICY, include_returned_nodes=True, datahub=phase == "datahub",
        )
    rows = [results[task["key"]]["deterministic"] for task in jobs]
    if any(tuple(row[field] for field in RESULT_KEY) != tuple(task[field] for field in RESULT_KEY)
           for row, task in zip(rows, jobs, strict=True)):
        raise ValueError("Returned rows differ from the planned job identities")
    runner.atomic_json(output, {"schema": 1, "repo": PHASES[phase][0], "identity": identity,
                                "rows": rows, "rows_sha256": runner.digest(rows)})


def main(argv=None, *, pool=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, choices=PHASES)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.workers <= 4:
        parser.error("Use 1–4 workers")
    run(args.phase, args.workers, args.checkpoint, args.resume, args.out, pool)


if __name__ == "__main__":
    main()
