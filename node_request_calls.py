"""Node.js request-package HTTP extraction with CommonJS endpoint modules.

Only AST-confirmed invocation sites and uniquely resolved local module
exports are used. Dynamic path segments may be abstracted but unknown host
ownership remains conditional or unresolved.
"""
from __future__ import annotations

import ast
import posixpath
import re
from dataclasses import dataclass

from polyglot import TreeSitterExtractor


@dataclass(frozen=True)
class Uri:
    value: str
    conditional: bool = False


def _exported_endpoints(content):
    result = {}
    dynamic_domain = bool(re.search(r"\bprocess\.argv\b", content))
    for match in re.finditer(
        r"\b(\w+)\s*:\s*util\.format\s*\(\s*"
        r"(['\"])(https?://[^'\"]+)\2\s*,\s*(\w+)\s*\)", content):
        key, url, var = match.group(1), match.group(3), match.group(4)
        default = re.search(
            r"\b(?:var|const|let)\s+" + re.escape(var) +
            r"\s*=\s*(['\"])(.*?)\1", content)
        if default is None:
            continue
        if url.count("%s") != 1:
            continue
        result[key] = Uri(url.replace("%s", default.group(2)), dynamic_domain)
    for match in re.finditer(
        r"\b(\w+)\s*:\s*(['\"])(https?://[^'\"]+)\2\s*[,}]", content
    ):
        result[match.group(1)] = Uri(match.group(3))
    return result


def _imports(builder, file, source):
    bindings = {}
    dirname = posixpath.dirname(file)
    for match in re.finditer(
        r"\b(?:var|const|let)\s+(\w+)\s*=\s*require\s*\(\s*"
        r"(['\"])(\.[^'\"]+)\2\s*\)", source):
        alias, requested = match.group(1), match.group(3)
        stem = posixpath.normpath(posixpath.join(dirname, requested))
        options = [stem, stem + ".js", stem + "/index.js"]
        matches = [p for p in options if p in builder.raw_file_lines]
        if len(matches) == 1:
            bindings[alias] = _exported_endpoints(
                "\n".join(builder.raw_file_lines[matches[0]]))
    return bindings


def _value(source, exports, depth=0):
    if depth > 10:
        return None
    source = source.strip()
    if source.startswith(("'", '"')) and source.endswith(source[0]):
        try:
            value = ast.literal_eval(source)
        except (ValueError, SyntaxError):
            return None
        return Uri(value) if isinstance(value, str) else None
    match = re.fullmatch(r"(\w+)\.(\w+)", source)
    if match:
        return exports.get(match.group(1), {}).get(match.group(2))
    # Source-text splitting is limited to top-level '+' to avoid interpreting
    # arbitrary JS expressions or making up runtime hosts.
    pieces = re.split(r"\s+\+\s+", source)
    if len(pieces) > 1:
        result = ""
        conditional = False
        for piece in pieces:
            item = _value(piece, exports, depth+1)
            if item is None:
                if "://" not in result or "/" not in result.split("://", 1)[1]:
                    # A missing host or first endpoint segment cannot be guessed.
                    return None
                result += "{*}"
                conditional = True
                continue
            result += item.value
            conditional |= item.conditional
        return Uri(result, conditional)
    return None


def _source(node, raw):
    return raw[node.start_byte:node.end_byte].decode("utf8", "replace")


def _walk(node):
    yield node
    for child in node.named_children:
        yield from _walk(child)


def _caller(builder, file, call, raw, graph):
    line = call.start_point.row + 1
    nid = f"{builder.repo_prefix}{file}:http_client@{line}"
    if nid not in graph:
        graph.add_node(
            nid, id=nid, type="http_callsite", layer="Ldep",
            name="node_request", file=builder.repo_prefix + file,
            repo=builder.repo_id or "", line_no=line,
            code=_source(call, raw)[:350])
        fid = f"file::{builder.repo_prefix}{file}"
        if fid in graph:
            graph.add_edge(
                fid, nid, key=f"node_request_contains::{nid}",
                relation="CONTAINS", layer="Lsyn")
    return nid


def extract_node_request_calls(builder, graph):
    results = []
    for file, lines in sorted(builder.raw_file_lines.items()):
        if not file.endswith((".js", ".jsx", ".mjs", ".cjs")):
            continue
        source = "\n".join(lines)
        if not re.search(r"\brequire\s*\(\s*['\"]request['\"]\s*\)", source):
            continue
        aliases = set(re.findall(
            r"\b(?:var|const|let)\s+(\w+)\s*=\s*require\s*\(\s*"
            r"['\"]request['\"]\s*\)", source))
        if not aliases:
            continue
        exports = _imports(builder, file, source)
        raw = source.encode("utf8")
        tree = TreeSitterExtractor(".js").parser.parse(raw)
        for node in _walk(tree.root_node):
            if node.type != "call_expression":
                continue
            func = _source(node.child_by_field_name("function"), raw)
            head, _, action = func.partition(".")
            if head not in aliases or action not in {"", "get", "post",
                                                       "put", "patch", "delete"}:
                continue
            args = node.child_by_field_name("arguments")
            if args is None or not args.named_children:
                continue
            first = _source(args.named_children[0], raw)
            url = _value(first, exports)
            method = action.upper() if action else "GET"
            if url is None and first.startswith("{"):
                url_expr = re.search(r"\b(?:uri|url)\s*:\s*([^,}]+)", first)
                verb_expr = re.search(r"\bmethod\s*:\s*['\"]([A-Z]+)['\"]", first)
                if url_expr:
                    url = _value(url_expr.group(1), exports)
                if verb_expr:
                    method = verb_expr.group(1)
            if url is None or not url.value.startswith(("http://", "https://")):
                continue
            caller = _caller(builder, file, node, raw, graph)
            results.append((caller, url.value, method, file,
                            node.start_point.row + 1,
                            "js_request_conditional_default" if url.conditional
                            else "js_request_literal"))
    return results
