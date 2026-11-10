"""Export deterministic, gold-free traversal traces after an in-memory size check.

Default: all DEV queries, ten methods, budgets 20/40. Total trace bytes must
not exceed 100,000,000 before any output directory/file is created. Candidate
traces retain selected entries plus highest-mean remaining entries up to 60;
exported beam widths are four, so every selection fits within that cap.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from bench.egpot_eval import (BFS, EGPOTRetriever, GreedyWalk, VectorTopK, metrics, split_by_link)
from eg_pot import EGPOTConfig, GraphView, QueryScorer


METHODS = ("egpot_full", "egpot_full_mcts", "egpot_no_pareto", "egpot_no_pareto_mcts",
           "egpot_no_entropy", "egpot_no_contracts", "egpot_no_choke_point",
           "vector_topk", "bfs", "greedy_walk")
DEFAULT_OUTPUT = ROOT / "viz/data/online_boutique"


def make_methods(view: GraphView, scorer: QueryScorer) -> dict:
    configs = {
        "egpot_full": EGPOTConfig(use_mcts=False),
        "egpot_full_mcts": EGPOTConfig(use_mcts=True),
        "egpot_no_pareto": EGPOTConfig(use_mcts=False, use_pareto=False),
        "egpot_no_pareto_mcts": EGPOTConfig(use_mcts=True, use_pareto=False),
        "egpot_no_entropy": EGPOTConfig(use_mcts=False, use_entropy=False),
        "egpot_no_contracts": EGPOTConfig(use_mcts=False, use_contracts=False),
        "egpot_no_choke_point": EGPOTConfig(use_mcts=False),
    }
    methods = {name: EGPOTRetriever(config, view, scorer, use_choke_point=name != "egpot_no_choke_point")
               for name, config in configs.items()}
    methods.update(vector_topk=VectorTopK(view, scorer), bfs=BFS(view, scorer), greedy_walk=GreedyWalk(view, scorer))
    return methods


def _rounded(value):
    if isinstance(value, float):
        result = round(value, 6)
        return 0.0 if result == 0 else result
    if isinstance(value, dict):
        return {key: _rounded(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_rounded(item) for item in value]
    return value


def json_bytes(value) -> bytes:
    """Sorted keys and six-decimal float rounding, with no timing fields."""
    return (json.dumps(_rounded(value), sort_keys=True, ensure_ascii=False,
                       allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")


def build_export(graph, rows, *, method_names=METHODS, budgets=(20, 40), query_ids=None,
                 include_test=False, confirm_test=False, max_bytes=100_000_000):
    """Build every output byte in memory; reject oversized exports before writes."""
    if include_test != confirm_test:
        raise ValueError("test export requires both --include-test AND --confirm-test")
    unknown = set(method_names) - set(METHODS)
    if unknown:
        raise ValueError(f"unknown methods: {sorted(unknown)}")
    if any(type(budget) is not int or budget < 1 for budget in budgets):
        raise ValueError("budgets must be positive integers")
    splits = split_by_link(rows)
    dev_ids = {r["id"] for r in splits["dev"]}
    selected = rows if include_test else splits["dev"]
    if query_ids is not None:
        requested = set(query_ids)
        if requested - {r["id"] for r in selected}:
            raise ValueError("requested query is missing or belongs to the guarded test split")
        selected = [r for r in selected if r["id"] in requested]
    view = GraphView(graph, use_choke_point=True)
    scorer = QueryScorer(view)
    methods = make_methods(view, scorer)
    files, index = {}, []
    for row in sorted(selected, key=lambda r: r["id"]):
        for method in sorted(set(method_names)):
            retriever = methods[method]
            for budget in sorted(set(budgets)):
                trace = {"schema": 1, "repo": "online_boutique", "method": method,
                         "config": asdict(retriever.config) if isinstance(retriever, EGPOTRetriever) else {},
                         "query_id": row["id"], "link_id": row["link_id"], "type": row["type"],
                         "query": row["query"], "start_node": row["start_node"],
                         "node_budget": budget, "split": "dev" if row["id"] in dev_ids else "test", "steps": []}
                if trace["config"]:
                    trace["config"]["node_budget"] = budget
                # Never pass a row or any gold fields to a retriever.
                result = retriever.retrieve(row["query"], row["start_node"], budget, trace=trace)
                if set(result.discovery_order) != result.visited or len(result.visited) > budget:
                    raise ValueError("invalid discovery order/budget")
                if trace["final"]["visited_order"] != result.discovery_order:
                    raise ValueError("trace differs from actual result")
                path = f"traces/{row['id']}__{method}__b{budget}.json"
                files[path] = json_bytes(trace)
                score = metrics(result, row["gold_nodes"], row["gold_path"])
                index.append({"query_id": row["id"], "link_id": row["link_id"], "type": row["type"],
                              "method": method, "budget": budget, "path": path, "hit": score["hit"]})
        print(f"Prepared {row['id']}: {len(files)} trace files in memory", flush=True)
    sizes = {path: len(data) for path, data in files.items()}
    total = sum(sizes.values())
    largest = max(sizes, key=lambda path: (sizes[path], path)) if sizes else None
    summary = {"trace_files": len(files), "total_bytes": total,
               "largest_file": largest, "largest_bytes": sizes[largest] if largest else 0,
               "average_bytes": total / len(files) if files else 0}
    print(f"Preflight: {len(files)} traces, {total / 1_000_000:.3f} MB; largest {largest}: "
          f"{summary['largest_bytes']} bytes; average {summary['average_bytes']:.1f} bytes", flush=True)
    index_bytes = json_bytes(index)
    if total + len(index_bytes) > max_bytes:
        raise ValueError(f"STOP before writing: {total + len(index_bytes)} bytes including index exceed {max_bytes}; "
                         f"size summary: {summary}")
    files["traces_index.json"] = index_bytes
    return files, summary


def write_export(files, output_root):
    """Write only approved trace/index paths after successful preflight."""
    root = Path(output_root).resolve()
    # Validate the complete destination set before creating anything.
    destinations = {relative: (root / relative).resolve() for relative in files}
    if any(not path.is_relative_to(root) for path in destinations.values()):
        raise ValueError("output path escapes output root")
    for relative in sorted(files):
        path = destinations[relative]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(files[relative])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, default=ROOT / "bench/results/online_boutique_graph_fresh.graphml")
    parser.add_argument("--queries", type=Path, default=ROOT / "bench/labels/online_boutique_egpot_queries.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--include-test", action="store_true")
    parser.add_argument("--confirm-test", action="store_true")
    parser.add_argument("--methods", nargs="+", choices=METHODS, default=METHODS)
    parser.add_argument("--budgets", nargs="+", type=int, default=(20, 40))
    parser.add_argument("--query-id", action="append")
    args = parser.parse_args(argv)
    if args.include_test != args.confirm_test:
        parser.error("test export requires both --include-test AND --confirm-test")
    graph = nx.read_graphml(args.graph, force_multigraph=True)
    with args.queries.open(encoding="utf-8") as stream:
        rows = json.load(stream)
    try:
        files, summary = build_export(graph, rows, method_names=args.methods, budgets=args.budgets,
                                      query_ids=args.query_id, include_test=args.include_test,
                                      confirm_test=args.confirm_test)
    except ValueError as exc:
        parser.error(str(exc))
    write_export(files, args.output)
    print(f"Wrote {len(files)} files ({summary['trace_files']} traces + index) to {args.output}; "
          f"total including index {sum(map(len, files.values())) / 1_000_000:.3f} MB", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
