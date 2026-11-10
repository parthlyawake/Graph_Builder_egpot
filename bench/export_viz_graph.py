"""Export deterministic script globals for a buildless, file-based graph explorer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from bench.egpot_eval import split_by_link
from eg_pot import GraphView

# Fixed Paul Tol qualitative colors, followed by complementary Tol bright colors.
PALETTE = ("#88CCEE", "#44AA99", "#117733", "#999933", "#DDCC77", "#CC6677",
           "#882255", "#AA4499", "#DDDDDD", "#4477AA", "#66CCEE", "#228833",
           "#CCBB44", "#EE6677", "#AA3377", "#BBBBBB")


def _line(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def graph_payload(graph):
    view = GraphView(graph)
    nodes = []
    for node, data in sorted(graph.nodes(data=True), key=lambda item: str(item[0])):
        nodes.append({"id": str(node), "type": str(data.get("type") or "unknown"),
                      "repo": str(data.get("repo") or "contracts"),
                      "name": str(data.get("name") or node), "file": str(data.get("file") or ""),
                      "line_no": _line(data.get("line_no")), "layer": str(data.get("layer") or ""),
                      "docstring": str(data.get("docstring") or "")[:200]})
    edges = []
    for u, v, key, data in sorted(graph.edges(keys=True, data=True),
                                  key=lambda item: (str(item[0]), str(item[1]), str(item[2]))):
        meta = view.edge_meta(u, v, key)
        edges.append({"source": str(u), "target": str(v), "key": str(key),
                      "relation": str(data.get("relation") or "LINK"),
                      "layer": str(data.get("layer") or ""),
                      "c_type": round(meta["c_type"], 6), "f_call": round(meta["f_call"], 6)})
    services = sorted({node["repo"] for node in nodes})
    return {"nodes": nodes, "edges": edges,
            "meta": {"repo": "online_boutique", "node_count": len(nodes), "edge_count": len(edges),
                     "services": [{"name": name, "color": PALETTE[i % len(PALETTE)]}
                                  for i, name in enumerate(services)],
                     "node_types": sorted({node["type"] for node in nodes}),
                     "relations": sorted({edge["relation"] for edge in edges})}}


def query_payload(rows):
    dev_ids = {row["id"] for row in split_by_link(rows)["dev"]}
    return [{"id": row["id"], "link_id": row["link_id"], "type": row["type"],
             "query": row["query"], "start_node": row["start_node"],
             "split": "dev" if row["id"] in dev_ids else "test"}
            for row in sorted(rows, key=lambda row: row["id"])]


def script_bytes(global_name, data):
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return f"window.{global_name} = {payload};\n".encode("utf-8")


def export(graph_path, queries_path, output_dir):
    graph = nx.read_graphml(graph_path, force_multigraph=True)
    with Path(queries_path).open(encoding="utf-8") as stream:
        rows = json.load(stream)
    files = {"graph.js": script_bytes("VIZ_GRAPH", graph_payload(graph)),
             "queries.js": script_bytes("VIZ_QUERIES", query_payload(rows))}
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (output / name).write_bytes(data)
        print(f"{output / name}: {len(data):,} bytes")
    return files


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, default=ROOT / "bench/results/online_boutique_graph_fresh.graphml")
    parser.add_argument("--queries", type=Path, default=ROOT / "bench/labels/online_boutique_egpot_queries.json")
    parser.add_argument("--output", type=Path, default=ROOT / "viz/data/online_boutique")
    args = parser.parse_args(argv)
    export(args.graph, args.queries, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
