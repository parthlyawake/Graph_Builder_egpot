"""Link typed Apollo hook imports to checked-in GraphQL operations."""
from collections import defaultdict
from functools import lru_cache
import os
import posixpath
import re


HOOK = re.compile(r"use[A-Z][\w$]*(?:Query|Mutation|Subscription)\Z")
FUNCTION = {"arrow_function", "function_expression", "function_declaration", "method_definition"}
SCOPE = FUNCTION | {"program", "statement_block"}


def _text(node, source):
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace") if node else ""


def _walk(node):
    yield node
    for child in node.named_children:
        yield from _walk(child)


@lru_cache(maxsize=16)
def _react_names(root, source):
    named, namespaces = set(), set()
    for node in root.named_children:
        if node.type != "import_statement" or _text(node.child_by_field_name("source"), source)[1:-1] != "react":
            continue
        for entry in _walk(node):
            if entry.type == "import_specifier" and _text(entry.child_by_field_name("name"), source) == "useCallback":
                named.add(_text(entry.child_by_field_name("alias"), source) or "useCallback")
            if entry.type in {"import_clause", "namespace_import"}:
                namespaces.update(_text(child, source) for child in entry.named_children if child.type == "identifier")
    return {name or "useCallback" for name in named} | {f"{name}.useCallback" for name in namespaces}


def react_callback(declaration, source):
    value = declaration.child_by_field_name("value")
    callee = _text(value.child_by_field_name("function"), source)
    if not re.fullmatch(r"\w+(?:\.useCallback)?", callee) or b"useCallback" not in source:
        return None
    root = declaration
    while root.parent is not None:
        root = root.parent
    if callee not in _react_names(root, source):
        return None
    args = value.child_by_field_name("arguments")
    first = next(iter(args.named_children), None) if args else None
    return first if first and first.type in {"arrow_function", "function_expression"} else None


def _scope(node):
    while node is not None and node.type not in SCOPE:
        node = node.parent
    return node


def _pattern_names(node):
    if node is None:
        return
    if node.type in {"identifier", "shorthand_property_identifier_pattern"}:
        yield node
    elif node.type in {"array_pattern", "object_pattern", "rest_pattern"}:
        for child in node.named_children:
            yield from _pattern_names(child)
    elif node.type in {"assignment_pattern", "object_assignment_pattern"}:
        yield from _pattern_names(node.child_by_field_name("left"))
    elif node.type == "pair_pattern":
        yield from _pattern_names(node.child_by_field_name("value"))
    elif node.type in {"required_parameter", "optional_parameter"}:
        yield from _pattern_names(node.child_by_field_name("pattern"))


def _operation_for_import(ids, module, caller_file, graph):
    if not ids:
        return None
    stem = re.sub(r"\.(?:[cm]?[jt]sx?)$", "", module)
    if stem.endswith((".generated", ".graphql", ".gql")):
        stem = stem.rsplit(".", 1)[0]
    elif not any(re.fullmatch(r"(?:__)?generated(?:__)?", p) for p in stem.split("/")):
        return None
    if stem.startswith("."):
        paths = {posixpath.normpath(posixpath.join(posixpath.dirname(caller_file), stem))}
        named = [n for n in ids if graph.nodes[n]["file"].rsplit(".", 1)[0] in paths]
    else:
        suffix = stem.lstrip("@/")
        named = [n for n in ids if graph.nodes[n]["file"].rsplit(".", 1)[0].endswith("/" + suffix)]
    if not named and any(re.fullmatch(r"(?:__)?generated(?:__)?", p) for p in stem.split("/")):
        named = ids
    return named[0] if len(named) == 1 else None


def _file_bindings(root, source, file_path, operations, graph):
    declarations = defaultdict(dict)
    variables, calls = [], []
    for node in _walk(root):
        if node.type == "import_statement":
            module = _text(node.child_by_field_name("source"), source)[1:-1]
            for entry in _walk(node):
                if entry.type != "import_specifier":
                    continue
                original = _text(entry.child_by_field_name("name"), source)
                local = _text(entry.child_by_field_name("alias"), source) or original
                operation = _operation_for_import(operations.get(original, ()), module, file_path, graph)
                if operation is not None:
                    declarations[root.id][local] = (operation,)
        elif node.type == "variable_declarator":
            pattern = node.child_by_field_name("name")
            names = list(_pattern_names(pattern))
            scope = _scope(node.parent)
            for name in names:
                declarations[scope.id][_text(name, source)] = None
            variables.append((node, pattern, scope))
        elif node.type in FUNCTION:
            names = node.child_by_field_name("parameters") or node.child_by_field_name("parameter")
            for parameter in names.named_children if names and names.type == "formal_parameters" else [names]:
                for name in _pattern_names(parameter):
                    declarations[node.id][_text(name, source)] = None
            if node.type == "function_declaration":
                scope = _scope(node.parent)
                declarations[scope.id][_text(node.child_by_field_name("name"), source)] = None
        elif node.type == "call_expression":
            calls.append(node)

    def resolve(scope, name):
        while scope is not None:
            values = declarations.get(scope.id, {})
            if name in values:
                return values[name]
            scope = _scope(scope.parent)
        return None

    def expression_operations(node, scope):
        if not node:
            return ()
        if node.type == "identifier":
            return resolve(scope, _text(node, source)) or ()
        if node.type == "ternary_expression":
            left = expression_operations(node.child_by_field_name("consequence"), scope)
            right = expression_operations(node.child_by_field_name("alternative"), scope)
            return tuple(sorted(set(left) | set(right))) if left and right else ()
        return ()

    for decl, pattern, scope in variables:
        value = decl.child_by_field_name("value")
        if not pattern or not value or not _text(decl.parent, source).startswith("const "):
            continue
        if pattern.type == "identifier":
            targets = expression_operations(value, scope)
            if targets:
                declarations[scope.id][_text(pattern, source)] = targets
            continue
        if pattern.type != "array_pattern" or value.type != "call_expression":
            continue
        callee = _text(value.child_by_field_name("function"), source)
        targets = resolve(scope, callee) or ()
        first = next((part for part in pattern.children if part.type not in {"[", "comment"}), None)
        if targets and all(graph.nodes[n]["kind"] == "mutation" for n in targets) and first and first.type == "identifier":
            declarations[scope.id][_text(first, source)] = targets
    for call in calls:
        fn = call.child_by_field_name("function")
        if fn and fn.type == "identifier":
            callee = _text(fn, source)
            targets = resolve(_scope(call), callee) or ()
            for operation in targets:
                yield fn.start_point.row + 1, fn.start_point.column, callee, operation, len(targets) > 1


def bind_apollo_operations(workspace):
    from polyglot import TreeSitterExtractor

    graph = workspace.graph
    operations = defaultdict(list)
    for node, attrs in graph.nodes(data=True):
        name = attrs.get("name", "")
        if (attrs.get("type") == "graphql_operation" and attrs.get("kind") in {"query", "mutation", "subscription"}
                and name and name != "anonymous" and attrs.get("file", "").endswith((".graphql", ".gql"))):
            hook = f'use{name[0].upper()}{name[1:]}{attrs["kind"].title()}'
            if HOOK.fullmatch(hook):
                operations[hook].append(node)
    parsers = {}
    callbacks = [n for n, a in graph.nodes(data=True) if a.get("binding_kind") == "react_use_callback"]
    counts = {"callback_nodes": len(callbacks),
              "callback_contains_edges": sum(a.get('relation') == 'CONTAINS' for n in callbacks
                                             for _, _, a in graph.in_edges(n, data=True)),
              "operation_edges": 0, "consumes_edges": 0}
    if not operations:
        return counts
    for repo, builder in sorted(workspace.repo_builders.items()):
        calls = defaultdict(set)
        for entry in builder.callsite_evidence:
            calls[entry.get("file"), entry.get("line"), entry.get("column"), entry.get("callee")].add(entry["caller"])
        for file, lines in sorted(builder.raw_file_lines.items()):
            extension = posixpath.splitext(file)[1]
            if extension not in {".ts", ".tsx"}:
                continue
            source = "\n".join(lines).encode("utf8")
            if not re.search(rb"\buse[A-Z]\w*(?:Query|Mutation|Subscription)\b", source):
                continue
            if extension not in parsers:
                parsers[extension] = TreeSitterExtractor(extension)
            tree, _ = parsers[extension].parse_source(source)
            caller_file = os.path.relpath(os.path.join(builder.repo_path, file), workspace.config.base_dir).replace("\\", "/")
            for line, column, callee, operation, conditional in _file_bindings(tree.root_node, source, caller_file, operations, graph):
                candidates = calls[file, line, column, callee]
                if len(candidates) != 1:
                    continue
                caller = next(iter(candidates))
                if graph.nodes.get(caller, {}).get("type") != "function":
                    continue
                provenance = {"layer": "Lcontract", "binding_kind": "apollo_generated_hook",
                              "source_evidence": f"{repo}/{file}:{line}", "operation_id": operation,
                              "conditional": conditional}
                key = f"apollo::{operation}"
                if not graph.has_edge(caller, operation, key):
                    graph.add_edge(caller, operation, key=key, relation="USES_OPERATION", **provenance)
                    counts["operation_edges"] += 1
                attrs = graph.nodes[operation]
                kind = attrs["kind"]
                root_type = graph.graph.get("graphql_root_types", {}).get(kind, kind.title())
                for field in attrs["root_fields"]:
                    target = f"contract::graphql::{root_type}::{field}"
                    if target in graph and not graph.has_edge(caller, target, key):
                        graph.add_edge(caller, target, key=key, relation="CONSUMES", **provenance)
                        counts["consumes_edges"] += 1
    return counts
