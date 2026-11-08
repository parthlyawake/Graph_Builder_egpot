"""Export extra DEV experiments without changing any existing site payload."""
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
from bench.egpot_eval import (EGPOTRetriever, EGPOTConfig, GraphView, QueryScorer,
    NEW_BASELINES, STOCHASTIC_METHODS, make_comparison_retrievers,
    make_fairness_retrievers, metrics, split_by_link, weight_experiment_vectors)

OLD_METHODS = ("egpot_full", "egpot_full_mcts", "egpot_no_pareto", "vector_topk", "bfs", "greedy_walk")
OFF_METHODS = ("bfs_no_choke", "vector_bfs_k2_no_choke", "ppr_no_choke", "scalar_beam_no_choke",
               "mcts_standard_no_choke", "greedy_walk_no_choke")
BUDGETS = (5, 10, 15, 20, 30, 40)


def encode(payload, *, omit_latency=False):
    def clean(value):
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items() if not (omit_latency and k == "latency_s")}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value
    text = json.dumps(clean(payload), sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return ("window.VIZ_RESULTS_EXTRA = " + text + ";\n").encode("utf-8")


def build_extra(graph, labels, *, include_test=False, confirm_test=False, query_ids=None,
                row_methods=(*NEW_BASELINES, *OLD_METHODS), row_budgets=BUDGETS, panels=True):
    if include_test != confirm_test:
        raise ValueError("test export requires both --include-test AND --confirm-test")
    if set(row_methods) - set((*NEW_BASELINES, *OLD_METHODS)):
        raise ValueError("unknown row method")
    if set(row_budgets) - set(BUDGETS):
        raise ValueError("unsupported extra-data budget")
    selected = labels if include_test else split_by_link(labels)["dev"]
    if query_ids is not None:
        if set(query_ids) - {r["id"] for r in selected}:
            raise ValueError("query is missing or belongs to the guarded test split")
        selected = [r for r in selected if r["id"] in query_ids]
    selected = sorted(selected, key=lambda r: r["id"])
    view = GraphView(graph, use_choke_point=True)
    scorer = QueryScorer(view)
    ids = {(r["query"], r["start_node"]): r["id"] for r in selected}
    methods = make_comparison_retrievers(view, scorer, query_ids=ids)
    methods.update(make_fairness_retrievers(view, scorer, query_ids=ids))
    cache = {}

    def run(name, budget, seed=0, retriever=None):
        key = name, budget, seed
        if key not in cache:
            began = perf_counter()
            engine = retriever or methods[name]
            records = []
            for row in selected:
                result = engine.retrieve(row["query"], row["start_node"], budget)
                if (row["start_node"] not in result.visited or len(result.visited) > budget
                        or set(result.discovery_order) != result.visited):
                    raise ValueError("retriever violated start, budget or discovery-order invariant")
                score = metrics(result, row["gold_nodes"], row["gold_path"])
                records.append({"query_id": row["id"], "link_id": row["link_id"], "type": row["type"],
                    "method": name, "budget": budget,
                    **{k: v for k, v in score.items() if k != "precision_at_hit"},
                    "gold_found": sorted(set(row["gold_nodes"]) & result.visited),
                    "n_gold": len(set(row["gold_nodes"]))})
            cache[key] = records
            print(f"EXTRA method={name} budget={budget} seed={seed} queries={len(selected)} wall_s={perf_counter()-began:.3f}", flush=True)
        return cache[key]

    rows = []
    for name in row_methods:
        for budget in row_budgets:
            if name in OLD_METHODS and budget in (20, 40):
                continue
            rows.extend(run(name, budget))
    choke, seeds, weights = [], [], []
    if panels:
        for name in OFF_METHODS:
            for budget in (20, 40):
                choke.extend(run(name, budget))
        for seed in range(5):
            engines = methods if seed == 0 else {
                "mcts_standard": type(methods["mcts_standard"])(view, scorer, seed=seed, query_ids=ids),
                "egpot_full_mcts": EGPOTRetriever(EGPOTConfig(use_mcts=True, seed=seed), view, scorer),
                "egpot_no_pareto_mcts": EGPOTRetriever(EGPOTConfig(use_mcts=True, use_pareto=False, seed=seed), view, scorer),
            }
            for name in STOCHASTIC_METHODS:
                for budget in (20,40):
                    for row in run(name,budget,seed,engines[name]):
                        seeds.append({"method":name,"budget":budget,"seed":seed,"query_id":row["query_id"],
                                      "hit":row["hit"],"nodes_returned":row["nodes_returned"]})
        for name, vector in weight_experiment_vectors().items():
            engine = EGPOTRetriever(EGPOTConfig(use_mcts=False, use_pareto=False, weights=vector), view, scorer)
            samples = {budget: run("weight_"+name,budget,retriever=engine) for budget in (10,20)}
            weights.append({"id":name,"weights":list(vector),
                **{f"hit_b{b}":sum(r["hit"] for r in samples[b]) for b in (10,20)},
                **{f"nodes_b{b}":sum(r["nodes_returned"] for r in samples[b])/len(selected) for b in (10,20)},
                "explicit_hit_b20":sum(r["hit"] for r in samples[20] if r["type"]=="explicit"),
                "indirect_hit_b20":sum(r["hit"] for r in samples[20] if r["type"]=="indirect")})
        pareto = {b: run("egpot_full",b) for b in (10,20)}
        weights.append({"id":"pareto_reference",
            **{f"hit_b{b}":sum(r["hit"] for r in pareto[b]) for b in (10,20)},
            **{f"nodes_b{b}":sum(r["nodes_returned"] for r in pareto[b])/len(selected) for b in (10,20)}})
    return {"meta":{"repo":"online_boutique","split":"dev+test" if include_test else "dev",
                "n_queries":len(selected),"n_links":len({r["link_id"] for r in selected}),"seed":0,
                "generated_note":"Extra harness experiments; one shared fitted scorer; existing payloads preserved.",
                "note_latency":"measured on the machine that ran the export",
                "note":"latency measured on the exporting machine"},
            "rows":sorted(rows,key=lambda r:(r["query_id"],r["method"],r["budget"])),
            "choke":sorted(choke,key=lambda r:(r["query_id"],r["method"],r["budget"])),
            "seeds":sorted(seeds,key=lambda r:(r["method"],r["budget"],r["seed"],r["query_id"])),
            "weights":sorted(weights,key=lambda r:r["id"])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph",type=Path,default=ROOT/"bench/results/online_boutique_graph_fresh.graphml")
    parser.add_argument("--queries",type=Path,default=ROOT/"bench/labels/online_boutique_egpot_queries.json")
    parser.add_argument("--output",type=Path,default=ROOT/"viz/data/online_boutique/results_extra.js")
    parser.add_argument("--include-test",action="store_true")
    parser.add_argument("--confirm-test",action="store_true")
    args = parser.parse_args(argv)
    if args.include_test != args.confirm_test:
        parser.error("test export requires both --include-test AND --confirm-test")
    began = perf_counter()
    graph = nx.read_graphml(args.graph,force_multigraph=True)
    labels = json.loads(args.queries.read_text(encoding="utf-8"))
    payload = build_extra(graph,labels,include_test=args.include_test,confirm_test=args.confirm_test)
    data = encode(payload)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(data)
    print("EXPORT_COUNTS " + json.dumps({k:len(payload[k]) for k in ("rows","choke","seeds","weights")}),flush=True)
    print(f"EXPORTED bytes={len(data)} total_s={perf_counter()-began:.3f}",flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
