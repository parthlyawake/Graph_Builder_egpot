"""Run a non-fabricated GRAFT-CKG retrieval/ablation study on a pinned checkout.

For a publication, use --labels with independently reviewed EXACT source node IDs.
Different datasets must never be pooled without source hashes/revision metadata.
This runner compares implemented in-project methods, NOT published external systems.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from bench.paper_metrics import (retrieval_metrics, context_evidence_spans,
    byte_span_metrics, summarize_token_irrelevance, time_summary)
from hybrid_retrieval import CONFIGS, HybridRetriever
from dataclasses import replace


LAYER_NAMES=("Lsyn","Ldep","Lflow","Lsem","Lcontract")
CONFIGURATIONS=("R0","R1","R2","R3","R4","R5","R6","R9","R12","R13")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def revision(path):
    try:
        return subprocess.check_output(["git","-C",str(path),"rev-parse","HEAD"],
            stderr=subprocess.DEVNULL,text=True,timeout=8).strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def load_labels(path):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data,list) or not data:
        raise ValueError("Labels must be a nonempty list")
    ids=set()
    for item in data:
        if not isinstance(item.get("query"),str) or not item["query"].strip():
            raise ValueError("Query text required")
        if not isinstance(item.get("relevant"),list) or not item["relevant"]:
            raise ValueError("Exact list of relevant node IDs required")
        if not all(isinstance(x,str) and x for x in item["relevant"]):
            raise ValueError("Invalid exact node ID")
        if not isinstance(item.get("id"),str) or item["id"] in ids:
            raise ValueError("Unique query IDs required")
        ids.add(item["id"])
        # Evidence is optional; without it, do NOT publish token irrelevance.
        if "evidence" in item and (not isinstance(item["evidence"],list)
                or not all(isinstance(s,str) and s for s in item["evidence"])):
            raise ValueError("Evidence must be a list of nonempty exact excerpts")
    return data


def build(repo,workspace):
    if workspace:
        from multi_repo import WorkspaceCKGBuilder
        b=WorkspaceCKGBuilder(workspace)
    else:
        from graft_ckg import CKGBuilder
        b=CKGBuilder(repo)
    b.build()
    return b


def evaluate_variant(builder,labels,config,top_k,budget):
    retriever=HybridRetriever(builder)
    import tiktoken
    tokenizer=tiktoken.get_encoding("cl100k_base")
    rows=[]; token_rows=[]; timings=[]; missing=[]
    for item in labels:
        t0=time.perf_counter()
        result=retriever.retrieve(item["query"],config,top_k=top_k,token_budget=budget)
        timings.append(time.perf_counter()-t0)
        ranked=[x["node_id"] for x in result["top_matches"]]
        ctx=result["context"]
        evidence=item.get("evidence")
        token_metric=None
        if evidence is not None:
            try:
                spans=context_evidence_spans(ctx,evidence)
                token_metric=byte_span_metrics(ctx,spans,tokenizer)
                token_rows.append(token_metric)
            except ValueError as exc:
                missing.append({"id":item["id"],"reason":str(exc)})
        rows.append({"id":item["id"],"ranked_ids":ranked,
            "relevant_ids":item["relevant"],"bpe_tokens":result["bpe_tokens"],
            "effective_config":result["effective_config"],
            "token_evidence":token_metric})
        if result["bpe_tokens"]>budget:
            raise AssertionError("Context budget violated")
    ranking=retrieval_metrics(rows,k=top_k)
    return {"ranking":ranking,"mean_bpe_tokens":statistics.mean(
        r["bpe_tokens"] for r in rows),"timing":time_summary(timings),
        "token_irrelevance":summarize_token_irrelevance(token_rows),
        "token_evidence_unscored":missing,"queries":rows}


def filtered_graph(builder,removed_layer):
    """Post-construction edge masking; not falsely described as rebuild-time ablation."""
    clone=copy.copy(builder)
    clone.graph=builder.graph.copy()
    doomed=[(u,v,k) for u,v,k,d in clone.graph.edges(keys=True,data=True)
            if d.get("layer")==removed_layer]
    clone.graph.remove_edges_from(doomed)
    return clone,len(doomed)


def evaluate_grafting(builder, rows, labels, token_budget, allowed_layers=None):
    """Exact-ID recall among nodes actually packed by deterministic grafting.

    This is graph-context recall, NOT the context-body semantic evidence metric.
    Ranking inputs are supplied independently for each stage.
    """
    from traversal import SCKGTraversal
    traversal=SCKGTraversal(builder)
    scores=[]; tokens=[]; missing=0
    if len(rows)!=len(labels):
        raise ValueError("Ranking and label rows must align")
    for row,label in zip(rows,labels):
        if row["id"]!=label["id"]:
            raise ValueError("Query order mismatch")
        ranked=row["ranked_ids"]
        if not ranked:
            scores.append(0.0);tokens.append(0);missing+=1;continue
        graft=traversal.deterministic_subtree_graft(
            ranked[0],max_tokens=token_budget,layers=allowed_layers)
        if "error" in graft:
            scores.append(0.0);tokens.append(0);missing+=1;continue
        chosen=set(graft.get("selected_nodes",[]))
        gold=set(label["relevant"])
        scores.append(len(chosen & gold)/len(gold))
        tokens.append(int(graft["bpe_tokens"]))
        if tokens[-1]>token_budget:
            raise AssertionError("Graft token limit exceeded")
    return {"n_queries":len(labels),"mean_exact_node_recall":statistics.mean(scores),
            "mean_bpe_tokens":statistics.mean(tokens),
            "missing_roots":missing}


def main():
    p=argparse.ArgumentParser()
    dest=p.add_mutually_exclusive_group(required=True)
    dest.add_argument("--repo")
    dest.add_argument("--workspace")
    p.add_argument("--labels",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--top-k",type=int,default=5)
    p.add_argument("--token-budget",type=int,default=2048)
    p.add_argument("--configs",nargs="+",choices=CONFIGURATIONS,default=list(CONFIGURATIONS))
    p.add_argument("--ablations",action="store_true")
    args=p.parse_args()
    if args.top_k<1 or args.token_budget<1:
        p.error("Positive top-k and token-budget required")
    labels=load_labels(args.labels)
    repo_root=args.repo or str(Path(args.workspace).resolve().parent)
    t0=time.perf_counter()
    builder=build(args.repo,args.workspace)
    build_s=time.perf_counter()-t0
    graph=builder.graph
    report={"protocol":"graft-ckg-paper-evaluation-v1",
        "status":"unreviewed" if any(x.get("label_status")!="independently_reviewed" for x in labels)
                  else "labels_claim_independent_review",
        "label_sha256":sha(args.labels),"labels_path":str(args.labels),
        "source_revision":revision(repo_root),
        "builder_revision":revision(ROOT),"python":sys.version,"platform":platform.platform(),
        "top_k":args.top_k,"token_budget":args.token_budget,"query_count":len(labels),
        "graph":{"nodes":graph.number_of_nodes(),"edges":graph.number_of_edges(),
                 "build_seconds":build_s},
        "comparisons":{},"ablations":{},
        "limitations":["Labels are externally supplied; runner cannot establish independent review.",
         "Edge masking is a retrieval-layer ablation, not a parser rebuild ablation.",
         "Only bundled retrieval variants are compared, not published independent baselines."]}
    for config in args.configs:
        report["comparisons"][config]=evaluate_variant(
            builder,labels,config,args.top_k,args.token_budget)
    if args.ablations:
        # Ranker ablations are recomputed from a freshly constructed retriever.
        # For Lsem, explicitly deactivate semantic vector retrieval as well.
        base=CONFIGS["R5"]
        for layer in LAYER_NAMES:
            masked,removed=filtered_graph(builder,layer)
            replacement=replace(base,semantic=False) if layer=="Lsem" else base
            prior=CONFIGS["R5"]
            try:
                CONFIGS["R5"]=replacement
                metric=evaluate_variant(masked,labels,"R5",args.top_k,args.token_budget)
            finally:
                CONFIGS["R5"]=prior
            layer_filter=[name for name in LAYER_NAMES if name!=layer]
            full_rows=report["comparisons"]["R5"]["queries"] if "R5" in report["comparisons"] else (
                evaluate_variant(builder,labels,"R5",args.top_k,args.token_budget)["queries"])
            original_rows=metric["queries"]
            graft_only=evaluate_grafting(builder,full_rows,labels,args.token_budget,layer_filter)
            ranking_only=evaluate_grafting(builder,original_rows,labels,args.token_budget,None)
            both=evaluate_grafting(masked,original_rows,labels,args.token_budget,layer_filter)
            report["ablations"][layer]={"stage":"post_construction_feature_masks",
                "removed_edges":removed,"semantic_index_disabled":layer=="Lsem",
                "metric":metric,
                "graft_only":graft_only,"ranking_only":ranking_only,"ranking_and_graft":both,
                "construction_stage":"not separately evaluated"}
    output=Path(args.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print("Wrote",output,"status=",report["status"],"queries=",len(labels))


if __name__=="__main__":
    main()
