"""Repo-neutral orchestration of the unchanged frozen retrieval implementation.

No experiment is run at import time. Train labels are used only by run-locked;
smoke reads their start IDs solely to exclude those nodes from synthetic probes.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import multiprocessing
import os
from pathlib import Path
import platform
from statistics import fmean, median
import subprocess
import tempfile
from time import perf_counter

import networkx as nx

from eg_pot import LEGACY, EGPOTConfig, GraphView, QueryScorer
from bench import egpot_eval as frozen
from bench.egpot_eval import (EGPOTRetriever, VectorTopK, BFS, GreedyWalk,
    VectorBFS, StandardMCTS, metrics, evaluate, summarize, split_by_link,
    ablation_configs, weight_experiment_vectors, _final_config)

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "bench/results/test_final_41d61e11.json"
SCRATCH = Path(r"C:\dev\triage_out\step27")
DSB_DATASETS = ("dsb_social", "dsb_media")
DSB_BUILDER_TAG = ("egpot-bench-builder-v1", "94aae7b8aef08ac2beddcbc7fc37a7e2b2cc69ce")
DSB_EGPOT_TAG = ("egpot-tiebreak-v1", "f3d3163eec15c3e814302fb8269cd3fbca6430a1")
DSB_BUILDER_PATHS = (":(top,glob)*.py", ":(top,exclude)eg_pot.py", "contracts/",
                     "pyproject.toml", ":(top,glob)requirements*.txt")
DSB_EDGE_POLICY = replace(LEGACY, no_contract_match_relations=frozenset(
    {"ACCEPTS_SCHEMA", "RETURNS_SCHEMA", "INVOKES", "POSSIBLE_HTTP_TARGET"}))


@dataclass(frozen=True)
class Repo:
    graph: Path
    provenance: Path
    labels: Path
    label_provenance: Path
    preregistration: Path | None = None


REGISTRY = {
    "online_boutique": Repo(
        ROOT / "bench/results/online_boutique_graph_fresh.graphml",
        ROOT / "bench/results/online_boutique_graph_fresh.provenance.json",
        ROOT / "bench/labels/online_boutique_egpot_queries.json",
        ROOT / "bench/labels/online_boutique_egpot_queries.provenance.json"),
    "train_ticket": Repo(
        ROOT / "bench/results/train_ticket_graph.graphml",
        ROOT / "bench/results/train_ticket_graph.provenance.json",
        ROOT / "bench/labels/train_ticket_egpot_queries.json",
        ROOT / "bench/labels/train_ticket_egpot_queries.provenance.json",
        ROOT / "bench/preregistration_train_ticket.md"),
    **{name: Repo(
        ROOT / f"bench/results/{name}_graph.graphml",
        ROOT / f"bench/results/{name}_graph.provenance.json",
        ROOT / f"bench/labels/{name}_egpot_queries.json",
        ROOT / f"bench/labels/{name}_egpot_queries.provenance.json",
        ROOT / "bench/preregistration_dsb.md") for name in DSB_DATASETS},
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def git(*args, root=ROOT):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def load_settings(path=SETTINGS):
    """Use the record's config section, never its test-query results."""
    configs = read_json(path)["configs"]
    required = {"main", "choke", "seeds", "weights", "pareto_reference", "protocol"}
    if set(configs) != required:
        raise ValueError("Unexpected frozen config sections")
    # Reuse the existing config builder, and refuse a changed weight protocol.
    if canonical(configs["protocol"]["weight_vectors"]) != canonical(weight_experiment_vectors()):
        raise ValueError("Frozen weight builder differs from the saved protocol; no tuning allowed")
    return configs


def print_settings(configs):
    print("SETTINGS SOURCE:", SETTINGS, flush=True)
    print(json.dumps(configs, sort_keys=True, indent=2), flush=True)


def verify_inputs(repo: Repo, *, labels=True):
    if not repo.provenance.exists():
        raise ValueError(f"Missing frozen graph provenance: {repo.provenance}; hashes cannot be invented")
    expected = read_json(repo.provenance)["graphml_sha256"]
    graph_hash = sha256(repo.graph)
    if graph_hash != expected:
        raise ValueError("Graph SHA256 mismatch")
    hashes = {"graph": graph_hash}
    if labels:
        if not repo.label_provenance.exists():
            raise ValueError(f"Missing label provenance: {repo.label_provenance}")
        label_meta = read_json(repo.label_provenance)
        hashes["labels"] = sha256(repo.labels)
        if hashes["labels"] != label_meta["query_file_sha256"]:
            raise ValueError("Labels SHA256 mismatch")
        if label_meta["graphml_sha256"] != graph_hash:
            raise ValueError("Labels refer to another graph hash")
    return hashes


def verify_dsb_frozen_code(commit, *, root=ROOT):
    """Compare committed file bytes with the pinned builder and EG-POT trees."""
    for (tag, pin), paths in ((DSB_BUILDER_TAG, DSB_BUILDER_PATHS), (DSB_EGPOT_TAG, ("eg_pot.py",))):
        if git("rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}", root=root) != pin:
            raise ValueError(f"Frozen tag {tag} does not resolve to {pin}")
        changed = git("diff", "--name-only", "--no-ext-diff", "--no-textconv", "--no-renames",
                      pin, commit, "--", *paths, root=root)
        if changed:
            raise ValueError(f"Frozen code differs from {tag}:\n{changed}")


def locked_preflight(name, repo, output_dir, *, acknowledge=False, root=ROOT):
    """All locks precede reading any label queries or building any engine."""
    dirty = git("status", "--porcelain", "--untracked-files=no", root=root)
    if dirty:
        raise ValueError("Tracked git tree is dirty:\n" + dirty)
    commit = git("rev-parse", "HEAD", root=root)
    previous = sorted(Path(output_dir).glob(f"{name}_final_*.json"))
    if previous and not acknowledge:
        raise ValueError("Run already consumed: " + ", ".join(p.name for p in previous)
                         + "; --acknowledge-second-look is required (suffix _secondlook)")
    preregistration_hash = None
    if name == "train_ticket" or name in DSB_DATASETS:
        title = "Train-Ticket" if name == "train_ticket" else name
        if repo.preregistration is None or not repo.preregistration.is_file():
            raise ValueError(f"Missing {title} preregistration")
        try:
            git("ls-files", "--error-unmatch", str(repo.preregistration), root=root)
        except subprocess.CalledProcessError as exc:
            raise ValueError(f"{title} preregistration must be tracked") from exc
        preregistration_hash = sha256(repo.preregistration)
    if name in DSB_DATASETS:
        verify_dsb_frozen_code(commit, root=root)
    hashes = verify_inputs(repo)
    if preregistration_hash is not None:
        hashes["preregistration"] = preregistration_hash
    suffix = "_secondlook" if previous else ""
    target = Path(output_dir) / f"{name}_final_{commit[:8]}{suffix}.json"
    ordinal = 2
    while target.exists():
        target = Path(output_dir) / f"{name}_final_{commit[:8]}_secondlook_{ordinal}.json"
        ordinal += 1
    if previous:
        print("WARNING: SECOND LOOK AT THE WHOLE LABELED SET; writing", target, flush=True)
    return commit, hashes, target, [str(p) for p in previous]


def spec_at(spec, budget):
    config = spec.get("effective_configs", {}).get(str(budget), spec["config"])
    return {"class": spec["class"], "config": config,
            "choke_point": spec["choke_point"]}


def job(name, spec, budget, label):
    # Gold is available for metrics but never crosses frozen.evaluate's request allowlist.
    row = {k: label[k] for k in ("id", "link_id", "type", "query", "start_node", "gold_nodes", "gold_path")}
    value = {"method": name, "spec": spec_at(spec, budget), "budget": budget, "label": row}
    return {"key": digest(value), **value}


def plan_locked(labels, configs):
    jobs, aliases = {}, []
    def add(experiment, name, spec, seed=0):
        for budget in spec["budgets"]:
            for label in labels:
                task = job(name, spec, budget, label)
                jobs[task["key"]] = task
                aliases.append({"key": task["key"], "experiment": experiment,
                                "split": "all", "seed": seed})
    for section in ("main", "choke", "weights"):
        for name, spec in configs[section].items():
            add(section, name, spec)
    for name, seeds in configs["seeds"].items():
        for seed, spec in seeds.items():
            add("seeds", name, spec, int(seed))
    if "pareto_reference" in configs:
        add("pareto_reference", "egpot_full", configs["pareto_reference"])
    return list(jobs.values()), aliases


def _override_config(spec, **changes):
    updated = {**spec, "config": {**spec["config"], **changes}}
    if "effective_configs" in spec:
        updated["effective_configs"] = {
            budget: {**config, **changes} for budget, config in spec["effective_configs"].items()}
    return updated


def dsb_settings(locked):
    """Reuse the locked matrix, adding tiebreak and extending the seed sweep."""
    main = {**locked["main"], "egpot_full_tiebreak": _override_config(
        locked["main"]["egpot_full_mcts"], lookahead_mode="tiebreak")}
    seeds = {name: {**specs, "5": _override_config(specs["0"], seed=5)}
             for name, specs in locked["seeds"].items()}
    variants = {
        "egpot_full_tiebreak": _override_config(
            locked["seeds"]["egpot_full_mcts"]["0"], lookahead_mode="tiebreak"),
        "mcts_standard_no_choke": locked["choke"]["mcts_standard_no_choke"],
    }
    for name, spec in variants.items():
        seeds[name] = {str(seed): _override_config(spec, seed=seed) for seed in range(6)}
    return {"main": main, "choke": locked["choke"], "weights": locked["weights"],
            "seeds": seeds, "pareto_reference": locked["pareto_reference"],
            "edge_policy": {"excluded_relations": sorted(DSB_EDGE_POLICY.excluded_relations),
                            "no_contract_match_relations": sorted(DSB_EDGE_POLICY.no_contract_match_relations),
                            "entropy_over_eligible_only": DSB_EDGE_POLICY.entropy_over_eligible_only}}


def dsb_seed_summary(summary):
    """Summarize each reported metric over seeds, skipping undefined hit-only means."""
    groups = defaultdict(list)
    for row in summary:
        if row["experiment"] == "seeds":
            groups[row["method"], row["budget"]].append(row)
    fields = ("hit_count", "hit", "gold_recall", "precision", "path_coverage",
              "ordered_path_match", "nodes_returned", "nodes_to_hit", "precision_at_hit", "latency_s")
    output = []
    for (method, budget), runs in sorted(groups.items()):
        stats = {}
        for field in fields:
            values = [row[field] for row in runs if row[field] is not None]
            stats[field] = {"median": median(values) if values else None,
                            "min": min(values, default=None), "max": max(values, default=None),
                            "defined_seeds": len(values)}
        output.append({"method": method, "budget": budget, "primary_seed": 0, "metrics": stats})
    return output


_VIEW = _SCORER = None
_ENGINES = {}


def initialize_worker(graph_path, edge_policy=LEGACY):
    global _VIEW, _SCORER, _ENGINES
    graph = nx.read_graphml(graph_path, force_multigraph=True)
    _VIEW = GraphView(graph, edge_policy=edge_policy)
    _SCORER = QueryScorer(_VIEW)
    _ENGINES = {}


def make_engine(name, spec):
    """Instantiate unchanged classes; validate hard-coded baseline defaults."""
    cls = getattr(frozen, spec["class"], None)
    if cls is None:
        raise ValueError(f"Unknown frozen class: {spec['class']}")
    config = spec["config"]
    if cls is EGPOTRetriever:
        return cls(EGPOTConfig(**config), _VIEW, _SCORER,
                   use_choke_point=spec["choke_point"])
    kwargs = {}
    if issubclass(cls, StandardMCTS):
        kwargs["seed"] = config["seed"]
    if issubclass(cls, VectorBFS):
        kwargs["k"] = config["k"]
    engine = cls(_VIEW, _SCORER, **kwargs)
    # _final_config's only VectorBFS key is k2; the same frozen constructor
    # also supplies k3..k5 for historical DEV regression.
    config_name = "vector_bfs_k2" if issubclass(cls, VectorBFS) else name
    actual = _final_config(config_name, engine, [1])["config"]
    if issubclass(cls, VectorBFS):
        actual = {**actual, "k": engine.k}
    if canonical(actual) != canonical(config) or engine.graph_view.use_choke_point != spec["choke_point"]:
        raise ValueError(f"Saved settings do not match unchanged frozen implementation: {name}")
    return engine


def execute_job(task):
    key = digest({"method": task["method"], "spec": task["spec"]})
    if key not in _ENGINES:
        _ENGINES[key] = make_engine(task["method"], task["spec"])
    engine = _ENGINES[key]
    # StandardMCTS hashes query ID, not prose; provide only this job's identity.
    if isinstance(engine, StandardMCTS):
        engine.query_ids = {(task["label"]["query"], task["label"]["start_node"]): task["label"]["id"]}
    row = evaluate([task["label"]], {task["method"]: engine}, task["budget"], include_found=True)[0]
    latency = row.pop("latency_s")
    return task["key"], {"deterministic": row, "latency_s": latency}


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def run_jobs(graph_path, jobs, checkpoint, identity, *, workers=1, resume=False, edge_policy=LEGACY):
    if type(workers) is not int or workers < 1:
        raise ValueError("workers must be a positive integer")
    checkpoint = Path(checkpoint)
    manifest = {"identity": identity, "jobs_sha256": digest(sorted(j["key"] for j in jobs))}
    manifest_path = checkpoint / "manifest.json"
    if manifest_path.exists():
        if not resume:
            raise ValueError("Checkpoint exists; pass --resume")
        if read_json(manifest_path) != manifest:
            raise ValueError("Resume refused: commit, hashes or planned jobs differ")
    else:
        checkpoint.mkdir(parents=True, exist_ok=True)
        atomic_json(manifest_path, manifest)
    results = {}
    for task in jobs:
        path = checkpoint / (task["key"] + ".json")
        if path.exists():
            saved = read_json(path)
            if saved["key"] != task["key"] or saved["identity_sha256"] != digest(identity):
                raise ValueError("Corrupt checkpoint identity")
            results[task["key"]] = saved["result"]
    pending = [j for j in jobs if j["key"] not in results]
    if pending:
        context = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(max_workers=workers, mp_context=context,
                                 initializer=initialize_worker,
                                 initargs=(str(graph_path), edge_policy)) as pool:
            futures = [pool.submit(execute_job, task) for task in pending]
            for index, future in enumerate(as_completed(futures), 1):
                key, result = future.result()
                atomic_json(checkpoint / (key + ".json"),
                            {"key": key, "identity_sha256": digest(identity), "result": result})
                results[key] = result
                if index % 100 == 0 or index == len(pending):
                    print(f"CHECKPOINT {len(results)}/{len(jobs)} jobs", flush=True)
    return {j["key"]: results[j["key"]] for j in jobs}


def input_identity(repo, *, settings_path=SETTINGS):
    return {"commit": git("rev-parse", "HEAD"), "graph": sha256(repo.graph),
            "labels": sha256(repo.labels), "settings": sha256(settings_path),
            "versions": {"python": platform.python_version(), **{p: version(p) for p in
                         ("networkx", "numpy", "scikit-learn")}},
            "code": {name: sha256(ROOT / name) for name in
                     ("eg_pot.py", "bench/egpot_eval.py", "bench/egpot_multi_eval.py")}}


def publish(path, payload):
    """Publish only a complete JSON, atomically and without replacing a result."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".final-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)  # atomic exclusive publication; no partial final file
    finally:
        os.unlink(temporary)


def run_locked(name, configs, *, workers, checkpoint, resume=False, acknowledge=False,
               registry=REGISTRY, output_dir=None):
    repo = registry[name]
    output_dir = Path(output_dir) if output_dir else ROOT / "bench/results"
    commit, hashes, target, previous = locked_preflight(name, repo, output_dir, acknowledge=acknowledge)
    is_dsb = name in DSB_DATASETS
    if is_dsb:
        configs = dsb_settings(load_settings())
    identity = input_identity(repo)
    identity["verified_hashes"] = hashes
    if is_dsb:
        identity["protocol_sha256"] = digest(configs)
    labels = read_json(repo.labels)  # locks have passed; whole set, no split
    jobs, aliases = plan_locked(labels, configs)
    results = run_jobs(repo.graph, jobs, checkpoint, identity, workers=workers, resume=resume,
                       edge_policy=DSB_EDGE_POLICY if is_dsb else LEGACY)
    rows, latencies = [], []
    for alias in aliases:
        result = results[alias["key"]]
        rows.append({**result["deterministic"], **{k: v for k, v in alias.items() if k != "key"}})
        latencies.append({"job": alias["key"], "latency_s": result["latency_s"]})
    grouped = defaultdict(list)
    for alias, row in zip(aliases, rows):
        grouped[(row["experiment"], row["method"], row["node_budget"], row["seed"])].append(
            {**row, "latency_s": results[alias["key"]]["latency_s"]})
    summary = []
    for (experiment, method, budget, seed), records in sorted(grouped.items()):
        stats = summarize(records)
        if is_dsb:
            stats["n"] = len(records)
            for field in ("precision", "ordered_path_match"):
                stats[field] = fmean(row[field] for row in records)
        else:
            del stats["latency_s"]
        summary.append({"experiment": experiment, "method": method, "budget": budget,
                        "seed": seed, **stats})
    payload = {"schema": 1, "repo": name, "split": "all", "commit": commit,
               "identity": identity, "configs": configs, "worker_count": workers,
               "utc_timestamp": datetime.now(timezone.utc).isoformat(),
               "versions": {"python": platform.python_version(), **{p: version(p) for p in
                            ("networkx", "numpy", "scikit-learn")}},
               "second_look": bool(previous), "previous_results": previous,
               "rows": rows, "latencies": latencies, "summary": summary,
               "deterministic_sha256": digest(rows)}
    if is_dsb:
        payload["seed_summary"] = dsb_seed_summary(summary)
    if input_identity(repo) != {k: v for k, v in identity.items()
                                if k not in {"verified_hashes", "protocol_sha256"}}:
        raise ValueError("Inputs/code/commit changed during run; final result not consumed")
    if verify_inputs(repo) != {k: v for k, v in hashes.items() if k != "preregistration"}:
        raise ValueError("Input provenance changed during run")
    if repo.preregistration and sha256(repo.preregistration) != hashes.get("preregistration"):
        raise ValueError("Preregistration changed during run")
    publish(target, payload)
    print("LOCKED RESULT:", target, flush=True)
    return payload


def read_js(path):
    # Data scripts are JSON assignments, never evaluated as JavaScript.
    return json.loads(Path(path).read_text(encoding="utf-8").split("=", 1)[1].strip().removesuffix(";"))


def historical_spec(name, budget, seed, configs):
    if name in configs["seeds"]:
        return configs["seeds"][name][str(seed)]
    for section in ("main", "choke", "weights"):
        if name in configs[section]:
            return configs[section][name]
    if name == "pareto_reference":
        return configs["pareto_reference"]
    if name.startswith("vector_bfs_k"):
        k = int(name.removeprefix("vector_bfs_k"))
        spec = json.loads(json.dumps(configs["main"]["vector_bfs_k2"]))
        spec["config"]["k"] = k
        return spec
    # Reuse frozen ablation builder for the extra historical MCTS variants.
    component = name.removeprefix("egpot_").removesuffix("_mcts")
    key = component + "(MCTS)"
    if key in ablation_configs():
        ablation = ablation_configs()[key]
        return {"class": "EGPOTRetriever", "choke_point": ablation.use_choke_point,
                "config": asdict(ablation.config), "budgets": [budget]}
    raise ValueError(f"Cannot reuse frozen settings for saved method {name}")


def saved_dev_references(configs):
    references, aggregates = [], []
    directory = ROOT / "viz/data/online_boutique"
    sources = [directory / "results.js", directory / "results_extra.js", SETTINGS]
    for path in sources:
        if path.suffix == ".js":
            data = read_js(path)
            for section in ("rows", "choke", "seeds"):
                for row in data.get(section, []):
                    references.append((str(path), row))
            aggregates.extend(data.get("weights", []))
        else:
            references.extend((str(path), row) for row in read_json(path)["rows"]
                              if row["split"] == "dev")
    print("SAVED DEV SOURCES:", *map(str, sources), sep="\n", flush=True)
    return references, aggregates


def regress_ob_dev(configs, *, workers, checkpoint, resume=False, prove_workers=4):
    repo = REGISTRY["online_boutique"]
    labels = split_by_link(read_json(repo.labels))["dev"]
    lookup = {r["id"]: r for r in labels}
    print("DEV LINKS:", sorted({r["link_id"] for r in labels}), flush=True)
    references, aggregate_refs = saved_dev_references(configs)
    jobs, comparisons = {}, []
    def add(name, budget, seed, label):
        spec = historical_spec(name, budget, seed, configs)
        task = job("egpot_full" if name == "pareto_reference" else name, spec, budget, label)
        jobs[task["key"]] = task
        return task["key"]
    for source, row in references:
        qid = row.get("id", row.get("query_id"))
        if qid not in lookup:
            raise ValueError(f"Non-DEV reference refused: {qid}")
        key = add(row["method"], row.get("node_budget", row.get("budget")), row.get("seed", 0), lookup[qid])
        comparisons.append((key, source, row))
    # Historical weight data are aggregates only; rerun their DEV inputs exactly.
    weight_jobs = {}
    for reference in aggregate_refs:
        name = reference["id"]
        for field in reference:
            if field.startswith("hit_b"):
                budget = int(field.removeprefix("hit_b"))
                weight_jobs[name, budget] = [add(name, budget, 0, label) for label in labels]
    identity = input_identity(repo)
    job_list = list(jobs.values())
    a = run_jobs(repo.graph, job_list, Path(checkpoint) / f"workers{workers}", identity,
                 workers=workers, resume=resume)
    b = run_jobs(repo.graph, job_list, Path(checkpoint) / f"workers{prove_workers}", identity,
                 workers=prove_workers, resume=resume)
    parallel_mismatches = [key for key in a if a[key]["deterministic"] != b[key]["deterministic"]]
    mismatches, fields = [], 0
    for key, source, expected in comparisons:
        current = a[key]["deterministic"]
        for field, value in expected.items():
            if field == "latency_s":
                continue
            actual = ({"query_id": current["id"], "budget": current["node_budget"],
                       "n_gold": len(lookup[current["id"]]["gold_nodes"]),
                       "experiment": "main", "split": "dev", "seed": expected.get("seed", 0)}.get(field)
                      if field not in current else current[field])
            fields += 1
            if actual != value:
                mismatches.append({"source": source, "id": current["id"], "method": current["method"],
                                   "budget": current["node_budget"], "field": field,
                                   "expected": value, "actual": actual})
    aggregate_fields = 0
    for expected in aggregate_refs:
        name = expected["id"]
        for field, value in expected.items():
            if field in {"id", "weights"}:
                continue
            metric, budget = field.rsplit("_b", 1)
            values = [a[key]["deterministic"] for key in weight_jobs[name, int(budget)]]
            if metric in {"explicit_hit", "indirect_hit"}:
                kind = metric.removesuffix("_hit")
                actual = sum(r["hit"] for r in values if r["type"] == kind)
            elif metric == "hit":
                actual = sum(r["hit"] for r in values)
            elif metric == "nodes":
                actual = sum(r["nodes_returned"] for r in values) / len(values)
            else:
                raise ValueError(f"Unrecognized saved aggregate: {field}")
            aggregate_fields += 1
            if actual != value:
                mismatches.append({"source": "results_extra.js weights", "method": name,
                                   "field": field, "expected": value, "actual": actual})
    report = {"rows_compared": len(comparisons), "fields_compared": fields,
              "aggregate_rows": len(aggregate_refs), "aggregate_fields": aggregate_fields,
              "unique_jobs": len(jobs), "mismatches": mismatches,
              "worker_counts": [workers, prove_workers], "parallel_mismatches": parallel_mismatches,
              "exact_match": not mismatches, "parallel_exact_match": not parallel_mismatches}
    Path(checkpoint).mkdir(parents=True, exist_ok=True)
    atomic_json(Path(checkpoint) / "regression_report.json", report)
    print(json.dumps(report, indent=2), flush=True)
    return report


def smoke(name, configs, *, output):
    if name != "train_ticket":
        raise ValueError("Synthetic smoke is restricted to Train-Ticket")
    repo = REGISTRY[name]
    verify_inputs(repo, labels=False)
    # Only start IDs are used, never label query strings or gold targets.
    prohibited = {row["start_node"] for row in read_json(repo.labels)}
    began = perf_counter()
    initialize_worker(repo.graph)
    setup = perf_counter() - began
    starts = sorted(n for n, d in _VIEW.graph.nodes(data=True)
                    if d.get("type") == "function" and n not in prohibited)[:2]
    names = ["egpot_full", "egpot_full_mcts", "vector_topk", "bfs"]
    rows = []
    for method in names:
        engine = make_engine(method, spec_at(configs["main"][method], 20))
        for index, start in enumerate(starts):
            began = perf_counter()
            try:
                engine.retrieve("list available things", start, 20)  # discard; no output fields inspected
                rows.append({"method": method, "start_index": index, "seconds": perf_counter()-began, "error": None})
            except Exception as error:
                rows.append({"method": method, "start_index": index, "seconds": perf_counter()-began,
                             "error": type(error).__name__ + ": " + str(error)})
    # Count work from configs without using any Train label query.
    synthetic = {"id": "count", "link_id": 0, "type": "synthetic", "query": "",
                 "start_node": "", "gold_nodes": [], "gold_path": []}
    unique, aliases = plan_locked([synthetic], configs)
    query_count = read_json(repo.label_provenance)["query_count"]
    jobs_count = len(unique) * query_count
    average = sum(r["seconds"] for r in rows) / len(rows)
    dev_rows = [r for r in read_json(SETTINGS)["rows"] if r["split"] == "dev"]
    bytes_per_row = sum(len(canonical(r).encode()) for r in dev_rows) / len(dev_rows)
    report = {"synthetic_query": "list available things", "setup_seconds": setup, "calls": rows,
              "unique_jobs": jobs_count, "logical_rows": len(aliases)*query_count,
              "mean_smoke_seconds": average,
              "estimated_hours": {str(w): jobs_count*average/(3600*w) for w in (1, 4, 8)},
              "estimated_json_bytes": int(bytes_per_row*len(aliases)*query_count*1.4 + len(canonical(configs))),
              "estimate_limits": "Eight budget-20 synthetic calls only; assumes average applies to all methods/budgets. "
                                 "Ideal parallel scaling; excludes worker initialization, contention and checkpoint overhead. "
                                 "JSON size uses saved OB DEV row size with 40% allowance for separate latency records."}
    atomic_json(output, report)
    print(json.dumps(report, indent=2), flush=True)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=("regress-ob-dev", "smoke", "run-locked"))
    parser.add_argument("--repo", choices=REGISTRY, default="online_boutique")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--prove-workers", type=int, default=4)
    parser.add_argument("--checkpoint", type=Path, default=SCRATCH / "checkpoint")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--acknowledge-second-look", action="store_true")
    args = parser.parse_args(argv)
    if args.repo in DSB_DATASETS:
        if args.mode != "run-locked":
            parser.error(f"{args.repo} is available only in --mode run-locked")
        run_locked(args.repo, None, workers=args.workers, checkpoint=args.checkpoint,
                   resume=args.resume, acknowledge=args.acknowledge_second_look)
        return 0
    configs = load_settings()
    print_settings(configs)
    if args.mode == "regress-ob-dev":
        if args.repo != "online_boutique":
            parser.error("regress-ob-dev permits Online Boutique DEV only")
        regress_ob_dev(configs, workers=args.workers, prove_workers=args.prove_workers,
                       checkpoint=args.checkpoint, resume=args.resume)
    elif args.mode == "smoke":
        args.checkpoint.mkdir(parents=True, exist_ok=True)
        smoke(args.repo, configs, output=args.checkpoint / "smoke.json")
    else:
        run_locked(args.repo, configs, workers=args.workers, checkpoint=args.checkpoint,
                   resume=args.resume, acknowledge=args.acknowledge_second_look)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
