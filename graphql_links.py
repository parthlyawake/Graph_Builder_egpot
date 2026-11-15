"""GraphQL operation-document nodes and conservative schema field edges.

Operations are linked to an indexed schema field only when the GraphQL root
kind and field name match. These edges do NOT claim a resolved runtime Java
resolver or prove execution of the GraphQL operation.
"""
from __future__ import annotations

import re
from pathlib import Path
from dataclasses import dataclass


@dataclass(frozen=True)
class GraphQLOperation:
    kind: str
    name: str
    fields: tuple[str, ...]


def _remove_comments(text):
    out, i, quoted, escaped = [], 0, False, False
    while i < len(text):
        ch = text[i]
        if quoted:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                quoted = False
        elif ch == '"':
            quoted = True
            out.append(ch)
        elif ch == "#":
            while i < len(text) and text[i] != "\n":
                i += 1
            if i < len(text):
                out.append("\n")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _balanced_end(text, start, left="{", right="}"):
    if start >= len(text) or text[start] != left:
        return -1
    depth, quoted, escaped = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if quoted:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                quoted = False
            continue
        if ch == '"':
            quoted = True
        elif ch == left:
            depth += 1
        elif ch == right:
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


def _root_fields(selection):
    fields, depth, i = [], 1, 1
    while i < len(selection) - 1:
        ch = selection[i]
        if ch == '"':
            k, escaped = i + 1, False
            while k < len(selection):
                v = selection[k]
                if escaped:
                    escaped = False
                elif v == "\\":
                    escaped = True
                elif v == '"':
                    break
                k += 1
            i = k + 1
            continue
        if ch == "{":
            depth += 1
            i += 1
            continue
        if ch == "}":
            depth -= 1
            i += 1
            continue
        if depth != 1 or ch.isspace() or ch == ",":
            i += 1
            continue
        if selection.startswith("...", i):
            # Fragment spread/inline fragments require expansion, not guessing.
            i += 3
            while i < len(selection) and selection[i] not in "\n{":
                i += 1
            continue
        match = re.match(r"[A-Za-z_]\w*", selection[i:])
        if not match:
            i += 1
            continue
        field = match.group(0)
        i += len(field)
        while i < len(selection) and selection[i].isspace():
            i += 1
        if i < len(selection) and selection[i] == ":":
            i += 1
            while i < len(selection) and selection[i].isspace():
                i += 1
            actual = re.match(r"[A-Za-z_]\w*", selection[i:])
            if not actual:
                continue
            field = actual.group(0)
            i += len(field)
        fields.append(field)
        while i < len(selection) and selection[i].isspace():
            i += 1
        if i < len(selection) and selection[i] == "(":
            end = _balanced_end(selection, i, "(", ")")
            if end < 0:
                break
            i = end
        while True:
            while i < len(selection) and selection[i].isspace():
                i += 1
            if i >= len(selection) or selection[i] != "@":
                break
            i += 1
            directive = re.match(r"[A-Za-z_]\w*", selection[i:])
            if directive:
                i += len(directive.group(0))
            while i < len(selection) and selection[i].isspace():
                i += 1
            if i < len(selection) and selection[i] == "(":
                end = _balanced_end(selection, i, "(", ")")
                if end < 0:
                    break
                i = end
    return tuple(dict.fromkeys(fields))


def parse_graphql_operations(text):
    from graphql_ast_support import parse_operations_ast
    parsed = parse_operations_ast(text)
    if parsed is not None:
        return [GraphQLOperation(*item) for item in parsed]
    """Parse operation root selections without misreading SDL schema fields."""
    data = _remove_comments(text)
    top_level = [False] * len(data)
    curly = square = paren = 0
    quoted = escaped = False
    for index, ch in enumerate(data):
        top_level[index] = not quoted and curly == square == paren == 0
        if quoted:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                quoted = False
            continue
        if ch == '"':
            quoted = True
        elif ch == "{":
            curly += 1
        elif ch == "}":
            curly = max(0, curly - 1)
        elif ch == "[":
            square += 1
        elif ch == "]":
            square = max(0, square - 1)
        elif ch == "(":
            paren += 1
        elif ch == ")":
            paren = max(0, paren - 1)

    operations = []
    pattern = re.compile(r"\b(query|mutation|subscription)\b(?:\s+([A-Za-z_]\w*))?")
    for match in pattern.finditer(data):
        if not top_level[match.start()]:
            continue
        brace = next((i for i in range(match.end(), len(data))
                      if data[i] == "{" and top_level[i]), -1)
        if brace < 0:
            continue
        header = data[match.end():brace]
        if ":" in header.split("(", 1)[0]:
            continue
        end = _balanced_end(data, brace)
        if end < 0:
            continue
        operations.append(GraphQLOperation(
            match.group(1),
            match.group(2) or f"anonymous_{len(operations)+1}",
            _root_fields(data[brace:end]),
        ))
    if not operations and data.lstrip().startswith("{"):
        start = len(data) - len(data.lstrip())
        end = _balanced_end(data, start)
        if end > start:
            operations.append(GraphQLOperation(
                "query", "anonymous", _root_fields(data[start:end])))
    return operations

def link_graphql_operations(workspace, base_dir):
    root = Path(base_dir)
    if not root.is_dir():
        return 0
    linked = 0
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in {".graphql", ".gql"} or not path.is_file():
            continue
        if set(path.relative_to(root).parts) & {
                "node_modules", ".git", "vendor", "dist", "build"}:
            continue
        rel = path.relative_to(root).as_posix()
        operations = parse_graphql_operations(
            path.read_text(encoding="utf-8", errors="replace"))
        if not operations:
            continue
        file_id = f"file::{rel}"
        if not workspace.graph.has_node(file_id):
            workspace.graph.add_node(
                file_id, id=file_id, type="file", layer="Lsyn",
                name=path.name, file=rel, line_no=1)
        for operation in operations:
            operation_id = f"graphqlop::{rel}:{operation.kind}:{operation.name}"
            workspace.graph.add_node(
                operation_id, id=operation_id, type="graphql_operation",
                layer="Lcontract", name=operation.name, kind=operation.kind,
                root_fields=list(operation.fields), file=rel)
            workspace.graph.add_edge(
                file_id, operation_id, key=f"graphql_contains::{operation_id}",
                relation="CONTAINS", layer="Lsyn")
            root_type = workspace.graph.graph.get("graphql_root_types", {}).get(
                operation.kind, {
                    "query": "Query", "mutation": "Mutation",
                    "subscription": "Subscription",
                }[operation.kind]
            )
            for field in operation.fields:
                target = f"contract::graphql::{root_type}::{field}"
                if workspace.graph.has_node(target):
                    workspace.graph.add_edge(
                        operation_id, target,
                        key=f"graphql_uses::{operation_id}:{field}",
                        relation="CONSUMES", layer="Lcontract",
                        source_evidence=rel)
                    linked += 1
    # Follow typed nested selections and literal JS/TS tagged GraphQL documents.
    from graphql_embedded import (
        bind_selections, cross_document_fragments, link_embedded)
    fragment_registry = cross_document_fragments(root)
    for file in sorted(root.rglob("*")):
        if file.suffix.lower() not in {".graphql", ".gql"} or not file.is_file():
            continue
        if set(file.relative_to(root).parts) & {
                "node_modules", ".git", "vendor", "dist", "build"}:
            continue
        rel = file.relative_to(root).as_posix()
        document = file.read_text(encoding="utf8", errors="replace")
        for op in parse_graphql_operations(document):
            node = f"graphqlop::{rel}:{op.kind}:{op.name}"
            if node in workspace.graph:
                linked += bind_selections(
                    workspace.graph, node, document, fragment_registry)
    workspace.graph.graph["graphql_embedded"] = link_embedded(
        workspace, root, fragment_registry)
    return linked + workspace.graph.graph["graphql_embedded"]["typed_edges"]
