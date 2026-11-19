"""Analyze the two published DeathStarBench records without running retrieval."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from statistics import fmean

import numpy as np

from bench import egpot_multi_eval as locked
from bench.egpot_eval import CHOKE_PAIRS


BOOTSTRAP_SEED = 0
RESAMPLES = 10_000
BUDGETS = (10, 20, 40)
FULL = "egpot_full"
BASELINES = ("vector_topk", "bfs", "greedy_walk", "vector_bfs_k2", "ppr",
             "scalar_beam", "community_graphrag", "mcts_standard")
COMPONENTS = ("egpot_no_pareto", "egpot_no_entropy", "egpot_no_contracts", "egpot_no_choke_point")
LOOKAHEAD = ("egpot_full_mcts", "egpot_full_tiebreak")
HIT_ONLY = ("nodes_to_hit", "precision_at_hit")
AVERAGES = ("hit", "gold_recall", "precision", "path_coverage", "ordered_path_match",
            "nodes_returned", *HIT_ONLY, "latency_s")


def summarize(rows):
    hits = [row for row in rows if row["hit"]]
    result = {"n": len(rows), "hit_count": len(hits)}
    for field in AVERAGES:
        cohort = hits if field in HIT_ONLY else rows
        result[field] = fmean(row[field] for row in cohort) if cohort else None
    return result


def load_record(path, name, repo):
    data = locked.read_json(path)
    if (data.get("schema"), data.get("repo"), data.get("split")) != (1, name, "all"):
        raise ValueError(f"{name}: expected a whole-set schema-1 locked record")
    identity = data["identity"]
    hashes = locked.verify_inputs(repo)
    hashes["preregistration"] = locked.sha256(repo.preregistration)
    for key, checksum in hashes.items():
        if identity["verified_hashes"].get(key) != checksum or (
                key != "preregistration" and identity.get(key) != checksum):
            raise ValueError(f"{name}: {key} hash mismatch")
    if (identity["commit"] != data["commit"]
            or identity["protocol_sha256"] != locked.digest(data["configs"])
            or data["deterministic_sha256"] != locked.digest(data["rows"])):
        raise ValueError(f"{name}: locked commit, protocol or row digest mismatch")

    labels = locked.read_json(repo.labels)
    label_index = {row["id"]: row for row in labels}
    jobs, aliases = locked.plan_locked(labels, data["configs"])
    by_key = {job["key"]: job for job in jobs}
    expected_keys = {}
    for alias in aliases:
        job = by_key[alias["key"]]
        label = job["label"]
        key = (alias["experiment"], job["method"], job["budget"], alias["seed"], label["id"])
        expected_keys[key] = (alias["key"], label)
    rows = []
    for row, timing in zip(data["rows"], data["latencies"], strict=True):
        key = tuple(row[field] for field in ("experiment", "method", "node_budget", "seed", "id"))
        job_key, label = expected_keys.pop(key, (None, {}))
        if (job_key is None or timing["job"] != job_key or row["split"] != "all"
                or any(row[field] != label[field] for field in ("type", "link_id"))):
            raise ValueError(f"{name}: row or latency does not match the locked job {key}")
        rows.append({**row, "app": name, "latency_s": timing["latency_s"],
                     "label": label_index[row["id"]]})
    if expected_keys:
        raise ValueError(f"{name}: locked record is missing planned rows")
    return rows, {"commit": data["commit"], "hashes": hashes, "record_sha256": locked.sha256(path)}


def cluster_weights(query_starts, *, resamples=RESAMPLES, seed=BOOTSTRAP_SEED):
    """Return one query multiplicity per column. Each app retains its cluster count."""
    rng = np.random.RandomState(seed)
    indices = defaultdict(lambda: defaultdict(list))
    for column, (app, start) in enumerate(query_starts):
        indices[app][start].append(column)
    weights = np.zeros((resamples, len(query_starts)), dtype=np.int64)
    for app in sorted(indices):
        clusters = list(sorted(indices[app]))
        size = len(clusters)
        draws = rng.randint(size, size=(resamples, size))
        counts = np.zeros((resamples, size), dtype=np.int64)
        np.add.at(counts, (np.arange(resamples)[:, None], draws), 1)
        for j, start in enumerate(clusters):
            weights[:, indices[app][start]] = counts[:, j, None]
    return weights


def strongest_baseline(hits, nodes_to_hit):
    """Columns must be in alphabetical method order for the last tie-break."""
    alphabetical = np.broadcast_to(np.arange(hits.shape[1]), hits.shape)
    return np.lexsort((alphabetical, nodes_to_hit, -hits), axis=1)[:, 0]


def bootstrap(methods, query_starts, contrasts, baselines, *,
              resamples=RESAMPLES, seed=BOOTSTRAP_SEED):
    """Paired contrasts on aligned rows. Row zero is the observed cohort."""
    if not query_starts or any(len(rows) != len(query_starts) for rows in methods.values()):
        raise ValueError("Bootstrap requires a nonempty, aligned query cohort")
    names = list(sorted(methods))
    at = {name: i for i, name in enumerate(names)}
    weights = np.vstack((np.ones(len(query_starts), dtype=np.int64),
                         cluster_weights(query_starts, resamples=resamples, seed=seed)))
    n = weights.sum(axis=1, keepdims=True)
    hit_counts = weights @ np.array([[row["hit"] for row in methods[name]] for name in names]).T
    rates = {"hit_rate": hit_counts / n,
             "mean_recall": (weights @ np.array(
                 [[row["gold_recall"] for row in methods[name]] for name in names]).T) / n}
    baseline_indices = [at[name] for name in sorted(baselines)]
    rank = np.array([[row["nodes_to_hit"] or 0 for row in methods[name]] for name in names]).T
    means = np.divide(weights @ rank, hit_counts, out=np.full(hit_counts.shape, np.inf),
                      where=hit_counts > 0)
    strongest = np.asarray(baseline_indices)[strongest_baseline(
        hit_counts[:, baseline_indices], means[:, baseline_indices])]

    output = []
    for left, right in (*contrasts, (FULL, "strongest_baseline")):
        row = {"left": left, "right": right}
        for field, values in rates.items():
            right_value = values[np.arange(len(weights)), strongest] if right == "strongest_baseline" else values[:, at[right]]
            delta = values[:, at[left]] - right_value
            row[field] = {"difference": float(delta[0]),
                          "interval_95": np.percentile(delta[1:], [2.5, 97.5]).tolist()}
        if right == "strongest_baseline":
            row["observed_baseline"] = names[strongest[0]]
        output.append(row)
    return output


def compactness(left, right):
    paired = [(a["nodes_to_hit"], b["nodes_to_hit"])
              for a, b in zip(left, right, strict=True) if a["hit"] and b["hit"]]
    a, b = summarize(left), summarize(right)
    return {"left_hits": a["hit_count"], "right_hits": b["hit_count"],
            "left_hits_only": a["nodes_to_hit"], "right_hits_only": b["nodes_to_hit"],
            "both_hit_n": len(paired),
            "paired_left": fmean(x for x, _ in paired) if paired else None,
            "paired_right": fmean(y for _, y in paired) if paired else None,
            "paired_difference": fmean(x - y for x, y in paired) if paired else None}


def weight_summary(study, control, reference):
    counts = np.array([summarize(rows)["hit_count"] for rows in study.values()])
    pareto = summarize(reference)["hit_count"]
    quantiles = np.percentile(counts, [0, 25, 50, 75, 100]).tolist()
    return {**dict(zip(("min", "q25", "median", "q75", "max"), quantiles)),
            "mean": float(counts.mean()), "vectors": len(counts), "pareto_hits": pareto,
            "equal_control_hits": summarize(control)["hit_count"],
            "below": int((counts < pareto).sum()), "equal": int((counts == pareto).sum()),
            "above": int((counts > pareto).sum())}


def failures(rows):
    output = []
    for row in rows:
        label = row["label"]
        lookalikes = set(label.get("lookalike_nodes", ()))
        known = {label["start_node"], *row["gold_found"]}
        if "returned_nodes" in row:
            found = bool(lookalikes.intersection(row["returned_nodes"]))
        elif lookalikes & known:
            found = True
        elif not lookalikes or len(known) == row["nodes_returned"]:
            found = False
        else:
            found = None
        for node in sorted(set(label["gold_nodes"]) - set(row["gold_found"])):
            output.append({**{key: row[key] for key in ("app", "id", "link_id", "type",
                           "method", "experiment", "node_budget", "seed")},
                           "missed_gold_node": node, "lookalike_returned": found})
    return output


def tables(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["experiment"], row["node_budget"], row["method"], row["seed"]].append(row)
    for values in grouped.values():
        values.sort(key=lambda r: (r["app"], r["id"]))
    output = {key: [] for key in ("descriptive", "seeds", "paired", "claims", "compactness",
                                  "choke", "weights")}
    contrasts = ([(FULL, method) for method in (*BASELINES, *COMPONENTS, "egpot_no_pareto_mcts")]
                 + [(method, FULL) for method in LOOKAHEAD])
    for budget in BUDGETS:
        main = {method: values for (section, b, method, seed), values in grouped.items()
                if section == "main" and b == budget and seed == 0}
        if not main:
            raise ValueError(f"Missing main cohort at budget {budget}")
        keys = [(row["app"], row["id"]) for row in main[FULL]]
        if any([(row["app"], row["id"]) for row in values] != keys for values in main.values()):
            raise ValueError(f"Unpaired main cohort at budget {budget}")
        starts = [(row["app"], row["label"]["start_node"]) for row in main[FULL]]
        for method, values in sorted(main.items()):
            output["descriptive"].append({"method": method, "budget": budget, **summarize(values)})
            if method != FULL:
                output["compactness"].append({"left": FULL, "right": method, "budget": budget,
                                              **compactness(main[FULL], values)})
        for comparison in bootstrap(main, starts, contrasts, BASELINES):
            output["paired"].append({"budget": budget, **comparison})
            if comparison["right"] in COMPONENTS or comparison["left"] in LOOKAHEAD:
                for metric in ("hit_rate", "mean_recall"):
                    interval = comparison[metric]["interval_95"]
                    output["claims"].append({"left": comparison["left"], "right": comparison["right"],
                        "budget": budget, "metric": metric,
                        "verdict": "supported" if interval[0] > 0 else "not supported"})

        if budget in (20, 40):
            for on, off in CHOKE_PAIRS:
                off_rows = main[off] if off in main else grouped["choke", budget, off, 0]
                a, b = summarize(main[on]), summarize(off_rows)
                output["choke"].append({"on": on, "off": off, "budget": budget, "n": a["n"],
                    "on_hits": a["hit_count"], "off_hits": b["hit_count"],
                    "on_mean_nodes": a["nodes_returned"], "off_mean_nodes": b["nodes_returned"],
                    "delta_hits": b["hit_count"] - a["hit_count"]})
        if budget in (10, 20):
            study = {method: values for (section, b, method, seed), values in grouped.items()
                     if section == "weights" and b == budget and seed == 0 and method != "equal"}
            output["weights"].append({"budget": budget, **weight_summary(
                study, grouped["weights", budget, "equal", 0],
                grouped["pareto_reference", budget, FULL, 0])})

    seeds = [{"experiment": section, "method": method, "budget": budget, "seed": seed, **summarize(values)}
             for (section, budget, method, seed), values in sorted(grouped.items()) if section == "seeds"]
    primary = {(row["method"], row["budget"]): row for row in seeds if row["seed"] == 0}
    for record in locked.dsb_seed_summary(seeds):
        seed_zero = primary[record["method"], record["budget"]]
        record["seed_0"] = {field: seed_zero[field] for field in ("n", "hit_count", *AVERAGES)}
        output["seeds"].append(record)
    return output


def analyze(social_path, media_path, *, registry=locked.REGISTRY):
    cohorts, provenance = {}, {}
    for name, path in zip(locked.DSB_DATASETS, (social_path, media_path), strict=True):
        cohorts[name], provenance[name] = load_record(path, name, registry[name])
    pooled = [row for cohort in cohorts.values() for row in cohort]
    return {"bootstrap": {"seed": BOOTSTRAP_SEED, "resamples": RESAMPLES,
                          "interval": "95% percentile", "pooled_strata": "app"},
            "primary": {"method": FULL, "budget": 40, "metric": "hit_count"},
            "provenance": provenance,
            "tables": {name: tables(rows) for name, rows in {**cohorts, "pooled": pooled}.items()},
            "failures": failures(pooled),
            "lookalike_note": "Null means the locked record did not identify enough returned nodes."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--social", required=True, type=Path)
    parser.add_argument("--media", required=True, type=Path)
    parser.add_argument("--out", type=Path, help="Write JSON to a new file (default: stdout)")
    args = parser.parse_args(argv)
    report = json.dumps(analyze(args.social, args.media), indent=2, allow_nan=False) + "\n"
    if args.out is None:
        print(report, end="")
    else:
        with args.out.open("x", encoding="utf-8") as stream:
            stream.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
