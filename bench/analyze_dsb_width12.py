"""Analyze the frozen DeathStarBench width-12 follow-up without retrieval."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
import json
from pathlib import Path

import networkx as nx
import numpy as np

from bench import egpot_multi_eval as locked
from bench.analyze_dsb_distance import gold_depth, markdown_table
from bench.analyze_dsb_final import (
    AVERAGES, BOOTSTRAP_SEED, BUDGETS, RESAMPLES, cluster_weights, failures, load_record, summarize,
)


STATUS = locked.WIDTH12_STATUS
RESULTS = locked.ROOT / "bench/results"
FULL = "egpot_full"
WIDE = tuple(f"{name}_w12" for name in locked.WIDTH12_METHODS)
REFERENCES = (*locked.WIDTH12_METHODS, "ppr")
MAIN = (FULL, *WIDE, "ppr")
CONTRASTS = tuple((name, reference) for name in WIDE
                  for reference in (name.removesuffix("_w12"), "ppr"))


def load_app(app):
    root = locked.ROOT
    old_repo = locked.REGISTRY[app]
    new_repo = replace(old_repo, preregistration=root / locked.WIDTH12_PLAN)
    original, expected_configs = locked.width12_record_options(app, new_repo, root=root)
    run_commit = locked.git("rev-parse", f"{locked.WIDTH12_RESULT_TAG}^", root=root)
    relative = Path(f"bench/results/{app}_w12_{run_commit[:8]}.json")
    path = root / relative
    tagged = locked.git("rev-parse", f"{locked.WIDTH12_RESULT_TAG}:{relative.as_posix()}", root=root)
    # Git stores LF for this JSON even when the Windows publisher uses CRLF.
    if locked.git("hash-object", f"--path={relative.as_posix()}", str(path), root=root) != tagged:
        raise ValueError(f"{app}: width-12 record differs from the locked Git blob")
    locked.verify_dsb_frozen_code(run_commit, root=root)
    if (locked.git("rev-parse", f"{locked.WIDTH12_TAG}^{{commit}}", root=root) != locked.WIDTH12_FREEZE
            or locked.git("diff", "--name-only", locked.WIDTH12_FREEZE, run_commit, "--",
                          locked.WIDTH12_PLAN.as_posix(), root=root)):
        raise ValueError("Runner does not match the exploratory freeze")
    data = locked.read_json(path)
    if (data.get("commit") != run_commit or data.get("analysis_type") != STATUS
            or data.get("preregistration_commit") != locked.WIDTH12_FREEZE
            or data.get("beam_width") != 12 or data.get("configs") != expected_configs
            or data["identity"].get("settings") != locked.sha256(original)):
        raise ValueError(f"{app}: width-12 header or inherited protocol mismatch")
    old_rows, old_identity = load_record(original, app, old_repo)
    new_rows, new_identity = load_record(path, app, new_repo)
    if any(row.get("beam_width") != 12 or row["method"] not in WIDE for row in new_rows):
        raise ValueError(f"{app}: wrong width or method in a width-12 row")
    graph = nx.read_graphml(new_repo.graph, force_multigraph=True)
    view = graph.to_undirected(as_view=True)
    starts, depths = {}, {}
    for row in new_rows:
        key = (app, row["id"])
        if key in depths:
            continue
        label = row["label"]
        start = label["start_node"]
        if start not in starts:
            starts[start] = nx.single_source_shortest_path_length(view, start)
        depth = gold_depth([starts[start].get(node) for node in label["gold_nodes"]])
        if depth not in (1, 2):
            raise ValueError(f"{app}: unexpected gold depth for {row['id']}: {depth}")
        depths[key] = depth
    references = [row for row in old_rows if row["experiment"] == "main" and row["method"] in REFERENCES]
    return references + new_rows, depths, {"width4": old_identity, "width12": new_identity}


def summarize_scope(rows, depths, *, resamples=RESAMPLES):
    """Summaries and paired intervals for one app or the pooled cohort."""
    groups = defaultdict(list)
    for row in rows:
        key = (row["experiment"], row["node_budget"], row["method"], row["seed"])
        groups[key].append(row)
    for group in groups.values():
        group.sort(key=lambda row: (row["app"], row["id"]))
    records = {"main": [], "seeds": [], "depth": [], "paired": []}
    weights = None
    for budget in BUDGETS:
        main = {name: group for (section, b, name, seed), group in groups.items()
                if section == "main" and b == budget and seed == 0}
        if set(main) != set((*REFERENCES, *WIDE)):
            raise ValueError(f"Incomplete main method set at budget {budget}")
        ids = [(r["app"], r["id"]) for r in main[FULL]]
        if any([(r["app"], r["id"]) for r in group] != ids for group in main.values()):
            raise ValueError(f"Main results are not paired at budget {budget}")
        starts = [(r["app"], r["label"]["start_node"]) for r in main[FULL]]
        if weights is None:
            weights = cluster_weights(starts, resamples=resamples, seed=BOOTSTRAP_SEED)
            denominators = weights.sum(axis=1)
            query_ids = ids
        elif ids != query_ids:
            raise ValueError("Query cohort changed across budgets")
        for method, group in sorted(main.items()):
            records["main"].append({"budget": budget, "method": method, **summarize(group)})
            for depth in (1, 2):
                selected = [r for r in group if depths[(r["app"], r["id"])] == depth]
                if selected:
                    records["depth"].append({"budget": budget, "method": method, "depth": depth,
                                             **summarize(selected)})
        for left, right in CONTRASTS:
            comparison = {"budget": budget, "left": left, "right": right, "analysis_type": STATUS}
            for field in ("hit", "gold_recall"):
                diffs = np.array([a[field] - b[field] for a, b in zip(main[left], main[right], strict=True)])
                draws = (weights @ diffs) / denominators
                comparison[field] = {"difference": float(diffs.mean()),
                                     "interval_95": np.quantile(draws, [0.025, 0.975]).tolist()}
            records["paired"].append(comparison)
    for (section, budget, method, seed), group in sorted(groups.items()):
        if section == "seeds":
            seed_ids = [(r["app"], r["id"]) for r in group]
            if seed_ids != query_ids:
                raise ValueError("Tiebreak seed study query cohort does not match main")
            records["seeds"].append({"budget": budget, "method": method, "seed": seed, **summarize(group)})
    records["seed_spread"] = locked.dsb_seed_summary([
        {**row, "experiment": "seeds"} for row in records["seeds"]])
    records["misses"] = failures([r for r in rows if r["experiment"] == "main" or r["seed"] != 0])
    return records


def predictions(main):
    by = {(r["method"], r["budget"]): r for r in main}
    wide40 = by[FULL + "_w12", 40]
    wide10 = by[FULL + "_w12", 10]
    baseline40 = by["ppr", 40]
    baseline10 = by["ppr", 10]
    return {
        "A": {"held": wide40["hit_count"] > 37, "observed": wide40["hit_count"],
              "n": wide40["n"], "threshold": 37, "ppr_hits": baseline40["hit_count"]},
        "B": {"held": wide10["hit_count"] < 36, "observed": wide10["hit_count"],
              "n": wide10["n"], "threshold": 36, "ppr_hits": baseline10["hit_count"]},
        "C": {"held": wide40["nodes_returned"] > 24.8 and wide40["precision"] < 0.081,
              "nodes_returned": {"held": wide40["nodes_returned"] > 24.8,
                                 "observed": wide40["nodes_returned"], "threshold": 24.8,
                                 "ppr": baseline40["nodes_returned"]},
              "precision": {"held": wide40["precision"] < 0.081, "observed": wide40["precision"],
                            "threshold": 0.081, "ppr": baseline40["precision"]}},
    }


def analyze():
    scopes, provenance, all_rows, all_depths = {}, {}, [], {}
    for app in locked.DSB_DATASETS:
        rows, depths, provenance[app] = load_app(app)
        scopes[app] = summarize_scope(rows, depths)
        all_rows.extend(rows)
        all_depths.update(depths)
    scopes["pooled"] = summarize_scope(all_rows, all_depths)
    return {"analysis_type": STATUS, "inputs": provenance, "scopes": scopes,
            "predictions": predictions(scopes["pooled"]["main"]),
            "bootstrap": {"seed": BOOTSTRAP_SEED, "resamples": RESAMPLES, "confidence_level": .95,
                          "strata": "app", "cluster": "start_node", "analysis_type": STATUS}}


def markdown(report):
    def fmt(value):
        if value is None:
            return "—"
        return str(value) if isinstance(value, int) else f"{value:.5f}"

    def metrics(row):
        return (f"{row['hit_count']}/{row['n']}", *(fmt(row[key]) for key in AVERAGES))

    def verdict(holds):
        return "Held" if holds else "Failed"

    def interval(value):
        lo, hi = value["interval_95"]
        return f"{value['difference']:+.4f} [{lo:+.4f}, {hi:+.4f}]"

    lines = [f"# DeathStarBench width-12 follow-up ({STATUS})", "",
             "The preregistered width-4 analysis and C1–C7 remain primary. Width 12 was chosen "
             "on DEV after the DeathStarBench locked run had been seen. This follow-up provides "
             "no independent confirmation of that choice.", ""]

    def section(name, headers, rows):
        lines.extend([f"## {name} ({STATUS})", "", *markdown_table(headers, rows)])

    pooled = report["scopes"]["pooled"]["main"]
    section("Pooled comparison, seed 0", ["Budget", "Method", "Hits", "Recall", "Precision",
                                         "Nodes returned", "Nodes-to-hit"],
            ((r["budget"], r["method"], f"{r['hit_count']}/{r['n']}",
              *(fmt(r[f]) for f in ("gold_recall", "precision", "nodes_returned", "nodes_to_hit")))
             for b in BUDGETS for name in MAIN for r in pooled if (r["budget"], r["method"]) == (b, name)))
    p = report["predictions"]
    section("Prediction outcomes", ["Prediction", "Observed", "Threshold", "PPR", "Verdict"], [
        ("A · hits at 40", f"{p['A']['observed']}/{p['A']['n']}", ">37/46", f"{p['A']['ppr_hits']}/{p['A']['n']}",
         verdict(p["A"]["held"])),
        ("B · hits at 10", f"{p['B']['observed']}/{p['B']['n']}", "<36/46", f"{p['B']['ppr_hits']}/{p['B']['n']}",
         verdict(p["B"]["held"])),
        ("C · nodes at 40", fmt(p["C"]["nodes_returned"]["observed"]), ">24.8",
         fmt(p["C"]["nodes_returned"]["ppr"]), verdict(p["C"]["nodes_returned"]["held"])),
        ("C · precision at 40", fmt(p["C"]["precision"]["observed"]), "<0.081",
         fmt(p["C"]["precision"]["ppr"]), verdict(p["C"]["precision"]["held"])),
        ("C · jointly", "Both parts required", "", "", verdict(p["C"]["held"])),
    ])
    headers = ["Full hits", "Hit rate", "Recall", "Precision", "Path coverage", "Ordered path match",
               "Nodes returned", "Nodes-to-hit", "Precision-at-hit", "Mean latency s"]
    for scope, result in report["scopes"].items():
        section(f"{scope} main metrics, seed 0", ["Budget", "Method", *headers],
                ((r["budget"], r["method"], *metrics(r)) for r in result["main"]))
        section(f"{scope} by gold depth, seed 0", ["Depth", "Budget", "Method", *headers],
                ((r["depth"], r["budget"], r["method"], *metrics(r)) for r in result["depth"]))
        section(f"{scope} paired differences and unadjusted 95% intervals",
                ["Budget", "Width 12", "Reference", "Hit-rate difference", "Mean-recall difference"],
                ((r["budget"], r["left"], r["right"], interval(r["hit"]), interval(r["gold_recall"]))
                 for r in result["paired"]))
        section(f"{scope} tiebreak seeds", ["Budget", "Seed", *headers],
                ((r["budget"], r["seed"], *metrics(r)) for r in result["seeds"]))
        section(f"{scope} tiebreak seed spread", ["Budget", "Metric", "Median", "Min", "Max", "Defined seeds"],
                ((r["budget"], metric, *(fmt(m[k]) for k in ("median", "min", "max", "defined_seeds")))
                 for r in result["seed_spread"] for metric, m in r["metrics"].items()))
    lines.extend(["Seed-0 seed-study aliases are represented by the main rows in the miss table. "
                  "Lookalikes are descriptive.", ""])
    section("Missed gold IDs and returned lookalikes",
            ["App", "Query", "Method", "Budget", "Seed", "Missed gold", "Lookalike?", "Returned lookalikes"],
            ((r["app"], r["id"], r["method"], r["node_budget"], r["seed"], r["missed_gold_node"],
              "yes" if r["lookalike_returned"] else "no", ", ".join(r["returned_lookalike_nodes"]))
             for app in locked.DSB_DATASETS for r in report["scopes"][app]["misses"]))
    return "\n".join(lines)


def main():
    outputs = (RESULTS / "dsb_w12_analysis.json", RESULTS / "dsb_w12_analysis.md")
    if any(path.exists() for path in outputs):
        raise ValueError("Width-12 analysis output already exists")
    report = analyze()
    for path, contents in zip(outputs, (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n",
                                       markdown(report)), strict=True):
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(contents)
        print(path)


if __name__ == "__main__":
    main()
