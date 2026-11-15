"""Gorilla Mux / Go-kit HTTP route registrations.

Resolve explicit Methods(...).Path(...).Handler(...) chains from the Go AST.
The registration node is distinct from the eventual endpoint handler: dynamic
middleware, closure and Go-kit endpoint resolution cannot be guessed.
"""
from __future__ import annotations

import re
from polyglot import TreeSitterExtractor


_ROUTE = re.compile(
    r"\b(?P<router>[A-Za-z_]\w*)\s*\.\s*Methods\s*\(\s*"
    r'"(?P<method>GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)"\s*\)'
    r"\s*\.\s*(?P<kind>Path|PathPrefix)\s*\(\s*"
    r'"(?P<path>/[^"]*)"\s*\)\s*\.\s*Handler\s*\(',
    re.DOTALL,
)


def _text(node, raw):
    return raw[node.start_byte:node.end_byte].decode("utf8", "replace")


def _walk(node):
    yield node
    for child in node.named_children:
        yield from _walk(child)


def register_go_kit_routes(workspace, builder, sources):
    """Index AST-verified HTTP route registration expressions."""
    from http_extended import _register
    number = 0
    for file, source in sorted(sources.items()):
        if not file.endswith(".go") or ".Methods(" not in source:
            continue
        raw = source.encode("utf8")
        tree = TreeSitterExtractor(".go").parser.parse(raw)
        # Identify locally established Gorilla mux router variables only.
        routers = set(re.findall(
            r"\b([a-zA-Z_]\w*)\s*:=\s*mux\.NewRouter\s*\(", source))
        if not routers:
            continue
        for node in _walk(tree.root_node):
            if node.type != "call_expression":
                continue
            callee = node.child_by_field_name("function")
            if callee is None or not _text(callee, raw).endswith(".Handler"):
                continue
            snippet = _text(node, raw)
            match = _ROUTE.search(snippet)
            if not match or match["router"] not in routers:
                continue
            method, route = match["method"], match["path"]
            line = node.start_point.row + 1
            route_id = f"{builder.repo_prefix}{file}:http_route@{line}"
            if route_id not in workspace.graph:
                attributes = {
                    "id": route_id, "name": f"{method} {route}", "type": "http_endpoint",
                    "repo": builder.repo_id or "", "file": builder.repo_prefix + file,
                    "layer": "Lcontract", "line_no": line,
                    "method": method, "path": route,
                    "code": snippet[:1000],
                    "http_prefix_mount": match["kind"] == "PathPrefix",
                    "binding_kind": "gorilla_mux_handler_registration",
                }
                builder.graph.add_node(route_id, **attributes)
                workspace.graph.add_node(route_id, **attributes)
                file_node = f"file::{builder.repo_prefix}{file}"
                if file_node in workspace.graph:
                    workspace.graph.add_edge(
                        file_node, route_id,
                        key=f"go_route_contains::{route_id}",
                        relation="CONTAINS", layer="Lsyn")
            _register(workspace, builder, method, route, route_id)
            number += 1
    return number
