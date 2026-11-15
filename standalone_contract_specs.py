"""OpenAPI and GraphQL contract indexing for the standalone CKGBuilder.

WorkspaceCKGBuilder already has its own contract indexing. To avoid duplicate
workspace contracts, this helper is called only when builder.repo_id is None.
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace


_OPENAPI_NAMES = {
    "openapi.yaml", "openapi.yml", "openapi.json",
    "swagger.yaml", "swagger.yml", "swagger.json",
}


def index_standalone_specs(builder):
    from openapi_graphql_parser import OpenAPIContractParser, GraphQLContractParser
    from graphql_links import link_graphql_operations
    from graphql_java_bindings import bind_java_graphql_datafetchers

    root = Path(builder.repo_path)
    graph = builder.graph
    previous_file = builder.current_file
    counts = {"graphql_types": 0, "graphql_fields": 0, "openapi_operations": 0}
    try:
        for parent, directories, files in os.walk(root):
            directories[:] = sorted(
                dirname for dirname in directories
                if not builder._is_ignored(
                    (Path(parent) / dirname).relative_to(root).as_posix())
            )
            for name in sorted(files):
                path = Path(parent) / name
                rel = path.relative_to(root).as_posix()
                if builder._is_ignored(rel):
                    continue
                lower = name.lower()
                graphql = lower.endswith((".graphql", ".gql"))
                openapi = lower in _OPENAPI_NAMES or (
                    lower.endswith((".yaml", ".yml", ".json")) and
                    "openapi" in lower)
                if not graphql and not openapi:
                    continue

                builder.current_file = rel
                file_id = f"file::{builder.repo_prefix}{rel}"
                if file_id not in graph:
                    builder.add_ckg_node(file_id, "file", "Lsyn", name, 1)

                if graphql:
                    with path.open("r", encoding="utf-8", errors="replace") as handle:
                        spec = GraphQLContractParser.parse_text(handle.read())
                    if spec.invalid:
                        continue
                    if spec.root_types:
                        graph.graph.setdefault("graphql_root_types", {}).update(spec.root_types)
                    for type_name, entity in spec.types.items():
                        counts["graphql_types"] += 1
                        for field_name, field in entity.fields.items():
                            field_id = f"contract::graphql::{type_name}::{field_name}"
                            if field_id not in graph:
                                builder.add_ckg_node(
                                    field_id, "contract", "Lcontract",
                                    f"{type_name}.{field_name}", 1)
                                graph.nodes[field_id]["kind"] = entity.kind
                                graph.nodes[field_id]["field"] = field_name
                                graph.nodes[field_id]["return_type"] = field.type_name
                                graph.nodes[field_id]["spec"] = "graphql"
                                counts["graphql_fields"] += 1
                            if not any(v == field_id and d.get("relation") == "CONTAINS"
                                       for _, v, d in graph.out_edges(file_id, data=True)):
                                builder.add_ckg_edge(file_id, field_id, "CONTAINS", "Lsyn")
                elif openapi:
                    spec = OpenAPIContractParser.parse_file(str(path))
                    if not spec:
                        continue
                    for operation in spec.operations:
                        endpoint = f"endpoint::{operation.method}::{operation.path}"
                        if endpoint not in graph:
                            builder.add_ckg_node(
                                endpoint, "endpoint", "Lcontract",
                                f"{operation.method} {operation.path}", 1)
                            graph.nodes[endpoint]["path"] = operation.path
                            graph.nodes[endpoint]["method"] = operation.method
                            graph.nodes[endpoint]["operation_id"] = operation.operation_id
                            graph.nodes[endpoint]["spec"] = "openapi"
                            counts["openapi_operations"] += 1
                        from contract_schema_graph import emit_openapi_schema_edges
                        emit_openapi_schema_edges(graph, endpoint, operation)
                        if not any(v == endpoint and d.get("relation") == "CONTAINS"
                                   for _, v, d in graph.out_edges(file_id, data=True)):
                            builder.add_ckg_edge(file_id, endpoint, "CONTAINS", "Lsyn")
                        handlers = dict.fromkeys([
                            *builder.http_endpoints.get(
                                (operation.method, operation.path), ()),
                            *builder.http_endpoints.get(
                                ("*", operation.path), ()),
                        ])
                        for handler in handlers:
                            if handler in graph and not any(
                                    v == endpoint and d.get("relation") == "IMPLEMENTS"
                                    for _, v, d in graph.out_edges(handler, data=True)):
                                builder.add_ckg_edge(
                                    handler, endpoint, "IMPLEMENTS", "Lcontract")
    finally:
        builder.current_file = previous_file

    # Consumer edges require exact schema root type and selected field names.
    proxy = SimpleNamespace(graph=graph, repo_builders={"single": builder},
                            symbols_by_name=builder.symbols_by_name)
    counts["graphql_consumes"] = link_graphql_operations(proxy, root)
    counts["graphql_java_bindings"] = bind_java_graphql_datafetchers(proxy)
    return counts
