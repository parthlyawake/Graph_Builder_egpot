"""Source-pinned, real-Go-code gRPC fault injection against a temporary copy.

This tests conservative binding under a contract-breaking *uncompilable*
consumer call, not live gRPC runtime behavior and not independent P/R.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from graft_ckg import CKGBuilder
from bench.paper_performance import semantic_graph_signature, diagnose_graph_attribute_drift

EXPECTED_COMMIT="38e7348eb289eb5b87c0c6e8cb19ced0449dc389"
REL="src/frontend/rpc.go"
CALLER="src/frontend/rpc.go:frontendServer.getCart"
RPC="contract::CartService.GetCart"
OLD="pb.NewCartServiceClient(fe.cartSvcConn).GetCart("
NEW="pb.NewCartServiceClient(fe.cartSvcConn).GetCartTypo("


def _has_binding(graph):
    return any(u==CALLER and v==RPC and d.get("relation")=="CONSUMES"
               for u,v,d in graph.edges(data=True))


def _all_consumes(graph):
    return sorted(v for _,v,d in graph.out_edges(CALLER,data=True)
                  if d.get("relation")=="CONSUMES") if CALLER in graph else []


def inspect(repo: Path) -> dict:
    if not (repo/REL).is_file():
        raise ValueError("Pinned source file missing")
    with tempfile.TemporaryDirectory(prefix="ckg_rpc_fault_") as tmp:
        root=Path(tmp)/"checkout"
        shutil.copytree(repo,root,ignore=shutil.ignore_patterns(
            ".git",".venv","node_modules","__pycache__","*.pyc"))
        src=root/REL
        original=src.read_text(encoding="utf-8")
        if original.count(OLD)!=1:
            raise ValueError("Pinned upstream GetCart call anchor must be unique")
        with contextlib.redirect_stdout(io.StringIO()):
            builder=CKGBuilder(str(root))
            builder.build()
        baseline=_has_binding(builder.graph)
        src.write_text(original.replace(OLD,NEW,1),encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            builder.update_files([REL])
            fresh=CKGBuilder(str(root))
            fresh.build()
        incremental_binding=_has_binding(builder.graph)
        fresh_binding=_has_binding(fresh.graph)
        equivalent=(semantic_graph_signature(builder.graph)==
                    semantic_graph_signature(fresh.graph))
        mismatch=(diagnose_graph_attribute_drift(builder.graph, fresh.graph)
                  if not equivalent else None)
        unresolved=[
            list(x) for x in getattr(builder,"unresolved_contract_calls",[])
            if isinstance(x,(list,tuple)) and "GetCartTypo" in x
        ]
        return {
            "source_repo":"GoogleCloudPlatform/microservices-demo",
            "source_sha":EXPECTED_COMMIT,
            "scope":"One source-confirmed Go gRPC consumer call; static fault injection",
            "source_path":REL,
            "original_rpc":RPC,
            "mutation":NEW,
            "original_binding_present":baseline,
            "mutated_incremental_binding_present":incremental_binding,
            "mutated_fresh_binding_present":fresh_binding,
            "mutated_incremental_consumes":_all_consumes(builder.graph),
            "mutated_fresh_consumes":_all_consumes(fresh.graph),
            "unresolved_typo_candidates":unresolved,
            "semantic_graph_equivalence":equivalent,
            "attribute_mismatch_diagnostics":mismatch,
            "passed":bool(baseline and not incremental_binding and
                          not fresh_binding and equivalent),
            "limitations":["Compilation/runtime not tested: mutant intentionally refers to an undefined gRPC method",
                           "This evaluates one source mutation, not real-world cross-service precision"]
        }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--repo",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    result=inspect(Path(args.repo))
    target=Path(args.output)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print("PINNED_RPC_MUTATION", json.dumps({
        "passed":result["passed"],"baseline":result["original_binding_present"],
        "mutated_incremental":result["mutated_incremental_binding_present"],
        "mutated_fresh":result["mutated_fresh_binding_present"],
        "semantic_graph_equivalence":result["semantic_graph_equivalence"],
        "attribute_mismatch_diagnostics":result["attribute_mismatch_diagnostics"],
        "unresolved_candidates":len(result["unresolved_typo_candidates"])
    },sort_keys=True))
    if not result["passed"]:
        raise SystemExit(1)


if __name__=="__main__":
    main()
