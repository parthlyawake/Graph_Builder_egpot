"""GraphQL AST selection binding for documents embedded in JavaScript/TypeScript.

Only literal templates parse; interpolated selections are not promoted to
confirmed contract edges. Contract field types come from parsed SDL.
"""
from __future__ import annotations

import re
from pathlib import Path


def _type_name(field_type):
    return re.sub(r"[\[\]!\s]", "", str(field_type or ""))


def bind_selections(graph, operation_id, source, external_fragments=None):
    try:
        from graphql import parse
        definitions = parse(source).definitions
    except Exception:
        return 0
    operation = graph.nodes[operation_id]
    root_kind = operation.get("kind", "query")
    name = operation.get("name", "anonymous")
    found = [d for d in definitions if d.kind == "operation_definition" and
             d.operation.value == root_kind and
             (d.name.value if d.name else "anonymous") == name]
    if len(found) != 1:
        return 0
    fragments = dict(external_fragments or {})
    fragments.update({d.name.value: d for d in definitions
                      if d.kind == "fragment_definition"})
    root = graph.graph.get("graphql_root_types", {}).get(
        root_kind, {"query": "Query", "mutation": "Mutation",
                    "subscription": "Subscription"}.get(root_kind))
    if not root:
        return 0
    count, visited = 0, set()

    def visit(type_name, selections, active):
        nonlocal count
        if not selections:
            return
        for item in selections.selections:
            if item.kind == "fragment_spread":
                frag = fragments.get(item.name.value)
                if frag and item.name.value not in active and (
                        frag.type_condition.name.value == type_name):
                    visit(type_name, frag.selection_set, active | {item.name.value})
            elif item.kind == "inline_fragment":
                type_condition = (item.type_condition.name.value
                                  if item.type_condition else type_name)
                if type_condition == type_name:
                    visit(type_name, item.selection_set, active)
            elif item.kind == "field":
                target = f"contract::graphql::{type_name}::{item.name.value}"
                if target not in graph:
                    continue
                pair = operation_id, target
                if pair not in visited:
                    visited.add(pair)
                    if not any(v == target and d.get("relation") == "CONSUMES"
                               for _, v, d in graph.out_edges(operation_id, data=True)):
                        graph.add_edge(operation_id, target,
                                       key=f"graphql_typed::{operation_id}::{target}",
                                       relation="CONSUMES", layer="Lcontract",
                                       binding_kind="typed_graphql_selection",
                                       source_evidence=operation.get("file"))
                        count += 1
                visit(_type_name(graph.nodes[target].get("return_type")),
                      item.selection_set, active)

    visit(root, found[0].selection_set, set())
    return count


def cross_document_fragments(root):
    """Return uniquely named GraphQL fragment ASTs over the source workspace."""
    try:
        from graphql import parse
    except ImportError:
        return {}
    root = Path(root)
    candidates = {}
    for file in sorted(root.rglob("*")):
        if not file.is_file() or file.suffix.lower() not in {".graphql", ".gql"}:
            continue
        if set(file.relative_to(root).parts) & {
                "node_modules", ".git", "vendor", "dist", "build", "target"}:
            continue
        if file.stat().st_size > 5_000_000:
            continue
        try:
            definitions = parse(file.read_text(
                encoding="utf8", errors="replace")).definitions
        except Exception:
            continue
        for fragment in definitions:
            if fragment.kind == "fragment_definition":
                candidates.setdefault(fragment.name.value, []).append(fragment)
    # Duplicate names can refer to distinct modules. Abstain rather than
    # silently choosing whichever file was traversed first.
    return {name: items[0] for name, items in candidates.items()
            if len(items) == 1}


def literal_templates(source):
    """Extract gql/ graphql tags while avoiding runtime substitutions."""
    for m in re.finditer(r"\b(?:gql|graphql)\s*(?:\(\s*)?" + chr(96), source):
        start, pos, escaped = m.end(), m.end(), False
        while pos < len(source):
            ch = source[pos]
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == chr(96):
                break
            pos += 1
        if pos >= len(source):
            continue
        snippet = source[start:pos]
        if chr(36) + "{" in snippet:
            continue
        yield snippet, source.count("\n", 0, m.start()) + 1


def link_embedded(workspace, root, external_fragments=None):
    try:
        from graphql import parse
    except ImportError:
        return {"documents": 0, "typed_edges": 0}
    from graphql_links import parse_graphql_operations
    root = Path(root)
    counter = {"documents": 0, "typed_edges": 0}
    for file in sorted(root.rglob("*")):
        if not file.is_file() or file.suffix.lower() not in {
                ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}:
            continue
        if set(file.relative_to(root).parts) & {
                "node_modules", "vendor", "dist", "build", ".git", "target"}:
            continue
        if file.stat().st_size > 2_000_000:
            continue
        text = file.read_text(encoding="utf8", errors="replace")
        if "gql" not in text and "graphql" not in text:
            continue
        rel = file.relative_to(root).as_posix()
        for document, line in literal_templates(text):
            try:
                if not any(x.kind == "operation_definition" for x in parse(document).definitions):
                    continue
            except Exception:
                continue
            for index, op in enumerate(parse_graphql_operations(document)):
                node = f"graphqlop::{rel}:{line}:{index}:{op.kind}:{op.name}"
                if node in workspace.graph:
                    continue
                workspace.graph.add_node(
                    node, id=node, type="graphql_operation", layer="Lcontract",
                    kind=op.kind, name=op.name, file=rel, line_no=line,
                    root_fields=list(op.fields),
                    embedded_language=file.suffix.lower()[1:])
                file_id = "file::" + rel
                if file_id not in workspace.graph:
                    workspace.graph.add_node(
                        file_id, id=file_id, type="file", layer="Lsyn",
                        name=file.name, file=rel, line_no=1)
                workspace.graph.add_edge(
                    file_id, node, key=f"graphql_embedded::{node}",
                    relation="CONTAINS", layer="Lsyn")
                counter["documents"] += 1
                counter["typed_edges"] += bind_selections(
                    workspace.graph, node, document, external_fragments)
    return counter
