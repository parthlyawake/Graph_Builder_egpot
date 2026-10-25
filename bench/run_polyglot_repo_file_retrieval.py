"""File-level retrieval comparison on the eight pinned polyglot-list checkouts.

Reuses graph snapshots from the separate graph-builder audit. The repositories
are independent systems, so each is searched separately and scores are macro
averaged. Sock Shop's deployment-only checkout is reported as a smoke test.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import pickle
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hybrid_retrieval import BM25Okapi, CONFIGS, HybridRetriever  # noqa: E402


SOURCE_PATHS = {
    "microservices-demo": "microservices-demo",
    "opentelemetry-demo": "opentelemetry-demo",
    "retail-store-sample-app": "retail-store-sample-app",
    "robot-shop": "robot-shop",
    "bookinfo": "istio/samples/bookinfo",
    "train-ticket": "train-ticket",
    "DeathStarBench": "DeathStarBench-source",
    "sock-shop": "sock-shop",
}

# The final two graph snapshots were rebuilt after the other six during the
# builder fix audit. These directories together match fix_verification.json.
SNAPSHOT_DIRS = {
    "opentelemetry-demo": "results_fix2",
    "DeathStarBench": "results_fix2",
}

PINNED_REVISIONS = {
    "microservices-demo": "38e7348eb289eb5b87c0c6e8cb19ced0449dc389",
    "opentelemetry-demo": "5c8d404a85380226ff45a39dcb4159eda9552c56",
    "retail-store-sample-app": "d7a380b843e0759e58754f74188ea18252a51415",
    "robot-shop": "55292e2199f2fb00a165b1f7d3045fe7f8922038",
    "bookinfo": "64b84bc308d5533e26f71ab7241e2c3eb927d67e",
    "train-ticket": "313886e99befb94be6cd45f085c98e0019f59829",
    "DeathStarBench": "6ecb09706140f8730b5385c08f1386c654c3c526",
    "sock-shop": "9dff06fae4981921caec6a62393a6ebfce4b3e3f",
}


def _git_head(path: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _build_retriever(repo: str, validation_root: Path, lineage_commits: int) -> tuple[HybridRetriever, int]:
    graph_path = validation_root / SNAPSHOT_DIRS.get(repo, "results_fix") / repo / "graph.pkl"
    source = validation_root / SOURCE_PATHS[repo]
    if not graph_path.is_file() or not source.is_dir():
        raise FileNotFoundError(f"Missing graph or source checkout for {repo}: {graph_path}, {source}")
    # These pickles were produced by our own local graph audit. Do not load
    # graph snapshots from untrusted sources.
    with graph_path.open("rb") as stream:
        graph = pickle.load(stream)
    builder = SimpleNamespace(graph=graph, repo_path=str(source))
    retriever = HybridRetriever(builder, include_documents=True)
    lineage_added = retriever.ingest_lineage(max_commits=lineage_commits)
    return retriever, lineage_added


def _file_rank(result: dict, retriever: HybridRetriever, source: Path, top_k: int) -> list[str]:
    ranked = []
    seen = set()
    for match in result["top_matches"]:
        candidate = retriever.candidates[match["node_id"]]
        file = candidate.file.replace("\\", "/")
        if candidate.is_document and Path(file).is_absolute():
            try:
                file = Path(file).relative_to(source).as_posix()
            except ValueError:
                continue
        if not file or file in seen:
            continue
        seen.add(file)
        ranked.append(file)
        if len(ranked) == top_k:
            break
    return ranked


def _score(rows: list[dict], top_k: int) -> dict:
    n = len(rows)
    return {
        "tasks": n,
        f"MRR@{top_k}": round(sum(1 / row["first_rank"] for row in rows if row["first_rank"]) / n, 4),
        "Hits@1_pct": round(100 * sum(row["first_rank"] == 1 for row in rows) / n, 1),
        f"Hits@{top_k}_pct": round(100 * sum(row["first_rank"] is not None for row in rows) / n, 1),
        f"File_Recall@{top_k}_pct": round(100 * sum(row["recall"] for row in rows) / n, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validation-root", type=Path, default=ROOT.parent / "graph_validation_repos")
    parser.add_argument("--labels", type=Path, default=ROOT / "bench/labels/polyglot_repo_file_retrieval.json")
    parser.add_argument("--output", type=Path, default=ROOT / "bench/results/polyglot_repo_file_retrieval.json")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--candidate-window", type=int, default=250)
    parser.add_argument("--token-budget", type=int, default=2048)
    parser.add_argument("--lineage-commits", type=int, default=50)
    parser.add_argument("--configs", nargs="+", choices=list(CONFIGS), default=list(CONFIGS))
    args = parser.parse_args()
    if BM25Okapi is None:
        raise RuntimeError("rank_bm25 is required for this comparison; install the declared project dependency first")
    if args.top_k < 1 or args.candidate_window < args.top_k:
        parser.error("candidate-window must be at least top-k, and top-k must be positive")
    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    grouped = defaultdict(list)
    for task in labels:
        grouped[task["repo"]].append(task)
    unknown = set(grouped) - set(SOURCE_PATHS)
    if unknown:
        raise ValueError(f"Unknown repositories in labels: {sorted(unknown)}")

    report = {
        "scope": "File-level retrieval on each listed checkout independently; not a unified cross-repository workspace",
        "labels": str(args.labels),
        "top_k_distinct_files": args.top_k,
        "candidate_window_nodes": args.candidate_window,
        "token_budget": args.token_budget,
        "lineage_commits": args.lineage_commits,
        "builder_revision": _git_head(ROOT),
        "lexical_backend": "rank_bm25.BM25Okapi",
        "methods": {method: {"title": CONFIGS[method].title, "rows": []} for method in args.configs},
        "repositories": {},
        "limitations": [
            "Labels were manually selected from source, with three issue-like tasks per application and two deployment-dashboard smoke tasks for Sock Shop.",
            "The Sock Shop umbrella checkout has no application service source; its smoke tasks are excluded from the primary score.",
            "DeathStarBench C++ and Thrift application implementation is outside current parser coverage; tasks target supported Go, JavaScript and Python.",
            "No runtime traces are supplied, so R10 cannot test its additional runtime signal.",
            "The source snapshots have no .git histories, so R8 cannot test its additional Git-lineage signal.",
            "These are small, curated localization tasks, not an independent issue benchmark or proof of statistical superiority.",
        ],
    }
    started = time.perf_counter()
    for repo, tasks in grouped.items():
        print(f"[{repo}] loading graph and indexes", flush=True)
        t0 = time.perf_counter()
        source = (args.validation_root / SOURCE_PATHS[repo]).resolve()
        retriever, lineage_added = _build_retriever(repo, args.validation_root, args.lineage_commits)
        files_in_graph = {candidate.file.replace("\\", "/") for candidate in retriever.candidates.values()}
        for task in tasks:
            for expected in task["relevant_files"]:
                if not (source / expected).is_file():
                    raise FileNotFoundError(f"Missing labelled source file: {source / expected}")
                if expected not in files_in_graph:
                    raise ValueError(f"Labelled source file has no graph candidate: {repo}/{expected}")
        report["repositories"][repo] = {
            "source": str(source),
            "source_revision_from_graph_audit": PINNED_REVISIONS[repo],
            "source_git_head_available": _git_head(source),
            "graph_snapshot": str(args.validation_root / SNAPSHOT_DIRS.get(repo, "results_fix") / repo / "graph.pkl"),
            "graph_nodes": retriever.graph.number_of_nodes(),
            "candidate_nodes": len(retriever.candidates),
            "lineage_commits_added": lineage_added,
            "tasks": len(tasks),
            "smoke_only": all(task.get("smoke_only", False) for task in tasks),
        }
        for method in args.configs:
            print(f"[{repo}] {method}", flush=True)
            for task in tasks:
                result = retriever.retrieve(
                    task["query"], config=method,
                    top_k=args.candidate_window, token_budget=args.token_budget,
                )
                files = _file_rank(result, retriever, source, args.top_k)
                expected = set(task["relevant_files"])
                first_rank = next((i for i, file in enumerate(files, 1) if file in expected), None)
                row = {
                    "id": task["id"], "repo": repo, "query": task["query"],
                    "expected_files": task["relevant_files"], "first_rank": first_rank,
                    "recall": round(len(expected.intersection(files)) / len(expected), 4),
                    "top_files": files, "effective_config": result["effective_config"],
                    "smoke_only": bool(task.get("smoke_only", False)),
                }
                report["methods"][method]["rows"].append(row)
        report["repositories"][repo]["seconds"] = round(time.perf_counter() - t0, 1)
        print(f"[{repo}] complete in {report['repositories'][repo]['seconds']}s", flush=True)
        # Checkpoint so large runs are recoverable and progress is inspectable.
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for method in args.configs:
        rows = report["methods"][method]["rows"]
        report["methods"][method]["primary"] = _score([row for row in rows if not row["smoke_only"]], args.top_k)
        report["methods"][method]["sock_shop_smoke"] = _score([row for row in rows if row["smoke_only"]], args.top_k)
        report["methods"][method]["by_repo"] = {
            repo: _score([row for row in rows if row["repo"] == repo], args.top_k)
            for repo in grouped if repo != "sock-shop"
        }
    report["seconds"] = round(time.perf_counter() - started, 1)
    report["ranked_by"] = [method for method in sorted(
        args.configs,
        key=lambda method: (
            -report["methods"][method]["primary"][f"File_Recall@{args.top_k}_pct"],
            -report["methods"][method]["primary"][f"MRR@{args.top_k}"],
            method,
        ),
    )]
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}", flush=True)
    for method in report["ranked_by"]:
        print(method, report["methods"][method]["primary"], flush=True)


if __name__ == "__main__":
    main()
