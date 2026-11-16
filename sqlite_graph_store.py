"""Immutable, content-integrity-checked GRAFT-CKG graph snapshots in SQLite.

This is local durable snapshot storage, not a distributed property graph or
signed build provenance. Each version is immutable; one serialized writer may
advance the head using an expected-parent compare-and-swap.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any

import networkx as nx


SCHEMA_VERSION = 1


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)


def _dump(graph: nx.MultiDiGraph) -> str:
    if not isinstance(graph, nx.MultiDiGraph):
        raise TypeError("storage requires nx.MultiDiGraph")
    data = {
        "format": "graft-ckg-immutable-snapshot-v1",
        "graph_metadata": dict(graph.graph),
        "nodes": [
            {"id": n, "attrs": dict(d)}
            for n, d in sorted(graph.nodes(data=True), key=lambda x: str(x[0]))
        ],
        "edges": [
            {"source": u, "target": v, "key": k, "attrs": dict(d)}
            for u, v, k, d in sorted(
                graph.edges(keys=True, data=True),
                key=lambda e: (str(e[0]), str(e[1]), str(e[2])))
        ],
    }
    if any(not isinstance(x["id"], str) for x in data["nodes"]):
        raise ValueError("Graph snapshot IDs must be strings")
    return _canonical(data)


def _restore(content: str) -> nx.MultiDiGraph:
    data = json.loads(content)
    if not isinstance(data, dict) or data.get("format") != "graft-ckg-immutable-snapshot-v1":
        raise ValueError("Unsupported graph snapshot schema")
    if not isinstance(data.get("graph_metadata"), dict) or not isinstance(data.get("nodes"), list) or not isinstance(data.get("edges"), list):
        raise ValueError("Malformed graph snapshot")
    graph = nx.MultiDiGraph()
    graph.graph.update(data["graph_metadata"])
    for item in data["nodes"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("attrs"), dict):
            raise ValueError("Invalid node record")
        nid = item["id"]
        if nid in graph:
            raise ValueError("Duplicate node")
        graph.add_node(nid, **item["attrs"])
    for item in data["edges"]:
        if not isinstance(item, dict) or not isinstance(item.get("attrs"), dict):
            raise ValueError("Invalid edge record")
        u, v, key = item.get("source"), item.get("target"), item.get("key")
        if not isinstance(u, str) or not isinstance(v, str) or not isinstance(key, (str, int)):
            raise ValueError("Invalid edge identity")
        if u not in graph or v not in graph or graph.has_edge(u, v, key):
            raise ValueError("Dangling or duplicate graph edge")
        attrs = item["attrs"]
        if not attrs.get("relation") or not attrs.get("layer"):
            raise ValueError("Missing typed graph edge")
        graph.add_edge(u, v, key=key, **attrs)
    return graph


class SQLiteGraphStore:
    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS graph_snapshots(
                    revision TEXT PRIMARY KEY,
                    parent TEXT,
                    format_version INTEGER NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS graph_head(
                    slot INTEGER PRIMARY KEY CHECK(slot=1),
                    revision TEXT NOT NULL REFERENCES graph_snapshots(revision)
                );
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("PRAGMA busy_timeout = 30000")
        db.execute("PRAGMA foreign_keys = ON")
        return db

    def head(self) -> str | None:
        with self._connect() as db:
            row = db.execute("SELECT revision FROM graph_head WHERE slot=1").fetchone()
        return row[0] if row else None

    def save(self, revision: str, graph: nx.MultiDiGraph, *,
             parent: str | None = None) -> dict:
        """Commit graph atomically if parent is exactly the current head."""
        if not isinstance(revision, str) or not revision.strip():
            raise ValueError("revision must be a nonempty string")
        payload = _dump(graph)
        digest = sha256(payload.encode("utf-8")).hexdigest()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT revision FROM graph_head WHERE slot=1").fetchone()
            current = existing[0] if existing else None
            if parent != current:
                raise ValueError(f"revision conflict: expected parent={parent}, actual head={current}")
            if current == revision or db.execute("SELECT 1 FROM graph_snapshots WHERE revision=?", (revision,)).fetchone():
                raise ValueError("immutable revision already exists")
            db.execute("INSERT INTO graph_snapshots(revision,parent,format_version,content_sha256,payload) VALUES(?,?,?,?,?)",
                       (revision, parent, SCHEMA_VERSION, digest, payload))
            db.execute("INSERT INTO graph_head(slot, revision) VALUES(1,?) ON CONFLICT(slot) DO UPDATE SET revision=excluded.revision",
                       (revision,))
        return {"revision": revision, "parent": parent, "sha256": digest,
                "nodes": graph.number_of_nodes(), "edges": graph.number_of_edges(),
                "verification": "stored_content_sha256_only"}

    def load(self, revision: str | None = None) -> nx.MultiDiGraph:
        with self._connect() as db:
            if revision is None:
                head = db.execute("SELECT revision FROM graph_head WHERE slot=1").fetchone()
                if not head:
                    raise KeyError("empty graph store")
                revision = head[0]
            row = db.execute("SELECT format_version,content_sha256,payload FROM graph_snapshots WHERE revision=?",
                             (revision,)).fetchone()
        if not row:
            raise KeyError(f"unknown graph revision: {revision}")
        schema, digest, payload = row
        if schema != SCHEMA_VERSION:
            raise ValueError("Unsupported stored graph schema version")
        if sha256(payload.encode("utf-8")).hexdigest() != digest:
            raise ValueError("Stored graph digest mismatch")
        return _restore(payload)

    def lineage(self) -> list[dict[str, str | None]]:
        """Return newest-first durable snapshot chain, detecting cycles/gaps."""
        result, seen = [], set()
        current = self.head()
        with self._connect() as db:
            while current is not None:
                if current in seen:
                    raise ValueError("Snapshot ancestry cycle")
                seen.add(current)
                row = db.execute("SELECT parent,content_sha256 FROM graph_snapshots WHERE revision=?",
                                 (current,)).fetchone()
                if row is None:
                    raise ValueError("Snapshot parent is missing")
                result.append({"revision": current, "parent": row[0], "sha256": row[1]})
                current = row[0]
        return result
