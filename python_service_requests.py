"""Bounded Python HTTP URL propagation for service dictionaries and wrappers.

Handles source literals, config-provided environments, defaults, formatting,
dictionary indexing, simple helper forwarding and abstract path parameters.
A default from an unproven environment branch is conditional evidence, never
a confirmed cross-service HTTP_CALLS edge.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class Value:
    data: object = None
    conditional: bool = False


def _env_call(node):
    if not isinstance(node, ast.Call) or not node.args:
        return None
    name = ast.unparse(node.func)
    if name not in ("os.getenv", "os.environ.get"):
        return None
    arg = node.args[0]
    return arg.value if isinstance(arg, ast.Constant) and isinstance(arg.value, str) else None


def _evaluate(node, values, config, depth=0):
    if node is None or depth > 15:
        return Value()
    if isinstance(node, ast.Constant):
        return Value(node.value)
    if isinstance(node, ast.Name):
        return values.get(node.id, Value())
    if isinstance(node, ast.Subscript):
        owner = _evaluate(node.value, values, config, depth+1)
        key = _evaluate(node.slice, values, config, depth+1)
        if isinstance(owner.data, dict) and key.data in owner.data:
            child = owner.data[key.data]
            return Value(child.data, child.conditional or owner.conditional)
        return Value()
    if isinstance(node, ast.Dict):
        obj, conditional = {}, False
        for key, value in zip(node.keys, node.values):
            k = _evaluate(key, values, config, depth+1)
            v = _evaluate(value, values, config, depth+1)
            if not isinstance(k.data, (str, int)):
                return Value()
            obj[k.data] = v
            conditional |= v.conditional
        return Value(obj, conditional)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        a, b = (_evaluate(x, values, config, depth+1) for x in (node.left, node.right))
        if isinstance(a.data, str) and isinstance(b.data, str):
            return Value(a.data + b.data, a.conditional or b.conditional)
        return Value()
    if isinstance(node, ast.IfExp):
        # Default branches of 'ENV.get(NAME) is None' remain conditional
        # unless the environment key is supplied by deployment configuration.
        test = node.test
        if isinstance(test, ast.Compare) and len(test.ops) == 1 and len(test.comparators) == 1:
            key = _env_call(test.left)
            is_none = isinstance(test.comparators[0], ast.Constant) and test.comparators[0].value is None
            if key and is_none and isinstance(test.ops[0], (ast.Is, ast.IsNot)):
                condition_is_none = isinstance(test.ops[0], ast.Is)
                if key in config:
                    branch = node.orelse if condition_is_none else node.body
                    return _evaluate(branch, values, config, depth+1)
                # Source default is a possible deployment branch, not certain.
                branch = node.body if condition_is_none else node.orelse
                value = _evaluate(branch, values, config, depth+1)
                return Value(value.data, True)
        a = _evaluate(node.body, values, config, depth+1)
        b = _evaluate(node.orelse, values, config, depth+1)
        if a.data == b.data:
            return Value(a.data, a.conditional or b.conditional)
        return Value()
    if isinstance(node, ast.JoinedStr):
        pieces = [_evaluate(x.value, values, config, depth+1) if isinstance(x, ast.FormattedValue)
                  else _evaluate(x, values, config, depth+1)
                  for x in node.values]
        if all(isinstance(x.data, str) for x in pieces):
            return Value("".join(x.data for x in pieces),
                         any(x.conditional for x in pieces))
        return Value()
    if isinstance(node, ast.Call):
        key = _env_call(node)
        if key is not None:
            if key in config:
                return Value(str(config[key]))
            if len(node.args) >= 2:
                val = _evaluate(node.args[1], values, config, depth+1)
                return Value(val.data, True)
            return Value()
        name = ast.unparse(node.func)
        if name == "str" and len(node.args) == 1:
            val = _evaluate(node.args[0], values, config, depth+1)
            if val.data is None:
                # Only represents a single unknown URL path segment; never a host.
                return Value("*", val.conditional)
            if isinstance(val.data, (str, int, float)):
                return Value(str(val.data), val.conditional)
        if (isinstance(node.func, ast.Attribute) and
                node.func.attr == "format"):
            fmt = _evaluate(node.func.value, values, config, depth+1)
            args = [_evaluate(x, values, config, depth+1) for x in node.args]
            if isinstance(fmt.data, str) and all(
                    isinstance(x.data, (str, int, float)) for x in args):
                try:
                    return Value(fmt.data.format(*(x.data for x in args)),
                                 fmt.conditional or any(x.conditional for x in args))
                except (IndexError, KeyError, ValueError):
                    return Value()
    return Value()


def _http_wrappers(tree):
    methods = {"get", "post", "put", "delete", "patch", "head", "options"}
    wrappers = {}
    for fn in tree.body:
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        names = {arg.arg for arg in fn.args.args}
        matches = []
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if (isinstance(node.func.value, ast.Name) and
                    node.func.value.id in {"requests", "httpx"} and
                    node.func.attr in methods and node.args and
                    isinstance(node.args[0], ast.Name) and
                    node.args[0].id in names):
                matches.append((node.args[0].id, node.func.attr.upper()))
        if len(matches) == 1:
            wrappers[fn.name] = matches[0]
    return wrappers


def extract_requests(builder, file, source, configuration):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    wrappers = _http_wrappers(tree)
    globals_ = {}
    for item in tree.body:
        if isinstance(item, ast.Assign):
            value = _evaluate(item.value, globals_, configuration)
            for target in item.targets:
                if isinstance(target, ast.Name):
                    globals_[target.id] = value
    from http_extended import _function_node
    results = []

    def scan_statements(statements, values, caller):
        for statement in statements:
            if isinstance(statement, ast.Assign):
                value = _evaluate(statement.value, values, configuration)
                for target in statement.targets:
                    if isinstance(target, ast.Name):
                        values[target.id] = value
            if isinstance(statement, (ast.If, ast.Try, ast.With, ast.AsyncWith,
                                      ast.For, ast.AsyncFor, ast.While)):
                # Visit nested, zero-or-more loop bodies independently. Facts
                # established in a loop must not escape as unconditional
                # assignments; extraction only records literal URL evidence.
                branches = [getattr(statement, "body", ()),
                            getattr(statement, "orelse", ()),
                            getattr(statement, "finalbody", ())]
                for branch in branches:
                    if branch:
                        scan_statements(branch, dict(values), caller)
                continue
            for node in ast.walk(statement):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                    continue
                binding = wrappers.get(node.func.id)
                if binding is None:
                    continue
                param, method = binding
                definition = next((f for f in tree.body if isinstance(
                    f, (ast.FunctionDef, ast.AsyncFunctionDef)) and f.name == node.func.id), None)
                if definition is None:
                    continue
                arg_names = [a.arg for a in definition.args.args]
                supplied = {n: v for n, v in zip(arg_names, node.args)}
                supplied.update({k.arg: k.value for k in node.keywords if k.arg})
                if param not in supplied:
                    continue
                url = _evaluate(supplied[param], values, configuration)
                if (isinstance(url.data, str) and url.data.startswith(
                        ("http://", "https://")) and
                        "/*" not in url.data.split("://", 1)[1].split("/", 1)[0]):
                    results.append((
                        caller, url.data, method, file, node.lineno,
                        "python_conditional_default" if url.conditional
                        else "python_source_wrapper"
                    ))

    for fn in tree.body:
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            caller = _function_node(builder, file, fn.name)
            if caller:
                scan_statements(fn.body, dict(globals_), caller)
    return list(dict.fromkeys(results))
