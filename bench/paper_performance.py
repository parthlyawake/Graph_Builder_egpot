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
    """Structural ID/typed-edge multiplicity signature (not attribute equality)."""
    nodes=set(map(str,g.nodes))
    edges=Counter((str(u),str(v),str(d.get("relation","")),str(d.get("layer","")))
                  for u,v,d in g.edges(data=True))
    return nodes,edges


def full_graph_signature(g):
    """Exact JSON-encodable graph metadata, node attrs and keyed-edge attrs.

    Distinguishes graphs that are structurally identical but have stale source
    lines, incorrect provenance, or conflicting dispatch confidence. Refuse
    opaque unserializable attributes instead of coercing them to strings.
    """
    from sqlite_graph_store import _dump
    return hashlib.sha256(_dump(g).encode("utf-8")).hexdigest()


def semantic_graph_signature(graph):
    """Full JSON metadata/attribute signature, ignoring ephemeral eNNN edge keys.

    Parallel edge multiplicity and every user-visible node/edge attribute are
    still included; only internal insertion-order counter keys are excluded.
    """
    from sqlite_graph_store import _dump, _canonical
    data=json.loads(_dump(graph))
    for edge in data["edges"]:
        del edge["key"]
    data["edges"].sort(key=lambda e: (e["source"], e["target"],
                                     _canonical(e["attrs"])))
    return hashlib.sha256(_canonical(data).encode("utf-8")).hexdigest()


def diagnose_graph_attribute_drift(incremental, fresh, *, limit=5):
    """Identify attribute drift without masking it as structural equality."""
    from collections import Counter
    from sqlite_graph_store import _canonical
    a, b = incremental, fresh
    metadata_keys = sorted(set(a.graph) | set(b.graph))
    metadata = [key for key in metadata_keys
                if a.graph.get(key) != b.graph.get(key)]
    common = set(a.nodes) & set(b.nodes)
    nodes = []
    for node in sorted(common, key=str):
        left, right = dict(a.nodes[node]), dict(b.nodes[node])
        if left != right:
            keys = sorted(set(left) | set(right))
            changed = [key for key in keys if left.get(key) != right.get(key)]
            nodes.append({"id": str(node), "changed_attrs": changed})
    def edge_counter(graph, *, include_key):
        return Counter(
            (str(u), str(v), str(k) if include_key else "",
             _canonical(dict(attrs)))
            for u, v, k, attrs in graph.edges(keys=True, data=True))
    a_exact, b_exact = edge_counter(a, include_key=True), edge_counter(b, include_key=True)
    a_sem, b_sem = edge_counter(a, include_key=False), edge_counter(b, include_key=False)
    return {
        "changed_graph_metadata_keys": metadata,
        "changed_node_attributes_count": len(nodes),
        "changed_node_attribute_examples": nodes[:limit],
        "exact_keyed_edge_attribute_equivalence": a_exact == b_exact,
        "edge_attribute_equivalence_disregarding_keys": a_sem == b_sem,
        "unmatched_edge_attribute_rows_without_keys": sum((a_sem-b_sem).values()),
        "sample_semantic_incremental_only_edges": [
            {"source": key[0], "target": key[1], "attrs": key[3][:900]}
            for key in list((a_sem-b_sem).keys())[:limit]],
        "sample_semantic_fresh_only_edges": [
            {"source": key[0], "target": key[1], "attrs": key[3][:900]}
            for key in list((b_sem-a_sem).keys())[:limit]],
        "unmatched_keyed_edge_rows": sum((a_exact-b_exact).values()),
        "sample_incremental_only_edges": [
            {"source": key[0], "target": key[1], "key": key[2],
             "attrs": key[3][:300]} for key in list((a_exact-b_exact).keys())[:limit]
        ],
        "sample_fresh_only_edges": [
            {"source": key[0], "target": key[1], "key": key[2],
             "attrs": key[3][:300]} for key in list((b_exact-a_exact).keys())[:limit]
        ],
    }


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
            full_equal=full_graph_signature(builder.graph)==full_graph_signature(fresh.graph)
            semantic_equal=(semantic_graph_signature(builder.graph)==
                            semantic_graph_signature(fresh.graph))
            mismatch = diagnose_graph_attribute_drift(builder.graph, fresh.graph) if not full_equal else None
            trials.append({"attribute_mismatch_diagnostics":mismatch,
                           "semantic_attribute_equivalence":semantic_equal,
                           "exact_attribute_equivalence":full_equal,"cold_s":cold,"incremental_s":incremental,"fresh_after_edit_s":rebuild,
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
        "exact_attribute_equivalence_passes":sum(x["exact_attribute_equivalence"] for x in trials),
        "semantic_attribute_equivalence_passes":sum(x["semantic_attribute_equivalence"] for x in trials),
        "example_attribute_mismatch":next((x["attribute_mismatch_diagnostics"] for x in trials
                                           if x["attribute_mismatch_diagnostics"]), None),
        "note":"Typed graph structural agreement is weaker than complete metadata and attribute agreement.",
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
    for case in result["cases"]:
        print("P4_VERIFIED_CASE", json.dumps({
            "name":case["name"],
            "git_commit":case["git_commit"],
            "equivalence_passes":case["equivalence_passes"],
            "exact_attribute_equivalence_passes":case["exact_attribute_equivalence_passes"],
            "semantic_attribute_equivalence_passes":case["semantic_attribute_equivalence_passes"],
            "attribute_mismatch":case["example_attribute_mismatch"],
            "incremental_p50_s":case["incremental"]["p50_s"],
            "rebuild_p50_s":case["fresh_after_edit"]["p50_s"],
            "speedup_p50":case["incremental_vs_fresh_speedup_p50"],
            "repetitions":args.repetitions
        },sort_keys=True))


if __name__=="__main__":main()
