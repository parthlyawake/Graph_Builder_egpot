"""Paired, seed-reproducible bootstrap for *exploratory* exact-ID retrieval.

The interval conditions on a hand-constructed query set; it is not a
population confidence interval or a substitute for independent adjudication.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def _per_query_reciprocal(rows: list[dict], top_k: int) -> dict[str, float]:
    found = {}
    for row in rows:
        qid = row["id"]
        if qid in found:
            raise ValueError("Duplicate query IDs")
        targets = set(row["relevant_ids"])
        if not targets:
            raise ValueError("At least one exact relevant ID required")
        rank = next((i for i, node in enumerate(row["ranked_ids"][:top_k], 1)
                     if node in targets), None)
        found[qid] = 1.0 / rank if rank else 0.0
    return found


def bootstrap_paired_difference(left: list[dict], right: list[dict],
                                *, top_k: int=5, seed: int=20261117,
                                repetitions: int=10000) -> dict:
    if repetitions < 100 or top_k < 1:
        raise ValueError("At least 100 repetitions and top_k > 0 required")
    a, b = _per_query_reciprocal(left, top_k), _per_query_reciprocal(right, top_k)
    if not a or set(a) != set(b):
        raise ValueError("Query cohorts differ")
    if {r["id"]: set(r["relevant_ids"]) for r in left} != {
            r["id"]: set(r["relevant_ids"]) for r in right}:
        raise ValueError("Ground truth differs by comparison arm")
    ids = sorted(a)
    delta = [a[i]-b[i] for i in ids]
    n = len(delta)
    estimate = sum(delta)/n
    rng = random.Random(seed)
    sims = sorted(sum(delta[rng.randrange(n)] for _ in ids)/n
                  for _ in range(repetitions))
    lo = sims[int(0.025 * (repetitions - 1))]
    hi = sims[int(0.975 * (repetitions - 1))]
    return {"left_minus_right_mrr": estimate, "left_mrr":sum(a.values())/n,
            "right_mrr":sum(b.values())/n, "bootstrap_95_percentile":[lo,hi],
            "n_queries":n, "seed":seed, "resamples":repetitions,
            "scope":"exploratory hand-constructed queries; labels not independently adjudicated",
            "interval_validity":"within-cohort paired resampling, not population inference"}


def study_summary(report: dict) -> dict:
    configs = report.get("comparisons", {})
    if not {"R1", "R5"} <= set(configs):
        raise ValueError("Must include R1 semantic and R5 static hybrid comparison")
    k = report.get("top_k", 5)
    paired = bootstrap_paired_difference(
        configs["R1"]["queries"], configs["R5"]["queries"], top_k=k)
    baselines = {name: cfg["ranking"] for name, cfg in configs.items()}
    masks = {}
    for layer, results in report.get("ablations", {}).items():
        masks[layer] = {
            "removed_edges":results["removed_edges"],
            "ranking":results["metric"]["ranking"],
            "graft_only":results["graft_only"],
            "ranking_only":results["ranking_only"],
            "ranking_and_graft":results["ranking_and_graft"],
            "stage":results["stage"],
        }
    return {"status":report.get("status"), "top_k":k,
            "queries":paired["n_queries"], "paired_R1_minus_R5":paired,
            "baselines":baselines, "ablations":masks,
            "warning":"Post-construction masks are not construction ablations; "
                      "no independent published implementation was run."}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args=ap.parse_args()
    report = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result=study_summary(report)
    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True)+"\n",
                                 encoding="utf-8")
    print(json.dumps(result["paired_R1_minus_R5"], indent=2))


if __name__=="__main__":
    main()
