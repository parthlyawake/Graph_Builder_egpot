"""Multi-repository incremental composition from cached per-repository source graphs.

Only the modified repository reparses files. Workspace-specific graph edges
are recomputed after composition to prevent dangling cross-service bindings.
This is not a zero-cost edge delta: graph composition scales with workspace size.
"""
from graph_builder_bindings import bind_managed_grpc


def update_workspace_files(workspace, repo_id, changed_rel_paths, deleted_rel_paths=()):
    if repo_id not in workspace.repo_builders:
        raise KeyError(f"Unknown or unbuilt repository: {repo_id}")
    if not (changed_rel_paths or deleted_rel_paths):
        return workspace.graph
    workspace.repo_builders[repo_id].update_files(changed_rel_paths, deleted_rel_paths)
    return recompose_workspace(workspace)


def recompose_workspace(workspace):
    """Compose cached per-repo graphs and rebuild workspace-only indexes."""
    workspace.graph.clear()
    workspace.canonical_contracts.clear()
    workspace.contract_skews.clear()
    workspace.http_endpoints.clear()
    workspace.symbols_by_name.clear()
    workspace.docstrings.clear()
    workspace.raw_file_lines.clear()
    workspace.total_loc = 0
    workspace.edge_counter = 0
    workspace.vectorizer = None
    workspace.tfidf_matrix = None
    workspace.bm25_index = None
    workspace.indexed_node_ids = []

    for rid, builder in workspace.repo_builders.items():
        workspace.total_loc += builder.total_loc
        for rel, lines in builder.raw_file_lines.items():
            workspace.raw_file_lines[f"{rid}/{rel}"] = lines
        for name, ids in builder.symbols_by_name.items():
            workspace.symbols_by_name.setdefault(name, []).extend(ids)
        workspace.docstrings.update(builder.docstrings)
        for key, handlers in builder.http_endpoints.items():
            workspace.http_endpoints.setdefault(key, []).extend(handlers)

    workspace._index_shared_contracts()
    for rid, builder in workspace.repo_builders.items():
        for nid, data in builder.graph.nodes(data=True):
            if nid not in workspace.graph:
                workspace.graph.add_node(nid, **data)
            elif "definitions" in data:
                workspace.graph.nodes[nid].setdefault("definitions", []).extend(data["definitions"])
        for u, v, key, data in builder.graph.edges(keys=True, data=True):
            workspace.graph.add_edge(u, v, key=f"w_{rid}_{key}", **data)

    workspace._unify_contract_layer()
    workspace._resolve_cross_repo_grpc_producers()
    for builder in workspace.repo_builders.values():
        bind_managed_grpc(builder, workspace.graph, workspace.canonical_contracts)
    workspace._resolve_cross_repo_http_calls()
    workspace._resolve_cross_repo_grpc_calls()
    workspace._resolve_cross_repo_proto_types()
    workspace._resolve_inter_service_dataflow()
    workspace._index_openapi_and_graphql()
    workspace._resolve_graphql_java_bindings()
    workspace._index_graphql_operations()
    workspace._build_semantic_layer()
    return workspace.graph
