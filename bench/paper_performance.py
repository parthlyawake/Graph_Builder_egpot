"""Versioned cold-build/incremental benchmark with fresh-build equivalence.

The manifest contains real, pinned local checkouts. Every trial is isolated in
a temporary source copy. CPU, OS, Python, dependency versions, memory and raw
times are recorded. A workspace update is NOT assumed O(delta).
"""
from __future__ import annotations
from collections import Counter
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from bench.paper_metrics import time_summary


def graph_signature(g):
    nodes=set(map(str,g.nodes))
    edges=Counter((str(u),str(v),str(d.get("relation","")),str(d.get("layer","")))
                  for u,v,d in g.edges(data=True))
    return nodes,edges


def rev(root):
    try:return subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],
           stderr=subprocess.DEVNULL,text=True,timeout=5).strip()
    except (OSError,subprocess.CalledProcessError,subprocess.TimeoutExpired):return None


def run_case(case,repeats):
    """case: {name,repo,relative_file,mode,expected_commit?}."""
    from graft_ckg import CKGBuilder
    src=Path(case["repo"]).resolve()
    rel=Path(case["relative_file"])
    if not src.is_dir() or rel.is_absolute() or ".." in rel.parts or not (src/rel).is_file():
        raise ValueError("Invalid or missing case path")
    revision=rev(src)
    if not revision or not case.get("expected_commit"):
        raise ValueError("For publication, pin each clone and supply expected_commit")
    if revision!=case["expected_commit"]:
        raise ValueError(f"Revision mismatch for {case['name']}: {revision}")
    mode=case.get("mode","append_comment")
    if mode not in ("append_comment","append_python_function"):
        raise ValueError("Unsupported edit mode")
    if mode=="append_python_function" and rel.suffix!=".py":
        raise ValueError("Function append requires a Python source file")
    trials=[]
    for repeat in range(repeats):
        with tempfile.TemporaryDirectory(prefix="sckg-paper-") as td:
            dst=Path(td)/"checkout"
            shutil.copytree(src,dst,ignore=shutil.ignore_patterns(".git","node_modules",
                                      "__pycache__",".venv",".pytest_cache"))
            tracemalloc.start()
            builder=CKGBuilder(str(dst))
            t0=time.perf_counter();builder.build();cold=time.perf_counter()-t0
            _,peak_cold=tracemalloc.get_traced_memory()
            tracemalloc.reset_peak()
            target=dst/rel
            if mode=="append_comment":
                change="\n# sckg_paper_benchmark_edit_unique\n" if rel.suffix==".py" else "\n// sckg_paper_benchmark_edit_unique\n"
            else:
                change="\ndef sckg_paper_benchmark_probe_unique(x):\n    return x + 1\n"
            with target.open("a",encoding="utf-8") as f:f.write(change)
            t1=time.perf_counter()
            builder.update_files([rel.as_posix()])
            incremental=time.perf_counter()-t1
            _,peak_incr=tracemalloc.get_traced_memory()
            tracemalloc.reset_peak()
            fresh=CKGBuilder(str(dst))
            t2=time.perf_counter();fresh.build();rebuild=time.perf_counter()-t2
            _,peak_fresh=tracemalloc.get_traced_memory()
            tracemalloc.stop()
            equal=graph_signature(builder.graph)==graph_signature(fresh.graph)
            trials.append({"cold_s":cold,"incremental_s":incremental,"fresh_after_edit_s":rebuild,
                           "peak_cold_tracemalloc_bytes":peak_cold,
                           "peak_incremental_tracemalloc_bytes":peak_incr,
                           "peak_fresh_tracemalloc_bytes":peak_fresh,
                           "equivalent":equal,"post_edit_nodes":builder.graph.number_of_nodes(),
                           "post_edit_edges":builder.graph.number_of_edges()})
            if not equal:
                raise AssertionError("Incremental graph differs from fresh build; trial aborted")
    return {"name":case["name"],"repo":str(src),"git_commit":revision,
        "relative_file":rel.as_posix(),"mode":mode,"trials":trials,
        "cold":time_summary([x["cold_s"] for x in trials]),
        "incremental":time_summary([x["incremental_s"] for x in trials]),
        "fresh_after_edit":time_summary([x["fresh_after_edit_s"] for x in trials]),
        "equivalence_passes":sum(x["equivalent"] for x in trials),
        "incremental_vs_fresh_speedup_p50":statistics.median(x["fresh_after_edit_s"] for x in trials) /
                   statistics.median(x["incremental_s"] for x in trials)}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--manifest",required=True,help="JSON list of pinned local repo cases")
    p.add_argument("--repetitions",type=int,default=5)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    if args.repetitions<3: p.error("At least 3 repetitions required")
    cases=json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if not isinstance(cases,list) or not cases:p.error("Nonempty list required")
    result={"protocol":"cold-incremental-fresh-v1",
        "environment":{"python":sys.version,"platform":platform.platform(),
                       "processor":platform.processor(),"cpu_count":os.cpu_count()},
        "manifest_sha256":hashlib.sha256(Path(args.manifest).read_bytes()).hexdigest(),
        "repetitions":args.repetitions,
        "scope":"single-repository file-level incremental; workspace composition not benchmarked",
        "timing_instrumentation":"tracemalloc enabled in all timed phases; reported peaks reflect process allocations and existing live objects, not RSS",
        "cases":[run_case(case,args.repetitions) for case in cases]}
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print("Wrote",out)


if __name__=="__main__":main()
