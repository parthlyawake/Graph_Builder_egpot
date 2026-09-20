"""
bench_agent_toolcall.py  —  GRAFT-CKG Agentic Tool-Call Experiment
====================================================================
Paper Section VII-C: Validates that an LLM agent equipped with GRAFT-CKG
tools (graft_subtree, query_blast_radius) resolves bug-localisation tasks
using fewer tool calls and fewer context tokens than a baseline agent that
performs raw file reads.

Design (LLM-free simulation)
-----------------------------
An agent is represented as a deterministic "task solver" that:
  - GRAFT-CKG Agent: uses deterministic_subtree_graft then checks a
    predicate over the returned context snippet.
  - Baseline Agent : reads whole source files one at a time until it
    finds the answer predicate.

For each task we record:
  - tool_calls   : number of graph/file API calls made
  - tokens_in    : total characters fed into the "agent" (proxy for tokens)
  - resolved     : True if the agent found the answer within budget
  - latency_ms   : wall-clock time

10 canonical bug-localisation tasks are defined over examples/polyglot_system.
"""

import os
import sys
import time
import json
import statistics

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from graft_ckg import CKGBuilder
from traversal import SCKGTraversal

# ---------------------------------------------------------------------------
# Task Definitions
# ---------------------------------------------------------------------------

EXAMPLE_REPO = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "examples", "polyglot_system",
)

# Each task is a dict:
#   query      - the natural language question an engineer asks
#   expect_kw  - a keyword that must appear in the resolved context (success predicate)
#   root_hint  - optional node id fragment for GRAFT-CKG agent to anchor subtree
TASKS = [
    {
        "id": "T01",
        "query": "Where is ShipOrder implemented?",
        "expect_kw": "ShipOrder",
        "root_hint": "ShipOrder",
    },
    {
        "id": "T02",
        "query": "Which function handles checkout submission?",
        "expect_kw": "submitCheckout",
        "root_hint": "submitCheckout",
    },
    {
        "id": "T03",
        "query": "What proto contract governs the shipping service?",
        "expect_kw": "shipping",
        "root_hint": "shipping",
    },
    {
        "id": "T04",
        "query": "What Python function places orders?",
        "expect_kw": "place_order",
        "root_hint": "place_order",
    },
    {
        "id": "T05",
        "query": "What is the grpc method for getting a quote?",
        "expect_kw": "GetQuote",
        "root_hint": "GetQuote",
    },
    {
        "id": "T06",
        "query": "Which function computes shipping cost?",
        "expect_kw": "calculate_shipping",
        "root_hint": "calculate_shipping",
    },
    {
        "id": "T07",
        "query": "What HTTP endpoint does the checkout call externally?",
        "expect_kw": "fetch",
        "root_hint": "submitCheckout",
    },
    {
        "id": "T08",
        "query": "Find functions defined in order_service.py",
        "expect_kw": "order",
        "root_hint": "order_service",
    },
    {
        "id": "T09",
        "query": "What message types are defined in the shipping proto?",
        "expect_kw": "ShippingAddress",
        "root_hint": "ShippingAddress",
    },
    {
        "id": "T10",
        "query": "What class or function invokes the shipping service from Python?",
        "expect_kw": "ship",
        "root_hint": "ship",
    },
]

# ---------------------------------------------------------------------------
# Agent Simulation Helpers
# ---------------------------------------------------------------------------

CHAR_PER_TOKEN = 4  # rough approximation


def _tokens(text: str) -> int:
    return max(1, len(text) // CHAR_PER_TOKEN)


def graft_agent_solve(traversal: SCKGTraversal, task: dict, token_budget: int = 4096):
    """
    GRAFT-CKG Agent:
      1. Use RAG query to find root node.
      2. Call deterministic_subtree_graft to extract bounded context.
      3. Check predicate.
    Returns (tool_calls, tokens_in, resolved, latency_s).
    """
    tool_calls = 0
    tokens_in = 0
    resolved = False
    t0 = time.perf_counter()

    # Tool call 1: RAG query
    query = task["query"]
    rag_dict = traversal.builder.rag_query(query, top_k=3)
    tool_calls += 1
    tokens_in += _tokens(query)

    # rag_query returns {"query":..., "hits":..., "top_matches":[{node_id, score, ...}], ...}
    top_matches = rag_dict.get("top_matches", [])

    # Determine best root node from RAG or hint
    root_node = None
    hint = task.get("root_hint", "").lower()
    for match in top_matches:
        node_id = match.get("node_id", "")
        snippet = match.get("code_snippet", "") + " " + match.get("docstring", "")
        name = match.get("name", "")
        if hint in node_id.lower() or hint in snippet.lower() or hint in name.lower():
            root_node = node_id
            break
    if root_node is None and top_matches:
        root_node = top_matches[0].get("node_id")

    # Tool call 2: graft_subtree
    if root_node:
        graft_result = traversal.deterministic_subtree_graft(root_node, max_tokens=token_budget)
        tool_calls += 1
        ctx = graft_result.get("grafted_context", "")
        tokens_in += _tokens(ctx)
        expect = task["expect_kw"].lower()
        if expect in ctx.lower():
            resolved = True
    else:
        # Last-resort: check grafted_execution_context directly from rag
        ctx = str(rag_dict.get("grafted_execution_context", ""))
        tokens_in += _tokens(ctx)
        if task["expect_kw"].lower() in ctx.lower():
            resolved = True

    latency_s = time.perf_counter() - t0
    return tool_calls, tokens_in, resolved, latency_s


def baseline_agent_solve(repo_path: str, task: dict, token_budget: int = 4096):
    """
    Baseline Agent (raw file reader):
      Iterates source files alphabetically, reads each one,
      checks the success predicate. Stops when budget exceeded.
    Returns (tool_calls, tokens_in, resolved, latency_s).
    """
    tool_calls = 0
    tokens_in = 0
    resolved = False
    t0 = time.perf_counter()
    expect = task["expect_kw"].lower()

    for root, dirs, files in os.walk(repo_path):
        dirs.sort()
        for fname in sorted(files):
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
            except Exception:
                continue
            tool_calls += 1
            tokens_in += _tokens(content)
            if expect in content.lower():
                resolved = True
                break
            if tokens_in > token_budget:
                break
        if resolved or tokens_in > token_budget:
            break

    latency_s = time.perf_counter() - t0
    return tool_calls, tokens_in, resolved, latency_s


# ---------------------------------------------------------------------------
# Main experiment
# ---------------------------------------------------------------------------

def run_experiment():
    print("=" * 70)
    print("  GRAFT-CKG Agentic Tool-Call Experiment (Paper §VII-C)")
    print("=" * 70)
    print(f"[*] Building CKG from: {EXAMPLE_REPO}")

    builder = CKGBuilder(EXAMPLE_REPO)
    builder.build()
    traversal = SCKGTraversal(builder)

    print(f"[*] Graph: {builder.graph.number_of_nodes()} nodes, {builder.graph.number_of_edges()} edges")
    print()

    graft_rows = []
    base_rows = []

    HEADER = (
        f"  {'ID':<5} {'Resolved':<10} {'Calls':<8} "
        f"{'Tokens':<10} {'Latency':>10}"
    )
    DIVIDER = "  " + "-" * 48

    # ---- GRAFT-CKG Agent ----
    print("  [A] GRAFT-CKG Agent")
    print(HEADER)
    print(DIVIDER)
    for task in TASKS:
        tc, tok, res, lat = graft_agent_solve(traversal, task)
        graft_rows.append({"id": task["id"], "tool_calls": tc, "tokens": tok,
                           "resolved": res, "latency_ms": round(lat * 1000, 1)})
        print(
            f"  {task['id']:<5} {'OK' if res else 'FAIL':<10} {tc:<8} "
            f"{tok:<10} {lat*1000:>9.1f}ms"
        )
    print(DIVIDER)

    # ---- Baseline Agent ----
    print()
    print("  [B] Baseline Agent (raw file reads)")
    print(HEADER)
    print(DIVIDER)
    for task in TASKS:
        tc, tok, res, lat = baseline_agent_solve(EXAMPLE_REPO, task)
        base_rows.append({"id": task["id"], "tool_calls": tc, "tokens": tok,
                          "resolved": res, "latency_ms": round(lat * 1000, 1)})
        print(
            f"  {task['id']:<5} {'OK' if res else 'FAIL':<10} {tc:<8} "
            f"{tok:<10} {lat*1000:>9.1f}ms"
        )
    print(DIVIDER)

    # ---- Aggregate comparison ----
    def _agg(rows):
        resolved_n = sum(1 for r in rows if r["resolved"])
        return {
            "recall": resolved_n / len(rows),
            "mean_calls": statistics.mean(r["tool_calls"] for r in rows),
            "mean_tokens": statistics.mean(r["tokens"] for r in rows),
            "mean_latency_ms": statistics.mean(r["latency_ms"] for r in rows),
            "total_resolved": resolved_n,
        }

    ga = _agg(graft_rows)
    ba = _agg(base_rows)

    call_reduction  = (ba["mean_calls"]   - ga["mean_calls"])   / max(ba["mean_calls"],   1) * 100
    token_reduction = (ba["mean_tokens"]  - ga["mean_tokens"])  / max(ba["mean_tokens"],  1) * 100

    print()
    print("=" * 70)
    print("  COMPARISON TABLE  (paper VII-C, Table III)")
    print("=" * 70)
    print(f"  {'Metric':<30} {'GRAFT-CKG':>12} {'Baseline':>12} {'Delta':>10}")
    print("  " + "-" * 66)
    print(f"  {'Task Recall (%)':<30} {ga['recall']*100:>11.1f}% {ba['recall']*100:>11.1f}%")
    print(f"  {'Mean Tool Calls':<30} {ga['mean_calls']:>12.1f} {ba['mean_calls']:>12.1f} {call_reduction:>+8.1f}%")
    print(f"  {'Mean Context Tokens':<30} {ga['mean_tokens']:>12.1f} {ba['mean_tokens']:>12.1f} {token_reduction:>+8.1f}%")
    print(f"  {'Mean Latency (ms)':<30} {ga['mean_latency_ms']:>12.1f} {ba['mean_latency_ms']:>12.1f}")
    print("=" * 70)
    print()

    verdict_recall = ga["recall"] >= ba["recall"]
    verdict_tokens = token_reduction > 0
    verdict_calls  = call_reduction > 0
    overall = "PASS" if (verdict_recall and (verdict_tokens or verdict_calls)) else "REVIEW"
    print(f"  Verdict: {overall}")
    print(f"    Recall    : {'>= baseline [PASS]' if verdict_recall else '< baseline [REVIEW]'}")
    print(f"    Call reduction : {call_reduction:+.1f}% {'[PASS]' if verdict_calls else '[REVIEW]'}")
    print(f"    Token reduction: {token_reduction:+.1f}% {'[PASS]' if verdict_tokens else '[REVIEW]'}")

    # ---- Write JSON ----
    results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(results_dir, exist_ok=True)
    out_path = os.path.join(results_dir, "bench_agent_toolcall.json")
    with open(out_path, "w") as f:
        json.dump({
            "graft_ckg_agent": {"rows": graft_rows, "aggregate": ga},
            "baseline_agent": {"rows": base_rows, "aggregate": ba},
            "comparison": {
                "call_reduction_pct": round(call_reduction, 2),
                "token_reduction_pct": round(token_reduction, 2),
                "recall_graft": ga["recall"],
                "recall_baseline": ba["recall"],
            },
        }, f, indent=2)
    print(f"\n  Results written to: {out_path}")


if __name__ == "__main__":
    run_experiment()
