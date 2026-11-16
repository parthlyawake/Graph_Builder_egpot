"""Source-file delta updater with explicit fallback for shared contract changes.

Changed supported sources are reparsed. Existing source facts and callsite
registries are preserved for unchanged files; derived edges are re-resolved.
A protocol/schema/config change requires a clean full build because canonical
contract identity may change throughout the workspace.
"""
from __future__ import annotations

import os
from pathlib import Path


def incremental_update(builder, changed_rel_paths, deleted_rel_paths=()):
    from language_adapters import adapter_for, spec_for

    changed = {str(path).replace("\\", "/").removeprefix("./") for path in changed_rel_paths}
    deleted = {str(path).replace("\\", "/").removeprefix("./") for path in deleted_rel_paths}
    affected = changed | deleted
    if not affected:
        return builder.graph
    if any(path.startswith("/") or ".." in Path(path).parts for path in affected):
        raise ValueError("Update paths must be relative to the repository")
    if not getattr(builder, "_built_once", False):
        return builder.build()
    config_files = {"tsconfig.json", "package.json", ".ckgignore"}
    # Schema, IDL, manifest and configuration edits change canonical global
    # identities. They MUST trigger full source+contract reindexing instead of
    # silently preserving stale declarations from old schema files.
    global_contract_extensions = (
        ".proto", ".graphql", ".gql", ".thrift", ".pdl", ".avsc",
        ".yaml", ".yml", ".json",
    )
    if any(path.lower().endswith(global_contract_extensions) or
           os.path.basename(path).lower() in config_files for path in affected):
        return builder.build()

    # Do not lose persisted callsites or contracts in untouched source files.
    registries = (
        ("calls_to_resolve", 3), ("http_calls_to_resolve", 3),
        ("dynamic_http_calls", 3), ("grpc_calls_to_resolve", 3),
        ("pending_attr_calls", 3), ("recorded_attr_calls", 3),
        ("class_base_records", 2), ("interface_implementation_records", 2),
        ("interface_extension_records", 2), ("grpc_server_registrations", 2),
        ("grpc_servicer_records", 2), ("js_add_service_records", 2),
        ("managed_grpc_registrations", 2),
    )
    for attribute, file_index in registries:
        records = getattr(builder, attribute, None)
        if isinstance(records, list):
            setattr(builder, attribute, [r for r in records
                    if len(r) <= file_index or r[file_index] not in affected])

    builder.callsite_evidence = [
        item for item in builder.callsite_evidence
        if item.get("file") not in affected
    ]
    builder._assigned_call_results.clear()
    builder._returning_calls.clear()

    if hasattr(builder, "recorded_attr_calls"):
        builder.pending_attr_calls = list(dict.fromkeys(
            [*builder.pending_attr_calls, *builder.recorded_attr_calls]
        ))
    if hasattr(builder, "unresolved_contract_calls"):
        builder.unresolved_contract_calls = []

    prefix = builder.repo_prefix
    def file_owned(nid, data):
        source = str(data.get("file") or "")
        if prefix and source.startswith(prefix):
            source = source[len(prefix):]
        if source in affected and not str(nid).startswith(
                ("module::", "symbol::", "external::")):
            return True
        return any(nid == f"file::{prefix}{rel}" or
                   str(nid).startswith(f"{prefix}{rel}:") for rel in affected)

    removal = [n for n, d in builder.graph.nodes(data=True) if file_owned(n, d)]
    for node in removal:
        builder.graph.remove_node(node)
    for rel in affected:
        for attribute in ("raw_file_lines", "imports_by_file", "file_symbols",
                          "grpc_client_vars", "go_type_vars"):
            collection = getattr(builder, attribute, None)
            if isinstance(collection, dict):
                collection.pop(rel, None)
    for attribute in ("var_defs", "var_types", "go_struct_fields",
                      "code_snippets", "docstrings", "type_signatures"):
        collection = getattr(builder, attribute, None)
        if isinstance(collection, dict):
            for node in removal:
                collection.pop(node, None)

    for key, handlers in list(builder.http_endpoints.items()):
        remaining = [node for node in handlers if node in builder.graph]
        if remaining:
            builder.http_endpoints[key] = remaining
        else:
            del builder.http_endpoints[key]

    derived = {"CALLS", "POLYMORPHIC_CALL", "EXTENDS", "IMPLEMENTS",
               "INVOKES", "EVALUATES",
               "CONSUMES", "PRODUCES", "HTTP_CALLS", "SEMANTIC_SIMILAR",
               "HTTP_REQUEST", "POSSIBLE_HTTP_TARGET"}
    builder.graph.remove_edges_from([
        (u, v, k) for u, v, k, data in builder.graph.edges(keys=True, data=True)
        if data.get("relation") in derived
    ])
    builder.graph.remove_nodes_from([
        n for n, data in builder.graph.nodes(data=True)
        if data.get("type") in {"http_endpoint", "http_callsite",
                                "callsite", "argument_expression"} or
           str(n).startswith(("http::", "httpcall::"))
    ])
    builder.http_contract_ids = {}
    builder.class_bases = {}
    builder.class_subclasses = {}

    for rel in sorted(changed):
        full_path = os.path.join(builder.repo_path, rel)
        if (os.path.isfile(full_path) and spec_for(rel)
                and not builder._is_ignored(rel)):
            adapter_for(rel).extract(builder, rel, full_path)

    # Recreate symbols from surviving source declarations only.
    builder.symbols_by_name = {}
    for node_id, data in builder.graph.nodes(data=True):
        if data.get("type") in {"function", "class", "interface", "struct", "type", "method"}:
            name = data.get("name")
            if name:
                builder.symbols_by_name.setdefault(name, []).append(node_id)

    builder.module_to_file = {}
    for rel in sorted(builder.raw_file_lines):
        name = builder._module_name_for_file(rel)
        if name:
            builder.module_to_file[name] = rel
        basename = os.path.splitext(os.path.basename(rel))[0]
        if basename and basename not in builder.module_to_file:
            builder.module_to_file[basename] = rel
    builder._load_module_configuration()
    builder.total_loc = sum(len(lines) for lines in builder.raw_file_lines.values())

    builder._resolve_inheritance()
    builder._resolve_interface_contracts()
    from compiler_resolution import configure_compiler_provider
    configure_compiler_provider(builder)
    builder._resolve_dependency_layer()
    from interprocedural_flow import connect_interprocedural_flow
    connect_interprocedural_flow(builder)
    builder._build_http_contracts()
    builder._build_dynamic_http_calls()
    builder._resolve_http_calls()
    builder._resolve_contract_layer()
    builder._build_semantic_layer()
    if builder.repo_id is None:
        from standalone_contract_specs import index_standalone_specs
        builder.contract_spec_counts = index_standalone_specs(builder)

    builder.graph.remove_nodes_from([
        n for n, data in builder.graph.nodes(data=True)
        if data.get("type") in {"external_func", "symbol_ref", "module"}
        and builder.graph.degree(n) == 0
    ])
    builder._print_layer_statistics()
    return builder.graph
