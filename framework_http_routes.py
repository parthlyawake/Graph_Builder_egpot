"""Source-backed JAX-RS and Node httpdispatcher route extraction.

These are framework recognition rules, not per-repository paths. A regexp
route is conservatively converted only when its syntax is a literal anchored
path with a simple terminal numeric/string capture segment.
"""
from __future__ import annotations

import re

from polyglot import TreeSitterExtractor


def _text(node, source):
    return source[node.start_byte:node.end_byte].decode("utf8", "replace") if node else ""


def _nodes(node):
    yield node
    for child in node.named_children:
        yield from _nodes(child)


def _route_symbol(workspace, builder, file, line, method, path, evidence,
                  *, regex_route=False):
    from http_extended import _register
    ident = f"{builder.repo_prefix}{file}:http_route@{line}"
    if ident not in workspace.graph:
        props = dict(id=ident, type="http_endpoint", layer="Lcontract",
                     name=f"{method} {path}", repo=builder.repo_id or "",
                     file=builder.repo_prefix + file, line_no=line,
                     http_method=method, http_path=path,
                     source_evidence=f"{file}:{line}",
                     route_from_regex=regex_route, code=evidence[:400])
        builder.graph.add_node(ident, **props)
        workspace.graph.add_node(ident, **props)
    _register(workspace, builder, method, path, ident)


def jaxrs_routes(workspace, builder, sources):
    from http_extended import _function_node, _register, join_path
    count = 0
    for file, content in sorted(sources.items()):
        if not file.endswith(".java") or not re.search(
                r"\bimport\s+(?:javax|jakarta)\.ws\.rs\.", content):
            continue
        raw = content.encode("utf8")
        tree = TreeSitterExtractor(".java").parser.parse(raw)
        for node in _nodes(tree.root_node):
            if node.type != "method_declaration":
                continue
            modifier = next((c for c in node.named_children
                             if c.type == "modifiers"), None)
            source = _text(modifier, raw)
            methods = [verb for verb in ("GET", "POST", "PUT", "PATCH",
                                         "DELETE", "HEAD", "OPTIONS")
                       if re.search(r"@\s*" + verb + r"\b", source)]
            if len(methods) != 1:
                continue
            path_match = re.search(r'@\s*Path\s*\(\s*"([^"]*)"\s*\)', source)
            path = path_match.group(1) if path_match else ""
            owner = node.parent
            prefix = ""
            while owner:
                if owner.type in {"class_declaration", "record_declaration"}:
                    owner_mod = next((c for c in owner.named_children
                                      if c.type == "modifiers"), None)
                    cls_match = re.search(
                        r'@\s*Path\s*\(\s*"([^"]*)"\s*\)',
                        _text(owner_mod, raw))
                    if cls_match:
                        prefix = cls_match.group(1)
                    break
                owner = owner.parent
            full = join_path(prefix, path)
            if not full:
                continue
            name = _text(node.child_by_field_name("name"), raw)
            handler = _function_node(builder, file, name)
            if handler:
                _register(workspace, builder, methods[0], full, handler)
                count += 1
    return count


def regex_route_template(pattern):
    """Accept ^\\/path\\/digits expressions only, without runtime captures."""
    if not pattern.startswith("/") or pattern.count("/") < 2:
        return None
    if not pattern.startswith("/^"):
        return None
    if not pattern.endswith("/"):
        return None
    data = pattern[2:-1]
    if data.endswith("$"):
        data = data[:-1]
    data = data.replace(r"\/", "/")
    # Permit a single terminal character class, e.g. /products/[0-9]*
    terminal = re.search(r"/(\[0-9\]\+|\[0-9\]\*|\\d\+|\\d\*)$", data)
    if terminal:
        data = data[:terminal.start()] + "/{value}"
    if not re.fullmatch(r"/[A-Za-z0-9_./{}-]+", data):
        return None
    if "{" in data and not data.endswith("{value}"):
        return None
    return data


def httpdispatcher_routes(workspace, builder, sources):
    count = 0
    for file, content in sorted(sources.items()):
        if not file.endswith((".js", ".jsx", ".mjs", ".cjs")) or "httpdispatcher" not in content:
            continue
        aliases = set(re.findall(
            r"\b(?:var|let|const)\s+(\w+)\s*=\s*require\s*\(\s*"
            r"['\"]httpdispatcher['\"]\s*\)", content))
        if not aliases:
            continue
        raw = content.encode("utf8")
        tree = TreeSitterExtractor(".js").parser.parse(raw)
        for node in _nodes(tree.root_node):
            if node.type != "call_expression":
                continue
            fn = _text(node.child_by_field_name("function"), raw)
            pieces = fn.rsplit(".", 1)
            if len(pieces) != 2 or pieces[0] not in aliases:
                continue
            suffix = pieces[1]
            methods = {"onGet": "GET", "onPost": "POST", "onPut": "PUT",
                       "onPatch": "PATCH", "onDelete": "DELETE"}
            if suffix not in methods:
                continue
            args = node.child_by_field_name("arguments")
            if args is None or not args.named_children:
                continue
            first = _text(args.named_children[0], raw)
            regex_route = first.startswith("/")
            if regex_route:
                route = regex_route_template(first)
            else:
                match = re.fullmatch(r"['\"](/[^'\"]*)['\"]", first)
                route = match.group(1) if match else None
            if not route:
                continue
            line = node.start_point.row+1
            _route_symbol(workspace, builder, file, line, methods[suffix],
                          route, _text(node, raw), regex_route=regex_route)
            count += 1
    return count
