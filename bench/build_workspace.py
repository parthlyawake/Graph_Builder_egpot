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


def run(manifest, report, graph_path=None, *, strict=False, min_http=0,
        min_possible_http=0, min_event_paths=0, min_graphql_fields=0,
        min_graphql_ops=0, min_graphql_links=0):
    builder = WorkspaceCKGBuilder(str(manifest))
    graph = builder.build()
    verification = builder.verify_graph()
    relationships = Counter(d.get("relation", "unknown")
                            for _, _, d in graph.edges(data=True))
    possible = relationships.get("POSSIBLE_HTTP_TARGET", 0)
    graphql_operations = sum(d.get("type") == "graphql_operation"
                             for _, d in graph.nodes(data=True))
    graphql_links = sum(
        d.get("relation") == "CONSUMES" and str(src).startswith("graphqlop::")
        and str(dst).startswith("contract::graphql::")
        for src, dst, d in graph.edges(data=True))
    from traversal import SCKGTraversal
    traversal = SCKGTraversal(builder)
    graphql_fields = sum(
        1 for node, data in graph.nodes(data=True)
        if node.startswith("contract::graphql::") and data.get("spec") == "graphql"
    )
    event_paths = 0
    for src, data in graph.nodes(data=True):
        if graph.out_degree(src) == 0:
            continue
        if any(edge.get("relation") == "PRODUCES_EVENT"
               for _, _, edge in graph.out_edges(src, data=True)):
            event_paths += traversal.event_delivery_paths(src, max_paths=1000).get("path_count", 0)
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
    if possible < min_possible_http:
        failures.append("insufficient_source_evidenced_possible_http_edges")
    if event_paths < min_event_paths:
        failures.append("insufficient_confirmed_event_delivery_paths")
    if graphql_fields < min_graphql_fields:
        failures.append("insufficient_source_evidenced_graphql_contract_fields")
    if graphql_operations < min_graphql_ops:
        failures.append("insufficient_graphql_operations")
    if graphql_links < min_graphql_links:
        failures.append("insufficient_typed_graphql_consumes")
    if not verification["total_nodes"] or not verification["total_edges"]:
        failures.append("empty_graph")
    result = {
        "manifest": str(Path(manifest).resolve()),
        "evaluation": "graph_construction_and_coverage_not_edge_ground_truth",
        "verification": verification,
        "relations": dict(sorted(relationships.items())),
        "unresolved_http_candidates": possible,
        "source_evidenced_event_delivery_paths": event_paths,
        "graphql_contract_fields": graphql_fields,
        "graphql_operations": graphql_operations,
        "graphql_contract_consumes": graphql_links,
        "http_resolution_diagnostics": graph.graph.get("http_resolution_diagnostics", {}),
        "runtime_bindings": runtime,
        "gate": {"passed": not failures, "failed_checks": failures,
                 "strict_coverage": strict, "minimum_confirmed_http": min_http,
                 "minimum_possible_http": min_possible_http,
                 "minimum_event_paths": min_event_paths,
                 "minimum_graphql_fields": min_graphql_fields,
                 "minimum_graphql_ops": min_graphql_ops,
                 "minimum_graphql_links": min_graphql_links},
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
    p.add_argument("--min-possible-http", type=int, default=0)
    p.add_argument("--min-event-paths", type=int, default=0)
    p.add_argument("--min-graphql-fields", type=int, default=0)
    p.add_argument("--min-graphql-ops", type=int, default=0)
    p.add_argument("--min-graphql-links", type=int, default=0)
    options = p.parse_args()
    report = run(options.manifest, options.report, options.graph,
                 strict=options.strict_coverage, min_http=options.min_http,
                 min_possible_http=options.min_possible_http,
                 min_event_paths=options.min_event_paths,
                 min_graphql_fields=options.min_graphql_fields,
                 min_graphql_ops=options.min_graphql_ops,
                 min_graphql_links=options.min_graphql_links)
    print(json.dumps({"nodes": report["verification"]["total_nodes"],
                      "edges": report["verification"]["total_edges"],
                      "services": report["verification"]["total_repositories"],
                      "confirmed_http": report["relations"].get("HTTP_CALLS", 0),
                      "possible_http": report["unresolved_http_candidates"],
                      "confirmed_event_delivery_paths": report["source_evidenced_event_delivery_paths"],
                      "graphql_contract_fields": report["graphql_contract_fields"],
                      "graphql_operations": report["graphql_operations"],
                      "graphql_contract_consumes": report["graphql_contract_consumes"],
                      "source_request_outcomes": {
                          repo: values["counts"]
                          for repo, values in report["http_resolution_diagnostics"].items()
                      },
                      "source_complete": report["verification"]["source_coverage_complete"],
                      "gate": report["gate"]}, indent=2))
    if not report["gate"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
