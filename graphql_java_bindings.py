"""Conservative Java GraphQL DataFetcher-to-schema contract bindings.

Recognizes explicit RuntimeWiring .type("Type", lambda...) blocks and
.dataFetcher("field", new ResolverClass(...)) constructions. Unresolved or
ambiguous names are omitted, never guessed from filename similarities.
"""
from __future__ import annotations

import re


_TYPE_CALL = re.compile(
    r'\.\s*type\s*\(\s*(?:"([^"]+)"|([A-Z_][A-Z0-9_]*))\s*,'
)
_FETCHER = re.compile(
    r'\.\s*dataFetcher\s*\(\s*"([^"]+)"\s*,\s*'
    r'new\s+(?:[A-Za-z_$]\w*\.)*([A-Za-z_$]\w*)'
    r'(?:\s*<[^>]*>)?\s*\(',
    re.DOTALL,
)
_CONSTANT = re.compile(
    r'\b([A-Z_][A-Z0-9_]*)\s*=\s*"([^"]+)"'
)


def _matching_parenthesis(text, opening):
    """Return the close-parenthesis index after an opening '(' in Java."""
    if opening < 0 or opening >= len(text) or text[opening] != "(":
        return -1
    depth, quoted, escaped = 0, False, False
    i = opening
    while i < len(text):
        c = text[i]
        if quoted:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                quoted = False
        elif text.startswith("//", i):
            end = text.find("\n", i)
            i = len(text) if end < 0 else end
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = len(text) if end < 0 else end + 2
            continue
        elif c == '"':
            quoted = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def explicit_datafetchers(source):
    """Yield (schema_type, field, resolver_class, source_line) from Java source."""
    constants = dict(_CONSTANT.findall(source))
    for match in _TYPE_CALL.finditer(source):
        schema_type = match.group(1) or constants.get(match.group(2), "")
        if not schema_type:
            continue
        open_paren = source.find("(", match.start())
        close_paren = _matching_parenthesis(source, open_paren)
        if close_paren < 0:
            continue
        fragment = source[match.end():close_paren]
        for child in _FETCHER.finditer(fragment):
            field, class_name = child.group(1), child.group(2)
            line = source.count("\n", 0, match.end() + child.start()) + 1
            yield schema_type, field, class_name, line


def _get_implementation(graph, resolver):
    """Use the unique nearest get(DataFetchingEnvironment) declaration."""
    layer = {resolver}
    seen = set(layer)
    while layer:
        methods, bases = set(), set()
        for owner in sorted(layer):
            for _, child, edge in graph.out_edges(owner, data=True):
                node = graph.nodes[child]
                rel = edge.get('relation')
                if rel == 'EXTENDS' and node.get('type') == 'class':
                    bases.add(child)
                if rel != 'CONTAINS' or node.get('type') != 'function' or node.get('name') != 'get':
                    continue
                parameters = node.get('param_types', ())
                if len(parameters) == 1 and parameters[0].rsplit('.', 1)[-1] == 'DataFetchingEnvironment':
                    methods.add(child)
        if methods:
            return next(iter(methods)) if len(methods) == 1 else None
        layer = bases - seen
        seen.update(layer)
    return None


def bind_java_graphql_datafetchers(workspace):
    """Attach uniquely resolved Java DataFetchers to indexed GraphQL fields."""
    graph = workspace.graph
    bindings = 0
    method_bindings = 0
    v2 = workspace.config.contract_bindings_v2
    for repo_id, builder in sorted(workspace.repo_builders.items()):
        for rel_file, lines in sorted(builder.raw_file_lines.items()):
            if not rel_file.endswith(".java"):
                continue
            content = "\n".join(lines)
            for type_name, field, class_name, line in explicit_datafetchers(content):
                target = f"contract::graphql::{type_name}::{field}"
                if target not in graph:
                    continue
                candidates = [
                    node_id
                    for node_id in workspace.symbols_by_name.get(class_name, ())
                    if node_id in graph and
                    graph.nodes[node_id].get("type") in {"class", "struct", "type"}
                ]
                if len(set(candidates)) != 1:
                    continue
                source_id = candidates[0]
                origin = f"{repo_id}/{rel_file}:{line}"
                if not any(
                    v == target and data.get("relation") == "IMPLEMENTS"
                    for _, v, data in graph.out_edges(source_id, data=True)
                ):
                    graph.add_edge(
                        source_id, target,
                        key=f"graphql_impl::{source_id}::{target}::{origin}",
                        relation="IMPLEMENTS", layer="Lcontract",
                        source_evidence=origin,
                        binding_kind="explicit_java_datafetcher",
                    )
                    bindings += 1
                if v2 and (method := _get_implementation(graph, source_id)) is not None:
                    key = f'graphql_method_impl::{method}::{target}'
                    if not graph.has_edge(method, target, key):
                        graph.add_edge(method, target, key=key, relation='IMPLEMENTS', layer='Lcontract',
                                       source_evidence=origin, binding_kind='java_datafetcher_method')
                        method_bindings += 1
    if v2:
        graph.graph['contract_bindings_v2']['graphql_java'] = {'implements_edges': method_bindings}
    return bindings
