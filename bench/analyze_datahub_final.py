"""Analyze a published DataHub locked record without running retrieval."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path

import numpy as np

from bench import egpot_multi_eval as locked
from bench.analyze_dsb_final import (
    ALPHA, AVERAGES, BOOTSTRAP_SEED, RESAMPLES, cluster_weights, compactness,
    load_record, strongest_baseline, summarize, weight_summary,
)
from bench.datahub_protocol import settings
from bench.egpot_test_splits import BASELINES, CHOKE


FULL = "egpot_full_w4"
WIDE = "egpot_full_w12"
STRONGEST = "strongest_baseline"
CONTRASTS = (
    ("C1", 10, FULL, STRONGEST),
    ("C2", 40, WIDE, STRONGEST),
    ("C3", 10, FULL, WIDE),
    ("C4", 40, FULL, "egpot_no_contracts_w4"),
)
LOOKAHEAD_CONTROLS = {
    "egpot_full_tiebreak_w4": FULL,
    "egpot_full_tiebreak_w12": WIDE,
    "egpot_full_mcts_w4": FULL,
    "egpot_no_pareto_mcts_w4": "egpot_no_pareto_w4",
}


def handler_class(label):
    # The pinned Java node ID identifies both the source file and declaring
    # class. Retaining the file qualifier distinguishes classes across modules.
    handler = label["gold_nodes"][1]
    qualifier, separator, _ = handler.rpartition(".")
    if not separator or ".java:" not in qualifier:
        raise ValueError(f"Missing source-qualified Java handler class: {handler}")
    return qualifier


def paired_contrasts(main, *, cluster_by, exploratory=False):
    cohort = main[10][FULL]
    ids = [row["id"] for row in cohort]
    clusters = [cluster_by(row["label"]) for row in cohort]
    weights = np.vstack((np.ones(len(ids), dtype=np.int64),
                         cluster_weights([("DataHub", key) for key in clusters])))
    denominators = weights.sum(axis=1)
    alpha = ALPHA if exploratory else ALPHA / len(CONTRASTS)
    tails = (alpha / 2, 1 - alpha / 2)
    output = []
    for contrast, budget, left, right in CONTRASTS:
        names = sorted({left, *(BASELINES if right == STRONGEST else (right,))})
        rows = [main[budget][name] for name in names]
        if any([row["id"] for row in method] != ids for method in rows):
            raise ValueError(f"Unpaired DataHub cohort for {contrast}")
        hits = weights @ np.array([[row["hit"] for row in method] for method in rows]).T
        rates = hits / denominators[:, None]
        reference = right
        if right == STRONGEST:
            baselines = [names.index(name) for name in sorted(BASELINES)]
            rank = np.array([[row["nodes_to_hit"] or 0 for row in method] for method in rows]).T
            defined = np.array([[row["nodes_to_hit"] is not None for row in method] for method in rows]).T
            counts = weights @ defined
            means = np.divide(weights @ rank, counts, out=np.full(hits.shape, np.inf),
                              where=counts > 0)
            best = np.asarray(baselines)[strongest_baseline(rates[:, baselines], means[:, baselines])]
            right_rates = rates[np.arange(len(weights)), best]
            reference = names[best[0]]
        else:
            right_rates = rates[:, names.index(right)]
        delta = rates[:, names.index(left)] - right_rates
        low, high = np.quantile(delta[1:], tails).tolist()
        result = {"id": contrast, "budget": budget, "left": left, "right": right,
                  "observed_comparator": reference, "difference": float(delta[0]),
                  "interval": [low, high], "confidence_level": 1 - alpha,
                  "clusters": len(set(clusters)), "queries": len(ids),
                  "analysis_type": "exploratory" if exploratory else "confirmatory"}
        if not exploratory:
            result["verdict"] = ("supported" if low > 0 else
                                 "significantly worse" if high < 0 else "not supported")
        output.append(result)
    return output


def describe(groups, protocol):
    tables = {"analysis_type": "exploratory", "metrics": [], "seed_spread": [],
              "compactness": [], "choke": [], "weights": []}
    summaries = {}
    for (section, budget, method, seed), rows in sorted(groups.items()):
        stats = summarize(rows)
        summaries[section, budget, method, seed] = stats
        tables["metrics"].append({"experiment": section, "budget": budget,
                                  "method": method, "seed": seed, **stats})
    for (method, budget), runs in sorted(seed_runs(summaries).items()):
        stats = {}
        for field in ("hit_count", *AVERAGES):
            values = [run[field] for run in runs.values() if run[field] is not None]
            stats[field] = {"min": min(values, default=None), "median": float(np.median(values)) if values else None,
                            "max": max(values, default=None), "defined_seeds": len(values)}
        tables["seed_spread"].append({"method": method, "budget": budget,
                                      "seed_0": runs[0], "spread": stats})
    for budget in (10, 20, 40):
        main = {method: rows for (section, b, method, seed), rows in groups.items()
                if section == "main" and b == budget and seed == 0}
        pairs = {(FULL, method) for method in main if method != FULL}
        pairs.update(LOOKAHEAD_CONTROLS.items())
        pairs.update((WIDE, method) for method in BASELINES)
        for left, right in sorted(pairs):
            if left in main and right in main:
                tables["compactness"].append({"budget": budget, "left": left, "right": right,
                                              **compactness(main[left], main[right])})
        if budget in (20, 40):
            for on, off in (*CHOKE, (FULL, "egpot_no_choke_point_w4")):
                on_key = ("main", budget, on, 0)
                off_key = ("main" if off in main else "choke", budget, off, 0)
                if on_key in summaries and off_key in summaries:
                    a, b = summaries[on_key], summaries[off_key]
                    tables["choke"].append({"budget": budget, "on": on, "off": off,
                                            "off_minus_on": {
                        key: b[key] - a[key] if None not in (a[key], b[key]) else None
                        for key in ("hit_count", *AVERAGES)}})
        if budget in protocol["pareto_reference"]["budgets"]:
            study = {method: groups["weights", budget, method, 0]
                     for method in protocol["weights"] if method != "equal"}
            tables["weights"].append({"budget": budget, **weight_summary(
                study, groups["weights", budget, "equal", 0],
                groups["pareto_reference", budget, FULL, 0])})
    return tables


def seed_runs(summaries):
    runs = defaultdict(dict)
    for (section, budget, method, seed), stats in summaries.items():
        if section == "seeds":
            runs[method, budget][seed] = stats
    return runs


def lookalike_failures(rows):
    for row in rows:
        label = row["label"]
        lookalikes = set(label["lookalike_ids"])
        found = [node for node in row["returned_nodes"] if node in lookalikes]
        for node in sorted(set(label["gold_nodes"]) - set(row["gold_found"])):
            yield {**{key: row[key] for key in ("id", "link_id", "type", "method",
                                               "experiment", "node_budget", "seed")},
                   "module_pair": label["module_pair"], "missed_gold_node": node,
                   "lookalike_returned": bool(found), "returned_lookalike_nodes": found}


def analyze_rows(rows, protocol, coverage):
    missing = {row["id"] for row in coverage if row["status"] != "fully covered"}
    rows = sorted((row for row in rows if row["link_id"] not in missing),
                  key=lambda row: (row["experiment"], row["node_budget"], row["method"],
                                   row["seed"], row["id"]))
    scopes = defaultdict(lambda: defaultdict(list))
    for row in rows:
        key = (row["experiment"], row["node_budget"], row["method"], row["seed"])
        for scope in ("pooled", row["label"]["module_pair"]):
            scopes[scope][key].append(row)
    main = defaultdict(dict)
    for (section, budget, method, seed), values in scopes["pooled"].items():
        if section == "main" and seed == 0:
            main[budget][method] = values
    return {
        "confirmatory": paired_contrasts(main, cluster_by=lambda label: label["start_node"]),
        "handler_class_sensitivity": paired_contrasts(main, cluster_by=handler_class, exploratory=True),
        "bootstrap": {"resamples": RESAMPLES, "seed": BOOTSTRAP_SEED, "method": "percentile",
                      "confirmatory_family_size": len(CONTRASTS),
                      "confirmatory_tail_probability": ALPHA / (2 * len(CONTRASTS))},
        "coverage": {"excluded_links": [row for row in coverage if row["id"] in missing],
                     "included_links": len({row["link_id"] for row in rows})},
        "descriptive": {scope: describe(groups, protocol) for scope, groups in sorted(scopes.items())},
        "lookalike_failure_analysis": {"analysis_type": "descriptive only",
                                       "failures": list(lookalike_failures(rows))},
    }


def analyze(path, *, repo=locked.REGISTRY[locked.DATAHUB]):
    if "Status: FROZEN" not in repo.preregistration.read_text(encoding="utf8").splitlines():
        raise ValueError("DataHub analysis requires a frozen preregistration")
    record = locked.read_json(path)
    protocol = settings()
    if record.get("second_look") is not False or record.get("previous_results") != []:
        raise ValueError("Expected a first-look DataHub locked record")
    if locked.digest(record["configs"]) != locked.digest(protocol):
        raise ValueError("DataHub record does not match the declared job matrix")
    rows, provenance = load_record(path, locked.DATAHUB, repo)
    coverage = locked.read_json(repo.provenance)["links"]
    if {row["id"] for row in coverage} != {row["link_id"] for row in rows}:
        raise ValueError("DataHub coverage records do not match the locked links")
    for row in rows:
        # Full hits are an exact-set outcome. Check it even if the row digest
        # was recomputed after an accidental edit.
        if row["hit"] != (set(row["label"]["gold_nodes"]) <= set(row["returned_nodes"])):
            raise ValueError(f"Incorrect full hit in DataHub row {row['id']}")
    return {**analyze_rows(rows, protocol, coverage), "provenance": provenance}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", required=True, type=Path)
    parser.add_argument("--out", type=Path, help="Write JSON to a new file (default: stdout)")
    args = parser.parse_args(argv)
    report = json.dumps(analyze(args.record), ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.out is None:
        print(report, end="")
    else:
        with args.out.open("x", encoding="utf-8") as stream:
            stream.write(report)


if __name__ == "__main__":
    main()
