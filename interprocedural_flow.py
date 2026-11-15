"""Source-evidenced interprocedural call, argument and return value flow.

For each concrete callsite we link argument expression/variable sources to
declared callee parameters and callee return nodes to assigned destinations.
Ambiguous dispatch receives possible=True, never an exact flow assertion.
No control-dependence or heap alias analysis is claimed.
"""
from __future__ import annotations

import ast

from static_dispatch import select_overloads


def connect_interprocedural_flow(builder):
    graph = builder.graph
    graph.remove_edges_from([
        (u, v, key)
        for u, v, key, d in graph.edges(keys=True, data=True)
        if d.get("flow_kind") == "interprocedural"
    ])
    graph.remove_nodes_from([
        n for n, d in graph.nodes(data=True)
        if d.get("type") in {"callsite", "argument_expression"} and
        d.get("flow_kind") == "interprocedural"
    ])
    returns_by_owner = {}
    for node_id, data in graph.nodes(data=True):
        if data.get("type") == "return" and ".return::" in str(node_id):
            owner = str(node_id).split(".return::", 1)[0]
            returns_by_owner.setdefault(owner, []).append(node_id)

    resolved = 0
    for entry in getattr(builder, "callsite_evidence", ()):
        caller = entry.get("caller")
        callee = entry.get("callee", "")
        source = entry.get("file", "")
        if caller not in graph:
            continue
        name = callee.rsplit(".", 1)[-1]
        targets = set()
        for _, target, edge in graph.out_edges(caller, data=True):
            if edge.get("relation") not in {"CALLS", "POLYMORPHIC_CALL"}:
                continue
            if (edge.get("callsite_spelling") != callee or
                    edge.get("callsite_file") != source):
                continue
            data = graph.nodes.get(target, {})
            if data.get("type") != "function" or data.get("name") != name:
                continue
            targets.add(target)
        selected = select_overloads(
            builder, caller, callee, source, records=[entry])
        if selected is not None:
            targets.intersection_update(selected)
        elif callee.startswith(("self.", "this.")):
            owner = caller.rsplit(".", 1)[0]
            found = builder._find_method(owner, name)
            targets.intersection_update({found} if found else set())
        else:
            # Do not use a globally-unique same-name guess to create a value
            # dependency. Use the caller file or an explicit import mapping.
            aliases = builder.imports_by_file.get(source, {})
            base = callee.split(".", 1)[0]
            imported = aliases.get(base, "")
            if imported:
                prefix = imported.rpartition(".")[0] if "." in imported else imported
                imported_file = (builder.module_to_file.get(prefix) or
                                 builder.module_to_file.get(imported) or "")
            else:
                imported_file = ""
            allowed_files = {source}
            if imported_file:
                allowed_files.add(imported_file)
            targets = {
                target for target in targets
                if builder.graph.nodes[target].get("file", "").removeprefix(
                    builder.repo_prefix) in allowed_files
            }
        if not targets:
            continue

        # A callsite ID includes a source location, so multiple calls in one
        # function are not collapsed into the same argument-flow path.
        line, column = int(entry.get("line", 0)), int(entry.get("column", 0))
        node_id = f"callsite::{caller}:{line}:{column}"
        graph.add_node(
            node_id, id=node_id, type="callsite", layer="Lflow", name=callee,
            file=source, line_no=line, caller=caller, flow_kind="interprocedural"
        )
        if not graph.has_edge(caller, node_id, key=f"contains::{node_id}"):
            graph.add_edge(
                caller, node_id, key=f"contains::{node_id}",
                relation="CONTAINS", layer="Lsyn", flow_kind="interprocedural")
        arguments = tuple(entry.get("arguments", ()))
        keywords = tuple(entry.get("keywords", ()))
        # Dynamic **kwargs and *args cannot be mapped to a fixed formal
        # parameter without runtime information. Avoid claiming exact flow.
        dynamic_call = bool(entry.get("starred_arguments")) or any(
            name is None for name, _ in keywords
        )
        for target in sorted(targets):
            data = graph.nodes[target]
            param_names = tuple(data.get("param_names", ()))
            if not param_names:
                continue
            # Bound Python instance methods implicitly supply self/cls.
            offset = (1 if param_names[0] in {"self", "cls"} and "." in callee
                      else 0)
            if dynamic_call or len(arguments) > len(param_names) - offset:
                continue
            available = {name: idx for idx, name in enumerate(param_names)}
            bindings = [(i, i + offset, value) for i, value in enumerate(arguments)]
            used = {idx + offset for idx in range(len(arguments))}
            invalid = False
            for name, value in keywords:
                formal = available.get(name)
                if formal is None or formal < offset or formal in used or (
                        name in data.get("posonly_params", ())):
                    invalid = True
                    break
                used.add(formal)
                bindings.append((len(bindings), formal, value))
            required = set(data.get("required_params", ()))
            if not required.issubset({param_names[i] for i in used} | (
                    {"self", "cls"} if offset else set())):
                invalid = True
            # Older language adapters do not carry default-parameter data.
            # Preserve strict argument-count handling for those adapters.
            if (not keywords and not data.get("required_params")
                    and len(param_names) - offset != len(arguments)):
                invalid = True
            if invalid:
                continue
            possible = len(targets) > 1
            graph.add_edge(
                node_id, target, key=f"invokes::{node_id}::{target}",
                relation="INVOKES", layer="Ldep", flow_kind="interprocedural",
                possible=possible, source_evidence=f"{source}:{line}")
            for index, formal_idx, value in bindings:
                param = f"{target}.var::{param_names[formal_idx]}"
                if param not in graph:
                    continue
                local_source = f"{caller}.var::{value}"
                if value.isidentifier() and local_source in graph:
                    argument_source = local_source
                else:
                    argument_source = f"argexpr::{node_id}:{index}"
                    graph.add_node(
                        argument_source, id=argument_source,
                        type="argument_expression", layer="Lflow", name=value[:160],
                        file=source, line_no=line, flow_kind="interprocedural")
                    graph.add_edge(
                        node_id, argument_source,
                        key=f"arg::{node_id}:{index}", relation="EVALUATES",
                        layer="Lflow", flow_kind="interprocedural")
                    # Record expression reads, not just the expression node.
                    # Complex aliasing and heap-state semantics are not inferred.
                    if source.endswith(".py"):
                        try:
                            expression = ast.parse(value, mode="eval")
                            names = sorted({n.id for n in ast.walk(expression)
                                            if isinstance(n, ast.Name) and
                                            isinstance(n.ctx, ast.Load)})
                        except SyntaxError:
                            names = []
                        for reference in names:
                            origin = f"{caller}.var::{reference}"
                            if origin in graph:
                                graph.add_edge(
                                    origin, argument_source,
                                    key=f"read::{node_id}:{index}:{reference}",
                                    relation="FLOWS_TO", layer="Lflow",
                                    source_evidence=f"{source}:{line}",
                                    flow_kind="interprocedural")
                graph.add_edge(
                    argument_source, param,
                    key=f"pass::{node_id}:{target}:{formal_idx}",
                    relation="FLOWS_TO", layer="Lflow",
                    argument_position=index,
                    parameter_name=param_names[formal_idx],
                    source_evidence=f"{source}:{line}",
                    possible=possible, flow_kind="interprocedural")
                resolved += 1
            # Return edges are emitted only when the source syntax names
            # a destination variable or a containing return statement.
            results = tuple(entry.get("result_nodes", ()))
            for result_node in results:
                if result_node not in graph:
                    continue
                for return_node in returns_by_owner.get(target, ()):
                    graph.add_edge(
                        return_node, result_node,
                        key=f"result::{node_id}:{return_node}:{result_node}",
                        relation="FLOWS_TO", layer="Lflow",
                        possible=possible, source_evidence=f"{source}:{line}",
                        flow_kind="interprocedural")
                    resolved += 1
    return resolved
