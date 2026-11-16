"""Pinned real-source mutation matrix, retaining failure evidence.

Every mutation runs in a separate temporary checkout. Structural equivalence
is insufficient: all user-visible node, edge and graph metadata must agree
with an independently constructed fresh graph (volatile edge IDs excluded).
No result is called a speedup if semantic equivalence fails.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from bench.paper_performance import graph_signature,semantic_graph_signature,diagnose_graph_attribute_drift
from graft_ckg import CKGBuilder

PINS={
    "boutique":"38e7348eb289eb5b87c0c6e8cb19ced0449dc389",
    "train":"313886e99befb94be6cd45f085c98e0019f59829",
    "deathstar":"6ecb09706140f8730b5385c08f1386c654c3c526"
}
CASES=[
    {"system":"boutique","kind":"grpc_bad_method","file":"src/frontend/rpc.go",
     "old":"pb.NewCartServiceClient(fe.cartSvcConn).GetCart(",
     "new":"pb.NewCartServiceClient(fe.cartSvcConn).GetCartTypo("},
    {"system":"boutique","kind":"schema_rpc_rename","file":"protos/demo.proto",
     "old":"rpc GetCart(GetCartRequest)", "new":"rpc GetCartV2(GetCartRequest)"},
    {"system":"boutique","kind":"deletion","file":"src/frontend/rpc.go"},
    {"system":"boutique","kind":"code_addition","file":"src/shippingservice/main.go",
     "append":"\nfunc sckgIndependentMutationProbe(x int) int { return x + 1 }\n"},
    {"system":"train","kind":"http_route_rename","file":
     "ts-order-service/src/main/java/order/controller/OrderController.java",
     "old":'@GetMapping(path = "/welcome")',
     "new":'@GetMapping(path = "/welcome-v2")'},
    {"system":"deathstar","kind":"thrift_rpc_rename","file":"socialNetwork/social_network.thrift",
     "old":"ComposeUniqueId (", "new":"ComposeUniqueIdV2 ("},
]

def run_one(src:Path, case:dict, iteration:int)->dict:
    rel=case["file"]
    with tempfile.TemporaryDirectory(prefix="sckg-mutation-") as td:
        root=Path(td)/"working"
        shutil.copytree(src,root,ignore=shutil.ignore_patterns(
            ".git",".venv","node_modules","__pycache__","*.pyc",".pytest_cache"))
        target=root/rel
        with contextlib.redirect_stdout(io.StringIO()):
            builder=CKGBuilder(str(root))
            builder.build()
        before_ids=set(map(str,builder.graph.nodes))
        before_edges=builder.graph.number_of_edges()
        if case["kind"]=="deletion":
            target.unlink()
        elif "append" in case:
            with target.open("a",encoding="utf-8") as out:
                out.write(case["append"])
        else:
            original=target.read_text(encoding="utf-8")
            if original.count(case["old"])!=1:
                raise ValueError(f"Mutation anchor not unique: {case['kind']} {original.count(case['old'])}")
            target.write_text(original.replace(case["old"],case["new"],1),encoding="utf-8")
        t0=time.perf_counter()
        with contextlib.redirect_stdout(io.StringIO()):
            if case["kind"]=="deletion":
                builder.update_files([],deleted_rel_paths=[rel])
            else:
                builder.update_files([rel])
        dt_inc=time.perf_counter()-t0
        fresh=CKGBuilder(str(root))
        t1=time.perf_counter()
        with contextlib.redirect_stdout(io.StringIO()):
            fresh.build()
        dt_fresh=time.perf_counter()-t1
        structural=graph_signature(builder.graph)==graph_signature(fresh.graph)
        semantic=semantic_graph_signature(builder.graph)==semantic_graph_signature(fresh.graph)
        after_ids=set(map(str,builder.graph.nodes))
        mutation_changed=(before_ids!=after_ids or before_edges!=builder.graph.number_of_edges())
        # Exact graph equality is not required: keys eNNN are ephemeral insertion ids.
        checks={
            "semantic_equivalence":semantic,
            "structural_equivalence":structural,
            "mutation_effect_on_node_or_edge_count":mutation_changed,
        }
        if case["kind"]=="deletion":
            checks["removed_file_nodes"] = all(
                rel not in str(n) for n in after_ids)
        if case["kind"]=="schema_rpc_rename":
            checks["old_rpc_absent"] = "contract::CartService.GetCart" not in after_ids
        if case["kind"]=="grpc_bad_method":
            caller="src/frontend/rpc.go:frontendServer.getCart"
            target_rpc="contract::CartService.GetCart"
            checks["old_grpc_link_absent"]=not any(
                u==caller and v==target_rpc and d.get("relation")=="CONSUMES"
                for u,v,d in builder.graph.edges(data=True))
        return {
            "system":case["system"],"kind":case["kind"],"iteration":iteration,
            "mutation":{k:v for k,v in case.items() if k not in ("system",)},
            "checks":checks,"passed":all(checks.values()),
            "incremental_s":dt_inc,"fresh_s":dt_fresh,
            "speedup_if_equivalent":dt_fresh/dt_inc if semantic and dt_inc>0 else None,
            "before_nodes":len(before_ids),"after_nodes":len(after_ids),
            "after_edges":builder.graph.number_of_edges(),
            "drift":diagnose_graph_attribute_drift(builder.graph,fresh.graph) if not semantic else None
        }

def main():
    p=argparse.ArgumentParser()
    for name in PINS:
        p.add_argument("--"+name, required=True, type=Path)
    p.add_argument("--repetitions",type=int,default=3)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    if not 1<=args.repetitions<=10:
        p.error("repetitions must be in 1..10")
    roots={name:getattr(args,name).resolve() for name in PINS}
    for name,root in roots.items():
        rev=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
        if rev!=PINS[name]:
            raise ValueError(f"Source pin mismatch {name}: {rev}")
    trials=[]
    for case in CASES:
        for iteration in range(1,args.repetitions+1):
            try:
                result=run_one(roots[case["system"]],case,iteration)
            except Exception as exc:
                result={"system":case["system"],"kind":case["kind"],
                        "iteration":iteration,"passed":False,
                        "error":repr(exc)}
            trials.append(result)
            print("PINNED_MUTATION",json.dumps({
                "system":result["system"],"kind":result["kind"],
                "iteration":result["iteration"],"passed":result["passed"],
                "checks":result.get("checks"),"error":result.get("error")},sort_keys=True),flush=True)
    summary=[]
    for case in CASES:
        group=[r for r in trials if r["system"]==case["system"] and r["kind"]==case["kind"]]
        times=[r["incremental_s"] for r in group if r.get("passed")]
        full=[r["fresh_s"] for r in group if r.get("passed")]
        summary.append({
            "system":case["system"],"kind":case["kind"],
            "passes":sum(r["passed"] for r in group),"trials":len(group),
            "median_incremental_s":statistics.median(times) if times else None,
            "median_full_s":statistics.median(full) if full else None,
            "speedup_median_ratio_if_equivalent":(
                statistics.median(full)/statistics.median(times) if times and full else None)
        })
    report={"source_revisions":PINS,"scope":"six specific mutations in three real repositories",
            "human_ground_truth":False,"runner":{"python":sys.version,"cpu_count":os.cpu_count()},
            "repetitions":args.repetitions,
            "all_passed":all(r["passed"] for r in trials),
            "summary":summary,"trials":trials}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print("MUTATION_MATRIX_SUMMARY",json.dumps(summary,sort_keys=True))
    return 0 if report["all_passed"] else 2

if __name__=="__main__":
    raise SystemExit(main())
