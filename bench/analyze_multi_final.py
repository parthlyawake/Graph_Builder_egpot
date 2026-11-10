"""Read-only aggregation of persisted locked-run metrics; no retrieval imports.

Writes only the requested Markdown report. Stored metrics are aggregated,
never recomputed from a traversal. Missing discovery order is not inferred.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import fmean

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULT = ROOT / "bench/results/train_ticket_final_0545478c.json"
DEFAULT_OUTPUT = Path(r"C:\dev\triage_out\step29\train_summary.md")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def table(headers, rows):
    return ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"] + [
        "| " + " | ".join(str(value).replace("|", "\\|").replace("\n", " ") for value in row) + " |"
        for row in rows]


def number(value, digits=4):
    return "—" if value is None else f"{value:.{digits}f}"


def stats(rows):
    if not rows:
        return None
    hits = [row for row in rows if row["hit"]]
    for row in rows:
        assert bool(row["hit"]) == (row["nodes_to_hit"] is not None), "Inconsistent stored hit/nodes_to_hit"
    return {"n": len(rows), "hits": sum(row["hit"] for row in rows),
            "recall": fmean(row["gold_recall"] for row in rows),
            "nodes": fmean(row["nodes_returned"] for row in rows),
            "nodes_to_hit": fmean(row["nodes_to_hit"] for row in hits) if hits else None,
            "precision_at_hit": fmean(row["precision_at_hit"] for row in hits) if hits else None}


def select(data, method=None, budget=None, *, experiment="main", split=None, predicate=lambda r: True):
    return [row for row in data["rows"] if row["experiment"] == experiment
            and (method is None or row["method"] == method)
            and (budget is None or row["node_budget"] == budget)
            and (split is None or row["split"] == split) and predicate(row)]


def get(data, method, budget, **kwargs):
    return stats(select(data, method, budget, **kwargs))


def best_baseline(data, baselines, budget, *, split=None, efficiency=False):
    values = [(name, get(data, name, budget, split=split)) for name in baselines]
    values = [(name, s) for name, s in values if s is not None and
              (not efficiency or s["hits"] / s["n"] >= .9 and s["nodes_to_hit"] is not None)]
    return min(values, key=lambda item: (
        0 if efficiency else -item[1]["hits"],
        item[1]["nodes_to_hit"] if item[1]["nodes_to_hit"] is not None else math.inf,
        item[0]), default=None)


def integrity(data, result, graph_provenance, label_provenance, labels_path, preregistration):
    graph_meta, label_meta = read(graph_provenance), read(label_provenance)
    identity = data["identity"]
    checks = {
        "stored graph SHA matches graph provenance": identity["graph"] == graph_meta["graphml_sha256"],
        "stored label SHA matches label provenance": identity["labels"] == label_meta["query_file_sha256"],
        "label provenance refers to same graph": label_meta["graphml_sha256"] == identity["graph"],
        "verified graph hash agrees": identity["verified_hashes"]["graph"] == identity["graph"],
        "verified label hash agrees": identity["verified_hashes"]["labels"] == identity["labels"],
        "current labels hash agrees": sha(labels_path) == identity["labels"],
        "current preregistration hash agrees": sha(preregistration) == identity["verified_hashes"]["preregistration"],
    }
    canonical = json.dumps(data["rows"], sort_keys=True, separators=(",", ":"), allow_nan=False)
    checks["stored deterministic rows digest agrees"] = hashlib.sha256(canonical.encode()).hexdigest() == data["deterministic_sha256"]
    if not all(checks.values()):
        raise ValueError("Integrity failure: " + ", ".join(key for key, passed in checks.items() if not passed))
    provenance = {"commit": data["commit"], "graph_sha256": identity["graph"],
                  "labels_sha256": identity["labels"],
                  "preregistration_sha256": identity["verified_hashes"]["preregistration"],
                  "versions": data["versions"], "worker_count": data["worker_count"],
                  "utc_timestamp": data["utc_timestamp"], "result_file_sha256": sha(result)}
    return provenance, checks


def analyze(result, output, *, ob_result=ROOT / "bench/results/test_final_41d61e11.json",
            labels_path=ROOT / "bench/labels/train_ticket_egpot_queries.json",
            graph_provenance=ROOT / "bench/results/train_ticket_graph.provenance.json",
            label_provenance=ROOT / "bench/labels/train_ticket_egpot_queries.provenance.json",
            preregistration=ROOT / "bench/preregistration_train_ticket.md",
            scorecard_source=ROOT / "viz/js/final_test_logic.js"):
    data, ob = read(result), read(ob_result)
    provenance, checks = integrity(data, result, graph_provenance, label_provenance, labels_path, preregistration)
    labels = {row["id"]: row for row in read(labels_path)}
    js = Path(scorecard_source).read_text(encoding="utf-8")
    baselines = json.loads(re.search(r"const baselines=(\[.*?\]);", js).group(1))
    prereg = Path(preregistration).read_text(encoding="utf-8")
    required = ["at least 4 of 30 queries", "at least 6 of 30", "<= 60%"]
    if not all(text in prereg for text in required):
        raise ValueError("Preregistration rules changed; analyzer's threshold mapping must be reviewed")
    methods = list(data["configs"]["main"])
    budgets = sorted({row["node_budget"] for row in select(data)})
    assert budgets == [10, 20, 40]
    for method in methods:
        for budget in budgets:
            rows = select(data, method, budget)
            assert len(rows) == 30 and len({row["id"] for row in rows}) == 30
            saved = [s for s in data["summary"] if s["experiment"] == "main"
                     and s["method"] == method and s["budget"] == budget]
            assert len(saved) == 1
            computed = stats(rows)
            for field, source_field in (("hits", "hit_count"), ("recall", "gold_recall"),
                                        ("nodes", "nodes_returned"), ("nodes_to_hit", "nodes_to_hit"),
                                        ("precision_at_hit", "precision_at_hit")):
                assert computed[field] == saved[0][source_field], (method, budget, field, "stored summary mismatch")
    lines = ["# Train-Ticket locked result summary", "", "Read-only aggregation of stored JSON fields. No retriever, scorer, metric-from-traversal calculation or evaluation was run.", "",
             "## 1. Integrity and stored provenance", "", "```json", json.dumps(provenance, indent=2), "```", ""]
    lines += table(["Check", "Result"], [(key, "PASS" if value else "FAIL") for key, value in checks.items()])
    lines += ["", "## 2. Main methods and ablations", "",
              "**Bold** marks every tied best value in each column, before display rounding. Hits/recall/precision-at-hit: higher is better; nodes/nodes-to-hit: lower is better. Low node counts do not imply high coverage. Nodes-to-hit and precision-at-hit use hits only; — means no hits.", ""]
    for budget in budgets:
        values = {name: get(data, name, budget) for name in methods}
        directions = {"hits": max, "recall": max, "nodes": min, "nodes_to_hit": min, "precision_at_hit": max}
        best = {key: function(s[key] for s in values.values() if s[key] is not None)
                for key, function in directions.items()}
        def mark(name, field, display):
            value = values[name][field]
            return f"**{display}**" if value is not None and value == best[field] else display
        rows = []
        for name, s in values.items():
            rows.append([name, mark(name, "hits", f"{s['hits']}/{s['n']}"),
                         mark(name, "recall", number(s["recall"])), mark(name, "nodes", number(s["nodes"])),
                         mark(name, "nodes_to_hit", number(s["nodes_to_hit"])) + f" ({s['hits']} hits)",
                         mark(name, "precision_at_hit", number(s["precision_at_hit"]))])
        lines += [f"### Budget {budget}", ""] + table(
            ["Method", "Hits", "Recall", "Mean nodes", "Mean nodes-to-hit (hit count)", "Mean precision-at-hit"], rows) + [""]
    lines += ["## 3. Hits by query type and lookalike group", ""]
    groups = [("Explicit", lambda r: r["type"] == "explicit", 15),
              ("Indirect", lambda r: r["type"] == "indirect", 15),
              ("Lookalike links 4,5,6", lambda r: r["link_id"] in {4, 5, 6}, 6),
              ("Other 12 links", lambda r: r["link_id"] not in {4, 5, 6}, 24)]
    for title, predicate, n in groups:
        values = {(name, budget): get(data, name, budget, predicate=predicate) for name in methods for budget in budgets}
        assert all(s["n"] == n for s in values.values())
        best = {budget: max(values[name, budget]["hits"] for name in methods) for budget in budgets}
        rows = []
        for name in methods:
            cells = []
            for budget in budgets:
                h = values[name, budget]["hits"]
                cells.append(f"**{h}/{n}**" if h == best[budget] else f"{h}/{n}")
            rows.append([name, *cells])
        lines += [f"### {title} (n={n})", ""] + table(["Method", *map(str, budgets)], rows) + [""]
    lines += ["## 4. Preregistered expectations", ""]
    differences = []
    for budget in budgets:
        full = {r["id"]: r for r in select(data, "egpot_full", budget)}
        off = {r["id"]: r for r in select(data, "egpot_no_choke_point", budget)}
        for qid in full:
            fields = set(full[qid]) | set(off[qid])
            changed = [key for key in sorted(fields) if key not in {"method", "latency_s"}
                       and full[qid].get(key) != off[qid].get(key)]
            if changed:
                differences.append([qid, budget, ", ".join(changed)])
    lines += [f"### E1: {'identical' if not differences else 'different'} stored records", "",
              f"Compared all stored non-latency fields except method name for 30 queries x 3 budgets = 90 pairs. Differences: {len(differences)}.",
              "Full visited sets/discovery order were not saved, so identity of those unrecorded outputs cannot be independently confirmed.", ""]
    if differences:
        lines += table(["Query", "Budget", "Differing fields"], differences) + [""]
    full20, no_contracts = get(data, "egpot_full", 20), get(data, "egpot_no_contracts", 20)
    obfull, oboff = get(ob, "egpot_full", 20, split="test"), get(ob, "egpot_no_contracts", 20, split="test")
    td, od = full20["hits"]-no_contracts["hits"], obfull["hits"]-oboff["hits"]
    lines += ["### E2: contract-score effect at budget 20", ""] + table(
        ["Dataset", "Full hits", "No-contracts hits", "Difference", "Difference in hit-rate points"],
        [["Train", f"{full20['hits']}/30", f"{no_contracts['hits']}/30", td, number(100*td/30)],
         ["Online Boutique TEST", f"{obfull['hits']}/{obfull['n']}", f"{oboff['hits']}/{oboff['n']}", od, number(100*od/obfull['n'])]])
    lines += ["", "The smaller contract-score effect expected for Train is not observed: its effect is larger in raw hits and slightly larger in hit-rate points.", "",
              "### E3: BFS-style baselines versus full", ""]
    rows = []
    for budget in budgets:
        for title, source, split in [("Train", data, None), ("Online Boutique TEST", ob, "test")]:
            ss = [get(source, method, budget, split=split) for method in ("egpot_full", "bfs", "vector_bfs_k2")]
            rows.append([title, budget, *[f"{s['hits']}/{s['n']}" for s in ss]])
    lines += table(["Dataset", "Budget", "EG-POT full", "BFS", "Vector BFS k2"], rows)
    lines += ["", "BFS-style baseline hit rates do not improve on Train: BFS remains at zero; vector-BFS is lower than Online Boutique at every budget.", "",
              "### E4: compactness at budget 40", ""]
    full40 = get(data, "egpot_full", 40)
    efficient = best_baseline(data, baselines, 40, efficiency=True)
    best40 = best_baseline(data, baselines, 40)
    ratio = full40["nodes_to_hit"] / efficient[1]["nodes_to_hit"] if efficient else None
    lines += table(["Item", "Stored-number result"], [
        ["Full nodes-to-hit", f"{number(full40['nodes_to_hit'])} ({full40['hits']}/30 hits)"],
        ["Qualifying baseline requirement", ">=27/30 hits"],
        ["Best qualifying baseline", efficient[0] if efficient else "None"],
        ["Ratio full/baseline", number(ratio)],
        ["Highest-hit baseline (not a substitute)", f"{best40[0]}: {best40[1]['hits']}/30 hits"]])
    lines += ["", "No qualifying baseline exists; a compactness ratio cannot be calculated under the registered rule.", "",
              "## 5. Mechanical scorecard", "",
              "Definitions and the eight-baseline pool are taken from viz/js/final_test_logic.js. Train has one whole set, not two splits: the registered 4-hit/6-hit thresholds apply once to that set. No artificial dev/test split is created. None of the observed component deltas is in the underspecified small-positive 1..3 range, so split-specific Inconclusive wording does not affect these verdicts.", ""]
    cards = []
    for title, ablation in [("Contract score helps", "egpot_no_contracts"), ("Choke-point rule helps", "egpot_no_choke_point"),
                            ("Entropy helps", "egpot_no_entropy"), ("Pareto beats equal weights", "egpot_no_pareto")]:
        off = get(data, ablation, 20)
        delta = full20["hits"]-off["hits"]
        verdict = "Supported" if delta >= 4 else "Not supported" if delta <= 0 else "Not determined: single-set subthreshold rule unspecified"
        cards.append([title, f"{full20['hits']} - {off['hits']} = {delta:+d}", verdict,
                      "Budget 20, no MCTS: full minus ablation must be >=4/30 hits."])
    on = get(data, "egpot_full_mcts", 20)
    delta = on["hits"]-full20["hits"]
    cards.append(["MCTS helps", f"{on['hits']} - {full20['hits']} = {delta:+d}",
                  "Supported" if delta >= 4 else "Not supported" if delta <= 0 else "Inconclusive",
                  "Budget 20: MCTS minus full must be >=4 hits; nonpositive effect is Not supported."])
    cards.append(["Compactness", f"Full {number(full40['nodes_to_hit'])}; qualifying baseline: " + (efficient[0] if efficient else "none"),
                  "Supported" if ratio is not None and ratio <= .6 else "Not supported",
                  "Budget 40: among eight baselines reaching >=90% hits, take lowest mean nodes-to-hit; full must use <=60% of it. No qualifying baseline means no support."])
    full10 = get(data, "egpot_full", 10)
    best10 = best_baseline(data, baselines, 10)
    delta = full10["hits"]-best10[1]["hits"]
    cards.append(["Small-budget advantage", f"{full10['hits']} - {best10[1]['hits']} ({best10[0]}) = {delta:+d}",
                  "Supported" if delta >= 6 else "Not supported",
                  "Budget 10: full minus the highest-hit of the eight baselines must be >=6/30 hits; baseline ties break by nodes-to-hit then name."])
    lines += table(["Claim", "Numbers", "Verdict", "Rule"], cards) + [""]
    lines += ["## 6. Seeds and weights", "", "### MCTS seeds", ""]
    rows = []
    for method, seeds in data["configs"]["seeds"].items():
        for budget in (20, 40):
            values = []
            for seed in sorted(map(int, seeds)):
                rr = select(data, method, budget, experiment="seeds", predicate=lambda r: r["seed"] == seed)
                assert len(rr) == 30
                values.append(sum(r["hit"] for r in rr))
            rows.append([method, budget, ", ".join(map(str, values)), min(values), max(values)])
    lines += table(["Method", "Budget", "Hits at seeds 0,1,2,3,4", "Min /30", "Max /30"], rows)
    lines += ["", "### Weight distribution", "", "Equal weights are a separate control, excluded from the 54 alternative vectors; no best vector is selected.", ""]
    rows = []
    for budget in (10, 20):
        reference = get(data, "egpot_full", budget)["hits"]
        vectors = [name for name in data["configs"]["weights"] if name != "equal"]
        assert len(vectors) == 54
        counts = []
        for name in vectors:
            rr = select(data, name, budget, experiment="weights")
            assert len(rr) == 30
            counts.append(sum(r["hit"] for r in rr))
        rows.append([budget, reference, sum(h < reference for h in counts), sum(h == reference for h in counts), sum(h > reference for h in counts)])
    lines += table(["Budget", "Pareto hits /30", "Worse", "Tied", "Better"], rows) + [""]
    lines += ["## 7. Per-link hits at budget 20", "", "E = explicit hit; I = indirect hit; - = miss. For example EI, E-, -I, --.", ""]
    grid = []
    for method in methods:
        rr = {(r["link_id"], r["type"]): r for r in select(data, method, 20)}
        cells = [("E" if rr[link, "explicit"]["hit"] else "-") +
                 ("I" if rr[link, "indirect"]["hit"] else "-") for link in range(1, 16)]
        grid.append([method, *cells])
    lines += table(["Method", *map(str, range(1, 16))], grid) + [""]
    lines += ["## 8. Misses at budget 20", "",
              "Missing gold IDs = hash-verified label gold_nodes minus the JSON's stored gold_found. First five returned IDs cannot be determined: the JSON saves no visited/discovery/ordered path list. gold_found is only a sorted gold subset, not retrieval order. No nodes are reconstructed or substituted.", ""]
    best20 = best_baseline(data, baselines, 20)
    miss_methods = list(dict.fromkeys(["egpot_full", "egpot_no_pareto", "mcts_standard", best20[0]]))
    lines += [f"Best baseline by hits: {best20[0]} ({best20[1]['hits']}/30); ties use lowest nodes-to-hit then method name.", ""]
    for method in miss_methods:
        rr = sorted((r for r in select(data, method, 20) if not r["hit"]), key=lambda r: r["id"])
        lines += [f"### {method}: {len(rr)} misses", ""]
        records = []
        for row in rr:
            missing = sorted(set(labels[row["id"]]["gold_nodes"]) - set(row["gold_found"]))
            records.append([row["id"], "; ".join("`"+n+"`" for n in missing), "Not recorded"])
        lines += table(["Query ID", "Missing gold node IDs", "First five returned IDs"], records) + [""]
    lines += ["## Limits", "",
              "- Full returned-node order and full visited sets are absent. First-five nodes and full-set identity for E1 cannot be independently established.",
              "- No baseline reaches the registered >=90% hit threshold at budget 40, so E4's ratio is unavailable.",
              "- The original site scorecard describes two splits; the preregistration replaces them with one 30-query set. Observed deltas avoid the unregistered small-positive inconclusive boundary.",
              "- Nodes-to-hit averages cover each method's successful queries, which may be different subsets.",
              "- All numeric tables aggregate stored fields only. Label strings are used solely to name missing gold nodes after hash verification."]
    report = "\n".join(lines) + "\n"
    output = Path(output)
    if not output.resolve().is_relative_to(DEFAULT_OUTPUT.parent.resolve()):
        raise ValueError("Analysis output must stay under C:\\dev\\triage_out\\step29")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", type=Path, default=DEFAULT_RESULT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    analyze(args.result, args.output)


if __name__ == "__main__":
    main()
