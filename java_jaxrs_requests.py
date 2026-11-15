"""JAX-RS Java client URL propagation with explicit configuration provenance.

Tracks JAX-RS Client -> WebTarget -> Invocation.Builder -> HTTP verbs.
Only direct source-declared client types and unique local variable flows
are eligible; environment defaults are annotated as conditional targets.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from polyglot import TreeSitterExtractor


@dataclass(frozen=True)
class Value:
    text: str | None = None
    conditional: bool = False
    jaxrs: str | None = None


def _raw(node, data):
    return data[node.start_byte:node.end_byte].decode("utf8", "replace") if node else ""


def _walk(node):
    yield node
    for child in node.named_children:
        yield from _walk(child)


def _args(node):
    parent = node.child_by_field_name("arguments")
    return list(parent.named_children) if parent else []


def _key_from_env(node, data):
    if node is not None and node.type == "method_invocation":
        if _raw(node.child_by_field_name("name"), data) == "getenv":
            if _raw(node.child_by_field_name("object"), data) in {"System", "java.lang.System"}:
                args = _args(node)
                if len(args) == 1 and args[0].type == "string_literal":
                    try:
                        return json.loads(_raw(args[0], data))
                    except ValueError:
                        pass
    return None


def _expr(node, data, variables, environment, depth=0):
    if node is None or depth > 18:
        return Value()
    if node.type == "string_literal":
        try:
            return Value(json.loads(_raw(node, data)))
        except ValueError:
            return Value()
    if node.type == "identifier":
        return variables.get(_raw(node, data), Value())
    if node.type == "parenthesized_expression" and node.named_children:
        return _expr(node.named_children[0], data, variables, environment, depth+1)
    if node.type == "binary_expression":
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        operator = node.child_by_field_name("operator")
        if _raw(operator, data) == "+":
            l = _expr(left, data, variables, environment, depth+1)
            r = _expr(right, data, variables, environment, depth+1)
            if l.text is not None and r.text is not None:
                return Value(l.text+r.text, l.conditional or r.conditional)
            # Unknown identifiers can stand for a complete URL path segment;
            # never invent an unknown host or missing URL prefix.
            if l.text is not None and l.text.startswith(("http://", "https://")):
                if l.text.endswith("/") and right is not None and right.type == "identifier":
                    # A dynamic path identifier is not a deployment choice.
                    # Preserve only the host/configuration uncertainty.
                    return Value(l.text + "*", l.conditional)
            return Value()
    if node.type == "ternary_expression":
        cond = node.child_by_field_name("condition")
        consequence = node.child_by_field_name("consequence")
        alternative = node.child_by_field_name("alternative")
        key, none_branch = None, None
        if cond is not None and cond.type == "binary_expression":
            lhs, rhs = cond.child_by_field_name("left"), cond.child_by_field_name("right")
            op = _raw(cond.child_by_field_name("operator"), data)
            key = _key_from_env(lhs, data) if _raw(rhs, data) == "null" else (
                _key_from_env(rhs, data) if _raw(lhs, data) == "null" else None)
            if key:
                if op == "==":
                    none_branch = consequence
                elif op == "!=":
                    none_branch = alternative
        if key and none_branch is not None:
            chosen = (alternative if none_branch == consequence else consequence) if (
                key in environment) else none_branch
            value = _expr(chosen, data, variables, environment, depth+1)
            return Value(value.text, value.conditional or key not in environment)
        a = _expr(consequence, data, variables, environment, depth+1)
        b = _expr(alternative, data, variables, environment, depth+1)
        if a.text == b.text:
            return Value(a.text, a.conditional or b.conditional)
        return Value()
    if node.type == "method_invocation":
        key = _key_from_env(node, data)
        if key is not None:
            return Value(str(environment[key])) if key in environment else Value()
        method = _raw(node.child_by_field_name("name"), data)
        obj = _raw(node.child_by_field_name("object"), data)
        args = _args(node)
        if method == "format" and obj in {"String", "java.lang.String"} and args:
            fmt = _expr(args[0], data, variables, environment, depth+1)
            vals = [_expr(a, data, variables, environment, depth+1) for a in args[1:]]
            if fmt.text is not None and all(x.text is not None for x in vals):
                if re.search(r"%(?!s|%)", fmt.text):
                    return Value()
                if fmt.text.count("%s") != len(vals):
                    return Value()
                parts = fmt.text.split("%s")
                output = parts[0]
                for v, suffix in zip(vals, parts[1:]):
                    output += v.text + suffix
                return Value(output.replace("%%", "%"),
                             fmt.conditional or any(x.conditional for x in vals))
        if method == "create" and obj in {"URI", "java.net.URI"} and len(args) == 1:
            return _expr(args[0], data, variables, environment, depth+1)
    return Value()


def _field_values(tree, data, environment):
    values = {}
    for node in _walk(tree.root_node):
        if node.type != "field_declaration":
            continue
        for child in node.named_children:
            if child.type != "variable_declarator":
                continue
            name = _raw(child.child_by_field_name("name"), data)
            value = _expr(child.child_by_field_name("value"), data, values, environment)
            if name:
                values[name] = value
    return values


def extract_jaxrs_requests(builder, file, content, environment):
    if not file.endswith(".java") or not re.search(
            r"\bimport\s+(?:javax|jakarta)\.ws\.rs\.client\.", content):
        return []
    raw = content.encode("utf8")
    tree = TreeSitterExtractor(".java").parser.parse(raw)
    fields = _field_values(tree, raw, environment)
    from http_extended import _function_node
    requests = []
    for node in _walk(tree.root_node):
        if node.type != "method_declaration":
            continue
        name = _raw(node.child_by_field_name("name"), raw)
        caller = _function_node(builder, file, name)
        if not caller:
            continue
        values = dict(fields)
        clients = set()
        targets = {}
        invocations = {}
        for expr in _walk(node):
            if expr.type == "variable_declarator":
                variable = _raw(expr.child_by_field_name("name"), raw)
                init = expr.child_by_field_name("value")
                if not variable:
                    continue
                values[variable] = _expr(init, raw, values, environment)
                # The declared JAX-RS type, not the name, authorizes a client.
                declaration = expr.parent
                dtype = _raw(declaration.child_by_field_name("type"), raw)
                if dtype in {"Client", "javax.ws.rs.client.Client", "jakarta.ws.rs.client.Client"}:
                    clients.add(variable)
                if init is not None and init.type == "method_invocation":
                    action = _raw(init.child_by_field_name("name"), raw)
                    obj = _raw(init.child_by_field_name("object"), raw)
                    args = _args(init)
                    if action == "target" and obj in clients and len(args) == 1:
                        url = _expr(args[0], raw, values, environment)
                        if url.text and url.text.startswith(("http://", "https://")):
                            targets[variable] = url
                    if action == "request" and obj in targets:
                        invocations[variable] = targets[obj]
            elif expr.type == "method_invocation":
                action = _raw(expr.child_by_field_name("name"), raw)
                obj = _raw(expr.child_by_field_name("object"), raw)
                if obj in invocations and action in {
                        "get", "post", "put", "delete", "head", "options"}:
                    url = invocations[obj]
                    host = (urlsplit(url.text).hostname or "") if url.text else ""
                    if not host or "{" in host or "*" in host:
                        continue
                    requests.append((
                        caller, url.text, action.upper(), file,
                        expr.start_point.row+1,
                        "java_jaxrs_conditional_default" if url.conditional
                        else "java_jaxrs_typed_client"
                    ))
    return list(dict.fromkeys(requests))
