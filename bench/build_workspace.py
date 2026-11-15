#!/usr/bin/env python3
"""Construct a reproducible multi-service graph and machine-readable handoff.

This checks graph construction and coverage; it does not equate edge presence
with an independently measured precision/recall benchmark.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from multi_repo import WorkspaceCKGBuilder


def run(manifest, report, graph_path=None, *, strict=False, min_http=0):
    builder = WorkspaceCKGBuilder(str(manifest))
    graph = builder.build()
    verification = builder.verify_graph()
    relationships = Counter(d.get("relation", "unknown")
                            for _, _, d in graph.edges(data=True))
    possible = relationships.get("POSSIBLE_HTTP_TARGET", 0)
    runtime = {
        "thrift": getattr(builder, "thrift_bindings", {}),
        "amqp": getattr(builder, "amqp_topology", {}),
        "kafka_schemas": getattr(builder, "kafka_schema_links", 0),
        "graphql_embedded": graph.graph.get("graphql_embedded", {}),
    }
    failures = []
    if strict and not verification["source_coverage_complete"]:
        failures.append("incomplete_source_coverage")
    if relationships["HTTP_CALLS"] < min_http:
        failures.append("insufficient_confirmed_http_edges")
    if not verification["total_nodes"] or not verification["total_edges"]:
        failures.append("empty_graph")
    result = {
        "manifest": str(Path(manifest).resolve()),
        "evaluation": "graph_construction_and_coverage_not_edge_ground_truth",
        "verification": verification,
        "relations": dict(sorted(relationships.items())),
        "unresolved_http_candidates": possible,
        "runtime_bindings": runtime,
        "gate": {"passed": not failures, "failed_checks": failures,
                 "strict_coverage": strict, "minimum_confirmed_http": min_http},
    }
    if graph_path:
        builder.export_graph(str(graph_path), "json")
        result["graph_export"] = str(Path(graph_path).resolve())
    path = Path(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--graph")
    p.add_argument("--strict-coverage", action="store_true")
    p.add_argument("--min-http", type=int, default=0)
    options = p.parse_args()
    report = run(options.manifest, options.report, options.graph,
                 strict=options.strict_coverage, min_http=options.min_http)
    print(json.dumps({"nodes": report["verification"]["total_nodes"],
                      "edges": report["verification"]["total_edges"],
                      "services": report["verification"]["total_repositories"],
                      "confirmed_http": report["relations"].get("HTTP_CALLS", 0),
                      "possible_http": report["unresolved_http_candidates"],
                      "source_complete": report["verification"]["source_coverage_complete"],
                      "gate": report["gate"]}, indent=2))
    if not report["gate"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
