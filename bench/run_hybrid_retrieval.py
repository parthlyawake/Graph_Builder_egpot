"""Reproducible runner for the R0-R13 hybrid retrieval experiment matrix."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hybrid_retrieval import CONFIGS, HybridRetriever, _load_labels


def build_target(repo: str | None, workspace: str | None):
    with contextlib.redirect_stdout(io.StringIO()):
        if workspace:
            from multi_repo import WorkspaceCKGBuilder
            builder = WorkspaceCKGBuilder(workspace)
        else:
            from graft_ckg import CKGBuilder
            builder = CKGBuilder(repo)
        builder.build()
    return builder


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark every GRAFT-CKG hybrid retrieval configuration.")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--repo")
    target.add_argument("--workspace")
    parser.add_argument("--labels", required=True, help="JSON tasks with query and relevant/targets fields")
    parser.add_argument("--configs", nargs="+", choices=sorted(CONFIGS), default=list(CONFIGS))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--token-budget", type=int, default=2048)
    parser.add_argument("--ingest-lineage", action="store_true")
    parser.add_argument("--runtime-trace", help="JSON list of {source,target,confidence} runtime edges for R10")
    parser.add_argument("--output", default="bench/results/hybrid_retrieval.json")
    parser.add_argument("--quiet", action="store_true", help="Write the report without printing the full JSON")
    args = parser.parse_args()

    builder = build_target(args.repo, args.workspace)
    runtime_edges = []
    if args.runtime_trace:
        runtime_edges = json.loads(Path(args.runtime_trace).read_text(encoding="utf-8"))
        if not isinstance(runtime_edges, list):
            raise ValueError("Runtime trace JSON must be a list of edge objects.")
    retriever = HybridRetriever(builder, runtime_edges=runtime_edges)
    if args.ingest_lineage:
        retriever.ingest_lineage()
    report = retriever.benchmark(
        _load_labels(args.labels), configs=args.configs, top_k=args.top_k, token_budget=args.token_budget
    )
    report.update({
        "source": args.workspace or args.repo,
        "implemented_configurations": list(CONFIGS),
        "note": "Run on fixed repository revisions and labels. Do not compare against results from different corpora or token budgets.",
    })
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if not args.quiet:
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
