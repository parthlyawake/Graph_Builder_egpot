"""CLI: enrich a Graph_Builder JSON export with a versioned operational manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from graph_io import load_graph_json
from operational_evidence import ingest_operational_evidence


def export_graph(graph):
    nodes = [{"id": str(n), **data} for n, data in sorted(graph.nodes(data=True), key=lambda row: str(row[0]))]
    edges = [{"source": str(u), "target": str(v), "key": k, **data}
             for u, v, k, data in sorted(graph.edges(keys=True, data=True), key=lambda row: (str(row[0]), str(row[1]), str(row[2])))]
    return {"format_version": "1.1", "graph_metadata": dict(graph.graph), "nodes": nodes, "edges": edges}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graph", required=True, help="existing valid Graph_Builder export")
    ap.add_argument("--manifest", required=True, help="operational manifest schema_version=1")
    ap.add_argument("--output", required=True, help="output enriched graph JSON")
    ap.add_argument("--report", help="optional ingestion report path")
    args = ap.parse_args(argv)
    graph = load_graph_json(args.graph)
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    enriched, report = ingest_operational_evidence(graph, manifest)
    payload = export_graph(enriched)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.report:
        path = Path(args.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
