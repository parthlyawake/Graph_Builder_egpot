"""Evidence-based managed gRPC producer binding.

Ported from the review implementation with explicit registration requirements,
qualified-class disambiguation, and idempotence. Does not infer handlers from
method names alone. Shared by single- and multi-repository builders.
"""
from __future__ import annotations


def bind_managed_grpc(builder, graph, contracts):
    count = 0
    for language, spelling, file, scope_id in sorted(set(builder.managed_grpc_registrations)):
        candidates = []
        for node, data in builder.graph.nodes(data=True):
            if data.get("type") != "class" or data.get("grpc_language") != language:
                continue
            short = node.rsplit(":", 1)[-1]
            qualified = data.get("grpc_qualified_name", "")
            if ("." in spelling and qualified == spelling) or (
                "." not in spelling and (short == spelling or short.endswith("." + spelling))
            ):
                candidates.append(node)
        local_prefix = f"{builder.repo_prefix}{file}:"
        lexical = scope_id.split(":", 1)[-1].split(".") if ":" in scope_id else []
        chosen = None
        if "." not in spelling:
            for depth in range(len(lexical), -1, -1):
                direct = local_prefix + ".".join([*lexical[:depth], spelling])
                if direct in candidates:
                    chosen = direct
                    break
        if chosen is None:
            same_file = [node for node in candidates if node.startswith(local_prefix)]
            options = same_file if same_file else candidates
            if len(options) == 1:
                chosen = options[0]
        if chosen is None or chosen not in graph:
            continue
        service_name = builder.graph.nodes[chosen].get("grpc_service")
        contract = contracts.get(service_name)
        if not contract or contract.get("node_id") not in graph:
            continue

        def bind(source, target):
            nonlocal count
            if source not in graph or target not in graph:
                return
            if any(data.get("relation") == "IMPLEMENTS"
                   for data in graph.get_edge_data(source, target, default={}).values()):
                return
            evidence_context = f"{builder.repo_prefix}{file}"
            metadata = {"d_scope": 0, "f_call": 1.0, "c_type": 1.0,
                        "id_ctx": evidence_context}
            graph.add_edge(
                source, target, key=f"w_managed_impl_{source}_{target}",
                relation="IMPLEMENTS", layer="Lcontract",
                metadata=metadata, **metadata,
                binding_evidence="explicit_server_registration",
                registration_file=file, registration_language=language,
            )
            count += 1

        bind(chosen, contract["node_id"])
        for rpc, rpc_id in sorted(contract.get("rpcs", {}).items()):
            method = rpc if language == "csharp" else rpc[:1].lower() + rpc[1:]
            node = f"{chosen}.{method}"
            data = builder.graph.nodes.get(node, {})
            if data.get("type") == "function" and (
                (language == "java" and not data.get("http_ambiguous_definition")) or
                (language == "csharp" and data.get("is_override"))
            ):
                bind(node, rpc_id)
    return count
