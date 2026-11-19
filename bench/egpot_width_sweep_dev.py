"""Replay width 4 and measure beam width on the two pinned DEV workspaces."""
import contextlib
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from statistics import fmean
import multiprocessing
from dataclasses import replace
import hashlib
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import networkx as nx

from bench import egpot_eval as evaluation, egpot_multi_eval as locked
from bench.analyze_dsb_distance import gold_depth, markdown_table
from bench.analyze_dsb_final import load_record
from multi_repo import WorkspaceCKGBuilder
import proto_compiler

BASE = "4ebe87f9c0cec3524ec736d5b67870e91273e961"
RESULTS = Path("bench/results")
OUTPUT = RESULTS / "egpot_dev_baseline_rows_4ebe87f9.json"
LINKS = (1, 4, 5, 9, 11, 13, 14, 15)
BUDGETS = (10, 20, 40)
SOURCES = {
    "online_boutique": (Path("C:/dev/microservices-demo"), "c7cb6d5bfd6ea3aed768634ebbcb98cb7a523712"),
    "train_ticket": (Path("C:/dev/polyglot_repos/train-ticket"), "313886e99befb94be6cd45f085c98e0019f59829"),
}
BEAM_METHODS = ("egpot_full", "egpot_no_pareto", "egpot_full_mcts", "egpot_no_contracts")
REFERENCES = ("ppr", "vector_topk", "bfs", "mcts_standard")
RULE = ("Recommend the smallest width whose pooled seed-0 egpot_full hits at budget 40 are within 1 of "
        "the best width and whose Train-Ticket hits drop by at most 1 versus width 4. "
        "If no width beats width 4 by more than 1 pooled hit, report no change recommended.")

def labels_dev(path):
    raw = path.read_bytes()
    expected = {f"{i:02}_{kind}" for i in LINKS for kind in ("explicit", "indirect")}
    labels = []
    for record in re.findall(rb"(?ms)^  \{\r?\n.*?^  \}(?=,?\r?$)", raw):
        link = re.search(rb'(?m)^    "link_id": (\d+),\r?$', record)
        if link is None:
            raise ValueError("Missing link marker")
        if int(link[1]) in LINKS:
            labels.append(json.loads(record))
    if len(labels) != 16 or {row["id"][2:] for row in labels} != expected:
        raise ValueError(f"Wrong DEV cohort for {path}")
    return labels, hashlib.sha256(raw).hexdigest()

def guard(event, args):
    if event == "open":
        _, mode, flags = args
        if (mode and any(c in mode for c in "wax+")) or flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            raise PermissionError(f"Audit guard blocked write: {args[0]}")
    if (event.startswith(("subprocess.", "socket.")) or event in {
            "os.system", "os.exec", "os.spawn", "os.posix_spawn", "os.mkdir", "os.remove", "os.rename",
            "os.rmdir", "os.link", "os.symlink", "os.chmod", "os.utime", "shutil.copyfile", "shutil.copystat"}):
        raise PermissionError(f"Audit guard blocked {event}")

def build(name, config):
    proto_compiler.compile_proto_file = lambda *_: (None, "In-memory measurement uses the source parser")
    with contextlib.redirect_stdout(StringIO()):
        graph = WorkspaceCKGBuilder(config).build()
    clean = nx.MultiDiGraph()
    def clean_attrs(attrs):
        return {key: value if isinstance(value, (str, int, float, bool)) else str(value)
                for key, value in attrs.items()}
    clean.add_nodes_from((node, clean_attrs(attrs)) for node, attrs in graph.nodes(data=True))
    clean.add_edges_from((u, v, key, clean_attrs(attrs)) for u, v, key, attrs in graph.edges(keys=True, data=True))
    buffer = BytesIO()
    nx.write_graphml(clean, buffer)
    checksum = hashlib.sha256(buffer.getbuffer()).hexdigest()
    buffer.seek(0)
    view = nx.read_graphml(buffer, force_multigraph=True)
    print(name, view.number_of_nodes(), view.number_of_edges(), checksum, flush=True)
    return view, checksum

def retrieval_context(graph, labels):
    view = evaluation.GraphView(graph, edge_policy=locked.DSB_EDGE_POLICY)
    ids = {(row["query"], row["start_node"]): row["id"] for row in labels}
    return view, evaluation.QueryScorer(view), ids


def engines(context, width, names):
    view, scorer, ids = context
    return evaluation.make_comparison_retrievers(
        view, scorer, query_ids=ids, method_names=names, beam_width=width)

def method_records(labels, name, budget, seed, engine):
    if name == "egpot_full_mcts":
        engine.config = replace(engine.config, seed=seed)
    if name == "mcts_standard":
        engine.seed = seed
    records = []
    for label in labels:
        row = locked.evaluate_locked_job({"label": label, "method": name, "budget": budget}, engine,
                                         include_returned_nodes=True)
        records.append({**row, "seed": seed})
    return records

WIDTHS = (4, 6, 8, 12, 16)
STOCHASTIC = ("egpot_full_mcts", "mcts_standard")
WORKERS = 8

_WORKER_LABELS = _WORKER_CONTEXT = None


def setup_worker(graph, labels):
    global _WORKER_CONTEXT, _WORKER_LABELS
    sys.addaudithook(guard)
    _WORKER_CONTEXT, _WORKER_LABELS = retrieval_context(graph, labels), labels


def run_row_batch(width, method, budget, seed):
    engine = engines(_WORKER_CONTEXT, width or 4, (method,))[method]
    return width, method_records(_WORKER_LABELS, method, budget, seed, engine)


def batches(widths, *, baselines=False):
    for width in widths:
        for method in BEAM_METHODS:
            for budget in BUDGETS:
                for seed in range(6) if method in STOCHASTIC else (0,):
                    yield width, method, budget, seed
    if baselines:
        for method in REFERENCES:
            for budget in BUDGETS:
                for seed in range(6) if method in STOCHASTIC else (0,):
                    yield None, method, budget, seed


def parallel_rows(graph, labels, jobs):
    with ProcessPoolExecutor(max_workers=WORKERS, mp_context=multiprocessing.get_context("spawn"),
                             initializer=setup_worker, initargs=(graph, labels)) as pool:
        futures = [pool.submit(run_row_batch, *job) for job in jobs]
        for i, future in enumerate(futures, 1):
            width, rows = future.result()
            if i % 10 == 0 or i == len(futures):
                print(f"Finished batch {i}/{len(futures)}", flush=True)
            yield from ({**row, "width": width} for row in rows)


def verify_dsb():
    counts = {}
    locked.verify_dsb_frozen_code(locked.git("rev-parse", "HEAD"))
    for app in locked.DSB_DATASETS:
        repo = locked.REGISTRY[app]
        rows, _ = load_record(RESULTS / f"{app}_final_6ba6e1cf.json", app, repo)
        selected = [r for r in rows if r["experiment"] == "main" and r["method"] == "egpot_full"
                    and r["node_budget"] == 40 and r["seed"] == 0]
        graph = nx.read_graphml(repo.graph, force_multigraph=True)
        labels = [r["label"] for r in selected]
        engine = engines(retrieval_context(graph, labels), 4, ("egpot_full",))["egpot_full"]
        for row in selected:
            label = row["label"]
            result = engine.retrieve(query=label["query"], start_node=label["start_node"], node_budget=40)
            if result.discovery_order != row["returned_nodes"]:
                raise ValueError(f"Width-4 locked replay differs for {app}/{row['id']}")
        counts[app] = len(selected)
    if counts != {"dsb_social": 28, "dsb_media": 18}:
        raise ValueError(f"Unexpected locked replay counts: {counts}")
    return counts


def compare_dev(rows, reference, dataset):
    def index(values):
        output = {}
        for row in values:
            key = tuple(row[name] for name in ("id", "method", "node_budget", "seed"))
            if key in output:
                raise ValueError(f"Duplicate DEV row: {dataset}/{key}")
            output[key] = locked.canonical({k: v for k, v in row.items() if k not in {"latency_s", "width"}})
        return output

    observed, expected = index(rows), index(reference)
    for key in sorted(observed.keys() | expected.keys()):
        if observed.get(key) != expected.get(key):
            raise ValueError(f"Width-4 deterministic DEV replay differs for {dataset}/{key}")
    return len(expected)


def bucket_depths(graph, labels):
    view = graph.to_undirected(as_view=True)
    return {row["id"]: gold_depth([distances.get(node) for node in row["gold_nodes"]])
            for row in labels for distances in [nx.single_source_shortest_path_length(view, row["start_node"])]}


def summaries(rows, depths):
    groups = defaultdict(list)
    for row in rows:
        key = tuple(row[k] for k in ("method", "width", "node_budget", "seed"))
        groups[key].append(row)
    summary = []
    for (method, width, budget, seed), cohort in groups.items():
        hits = [row for row in cohort if row["hit"]]
        fields = ("gold_recall", "precision", "path_coverage", "ordered_path_match", "nodes_returned", "latency_s")
        ordered = sorted(set(depths.values()), key=lambda d: (d is None, d))
        by_depth = [{"depth": depth, "queries": sum(depths[r["id"]] == depth for r in cohort),
                     "hits": sum(r["hit"] for r in cohort if depths[r["id"]] == depth)} for depth in ordered]
        summary.append({"method": method, "width": width, "budget": budget, "seed": seed,
                        "queries": len(cohort), "hits": len(hits),
                        **{name: fmean(r[name] for r in cohort) for name in fields},
                        **{name: fmean(r[name] for r in hits) if hits else None
                           for name in ("nodes_to_hit", "precision_at_hit")},
                        "by_gold_depth": by_depth})
    return summary


def recommendation(datasets):
    counts = {name: {r["width"]: r["hits"] for r in rows
                     if (r["method"], r["budget"], r["seed"]) == ("egpot_full", 40, 0)}
              for name, rows in datasets.items()}
    train = counts["train_ticket"]
    pooled = {width: sum(hits[width] for hits in counts.values()) for width in WIDTHS}
    best = max(pooled.values())
    choice = None
    if best - pooled[4] > 1:
        choice = next((width for width in WIDTHS
                       if pooled[width] >= best - 1 and train[width] >= train[4] - 1), None)
    return {"rule": RULE, "recommended_width": choice, "pooled_hits": pooled, "app_hits": counts,
            "verdict": f"recommend width {choice}" if choice else "no change recommended"}


def markdown(report):
    lines = ["# EG-POT beam-width sweep (DEV only)", "", "## Pre-stated selection rule", "", RULE, "",
             f"**Verdict.** {report['recommendation']['verdict']}.", "",
             "The DEV allowlist was links 1, 4, 5, 9, 11, 13, 14, and 15 for both workspaces. "
             "Only those label records were decoded and scored. GraphML hashes refer to in-memory "
             "serializations. Policy D and all scoring code were unchanged. DeathStarBench was used "
             "only to replay the saved width-4 main rows at budget 40, seed 0.", "",
             "For deterministic replay comparison, elapsed wall-clock latency is excluded. "
             "Each measured latency includes per-request retrieval and excludes indexing and setup. "
             "Independent batches were run in separate processes. Times can reflect contention.", ""]
    verdict = report["recommendation"]
    lines += markdown_table(["Width", "Boutique", "Train-Ticket", "Pooled"], (
        (w, verdict["app_hits"]["online_boutique"][w], verdict["app_hits"]["train_ticket"][w],
         verdict["pooled_hits"][w]) for w in WIDTHS))
    lines.extend(["Gold depth is the largest raw undirected distance from the start to any gold ID. "
                  "Depth columns give hits / queries. Nodes-to-hit and precision-at-hit average "
                  "hits only. A dash means no hits or a width-independent method.", ""])
    def format_number(value):
        return "—" if value is None else f"{value:.5f}"
    fields = ("gold_recall", "precision", "path_coverage", "ordered_path_match", "nodes_returned",
              "nodes_to_hit", "precision_at_hit", "latency_s")
    for app, rows in report["datasets"].items():
        lines.extend([f"## {app}", ""])
        lines += markdown_table(["Method", "Width", "Budget", "Seed", "Hits", "Recall", "Precision",
                                 "Path coverage", "Ordered path match", "Mean nodes returned",
                                 "Nodes-to-hit", "Precision-at-hit", "Latency s", "Hits by depth"], (
            (r["method"], r["width"] or "—", r["budget"], r["seed"], f"{r['hits']}/{r['queries']}",
             *(format_number(r[f]) for f in fields),
             "; ".join(f"{d['depth'] if d['depth'] is not None else 'unreachable'}: "
                       f"{d['hits']}/{d['queries']}" for d in r["by_gold_depth"])) for r in rows))
    return "\n".join(lines)


def main():
    if os.environ.get("PYTHONHASHSEED") != "0" or not sys.dont_write_bytecode:
        raise ValueError("Use PYTHONHASHSEED=0 and python -B for reproducible guarded builds")
    outputs = (RESULTS / "egpot_width_sweep_dev.json", RESULTS / "egpot_width_sweep_dev.md")
    if any(path.exists() for path in outputs):
        raise ValueError("Refusing to overwrite sweep outputs")
    capture = locked.read_json(OUTPUT)
    if (capture["commit"], capture["selection_rule"], capture["policy"]) != (BASE, RULE, "D"):
        raise ValueError("Unexpected baseline provenance")
    for name, (source, revision) in SOURCES.items():
        command = ["git", "-c", f"safe.directory={source.as_posix()}", "-C", str(source)]
        def read_git(*args):
            return subprocess.check_output([*command, *args], text=True).strip()
        if read_git("rev-parse", "HEAD") != revision or read_git("status", "--porcelain", "--untracked-files=no"):
            raise ValueError(f"Source checkout is not clean at {revision}: {name}")
    dsb_counts = verify_dsb()
    print("Locked width-4 replay exact:", dsb_counts, flush=True)
    audit = False
    def scoped_guard(event, args):
        if audit:
            guard(event, args)
    sys.addaudithook(scoped_guard)
    prepared, identity_counts = {}, {}
    for app in SOURCES:
        previous = capture["datasets"][app]
        labels, label_hash = labels_dev(locked.REGISTRY[app].labels)
        audit = True
        try:
            graph, graph_hash = build(app, previous["workspace"])
        finally:
            audit = False
        if (graph_hash, label_hash) != (previous["graphml_sha256"], previous["label_file_sha256"]):
            raise ValueError(f"{app}: graph or label checksum differs from the pre-change capture")
        print(f"Replaying DEV width 4 for {app}", flush=True)
        rows = list(parallel_rows(graph, labels, list(batches((4,), baselines=True))))
        identity_counts[app] = compare_dev(rows, previous["rows"], app)
        print(app, "DEV replay exact:", identity_counts[app], flush=True)
        prepared[app] = (graph, labels, rows)
    result = {}
    for app, (graph, labels, rows) in prepared.items():
        print(f"Sweeping widths 6, 8, 12, 16 for {app}", flush=True)
        rows.extend(parallel_rows(graph, labels, list(batches(WIDTHS[1:]))))
        result[app] = summaries(rows, bucket_depths(graph, labels))
    report = {"split": "dev", "policy": "D", "widths": WIDTHS, "budgets": BUDGETS,
              "width_4_replay": {"dsb_queries": dsb_counts, "dev_rows": identity_counts,
                                 "baseline_sha256": locked.sha256(OUTPUT)},
              "recommendation": recommendation(result), "datasets": result}
    rendered = (json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", markdown(report))
    for path, contents in zip(outputs, rendered, strict=True):
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(contents)
        print(path, flush=True)


if __name__ == "__main__":
    main()
