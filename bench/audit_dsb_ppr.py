"""Audit saved DeathStarBench PPR results without running a retriever."""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import inspect
from itertools import product
from pathlib import Path
from textwrap import dedent

import networkx as nx

from bench import egpot_multi_eval as locked
from bench.egpot_eval import PersonalizedPageRank
from eg_pot import GraphView


RECORDS = {
    "dsb_social": "f6d4d0bda72161da2d3ff27d80738e70819650d1396530f6ab22d17cfc21ca50",
    "dsb_media": "518da8e6b92296e3e67634f0b04d650b0735182aa2a7b4edf8f74363ae9b375c",
}
BUDGETS = (10, 20, 40)
RESULTS = locked.ROOT / "bench/results"


def audited_input(app):
    repo = locked.REGISTRY[app]
    path = RESULTS / f"{app}_final_6ba6e1cf.json"
    if locked.sha256(path) != RECORDS[app]:
        raise ValueError(f"{app}: locked record SHA-256 mismatch")
    record = locked.read_json(path)
    hashes = locked.verify_inputs(repo)
    if ((record["schema"], record["repo"], record["split"]) != (2, app, "all")
            or any(record["identity"]["verified_hashes"][key] != value for key, value in hashes.items())):
        raise ValueError(f"{app}: record schema or input identity mismatch")
    labels = {label["id"]: label for label in locked.read_json(repo.labels)}
    graph = nx.read_graphml(repo.graph, force_multigraph=True)
    return record, graph, labels


def choke_moves(graph):
    """Count changes in allowed adjacency, without solving PageRank."""
    on = GraphView(graph, use_choke_point=True, edge_policy=locked.DSB_EDGE_POLICY)
    off = GraphView(graph, use_choke_point=False, edge_policy=locked.DSB_EDGE_POLICY)
    suppressed, expected, unexpected = 0, 0, 0
    for node, attrs in graph.nodes(data=True):
        blocked = {
            (source, "DEFINES_RPC", "in", key)
            for source, _, key, edge in graph.in_edges(node, keys=True, data=True)
            if attrs.get("type") == "rpc_contract" and edge.get("relation") == "DEFINES_RPC"
        }
        normal = set(on.neighbors(node))
        bypassed = set(off.neighbors(node))
        removed = bypassed - normal
        suppressed += len(removed)
        expected += len(blocked)
        unexpected += len(removed ^ blocked) + len(normal - bypassed)
    return suppressed, expected, unexpected


def audit_app(app):
    record, graph, labels = audited_input(app)
    normal = [row for row in record["rows"] if row["method"] == "ppr" and row["experiment"] == "main"]
    seeds = sorted({row["seed"] for row in normal})
    row_keys = Counter((row["node_budget"], row["seed"], row["id"]) for row in normal)
    expected_keys = Counter(product(BUDGETS, seeds, labels))
    counts = Counter(main=len(normal), complete=int(bool(seeds) and row_keys == expected_keys))
    main_index = {(row["node_budget"], row["seed"], row["id"]): row for row in normal}
    details, hit_mismatches, missing_gold = [], [], []
    undirected = graph.to_undirected(as_view=True)
    distances_by_start = {}
    for row in normal:
        label = labels[row["id"]]
        returned = row["returned_nodes"]
        nodes = set(returned)
        start = label["start_node"]
        counts["within_budget"] += len(returned) <= row["node_budget"]
        counts["start_counted"] += start in nodes
        counts["no_duplicates"] += len(nodes) == len(returned)
        counts["valid_ids"] += nodes <= graph.nodes.keys()
        counts["returned_ids"] += len(returned)
        counts["valid_returned_ids"] += sum(node in graph for node in returned)
        if row["node_budget"] != 40 or row["seed"] != 0:
            continue
        counts["primary"] += 1
        gold = (label["contract_node"], label["handler_node"])
        if len(set(gold)) != 2 or set(gold) != set(label["gold_nodes"]):
            raise ValueError(f"{app}: inconsistent gold labels for {row['id']}")
        ranks = {node: rank for rank, node in enumerate(returned, 1)}
        hit = all(node in nodes for node in gold)
        counts["full_hits"] += hit
        counts["hit_agrees"] += int(hit) == row["hit"]
        if not hit:
            missing_gold.append(row["id"])
        if int(hit) != row["hit"]:
            hit_mismatches.append((row["id"], int(hit), row["hit"]))
        if start not in distances_by_start:
            distances_by_start[start] = nx.single_source_shortest_path_length(undirected, start, cutoff=3)
        distances = distances_by_start[start]
        nearby = [sum(distances.get(node, 4) <= cutoff for node in returned) for cutoff in (1, 2, 3)]
        details.append((row["id"], len(returned), *nearby, *(ranks.get(node, "missing") for node in gold)))

    choke = [row for row in record["rows"] if row["method"] == "ppr_no_choke"
             and row["experiment"] == "choke"]
    off_index = {(row["node_budget"], row["seed"], row["id"]): row for row in choke}
    side_budgets = (20, 40)
    expected_side = set(product(side_budgets, (0,), labels))
    for budget, seed, query_id in sorted(expected_side):
        key = budget, seed, query_id
        if key not in main_index or key not in off_index:
            continue
        on, off = main_index[key], off_index[key]
        counts[f"pairs_{budget}"] += 1
        counts[f"on_hits_{budget}"] += on["hit"]
        counts[f"off_hits_{budget}"] += off["hit"]
        counts[f"hit_agrees_{budget}"] += on["hit"] == off["hit"]
        counts[f"order_agrees_{budget}"] += on["returned_nodes"] == off["returned_nodes"]
    counts["side_complete"] = int(len(choke) == len(off_index) and set(off_index) == expected_side)
    counts["on_config"] = int(record["configs"]["main"]["ppr"]["choke_point"] is True
                              and record["configs"]["main"]["ppr"]["class"] == "PersonalizedPageRank")
    counts["off_config"] = int(record["configs"]["choke"]["ppr_no_choke"]["choke_point"] is False
                               and record["configs"]["choke"]["ppr_no_choke"]["class"] == "PPRNoChoke")
    counts["suppressed"], counts["expected_suppressed"], counts["unexpected_moves"] = choke_moves(graph)
    counts["labels"] = len(labels)
    return counts, seeds, sorted(details), hit_mismatches, missing_gold


def ppr_source_check():
    retrieve = PersonalizedPageRank.retrieve
    scores = PersonalizedPageRank.scores
    retrieve_ast = ast.parse(dedent(inspect.getsource(retrieve)))
    forbidden = {"query", "gold_nodes", "gold_path", "contract_node", "handler_node", "link_id", "label"}
    reads = {node.id for node in ast.walk(retrieve_ast)
             if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}
    source, first_line = inspect.getsourcelines(scores)
    index = next(i for i, line in enumerate(source) if "personalization = " in line)
    return not (reads & forbidden), first_line + index, dedent("".join(source[index:index + 3])).rstrip()


def format_report(results):
    apps = tuple(results)
    stats = {app: results[app][0] for app in apps}
    total = sum(stats.values(), Counter())
    valid_source, source_line, snippet = ppr_source_check()
    checks = [
        ("Main-row coverage", "complete", len(apps), "app(s) complete"),
        ("1a. Within node budget", "within_budget", total["main"], "rows"),
        ("1b. Start included in returned count", "start_counted", total["main"], "rows"),
        ("2. No duplicate node IDs", "no_duplicates", total["main"], "rows"),
        ("3a. Every returned ID exists in GraphML", "valid_ids", total["main"], "rows"),
        ("3b. Returned ID occurrences found in GraphML", "valid_returned_ids", total["returned_ids"], "IDs"),
        ("4a. Both gold nodes returned at budget 40, seed 0", "full_hits", total["labels"], "queries"),
        ("4b. Recorded hit matches independent recomputation", "hit_agrees", total["labels"], "queries"),
        ("7. Distance and rank rows at budget 40, seed 0", "primary", total["labels"], "queries"),
    ]
    report = ["# DeathStarBench PPR audit", "",
              "The audit reads locked records, labels and GraphML. It does not run a retriever.", "",
              "| Check | Status | Social | Media | Pooled |",
              "| --- | --- | ---: | ---: | ---: |"]
    denominators = {"complete": None, "valid_returned_ids": "returned_ids", "full_hits": "labels",
                    "hit_agrees": "labels", "primary": "labels"}
    passed = True
    for title, key, expected, unit in checks:
        passed &= total[key] == expected
        denominator = denominators.get(key, "main")
        per_app = [f"{stats[app][key]}/{stats[app][denominator] if denominator else 1}" for app in apps]
        status = "PASS" if total[key] == expected else "FAIL"
        report.append(f"| {title} | {status} | {' | '.join(per_app)} | {total[key]}/{expected} {unit} |")
    report += ["", "Main seeds by app: " + ", ".join(
        f"`{app}` {results[app][1]}" for app in apps) + ".",
        "Budget-40 hit-flag mismatches: " + str([m for app in apps for m in results[app][3]]) + ".",
        "Budget-40 queries missing at least one gold ID: " + str([m for app in apps for m in results[app][4]]) + ".",
        "", f"## 5. {'PASS' if valid_source else 'FAIL'} — PPR input and personalization", "",
        "`bench/egpot_eval.py:640–648` passes only query text, start node and budget to the retriever. "
        "`PersonalizedPageRank.retrieve` (lines 259–268) ignores query text and uses the graph and start for ranking. "
        "The budget caps the output and includes the start. PPR receives no gold, contract or handler label IDs, "
        "link ID, or query type. The evaluator scores against gold after retrieval (lines 660–664).", "",
        f"`PersonalizedPageRank.scores` at `bench/egpot_eval.py:{source_line}`:", "",
        "```python", snippet, "```", ""]
    choke_ok = (total["on_config"] == total["off_config"] == total["side_complete"] == len(apps)
                and total["unexpected_moves"] == 0)
    for budget in (20, 40):
        choke_ok &= total[f"pairs_{budget}"] == total[f"hit_agrees_{budget}"] == total["labels"]
    report += [f"## 6. {'PASS' if choke_ok else 'FAIL'} — Shared choke-point rule", "",
        "Normal PPR builds its move graph from the shared `GraphView.neighbors` "
        "(`bench/egpot_eval.py:73–80,230–250`). The OFF variant rebuilds from the same graph and "
        "policy with the rule disabled (`bench/egpot_eval.py:462–491`). The shared rule blocks only "
        "incoming `DEFINES_RPC` moves from `rpc_contract` nodes (`eg_pot.py:171–189`).", "",
        "| App | Suppressed moves (actual / expected) | Unexpected changes |",
        "| --- | ---: | ---: |"]
    for app in apps:
        c = stats[app]
        report.append(f"| {app} | {c['suppressed']}/{c['expected_suppressed']} | {c['unexpected_moves']} |")
    report += ["", "| App | Budget | ON hits | OFF hits | Same hit flag | Same returned order |",
               "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for app in apps:
        c = stats[app]
        for budget in (20, 40):
            n = c[f"pairs_{budget}"]
            report.append(f"| {app} | {budget} | {c[f'on_hits_{budget}']}/{n} | {c[f'off_hits_{budget}']}/{n} "
                          f"| {c[f'hit_agrees_{budget}']}/{n} | {c[f'order_agrees_{budget}']}/{n} |")
    if total["suppressed"]:
        report += ["", "The shared rule changes the available moves here. Identical hits are an observed "
                   "result of these records, not a guarantee of the rule."]
    else:
        report += ["", "The rule has no matching move in either graph, so both variants use identical adjacency."]
    report += ["", "## 7. Budget-40 query distances and gold positions", "",
               "Counts are cumulative shortest-path distances on the raw undirected GraphML and include "
               "the start at distance zero. Gold positions are one-based in the saved discovery order.", "",
               "| App | Query | Returned | Distance ≤1 | Distance ≤2 | Distance ≤3 | Contract rank | Handler rank |",
               "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for app in apps:
        for detail in results[app][2]:
            report.append("| " + " | ".join(map(str, (app, *detail))) + " |")
    return "\n".join(report) + "\n", bool(passed and valid_source and choke_ok)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=RESULTS / "dsb_ppr_audit.md")
    args = parser.parse_args(argv)
    report, passed = format_report({app: audit_app(app) for app in RECORDS})
    with args.out.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(report)
    print(f"{'PASS' if passed else 'FAIL'} {args.out}")
    return int(not passed)


if __name__ == "__main__":
    raise SystemExit(main())
