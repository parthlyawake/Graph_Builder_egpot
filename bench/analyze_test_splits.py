"""Analyze committed, explicitly disclosed historical test-split second looks."""
from __future__ import annotations

from collections import defaultdict
import json
import math
from statistics import fmean

import numpy as np

from bench import egpot_test_splits as protocol, egpot_multi_eval as locked
from bench.analyze_dsb_distance import markdown_table
from bench.analyze_dsb_final import AVERAGES, cluster_weights, failures, strongest_baseline, summarize
from bench.egpot_width_sweep_dev import OUTPUT as CAPTURE


STATUS = protocol.STATUS
RESULTS = protocol.RESULTS
FULL = protocol.FULL
WIDE = "egpot_full_w12"
STRONGEST = "strongest_baseline"
BUDGETS = protocol.BUDGETS
MAIN = (*protocol.EGPOT, *protocol.BASELINES)
PAIRINGS = (
    (WIDE, FULL), ("egpot_no_pareto_w12", "egpot_no_pareto_w4"),
    ("egpot_full_tiebreak_w12", "egpot_full_tiebreak_w4"),
    ("egpot_full_tiebreak_w4", FULL), ("egpot_full_tiebreak_w12", WIDE),
    ("egpot_full_mcts_w4", FULL),
    *((name, FULL) for name in ("egpot_no_pareto_w4", "egpot_no_entropy_w4",
                                "egpot_no_contracts_w4", "egpot_no_choke_point_w4")),
)


def verify_plan():
    if locked.git("rev-parse", f"{protocol.FREEZE_TAG}^{{commit}}") != protocol.FREEZE:
        raise ValueError("Unexpected preregistration tag")
    run_commit = locked.git("rev-parse", f"{protocol.RESULT_TAG}^")
    if locked.git("diff", "--name-only", protocol.FREEZE, run_commit, "--", protocol.PLAN.as_posix()):
        raise ValueError("Runner preregistration differs from the freeze")
    locked.verify_dsb_frozen_code(run_commit)
    if locked.sha256(CAPTURE) != protocol.DEV_INPUT_SHA256:
        raise ValueError("Wrong workspace reference")
    return run_commit


def load_record(app, reference, run_commit):
    path = RESULTS / protocol.result_name(app)
    relative = path.relative_to(protocol.ROOT).as_posix()
    tagged = locked.git("rev-parse", f"{protocol.RESULT_TAG}:{relative}")
    if locked.git("hash-object", f"--path={relative}", str(path)) != tagged:
        raise ValueError(f"{app}: result differs from the committed locked record")
    record = locked.read_json(path)
    expected_header = {
        "schema": 2, "repo": app, "split": "test", "commit": run_commit, "status": "complete",
        "analysis_type": STATUS, "second_look": True, "acknowledge_second_look": True,
        "preregistration_commit": protocol.FREEZE, "test_links": list(protocol.TEST_LINKS),
        "source_revision": reference["source_revision"],
        "frozen_code": {"engine": locked.DSB_EGPOT_TAG[1], "builder": locked.DSB_BUILDER_TAG[1]},
        "prior_record": dict(zip(("file", "sha256"), protocol.PRIOR[app], strict=True)),
    }
    for key, value in expected_header.items():
        if record.get(key) != value:
            raise ValueError(f"{app}: unexpected locked header field {key}")
    configs = record["configs"]
    expected_hashes = {"graph": reference["graphml_sha256"], "labels": reference["label_file_sha256"],
                       "preregistration": locked.sha256(protocol.ROOT / protocol.PLAN),
                       "dev_workspace": protocol.DEV_INPUT_SHA256, "protocol": locked.digest(configs)}
    if (record["verified_hashes"] != expected_hashes
            or record["deterministic_sha256"] != locked.digest(record["rows"])):
        raise ValueError(f"{app}: input or row digest mismatch")
    if (set(configs["main"]) != set(MAIN) or set(configs["choke"]) != {off for _, off in protocol.CHOKE}
            or set(configs["seeds"]) != set(protocol.SEEDED) or configs["weights"]
            or any(set(seeds) != set(map(str, range(6))) for seeds in configs["seeds"].values())):
        raise ValueError(f"{app}: changed run matrix")

    labels = protocol.load_test_labels(locked.REGISTRY[app].labels, expected_hashes["labels"])
    indexed = {row["id"]: row for row in labels}
    depths = record["gold_depths"]
    covers = record["covered_ids"]
    excluded = record["coverage_exclusions"]
    if (set(covers) != set(depths) or len(covers) + len(excluded) != len(labels)
            or set(covers) | {row["id"] for row in excluded} != set(indexed)
            or any(type(depth) is not int or depth < 0 for depth in depths.values())):
        raise ValueError(f"{app}: coverage partitions do not match the test labels")
    jobs, aliases = locked.plan_locked([row for row in labels if row["id"] in depths], configs)
    by_key = {job["key"]: job for job in jobs}
    expected_rows = {
        (alias["experiment"], by_key[alias["key"]]["method"], by_key[alias["key"]]["budget"],
         alias["seed"], by_key[alias["key"]]["label"]["id"]): alias["key"] for alias in aliases
    }
    output = []
    for row, clock in zip(record["rows"], record["latencies"], strict=True):
        row_key = tuple(row[field] for field in ("experiment", "method", "node_budget", "seed", "id"))
        key = expected_rows.pop(row_key, None)
        if key is None:
            raise ValueError(f"{app}: unexpected or duplicate row: {row_key}")
        task = by_key[key]
        query = indexed[task["label"]["id"]]
        width = int(task["method"].rsplit("_w", 1)[1]) if task["method"] in protocol.EGPOT else None
        returned = row["returned_nodes"]
        gold = set(query["gold_nodes"])
        found = set(returned) & gold
        latency = clock["latency_s"]
        if (row["id"] != query["id"] or row["link_id"] != query["link_id"] or row["type"] != query["type"]
                or row["method"] != task["method"] or row["node_budget"] != task["budget"]
                or row["split"] != "test" or row["beam_width"] != width
                or clock["job"] != key or not math.isfinite(latency) or latency < 0
                or len(set(returned)) != len(returned) or query["start_node"] not in returned
                or row["nodes_returned"] != len(returned) or len(returned) > row["node_budget"]
                or set(row["gold_found"]) != found or row["hit"] != int(gold == found)
                or row["gold_recall"] != len(found) / len(gold)):
            raise ValueError(f"{app}: row does not match its frozen job: {key}")
        lookalikes = set(query.get("lookalike_nodes", ()))
        if isinstance(query.get("lookalike_node"), str):
            lookalikes.add(query["lookalike_node"])
        output.append({**row, "app": app, "latency_s": latency, "depth": depths[row["id"]],
                       "label": {**query, "lookalike_nodes": sorted(lookalikes)}})
    if expected_rows:
        raise ValueError(f"{app}: missing rows for frozen jobs")
    return output, excluded, {"record_sha256": locked.sha256(path), **expected_hashes}


def bootstrap(groups, pairs, *, resamples=10_000):
    """Select the best baseline separately for each metric and each draw."""
    names = sorted(groups)
    reference = groups[FULL]
    ids = [(row["id"], row["label"]["start_node"]) for row in reference]
    if not ids or any([(r["id"], r["label"]["start_node"]) for r in g] != ids for g in groups.values()):
        raise ValueError("Expected paired results on the same start-node clusters")
    starts = [(row["app"], row["label"]["start_node"]) for row in reference]
    weights = np.vstack((np.ones(len(ids)), cluster_weights(starts, resamples=resamples, seed=0)))
    n = weights.sum(axis=1, keepdims=True)
    hits = weights @ np.array([[r["hit"] for r in groups[m]] for m in names]).T
    ranks = np.array([[r["nodes_to_hit"] or 0 for r in groups[m]] for m in names]).T
    compactness = np.divide(weights @ ranks, hits, out=np.full(hits.shape, np.inf), where=hits > 0)
    columns = {m: i for i, m in enumerate(names)}
    baseline = [columns[m] for m in sorted(set(protocol.BASELINES) & groups.keys())]
    rates = {"hit": hits / n, "gold_recall": weights @ np.array([
        [r["gold_recall"] for r in groups[m]] for m in names]).T / n}
    best = {field: np.array(baseline)[strongest_baseline(values[:, baseline], compactness[:, baseline])]
            for field, values in rates.items()}
    result = []
    for left, right in pairs:
        comparison = {"left": left, "right": right, "analysis_type": STATUS}
        for field, values in rates.items():
            rhs = best[field] if right == STRONGEST else columns[right]
            delta = values[:, columns[left]] - values[np.arange(len(weights)), rhs]
            comparison[field] = {"difference": float(delta[0]),
                                 "interval_95": np.quantile(delta[1:], [.025, .975]).tolist()}
            if right == STRONGEST:
                comparison[field]["observed_baseline"] = names[rhs[0]]
        result.append(comparison)
    return result


def analyze_app(rows, excluded, *, resamples=10_000):
    output = {key: [] for key in ("main", "overview", "depth", "choke", "seeds", "paired",
                                 "endpoint_returns")}
    output["coverage_exclusions"] = excluded
    groups = defaultdict(list)
    for row in rows:
        groups[row["experiment"], row["node_budget"], row["method"], row["seed"]].append(row)
    for group in groups.values():
        group.sort(key=lambda row: row["id"])
    for budget in BUDGETS:
        main = {name: groups["main", budget, name, 0] for name in MAIN}
        off = ({name: groups["choke", budget, name, 0] for _, name in protocol.CHOKE}
               if budget in (20, 40) else {})
        if not all(main.values()) or not all(off.values()):
            raise ValueError("Missing main or choke results")
        stats = {name: summarize(group) for name, group in main.items()}
        def baseline_rank(name):
            row = stats[name]
            return (-row["hit_count"], row["nodes_to_hit"] if row["nodes_to_hit"] is not None else math.inf, name)

        other = min(set(protocol.BASELINES) - {"ppr"}, key=baseline_rank)
        shown = (*protocol.EGPOT[:6], "ppr", other)
        output["overview"].extend({"budget": budget, "method": name, **stats[name]} for name in shown)
        output["main"].extend({"budget": budget, "method": name, **stats[name]} for name in MAIN)
        output["choke"].extend({"budget": budget, "method": name, **summarize(group)}
                               for name, group in off.items())
        for name, group in main.items():
            depths = sorted({r["depth"] for r in group})
            for depth in depths:
                output["depth"].append({"budget": budget, "method": name, "depth": depth,
                                        **summarize([r for r in group if r["depth"] == depth])})
        pairs = [(name, base) for name in protocol.EGPOT for base in (*protocol.BASELINES, STRONGEST)]
        pairs.extend(PAIRINGS)
        if off:
            pairs.extend((off_name, on) for on, off_name in protocol.CHOKE)
        output["paired"].extend({"budget": budget, **r}
                                for r in bootstrap(main | off, pairs, resamples=resamples))
    for (section, budget, method, seed), group in sorted(groups.items()):
        if section == "seeds":
            output["seeds"].append({"budget": budget, "method": method, "seed": seed, **summarize(group)})
            if method == "egpot_full_mcts_w4" and budget == 40:
                # Exact endpoint ID membership, independent of full-hit status.
                endpoint_rows = [r for r in group if r["label"]["contract_node"].startswith("http::")]
                output["endpoint_returns"].append({"seed": seed, "n": len(endpoint_rows),
                    "count": sum(r["label"]["contract_node"] in r["returned_nodes"] for r in endpoint_rows)})
    output["seed_spread"] = locked.dsb_seed_summary([{**r, "experiment": "seeds"} for r in output["seeds"]])
    output["misses"] = failures([r for r in rows if r["experiment"] != "seeds" or r["seed"] != 0])
    output["primary"] = next(r for r in output["paired"]
                             if (r["budget"], r["left"], r["right"]) == (40, FULL, STRONGEST))
    return output


def predictions(scopes):
    counts = {app: {(row["method"], row["budget"]): row["hit_count"] for row in data["main"]}
              for app, data in scopes.items()}
    train, boutique = counts["train_ticket"], counts["online_boutique"]
    strongest = scopes["train_ticket"]["primary"]["hit"]["observed_baseline"]
    endpoint = sorted(scopes["train_ticket"]["endpoint_returns"], key=lambda r: r["seed"])
    if len(endpoint) != 6 or any(not r["n"] for r in endpoint):
        raise ValueError("Expected six predictions on covered Train-Ticket endpoints")
    width = {}
    for app, count in counts.items():
        width[app] = {str(b): {"width4": count[FULL, b], "width12": count[WIDE, b],
                               "held": (count[WIDE, b] > count[FULL, b] if b == 40
                                        else count[WIDE, b] < count[FULL, b])} for b in (10, 40)}
    pooled_widths = {str(b): {"width4": sum(count[FULL, b] for count in counts.values()),
                               "width12": sum(count[WIDE, b] for count in counts.values())}
                     for b in (10, 40)}
    return {
        "A": {"held": train[FULL, 40] > train[strongest, 40], "full_w4": train[FULL, 40],
              "strongest": strongest, "baseline": train[strongest, 40]},
        "B": {"held": boutique["ppr", 40] >= boutique[FULL, 40], "ppr": boutique["ppr", 40],
              "full_w4": boutique[FULL, 40]},
        "C": {"held": all(part["held"] for app in width.values() for part in app.values()), "apps": width, "pooled": pooled_widths},
        "D": {"held": endpoint[0]["count"] == 0, "seeds": endpoint},
    }


def historical(app, new_rows):
    """Only analysis, after both tagged new records have been verified."""
    filename, digest = protocol.PRIOR[app]
    path = RESULTS / filename
    if locked.sha256(path) != digest:
        raise ValueError(f"{app}: historical record SHA-256 changed")
    records = locked.read_json(path)["rows"]
    old_split = "test" if app == "online_boutique" else "all"
    outcomes = {(r["method"], r["node_budget"], r["id"]): r for r in records
                if r["experiment"] == "main" and r["split"] == old_split and r["seed"] == 0
                and r["link_id"] in protocol.TEST_LINKS}
    comparisons = []
    weights_by_queries = {}
    for name in MAIN:
        if name.endswith("_w12"):
            continue
        old_name = name.removesuffix("_w4")
        for budget in BUDGETS:
            cohort = [r for r in new_rows if (r["method"], r["node_budget"], r["experiment"], r["seed"])
                      == (name, budget, "main", 0)]
            matching = [(outcomes[old_name, budget, r["id"]], r) for r in cohort
                        if (old_name, budget, r["id"]) in outcomes]
            if not matching:
                continue
            if any((a["link_id"], a["type"]) != (b["link_id"], b["type"]) for a, b in matching):
                raise ValueError(f"{app}: a historical query ID no longer matches link/type")
            metrics = {}
            old, new = zip(*matching, strict=True)
            for field in ("hit", "gold_recall", "precision", "path_coverage", "ordered_path_match",
                          "nodes_returned", "nodes_to_hit", "precision_at_hit"):
                if any(field not in r for r in old):
                    continue
                a = [r[field] for r in old if r[field] is not None]
                b = [r[field] for r in new if r[field] is not None]
                previous = sum(a) if field == "hit" else fmean(a) if a else None
                current = sum(b) if field == "hit" else fmean(b) if b else None
                metrics[field] = {"earlier": previous, "second_look": current,
                                  "difference": current - previous
                                  if current is not None and previous is not None else None}
            query_ids = tuple(r["id"] for r in new)
            if query_ids not in weights_by_queries:
                weights_by_queries[query_ids] = cluster_weights(
                    [(app, r["label"]["start_node"]) for r in new], resamples=10_000, seed=0)
            weights = weights_by_queries[query_ids]
            intervals = {}
            for field in ("hit", "gold_recall"):
                if field in metrics:
                    delta = np.array([b[field] - a[field] for a, b in matching])
                    intervals[field] = np.quantile((weights @ delta) / weights.sum(axis=1),
                                                   [.025, .975]).tolist()
            comparisons.append({"method": name, "earlier_method": old_name, "budget": budget,
                                "n": len(matching), "metrics": metrics, "rate_intervals_95": intervals})
    return {"file": filename, "sha256": digest, "analysis_type": STATUS, "comparisons": comparisons}


def analyze():
    commit = verify_plan()
    reference = locked.read_json(CAPTURE)["datasets"]
    inputs = {app: load_record(app, reference[app], commit) for app in protocol.PRIOR}
    scopes = {app: analyze_app(rows, excluded) for app, (rows, excluded, _) in inputs.items()}
    return {"analysis_type": STATUS, "inputs": {app: value[2] for app, value in inputs.items()},
            "bootstrap": {"resamples": 10_000, "seed": 0, "confidence_level": .95,
                          "cluster": "start_node", "multiplicity_adjustment": False},
            "scopes": scopes, "predictions": predictions(scopes),
            "historical": {app: historical(app, value[0]) for app, value in inputs.items()}}


def render(report):
    lines = [f"# Boutique and Train-Ticket test splits ({STATUS})", "",
             "The cohorts were scored previously. This report describes a second look. "
             "All intervals are unadjusted 95% start-node cluster bootstrap intervals.", ""]

    def section(title, headers, rows):
        lines.extend([f"## {title} ({STATUS})", "", *markdown_table(headers, rows)])

    def fmt(value):
        if value is None:
            return "—"
        return str(value) if isinstance(value, int) else f"{value:.5f}"

    def interval(stat):
        lo, hi = stat["interval_95"]
        return f"{stat['difference']:+.4f} [{lo:+.4f}, {hi:+.4f}]"

    def n_hits(data, method, budget):
        r = next(r for r in data["main"] if (r["method"], r["budget"]) == (method, budget))
        return f"{r['hit_count']}/{r['n']}"

    primary = [(app, data, data["primary"]) for app, data in report["scopes"].items()]
    section("Primary comparisons, budget 40, seed 0",
            ["App", "EG-POT w4", "Observed strongest", "Baseline hits", "Hit-rate difference [95% interval]", "Includes zero?"],
            ((app, n_hits(data, FULL, 40), p["hit"]["observed_baseline"],
              n_hits(data, p["hit"]["observed_baseline"], 40), interval(p["hit"]),
              "yes" if p["hit"]["interval_95"][0] <= 0 <= p["hit"]["interval_95"][1] else "no")
             for app, data, p in primary))
    p = report["predictions"]
    def verdict(held):
        return "Held" if held else "Failed"

    prediction_rows = [
        ("A · Train-Ticket", f"{p['A']['full_w4']} vs {p['A']['baseline']} ({p['A']['strongest']})",
         verdict(p["A"]["held"])),
        ("B · Boutique", f"PPR {p['B']['ppr']} vs EG-POT {p['B']['full_w4']}", verdict(p["B"]["held"])),
    ]
    for app, widths in p["C"]["apps"].items():
        for budget in ("10", "40"):
            data = widths[budget]
            prediction_rows.append((f"C · {app} budget {budget}", f"{data['width4']} → {data['width12']}",
                                    verdict(data["held"])))
    for budget, data in p["C"]["pooled"].items():
        prediction_rows.append((f"C · pooled budget {budget}", f"{data['width4']} → {data['width12']}",
                                "Descriptive"))
    prediction_rows.append(("C · both parts in both apps", "Width-12 gain at 40 and loss at 10",
                            verdict(p["C"]["held"])))
    prediction_rows.append(("D · Train-Ticket blend", ", ".join(f"{r['count']}/{r['n']}" for r in p["D"]["seeds"])
                            + " in seed order 0–5", verdict(p["D"]["held"])))
    section("Predictions made before this run; the cohorts were seen before",
            ["Prediction", "Observed full-hit count or endpoint returns", "Verdict"], prediction_rows)

    metrics = ["Hits", "Hit rate", "Recall", "Precision", "Path coverage", "Ordered path match",
               "Nodes", "Nodes-to-hit", "Precision-at-hit", "Latency s"]
    def stats(r):
        return (f"{r['hit_count']}/{r['n']}", *(fmt(r[key]) for key in AVERAGES))

    for app, data in report["scopes"].items():
        section(f"{app} budget comparison", ["Budget", "Method", *metrics],
                ((r["budget"], r["method"], *stats(r)) for r in data["overview"]))
        section(f"{app} all main methods", ["Budget", "Method", *metrics],
                ((r["budget"], r["method"], *stats(r)) for r in data["main"]))
        section(f"{app} choke-off side runs", ["Budget", "Method", *metrics],
                ((r["budget"], r["method"], *stats(r)) for r in data["choke"]))
        section(f"{app} paired 95% intervals", ["Budget", "Method", "Reference", "Hit rate", "Recall",
                                               "Strongest for hits", "Strongest for recall"],
                ((r["budget"], r["left"], r["right"], interval(r["hit"]), interval(r["gold_recall"]),
                  r["hit"].get("observed_baseline", "—"), r["gold_recall"].get("observed_baseline", "—"))
                 for r in data["paired"]))
        section(f"{app} by gold depth", ["Budget", "Depth", "Method", *metrics],
                ((r["budget"], r["depth"], r["method"], *stats(r)) for r in data["depth"]))
        section(f"{app} per-seed metrics", ["Budget", "Method", "Seed", *metrics],
                ((r["budget"], r["method"], r["seed"], *stats(r)) for r in data["seeds"]))
        section(f"{app} seed spread", ["Budget", "Method", "Metric", "Median", "Min", "Max", "Defined seeds"],
                ((r["budget"], r["method"], metric, *(fmt(values[key]) for key in
                  ("median", "min", "max", "defined_seeds"))) for r in data["seed_spread"]
                 for metric, values in r["metrics"].items()))
        section(f"{app} builder coverage exclusions", ["Query", "Link", "Type", "Missing nodes or edges"],
                ((r["id"], r["link_id"], r["type"], json.dumps(r["failures"], ensure_ascii=False))
                 for r in data["coverage_exclusions"]))
        section(f"{app} missed gold IDs", ["Query", "Method", "Budget", "Seed", "Missing gold",
                                          "Lookalike?", "Returned lookalikes"],
                ((r["id"], r["method"], r["node_budget"], r["seed"], r["missed_gold_node"],
                  "yes" if r["lookalike_returned"] else "no", ", ".join(r["returned_lookalike_nodes"]))
                 for r in data["misses"]))
    lines.extend(["## Earlier records, descriptive comparison only (second look, exploratory)", "",
                  "The comparison uses matched covered query IDs. Differences are descriptive. "
                  "The earlier runs used different engine, builder or policy versions.", ""])
    for app, data in report["historical"].items():
        section(f"{app} versus {data['file']}",
                ["Budget", "Current method", "Earlier method", "Matched queries", "Metric",
                 "Earlier", "Second look", "Difference", "95% interval of rate difference"],
                ((r["budget"], r["method"], r["earlier_method"], r["n"], key,
                  fmt(values["earlier"]), fmt(values["second_look"]), fmt(values["difference"]),
                  ("[" + ", ".join(fmt(x) for x in r["rate_intervals_95"][key]) + "]")
                  if key in r["rate_intervals_95"] else "—")
                 for r in data["comparisons"] for key, values in r["metrics"].items()))
    return "\n".join(lines)


def main():
    paths = (RESULTS / "test_splits_analysis.json", RESULTS / "test_splits_analysis.md")
    if any(path.exists() for path in paths):
        raise ValueError("Analysis already exists")
    report = analyze()
    outputs = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n", render(report))
    for path, content in zip(paths, outputs, strict=True):
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        print(path)


if __name__ == "__main__":
    main()
