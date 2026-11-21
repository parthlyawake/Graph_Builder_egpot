"""Render descriptive Suite 2 tables from completed runs' returned node IDs."""

import argparse
import json
from collections import Counter
from pathlib import Path


QUERIES = Path(__file__).with_name("suite2_queries.json")
SOURCE_CONSUMER_COUNTS = {"C06": 9, "C07": 8, "C08": 9}
GROUP_FIELDS = ("repo", "experiment", "method", "budget", "wording", "seed")
OUTCOME_FIELDS = (
    "recall", "precision", "recall_ceiling", "correct_retrieved", "decoy_retrieved",
    "clean", "confused", "b_retrieved", "c_retrieved", "partial", "hit",
)


def _outcomes(case, returned):
    gold = case["gold_ids"]
    found = set(gold).intersection(returned)
    if case["type"] == "blast_radius":
        size = len(gold)
        recall = len(found) / size
        total = SOURCE_CONSUMER_COUNTS.get(case["link_id"], size)
        return {
            "recall": recall,
            "precision": len(found) / len(returned) if returned else 0.0,
            "recall_ceiling": f"{size}/{total}",
            "hit": 5 * len(found) >= 4 * size,
        }
    if case["type"] == "lookalike":
        (correct,) = gold
        has_correct = correct in found
        has_decoy = case["decoy_id"] in returned
        return {
            "correct_retrieved": has_correct,
            "decoy_retrieved": has_decoy,
            "clean": has_correct and not has_decoy,
            "confused": has_decoy and not has_correct,
            "hit": has_correct,
        }
    if case["type"] != "chain":
        raise ValueError(f"Unknown Suite 2 case type: {case['type']}")
    b_node, c_node = gold
    return {
        "b_retrieved": b_node in found,
        "c_retrieved": c_node in found,
        "partial": len(found) == 1,
        "hit": len(found) == 2,
    }


def analyze(queries, results):
    """Use the run's rows, or a row list, and join by the frozen link ID."""
    cases = {case["link_id"]: case for case in queries}
    if len(cases) != len(queries):
        raise ValueError("Duplicate Suite 2 link IDs")
    if isinstance(results, dict):
        results = results["rows"]
    details = []
    hits, totals = Counter(), Counter()
    seen = set()
    for row in results:
        case = cases[row["link_id"]]
        budget = row.get("budget", row.get("node_budget"))
        wording = row.get("wording", row.get("type"))
        if budget not in case["budgets"] or wording not in ("explicit", "indirect"):
            raise ValueError(f"Unexpected budget or wording for {case['link_id']}")
        raw = row["returned_nodes"]
        if not isinstance(raw, list) or any(not isinstance(node, str) for node in raw):
            raise ValueError("returned_nodes must be a list of node ID strings")
        returned = set(raw)
        if len(returned) != len(raw) or len(raw) > budget:
            raise ValueError(f"Duplicate returned node or exceeded budget for {case['link_id']}")
        detail = {
            "link_id": case["link_id"], "repo": case["repo"], "type": case["type"],
            "experiment": row.get("experiment", "main"), "method": row["method"],
            "budget": budget, "wording": wording, "seed": row.get("seed", 0),
        }
        group = tuple(detail[field] for field in GROUP_FIELDS)
        key = (*group, detail["link_id"])
        if key in seen:
            raise ValueError(f"Duplicate Suite 2 output row: {key}")
        seen.add(key)
        detail.update(_outcomes(case, returned))
        details.append(detail)
        totals[group] += 1
        hits[group] += detail["hit"]
    details.sort(key=lambda row: (
        row["repo"], row["link_id"], *(row[field] for field in GROUP_FIELDS[1:])
    ))
    counts = [
        {**dict(zip(GROUP_FIELDS, group, strict=True)), "hits": hits[group], "links": totals[group]}
        for group in sorted(totals)
    ]
    return {"details": details, "counts": counts}


def _table(rows, fields):
    def cell(value):
        if value is None:
            return "—"
        if isinstance(value, bool):
            return "yes" if value else "no"
        if isinstance(value, float):
            return f"{value:.4f}"
        return str(value).replace("|", r"\|").replace("\n", " ")

    return "\n".join([
        "| " + " | ".join(key.replace("_", " ") for key in fields) + " |",
        "|" + "|".join("---" for _ in fields) + "|",
        *("| " + " | ".join(cell(row.get(key)) for key in fields) + " |" for row in rows),
    ])


def markdown(analysis):
    identity = ("link_id", "type", *GROUP_FIELDS)
    return "\n\n".join([
        "# Suite 2 exploratory results",
        "Each row represents one wording and seed. Lookalike hits count the correct "
        "node, and clean and confused outcomes have their own columns. Chain partial "
        "credit means exactly one destination was retrieved. Hit counts use each "
        "repository and experiment separately.",
        "## Per-link outcomes",
        _table(analysis["details"], (*identity, *OUTCOME_FIELDS)),
        "## Hit counts by method",
        _table(analysis["counts"], (*GROUP_FIELDS, "hits", "links")),
    ]) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--queries", type=Path, default=QUERIES)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    queries = json.loads(args.queries.read_text(encoding="utf-8"))
    results = json.loads(args.results.read_text(encoding="utf-8"))
    args.out.write_text(markdown(analyze(queries, results)), encoding="utf-8")


if __name__ == "__main__":
    main()
