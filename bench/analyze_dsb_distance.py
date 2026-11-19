"""Post-hoc exploratory description of graph distances and saved DeathStarBench hits."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from statistics import fmean, median

import networkx as nx
import numpy as np

from bench import egpot_multi_eval as locked
from bench.analyze_dsb_final import BOOTSTRAP_SEED, RESAMPLES, cluster_weights, load_record
from eg_pot import GraphView


STATUS = "post-hoc exploratory"
RESULTS = locked.ROOT / "bench/results"
BUDGETS = (10, 20, 40)
METHODS = ("egpot_full", "egpot_no_pareto", "egpot_full_mcts", "ppr", "bfs",
           "vector_topk", "mcts_standard")
GOLD_ROLES = ("contract", "handler")


def gold_depth(distances):
    return max(distances) if all(d is not None for d in distances) else None


def distance_facts(graph, undirected, start, contract, handler):
    """Measure raw GraphML topology and check the arrows of the gold structure."""
    gold = (contract, handler)
    plain = nx.single_source_shortest_path_length(undirected, start)
    forward = nx.single_source_shortest_path_length(graph, start)
    consumes = any(d.get("relation") == "CONSUMES"
                   for d in graph.get_edge_data(start, contract, default={}).values())
    implements = any(d.get("relation") == "IMPLEMENTS"
                     for d in graph.get_edge_data(handler, contract, default={}).values())
    hops = [plain.get(node) for node in gold]
    directed = [forward.get(node) for node in gold]
    return {
        "undirected_hops": hops,
        "forward_graph_hops": directed,
        # The two verified evidence arrows are start -> contract <- handler.
        "gold_structure_forward_hops": [1 if consumes else None, None],
        "gold_structure_walk_hops": [1 if consumes else None, 2 if consumes and implements else None],
        "gold_depth": gold_depth(hops),
        "forward_graph_depth": gold_depth(directed),
        "start_degree": undirected.degree(start),
        "contract_degree": undirected.degree(contract),
        "start_unique_neighbors": len(undirected[start]),
        "contract_unique_neighbors": len(undirected[contract]),
        "within_two_hops": sum(depth <= 2 for depth in plain.values()),
    }


def describe_app(app, graph, rows):
    """Join saved metadata to topology for reporting only."""
    undirected = graph.to_undirected(as_view=True)
    admissible = GraphView(graph, edge_policy=locked.DSB_EDGE_POLICY)
    moves = {node: {neighbor for neighbor, *_ in admissible.neighbors(node)} for node in graph}
    saved = {}
    labels = {}
    for row in rows:
        if row["experiment"] not in {"main", "seeds"} or row["method"] not in METHODS:
            continue
        key = (row["id"], row["method"], row["node_budget"], row["seed"], row["experiment"])
        saved[key] = row
        labels[row["id"]] = row["label"]
    queries, misses = [], []
    distance_cache, miss_cache = {}, {}
    for query_id, label in sorted(labels.items()):
        start = label["start_node"]
        gold = (label["contract_node"], label["handler_node"])
        location = (start, *gold)
        if location not in distance_cache:
            distance_cache[location] = distance_facts(graph, undirected, *location)
        query = {"app": app, "id": query_id, "start_node": start, "type": label["type"],
                 "link_id": label["link_id"], **distance_cache[location]}
        query["main_hits"] = {}
        query["seed_hits"] = {}
        query["ppr_ranks"] = {}
        for budget in BUDGETS:
            main = {method: saved[query_id, method, budget, 0, "main"] for method in METHODS}
            query["main_hits"][budget] = {method: row["hit"] for method, row in main.items()}
            query["seed_hits"][budget] = {
                method: {seed: saved[query_id, method, budget, seed, "seeds"]["hit"]
                         for seed in range(6) if (query_id, method, budget, seed, "seeds") in saved}
                for method in METHODS
            }
            ranks = {node: index for index, node in enumerate(main["ppr"]["returned_nodes"], 1)}
            query["ppr_ranks"][budget] = [ranks.get(node) for node in gold]
            if budget != 40 or main["egpot_full"]["hit"]:
                continue
            returned = main["egpot_full"]["returned_nodes"]
            for role, target in zip(GOLD_ROLES, gold, strict=True):
                if target in returned:
                    continue
                if target not in miss_cache:
                    miss_cache[target] = nx.single_source_shortest_path_length(undirected, target)
                distances = miss_cache[target]
                nearest = min(((distances[node], rank, node)
                               for rank, node in enumerate(returned, 1) if node in distances), default=None)
                if target in moves[start]:
                    diagnosis = "pruned at root"
                elif not any(target in moves[node] for node in returned):
                    diagnosis = "beyond returned frontier"
                else:
                    diagnosis = "undetermined (beam trace unavailable)"
                misses.append({
                    **{key: query[key] for key in ("app", "id", "link_id", "type", "gold_depth",
                                                  "start_degree", "contract_degree")},
                    "missing_gold_role": role, "missing_gold_id": target,
                    "nearest_hops": nearest[0] if nearest else None,
                    "nearest_rank": nearest[1] if nearest else None,
                    "nearest_returned_node": nearest[2] if nearest else None,
                    "frontier_or_pruned": diagnosis,
                })
        queries.append(query)
    starts = {q["start_node"]: q["within_two_hops"] for q in queries}
    neighborhood = {"app": app, "nodes": len(graph), "queries": len(queries), "unique_starts": len(starts),
                    "mean_within_two_hops_per_start": fmean(starts.values()),
                    "mean_within_two_hops_per_query": fmean(q["within_two_hops"] for q in queries),
                    "budget_40_graph_fraction": min(40, len(graph)) / len(graph)}
    return queries, misses, neighborhood


def depth_buckets(queries):
    groups = defaultdict(list)
    for query in queries:
        groups[query["gold_depth"]].append(query)
    return sorted(groups.items(), key=lambda pair: (pair[0] is None, pair[0]))


def bucket_statistics(queries):
    rows = []
    for depth, cohort in depth_buckets(queries):
        n = len(cohort)
        weights = (cluster_weights([(q["app"], q["start_node"]) for q in cohort],
                                   resamples=RESAMPLES, seed=BOOTSTRAP_SEED) if n >= 8 else None)
        for budget in BUDGETS:
            estimates = {}
            for method in METHODS:
                seed_counts = [q["seed_hits"][budget][method] for q in cohort]
                for query, seeds in zip(cohort, seed_counts, strict=True):
                    if seeds and (set(seeds) != set(range(6))
                                  or seeds[0] != query["main_hits"][budget][method]):
                        raise ValueError(f"Unexpected seed coverage for {method} at {budget}")
                if any(seed_counts) and not all(seed_counts):
                    raise ValueError(f"Incomplete seed coverage for {method} at {budget}")
                estimates[method] = {
                    "seed_0_hits": sum(q["main_hits"][budget][method] for q in cohort),
                    "median_hits": median(sum(entry[seed] for entry in seed_counts) for seed in range(6))
                    if all(seed_counts) else None,
                }
            interval = None
            if weights is not None:
                diff = np.array([q["main_hits"][budget]["egpot_full"] - q["main_hits"][budget]["ppr"]
                                 for q in cohort])
                resampled = (weights @ diff) / weights.sum(axis=1)
                interval = {"analysis_type": STATUS, "difference": float(diff.mean()),
                            "interval_95": np.quantile(resampled, [0.025, 0.975]).tolist()}
            ranks = {}
            for i, role in enumerate(GOLD_ROLES):
                found = [q["ppr_ranks"][budget][i] for q in cohort if q["ppr_ranks"][budget][i] is not None]
                ranks[role] = {"found": len(found), "mean_rank": fmean(found) if found else None}
            rows.append({"depth": depth, "budget": budget, "n": n, "hits": estimates,
                         "egpot_full_minus_ppr": interval, "ppr_ranks": ranks})
    return rows


def histogram(rows, key):
    counts = Counter(str(q[key]) if q[key] is not None else "unreachable" for q in rows)
    return dict(sorted(counts.items(), key=lambda pair: (not pair[0].isdigit(),
                                                          int(pair[0]) if pair[0].isdigit() else 0)))


def analyze():
    queries, misses, neighborhoods = [], [], []
    for app in locked.DSB_DATASETS:
        repo = locked.REGISTRY[app]
        rows, _ = load_record(RESULTS / f"{app}_final_6ba6e1cf.json", app, repo)
        graph = nx.read_graphml(repo.graph, force_multigraph=True)
        descriptions, missed, neighborhood = describe_app(app, graph, rows)
        queries.extend(descriptions)
        misses.extend(missed)
        neighborhoods.append(neighborhood)
    scopes = {app: [q for q in queries if q["app"] == app] for app in locked.DSB_DATASETS}
    scopes["pooled"] = queries
    distributions = []
    for app, cohort in scopes.items():
        for kind in ("all", "explicit", "indirect"):
            subset = [q for q in cohort if kind == "all" or q["type"] == kind]
            distributions.append({"scope": app, "type": kind, **{
                key: histogram(subset, key) for key in ("gold_depth", "start_degree", "contract_degree",
                    "start_unique_neighbors", "contract_unique_neighbors")}})
    return {
        "analysis_type": STATUS,
        "definitions": {
            "gold_depth": "Maximum of the two raw undirected GraphML shortest-path distances.",
            "gold_structure": "CONSUMES forward, then IMPLEMENTS against its raw arrow.",
            "degree": "Raw undirected multigraph degree. Unique-neighbor counts are separate.",
            "seed_median": "Median of the six per-seed hit counts where the seed study exists.",
            "nearest": "Raw undirected shortest distance from missing gold. Ties use earliest discovery rank.",
            "frontier_or_pruned": "Eligible start neighbors are candidates in round one. A gold with "
                                  "no allowed move from any returned node was beyond the returned frontier. "
                                  "Later candidate selection cannot be recovered without a beam trace.",
            "within_two_hops": "Includes the start at distance zero.",
        },
        "bootstrap": {"analysis_type": STATUS, "seed": BOOTSTRAP_SEED, "resamples": RESAMPLES,
                      "minimum_queries": 8, "interval": "unadjusted percentile 95%",
                      "cluster": "start_node within app"},
        "queries": queries, "distributions": distributions,
        "buckets": {scope: bucket_statistics(cohort) for scope, cohort in scopes.items()},
        "egpot_full_budget_40_misses": misses, "neighborhoods": neighborhoods,
    }


def markdown_table(headers, rows):
    return ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |",
            *("| " + " | ".join(map(str, row)) + " |" for row in rows), ""]


def markdown(report):
    lines = [f"# DeathStarBench distance analysis ({STATUS})", "",
             "This analysis uses saved hits and returned IDs. Graph distances are descriptive and were "
             "never inputs to a retriever or a label. This is outside C1–C7.", ""]
    def section(title, note=""):
        lines.extend([f"## {title} ({STATUS})", "", note, ""])

    def pair(values):
        return " / ".join("—" if v is None else str(v) for v in values)

    def counts(hist):
        return ", ".join(f"{k}×{v}" for k, v in hist.items())

    def hits(row, method):
        record = row["hits"][method]
        value = f"{record['seed_0_hits']}/{row['n']}"
        return value if record["median_hits"] is None else f"{value} ({record['median_hits']:g}/{row['n']})"

    section("Gold depth and degree distributions",
            "Each cell shows value × query count. Gold depth is the larger raw undirected distance. "
            "Multigraph degree counts parallel edges; unique undirected neighbors are in the JSON.")
    lines += markdown_table(["Scope", "Type", "Depth", "Start degree", "Contract degree"], (
        (d["scope"], d["type"], counts(d["gold_depth"]), counts(d["start_degree"]), counts(d["contract_degree"]))
        for d in report["distributions"]))
    section("Hits by gold depth", "Cells show seed 0 hits / queries, with the median hit count / queries in "
            "parentheses where seeds 0–5 were recorded.")
    lines += markdown_table(["Scope", "Depth", "Budget", *METHODS], (
        (scope, row["depth"], row["budget"], *(hits(row, method) for method in METHODS))
        for scope, rows in report["buckets"].items() for row in rows))
    section("Paired hit-rate differences by depth",
            "EG-POT full minus PPR at seed 0. Only buckets with at least eight queries get an "
            "unadjusted 95% cluster bootstrap interval. Other buckets have counts only above.")
    lines += markdown_table(["Scope", "Depth", "Budget", "Queries", "Difference", "95% interval"], (
        (scope, row["depth"], row["budget"], row["n"], f"{effect['difference']:+.4f}",
         f"[{effect['interval_95'][0]:+.4f}, {effect['interval_95'][1]:+.4f}]")
        for scope, rows in report["buckets"].items() for row in rows
        if (effect := row["egpot_full_minus_ppr"]) is not None))
    section("EG-POT full misses at budget 40", "One row per missing gold ID. The closest returned node "
            "uses raw undirected distance, with ties resolved by earliest one-based discovery rank. "
            "An eligible start neighbor was considered in round one and pruned if it is missing. "
            "A node with no eligible move from any returned node was beyond the returned frontier. "
            "Other cases are undetermined because the locked records contain no beam trace. "
            "These checks use the locked GraphView policy and the frozen root expansion and selection "
            "ledger (`eg_pot.py:397–410,556–647`).")
    lines += markdown_table(["App", "Query", "Type", "Depth", "Start degree", "Contract degree",
                              "Missing gold", "Nearest ID", "Rank", "Hops", "Frontier or pruned"], (
        (r["app"], r["id"], r["type"], r["gold_depth"], r["start_degree"], r["contract_degree"],
         r["missing_gold_role"], "`" + str(r["nearest_returned_node"]) + "`",
         r["nearest_rank"], r["nearest_hops"], r["frontier_or_pruned"])
        for r in report["egpot_full_budget_40_misses"]))
    section("PPR mean gold ranks by depth", "Means use only found IDs. Each cell shows mean rank (found / queries).")
    def mean_rank(r, role):
        stats = r["ppr_ranks"][role]
        return (f"{stats['mean_rank']:.2f}" if stats["mean_rank"] is not None else "—") + f" ({stats['found']}/{r['n']})"
    lines += markdown_table(["Scope", "Depth", "Budget", "Contract rank", "Handler rank"], (
        (scope, row["depth"], row["budget"], mean_rank(row, "contract"), mean_rank(row, "handler"))
        for scope, rows in report["buckets"].items() for row in rows))
    section("Two-hop neighborhoods and budget coverage", "Counts include the start at distance zero.")
    lines += markdown_table(["App", "Nodes", "Unique starts", "Mean within 2 per start", "Mean within 2 per query",
                              "Budget 40 / graph"], (
        (r["app"], r["nodes"], r["unique_starts"], f"{r['mean_within_two_hops_per_start']:.2f}",
         f"{r['mean_within_two_hops_per_query']:.2f}", f"{100*r['budget_40_graph_fraction']:.2f}%")
        for r in report["neighborhoods"]))
    section("Per-query distances and PPR ranks",
            "Pairs are contract / handler. Full-graph forward paths follow raw arrows. The labelled "
            "structure points from start to contract and from handler to contract. Its forward-only "
            "handler distance is therefore missing; following the labelled walk reverses the IMPLEMENTS hop. "
            "A dash in a rank pair means PPR did not return that gold ID.")
    lines += markdown_table(["App", "Query", "Type", "Undirected", "Full graph forward",
        "Gold structure forward", "Gold structure walk", "Depth", "Start degree", "Contract degree",
        "PPR rank @10", "PPR rank @20", "PPR rank @40"], (
        (q["app"], q["id"], q["type"], *(pair(q[key]) for key in ("undirected_hops", "forward_graph_hops",
           "gold_structure_forward_hops", "gold_structure_walk_hops")), q["gold_depth"], q["start_degree"],
         q["contract_degree"], *(pair(q["ppr_ranks"][b]) for b in BUDGETS)) for q in report["queries"]))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    json_path = RESULTS / "dsb_distance_analysis.json"
    md_path = RESULTS / "dsb_distance_analysis.md"
    if json_path.exists() or md_path.exists():
        parser.error("analysis output already exists")
    report = analyze()
    artifacts = {json_path: json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                 md_path: markdown(report)}
    for path, contents in artifacts.items():
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(contents)
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
