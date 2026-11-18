"""Export harness metrics for the local site; DEV only unless doubly confirmed."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from time import perf_counter

import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from bench.egpot_eval import (BFS, EGPOTRetriever, GreedyWalk, VectorTopK,
                             FULL_PLAIN, FULL_MCTS, ablation_configs, metrics, split_by_link)
from eg_pot import GraphView, QueryScorer

CONFIG_NAMES = {
    "egpot_full": FULL_PLAIN, "egpot_full_mcts": FULL_MCTS,
    **{f"egpot_no_{component}{suffix}": f"no_{component}({mode})"
       for component in ("pareto", "entropy", "contracts", "choke_point")
       for suffix, mode in (("", "no MCTS"), ("_mcts", "MCTS"))},
}
METHODS = (*CONFIG_NAMES, "vector_topk", "bfs", "greedy_walk")
SWEEP = ("egpot_full", "egpot_full_mcts", "vector_topk", "bfs")


def encode(payload, *, omit_latency=False):
    if omit_latency:
        payload = {**payload, "rows": [{k: v for k, v in row.items() if k != "latency_s"}
                                         for row in payload["rows"]]}
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).replace("<", "\\u003c")
    return ("window.VIZ_RESULTS = " + text + ";\n").encode("utf-8")


def build_results(graph, labels, *, include_test=False, confirm_test=False,
                  query_ids=None, method_names=METHODS, budgets=(20, 40, 60, 100, 200),
                  mcts_limit_s=600.0):
    if include_test != confirm_test:
        raise ValueError("test export requires both --include-test AND --confirm-test")
    if set(method_names) - set(METHODS):
        raise ValueError("unknown method")
    if any(type(b) is not int or b < 1 for b in budgets):
        raise ValueError("budgets must be positive integers")
    splits = split_by_link(labels)
    selected = labels if include_test else splits["dev"]
    if query_ids is not None:
        if set(query_ids) - {r["id"] for r in selected}:
            raise ValueError("query is missing or on the guarded test split")
        selected = [r for r in selected if r["id"] in query_ids]
    view = GraphView(graph, use_choke_point=True)
    scorer = QueryScorer(view)
    specs = ablation_configs()
    methods = {name: EGPOTRetriever(specs[key].config, view, scorer,
                                   use_choke_point=specs[key].use_choke_point)
               for name, key in CONFIG_NAMES.items()}
    methods.update(vector_topk=VectorTopK(view, scorer), bfs=BFS(view, scorer),
                   greedy_walk=GreedyWalk(view, scorer))
    records, mcts_seconds, measured = [], 0.0, {}
    skipped = []
    for budget in sorted(set(budgets)):
        for method in sorted(set(method_names)):
            if budget > 40 and method not in SWEEP:
                continue
            if method == "egpot_full_mcts" and budget == 200 and (
                    mcts_seconds + 2 * measured.get(100, 0.0) > mcts_limit_s):
                skipped.append("egpot_full_mcts at 200")
                print(f"SKIP MCTS-200: prior {mcts_seconds:.3f}s, estimated additional "
                      f"{2 * measured.get(100, 0.0):.3f}s; allowance {mcts_limit_s:.0f}s", flush=True)
                continue
            began = perf_counter()
            current = []
            for row in sorted(selected, key=lambda r: r["id"]):
                if method == "egpot_full_mcts" and budget == 200 and (
                        mcts_seconds + perf_counter() - began > mcts_limit_s):
                    skipped.append("egpot_full_mcts at 200 (incomplete, omitted)")
                    current = []
                    break
                result = methods[method].retrieve(row["query"], row["start_node"], budget)
                if len(result.visited) > budget or row["start_node"] not in result.visited:
                    raise ValueError("retriever violated budget/start invariant")
                score = metrics(result, row["gold_nodes"], row["gold_path"])
                current.append({"query_id": row["id"], "link_id": row["link_id"], "type": row["type"],
                                "method": method, "budget": budget,
                                **{k: v for k, v in score.items() if k != "precision_at_hit"},
                                "gold_found": sorted(set(row["gold_nodes"]) & result.visited),
                                "n_gold": len(set(row["gold_nodes"]))})
            elapsed = perf_counter() - began
            if method == "egpot_full_mcts":
                measured[budget] = elapsed
                mcts_seconds += elapsed
            records.extend(current)
            print(f"budget={budget} method={method} rows={len(current)} elapsed_s={elapsed:.3f}", flush=True)
    return {"meta": {"repo": "online_boutique", "split": "dev+test" if include_test else "dev",
                     "n_queries": len(selected), "n_links": len({r["link_id"] for r in selected}),
                     "generated_note": "Harness retrievers and exact-ID metrics; shared fitted TF-IDF; "
                                       "choke-point on except its ablation. " +
                                       ("Skipped: " + ", ".join(skipped) if skipped else "All requested runs completed."),
                     "seed": 0, "note_latency": "measured on the machine that ran the export"},
            "rows": sorted(records, key=lambda r: (r["query_id"], r["method"], r["budget"]))}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, default=ROOT / "bench/results/online_boutique_graph_fresh.graphml")
    parser.add_argument("--queries", type=Path, default=ROOT / "bench/labels/online_boutique_egpot_queries.json")
    parser.add_argument("--output", type=Path, default=ROOT / "viz/data/online_boutique/results.js")
    parser.add_argument("--include-test", action="store_true")
    parser.add_argument("--confirm-test", action="store_true")
    parser.add_argument("--methods", nargs="+", choices=METHODS, default=METHODS)
    parser.add_argument("--budgets", nargs="+", type=int, default=(20, 40, 60, 100, 200))
    parser.add_argument("--query-id", action="append")
    args = parser.parse_args(argv)
    if args.include_test != args.confirm_test:
        parser.error("test export requires both --include-test AND --confirm-test")
    began = perf_counter()
    graph = nx.read_graphml(args.graph, force_multigraph=True)
    labels = json.loads(args.queries.read_text(encoding="utf-8"))
    payload = build_results(graph, labels, include_test=args.include_test, confirm_test=args.confirm_test,
                            query_ids=args.query_id, method_names=args.methods, budgets=args.budgets)
    data = encode(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    print(f"Exported {len(payload['rows'])} rows; {len(data):,} bytes; total_s={perf_counter()-began:.3f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
