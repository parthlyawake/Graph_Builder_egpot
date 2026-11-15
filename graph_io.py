"""Stable loader for exported GRAFT-CKG workspace graphs.

Preserves typed multiedges, evidence attributes and graph metadata.
Rejects incomplete/malformed artifacts rather than implicitly creating
dangling endpoint nodes.
"""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx


def load_graph_json(path):
    """Load v1 or v2 JSON export into a directed multigraph."""
    raw = json.loads(Path(path).read_text(encoding="utf8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("nodes"), list) or not isinstance(raw.get("edges"), list):
        raise ValueError("Graph JSON must contain 'nodes' and 'edges' arrays")
    graph = nx.MultiDiGraph()
    meta = raw.get("graph_metadata", {})
    if not isinstance(meta, dict):
        raise ValueError("graph_metadata must be an object")
    graph.graph.update(meta)
    for item in raw["nodes"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("node must have a string id")
        node_id = item["id"]
        if node_id in graph:
            raise ValueError(f"duplicate node id: {node_id}")
        graph.add_node(node_id, **{k: v for k, v in item.items() if k != "id"})
    for item in raw["edges"]:
        if not isinstance(item, dict):
            raise ValueError("edge must be an object")
        src, dst, key = (item.get(k) for k in ("source", "target", "key"))
        if not all(isinstance(v, str) for v in (src, dst)):
            raise ValueError("edge endpoints must be strings")
        if src not in graph or dst not in graph:
            raise ValueError(f"dangling edge: {src} -> {dst}")
        if not isinstance(key, (str, int)):
            raise ValueError("edge requires a key")
        if graph.has_edge(src, dst, key=key):
            raise ValueError(f"duplicate multiedge: {src} -> {dst}: {key}")
        attrs = {k: v for k, v in item.items()
                 if k not in {"source", "target", "key"}}
        if not attrs.get("relation") or not attrs.get("layer"):
            raise ValueError("edge is missing relation/layer")
        graph.add_edge(src, dst, key=key, **attrs)
    return graph
