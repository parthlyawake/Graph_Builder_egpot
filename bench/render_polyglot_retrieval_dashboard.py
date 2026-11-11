"""Render a self-contained retrieval dashboard from the saved benchmark JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "bench/templates/polyglot_retrieval_dashboard.html"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=ROOT / "bench/results/polyglot_repo_file_retrieval.json")
    parser.add_argument("--output", type=Path, default=ROOT / "polyglot_retrieval_dashboard.html")
    args = parser.parse_args()
    result = json.loads(args.results.read_text(encoding="utf-8"))
    if result.get("lexical_backend") != "rank_bm25.BM25Okapi":
        raise ValueError("Dashboard requires a result produced with actual BM25")
    if len(result.get("methods", {})) != 14 or len(result.get("repositories", {})) != 8:
        raise ValueError("Expected the complete 14-method, eight-repository run")

    compact = {
        "builder_revision": result["builder_revision"],
        "scope": result["scope"],
        "top_k": result["top_k_distinct_files"],
        "token_budget": result["token_budget"],
        "lexical_backend": result["lexical_backend"],
        "repositories": {
            repo: {
                "revision": details["source_revision_from_graph_audit"],
                "graph_nodes": details["graph_nodes"],
                "candidate_nodes": details["candidate_nodes"],
                "smoke_only": details["smoke_only"],
            }
            for repo, details in result["repositories"].items()
        },
        "methods": {
            method: {
                "title": details["title"],
                "primary": details["primary"],
                "by_repo": details["by_repo"],
                "rows": [
                    {
                        "id": row["id"],
                        "repo": row["repo"],
                        "query": row["query"],
                        "expected_files": row["expected_files"],
                        "top_files": row["top_files"],
                        "first_rank": row["first_rank"],
                        "recall": row["recall"],
                        "effective_config": row["effective_config"],
                        "smoke_only": row["smoke_only"],
                    }
                    for row in details["rows"]
                ],
            }
            for method, details in result["methods"].items()
        },
    }
    embedded = json.dumps(compact, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8").replace("__EMBEDDED_RESULTS__", embedded)
    if "__EMBEDDED_RESULTS__" in html:
        raise RuntimeError("The dashboard data placeholder was not replaced")
    args.output.write_text(html, encoding="utf-8")
    print(f"Wrote {args.output} ({args.output.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
