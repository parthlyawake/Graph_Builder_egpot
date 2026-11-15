"""Typed request/response schema nodes for OpenAPI contract graphs."""
from __future__ import annotations

import hashlib
import json


def emit_openapi_schema_edges(graph, endpoint_id, operation):
    """Attach schema contracts to an endpoint without duplicating edges."""
    inserted = 0
    for media, schema in sorted(operation.request_schema.items()):
        parts = ("request", media)
        inserted += _add_schema(graph, endpoint_id, parts, schema, "ACCEPTS_SCHEMA")
    for status, media_types in sorted(operation.response_schemas.items()):
        for media, schema in sorted(media_types.items()):
            parts = ("response", str(status), media)
            inserted += _add_schema(graph, endpoint_id, parts, schema, "RETURNS_SCHEMA")
    return inserted


def _add_schema(graph, endpoint_id, parts, schema, relation):
    if not isinstance(schema, dict):
        return 0
    identity = json.dumps((endpoint_id, parts), separators=(",", ":"))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    node_id = f"openapi_schema::{digest}"
    if node_id not in graph:
        graph.add_node(
            node_id, id=node_id, type="schema_contract", layer="Lcontract",
            name=" ".join(parts), kind=parts[0], media_type=parts[-1],
            schema=schema, endpoint=endpoint_id)
    key = f"schema::{endpoint_id}::{node_id}"
    if graph.has_edge(endpoint_id, node_id, key=key):
        return 0
    graph.add_edge(
        endpoint_id, node_id, key=key,
        relation=relation, layer="Lcontract",
        source_evidence="OpenAPI document")
    return 1
