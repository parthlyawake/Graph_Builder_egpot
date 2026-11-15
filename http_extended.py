"""Conservative source-derived HTTP routes and client URLs.

This augments the core AST extraction with common framework conventions.
Only statically resolved URL/route/handler combinations become HTTP_CALLS;
runtime-unknown values do not become fabricated cross-service dependencies.
"""
from __future__ import annotations

import ast
import json
import os
import re
from pathlib import PurePosixPath
from urllib.parse import urljoin, urlsplit


VERBS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


def join_path(prefix, path):
    if not isinstance(prefix, str) or not isinstance(path, str):
        return None
    if not (path.startswith("/") or not path or not prefix):
        return None
    return "/" + "/".join(s.strip("/") for s in (prefix, path) if s.strip("/"))


def literal_python(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        a, b = literal_python(node.left), literal_python(node.right)
        return a + b if a is not None and b is not None else None
    return None


def _function_node(builder, file, name):
    prefix = builder.repo_prefix + file + ":"
    matching = [
        nid for nid, data in builder.graph.nodes(data=True)
        if nid.startswith(prefix) and data.get("type") in {"function", "method"}
        and (nid[len(prefix):] == name or nid.rsplit(".", 1)[-1] == name)
    ]
    return matching[0] if len(matching) == 1 else None


def _register(workspace, builder, method, path, handler, raw_path=None):
    if handler not in workspace.graph or not path or not path.startswith("/"):
        return
    if method not in VERBS and method != "*":
        return
    key = (method, path)
    handlers = workspace.http_endpoints.setdefault(key, [])
    if handler not in handlers:
        handlers.append(handler)
    if raw_path and raw_path != path:
        old = (method, raw_path)
        if old in workspace.http_endpoints:
            workspace.http_endpoints[old] = [x for x in workspace.http_endpoints[old]
                                              if x != handler]
            if not workspace.http_endpoints[old]:
                del workspace.http_endpoints[old]


def _external_python_mounts(sources):
    """Match imported router variables to a unique file in the same repository."""
    result = {}
    modules = {p: p[:-3].replace("/", ".") for p in sources if p.endswith(".py")}

    def destination(current, module, level):
        if not module:
            return None
        base = list(PurePosixPath(current).parts[:-1]) if level else []
        if level > 1:
            base = base[:-(level - 1)]
        stem = "/".join([*base, *module.split(".")])
        candidates = [stem + ".py", stem + "/__init__.py"]
        found = [x for x in candidates if x in sources]
        return found[0] if len(found) == 1 else None

    for file, text in sorted(sources.items()):
        if not file.endswith(".py"):
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        imported = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                target = destination(file, node.module or "", node.level)
                if target:
                    for alias in node.names:
                        imported[alias.asname or alias.name] = (target, alias.name)
        for node in ast.walk(tree):
            if (not isinstance(node, ast.Call) or
                    not isinstance(node.func, ast.Attribute) or
                    node.func.attr not in {"include_router", "register_blueprint"} or
                    not node.args or not isinstance(node.args[0], ast.Name)):
                continue
            remote = imported.get(node.args[0].id)
            if not remote:
                continue
            key = "prefix" if node.func.attr == "include_router" else "url_prefix"
            prefix = next((literal_python(k.value) for k in node.keywords
                           if k.arg == key), "") or ""
            result.setdefault(remote, set()).add(prefix)
    return result


def _python_routes(workspace, builder, file, text, external_mounts=None):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return
    creators = {}
    mounts = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            target = node.targets[0] if len(node.targets) == 1 else None
            if not isinstance(target, ast.Name):
                continue
            fn = ast.unparse(node.value.func).rsplit(".", 1)[-1]
            if fn not in {"APIRouter", "Blueprint"}:
                continue
            kw = "url_prefix" if fn == "Blueprint" else "prefix"
            creators[target.id] = next((literal_python(x.value) for x in node.value.keywords
                                        if x.arg == kw), "") or ""
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            action = node.func.attr
            if action in {"include_router", "register_blueprint"} and node.args:
                arg = node.args[0]
                if not isinstance(arg, ast.Name):
                    continue
                key = "prefix" if action == "include_router" else "url_prefix"
                mount = next((literal_python(x.value) for x in node.keywords
                              if x.arg == key), "") or ""
                mounts.setdefault(arg.id, set()).add(mount)

    methods = {"get": "GET", "post": "POST", "put": "PUT", "patch": "PATCH",
               "delete": "DELETE", "head": "HEAD", "options": "OPTIONS"}
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        handler = _function_node(builder, file, fn.name)
        if handler is None:
            continue
        for dec in fn.decorator_list:
            if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
                continue
            receiver = ast.unparse(dec.func.value)
            verb = methods.get(dec.func.attr)
            if verb is None and dec.func.attr not in {"route", "api_route"}:
                continue
            raw = literal_python(dec.args[0]) if dec.args else next(
                (literal_python(k.value) for k in dec.keywords if k.arg in {"path", "rule"}), None)
            if not raw or not raw.startswith("/"):
                continue
            verbs = [verb] if verb else ["GET"]
            for kw in dec.keywords:
                if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
                    verbs = [literal_python(x).upper() for x in kw.value.elts
                             if literal_python(x) and literal_python(x).upper() in VERBS]
            base = creators.get(receiver, "")
            mount_prefixes = (external_mounts or {}).get((file, receiver)) or mounts.get(receiver, {""})
            for mount in sorted(mount_prefixes):
                full = join_path(join_path(mount, base), raw)
                for method in verbs:
                    _register(workspace, builder, method, full, handler, raw_path=raw)

    # Django URL configurations are resolved across local Python modules in a
    # separate pass; no view is guessed from an unqualified filename alone.


def _django_routes(workspace, builder):
    sources = {p: "\n".join(lines) for p, lines in builder.raw_file_lines.items()
               if p.endswith(".py")}
    urls = {}
    for file, text in sources.items():
        if not file.endswith("urls.py"):
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        routes, includes = [], []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = ast.unparse(node.func).rsplit(".", 1)[-1]
            if name not in {"path", "re_path"} or len(node.args) < 2:
                continue
            route = literal_python(node.args[0])
            if route is None or name == "re_path":
                continue
            dest = node.args[1]
            if isinstance(dest, ast.Call) and ast.unparse(dest.func).rsplit(".", 1)[-1] == "include":
                module = literal_python(dest.args[0]) if dest.args else None
                if module:
                    includes.append((route, module))
            else:
                routes.append((route, ast.unparse(dest)))
        urls[file] = (routes, includes)

    def module_file(name):
        path = name.replace(".", "/") + ".py"
        if path in urls:
            return path
        matching = [p for p in urls if p.endswith("/" + path)]
        return matching[0] if len(matching) == 1 else None

    def view(file, expr):
        name = expr.rsplit(".", 1)[-1]
        possible = []
        for p in sources:
            if p.endswith("views.py") and (p.startswith(str(PurePosixPath(file).parent) + "/")
                                           or str(PurePosixPath(file).parent) in {"", "."}):
                nid = _function_node(builder, p, name)
                if nid:
                    possible.append(nid)
        return possible[0] if len(possible) == 1 else None

    def visit(file, prefix, seen):
        if file in seen or file not in urls:
            return
        routes, includes = urls[file]
        for path, expr in routes:
            handler = view(file, expr)
            if handler:
                _register(workspace, builder, "*", join_path(prefix, "/" + path), handler)
        for path, module in includes:
            child = module_file(module)
            if child:
                visit(child, join_path(prefix, "/" + path), seen | {file})
    included_files = {
        target for _, includes in urls.values()
        for _, module in includes
        for target in [module_file(module)] if target is not None
    }
    # The included module is mounted under its parent URLconf; indexing it
    # as an independent root would assert non-existent unprefixed endpoints.
    for file in sorted(set(urls) - included_files):
        visit(file, "", set())


def _js_routes(workspace, builder, sources):
    routes = []
    imports = {}
    for file, text in sources.items():
        if not file.endswith((".js", ".jsx", ".ts", ".tsx")):
            continue
        imported = {}
        for variable, module in re.findall(
                r"\b(?:const|let|var)\s+(\w+)\s*=\s*require\(\s*['\"](\.[^'\"]+)['\"]\s*\)",
                text):
            imported[variable] = module
        for variable, module in re.findall(
                r"\bimport\s+(\w+)\s+from\s+['\"](\.[^'\"]+)['\"]", text):
            imported[variable] = module
        imports[file] = imported
        pattern = (r"\b([A-Za-z_$][\w$]*)\."
                   r"(get|post|put|patch|delete|head|options)\(\s*"
                   r"(['\"])(/[^'\"\r\n]*)\3\s*,\s*"
                   r"([A-Za-z_$][\w$]*)\b")
        for match in re.finditer(pattern, text, re.I):
            receiver, verb, _, path, handler_name = match.groups()
            if receiver not in {"app", "router", "fastify", "server"} and not re.search(
                    r"\b(?:const|let)\s+" + re.escape(receiver)
                    + r"\s*=\s*(?:express\.Router|Router|fastify)\s*\(", text):
                continue
            handler = _function_node(builder, file, handler_name)
            if handler:
                routes.append((file, receiver, verb.upper(), path, handler))
        # Fastify's object-form registration and Express route chaining.
        for match in re.finditer(
                r"\b(?:fastify|server)\.route\(\s*\{([^{}]+)\}\s*\)", text, re.S):
            body = match.group(1)
            verb = re.search(r"\bmethod\s*:\s*['\"]([A-Za-z]+)['\"]", body)
            path = re.search(r"\b(?:url|path)\s*:\s*['\"](/[^'\"]+)['\"]", body)
            handler = re.search(r"\bhandler\s*:\s*([A-Za-z_$][\w$]*)", body)
            if verb and path and handler:
                nid = _function_node(builder, file, handler.group(1))
                if nid and verb.group(1).upper() in VERBS:
                    routes.append((file, "fastify", verb.group(1).upper(),
                                   path.group(1), nid))
        for match in re.finditer(
                r"\b(app|router)\.route\(\s*['\"](/[^'\"]+)['\"]\s*\)"
                r"\.(get|post|put|patch|delete|head|options)\(\s*(\w+)\s*\)",
                text, re.I):
            receiver, path, verb, name = match.groups()
            nid = _function_node(builder, file, name)
            if nid:
                routes.append((file, receiver, verb.upper(), path, nid))
    mounts = {}
    for file, text in sources.items():
        if file not in imports:
            continue
        for match in re.finditer(
                r"\b[A-Za-z_$][\w$]*\.use\(\s*['\"](/[^'\"]*)['\"]\s*,\s*(\w+)\s*\)", text):
            prefix, receiver = match.groups()
            target = file
            if receiver in imports[file]:
                module = imports[file][receiver]
                stem = str(PurePosixPath(file).parent / module)
                candidates = [stem + ext for ext in (".js", ".jsx", ".ts", ".tsx",
                                                     "/index.js", "/index.ts")]
                present = [p for p in candidates if p in sources]
                target = present[0] if len(present) == 1 else None
                receiver = "router"
            if target:
                mounts.setdefault((target, receiver), set()).add(prefix)
    for file, receiver, method, path, handler in routes:
        mount_list = mounts.get((file, receiver), {""})
        for prefix in sorted(mount_list):
            full = join_path(prefix, path)
            _register(workspace, builder, method, full, handler, raw_path=path)


def _go_routes(workspace, builder, sources):
    for file, text in sources.items():
        if not file.endswith(".go"):
            continue
        groups = {}
        for match in re.finditer(
                r"\b(\w+)\s*:?=\s*\w+\.Group\(\s*['\"`](/[^'\"`]*)['\"`]\s*\)",
                text):
            groups[match.group(1)] = match.group(2)
        pattern = (r"\b(\w+)\.(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|Get|Post|Put|Patch|Delete|Head|Options)"
                   r"\(\s*['\"`](/[^'\"`]*)['\"`]\s*,\s*"
                   r"(\w+)\b")
        for m in re.finditer(pattern, text):
            receiver, method, path, handler_name = m.groups()
            if receiver not in groups and not re.search(
                    r"\b" + re.escape(receiver)
                    + r"\s*:?=\s*(?:gin\.Default|gin\.New|echo\.New|chi\.NewRouter|mux\.NewRouter)",
                    text):
                continue
            handler = _function_node(builder, file, handler_name)
            if handler:
                _register(workspace, builder, method.upper(),
                          join_path(groups.get(receiver, ""), path), handler,
                          raw_path=path)
        for m in re.finditer(
                r"\b(\w+)\.HandleFunc\(\s*['\"`](/[^'\"`]*)['\"`]\s*,\s*(\w+)\s*\)"
                r"\.Methods\(\s*['\"`]([A-Z]+)['\"`]\s*\)", text):
            receiver, path, handler_name, method = m.groups()
            if not re.search(re.escape(receiver) + r"\s*:?=\s*mux\.NewRouter", text):
                continue
            handler = _function_node(builder, file, handler_name)
            if handler:
                _register(workspace, builder, method, path, handler)

        # Chi route blocks have lexical prefixes, not receiver-variable groups.
        for m in re.finditer(
                r"\b(\w+)\.Route\(\s*['\"](/[^'\"]+)['\"]\s*,\s*"
                r"func\(\s*(\w+)\s+chi\.Router\s*\)\s*\{", text):
            outer, prefix, inner = m.groups()
            if not re.search(r"\b" + re.escape(outer)
                             + r"\s*:?=\s*chi\.NewRouter\(", text):
                continue
            start, depth, index = m.end(), 1, m.end()
            while index < len(text) and depth:
                depth += (text[index] == "{") - (text[index] == "}")
                index += 1
            if depth:
                continue
            body = text[start:index - 1]
            for route in re.finditer(
                    r"\b" + re.escape(inner)
                    + r"\.(Get|Post|Put|Patch|Delete|Head|Options)"
                    + r"\(\s*['\"](/[^'\"]+)['\"]\s*,\s*(\w+)\b", body):
                method, path, handler_name = route.groups()
                handler = _function_node(builder, file, handler_name)
                if handler:
                    _register(workspace, builder, method.upper(),
                              join_path(prefix, path), handler, raw_path=path)


def register_routes(workspace):
    """Augment workspace routes, retaining only source-grounded handler IDs."""
    for builder in workspace.repo_builders.values():
        sources = {p: "\n".join(lines) for p, lines in builder.raw_file_lines.items()}
        external_mounts = _external_python_mounts(sources)
        for file, text in sorted(sources.items()):
            if file.endswith(".py"):
                _python_routes(workspace, builder, file, text, external_mounts)
        _django_routes(workspace, builder)
        _js_routes(workspace, builder, sources)
        _go_routes(workspace, builder, sources)


def _raw(node, source):
    return source[node.start_byte:node.end_byte].decode("utf-8")


def _literal_js(node, source, values, env, depth=0):
    if node is None or depth > 12:
        return None
    value = _raw(node, source).strip()
    if node.type in {"string", "string_fragment"}:
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return None
    if node.type == "template_string":
        body = value[1:-1]
        pattern = r"\x24\x7b([A-Za-z_$][\w$]*)\}"
        for name in re.findall(pattern, body):
            replacement = values.get(name)
            if not isinstance(replacement, str):
                return None
            body = re.sub(r"\x24\x7b" + re.escape(name) + r"\}", lambda _: replacement, body)
        return None if re.search(r"\x24\x7b", body) else body
    if node.type == "identifier":
        return values.get(value)
    if node.type == "member_expression":
        match = re.fullmatch(r"(?:process\.env|import\.meta\.env)\.(\w+)", value)
        return env.get(match.group(1)) if match else None
    if node.type == "binary_expression":
        a = _literal_js(node.child_by_field_name("left"), source, values, env, depth + 1)
        b = _literal_js(node.child_by_field_name("right"), source, values, env, depth + 1)
        if "+" in value and isinstance(a, str) and isinstance(b, str):
            return a + b
    if node.type == "parenthesized_expression" and node.named_children:
        return _literal_js(node.named_children[0], source, values, env, depth + 1)
    if node.type == "new_expression" and value.startswith("new URL"):
        args = next((c for c in node.named_children if c.type == "arguments"), None)
        if args and len(args.named_children) == 2:
            rel = _literal_js(args.named_children[0], source, values, env, depth + 1)
            base = _literal_js(args.named_children[1], source, values, env, depth + 1)
            if isinstance(rel, str) and isinstance(base, str) and base.startswith(("http://", "https://")):
                return urljoin(base.rstrip("/") + "/", rel.lstrip("/"))
    return None


def _js_calls(builder, file, text, environment):
    from polyglot import TreeSitterExtractor
    ext = PurePosixPath(file).suffix
    source = text.encode("utf-8")
    root = TreeSitterExtractor(ext).parser.parse(source).root_node
    calls = []
    env = environment or {}

    def walk(node):
        yield node
        for child in node.named_children:
            yield from walk(child)

    def parent_fn(node):
        node = node.parent
        while node:
            if node.type in {"function_declaration", "method_definition",
                             "function", "arrow_function", "generator_function_declaration"}:
                if node.type in {"arrow_function", "function"}:
                    owner = node.parent
                    if owner and owner.type == "variable_declarator":
                        name = owner.child_by_field_name("name")
                        return _raw(name, source) if name else None
                name = node.child_by_field_name("name")
                return _raw(name, source) if name else None
            node = node.parent
        return None

    for call in walk(root):
        if call.type != "call_expression":
            continue
        fn = call.child_by_field_name("function")
        args = call.child_by_field_name("arguments")
        if not fn or not args or not args.named_children:
            continue
        callee = _raw(fn, source)
        operation = re.fullmatch(
            r"(?:axios|[A-Za-z_$][\w$]*)\.(get|post|put|patch|delete|head|options)",
            callee)
        if callee != "fetch" and not operation and callee != "axios":
            continue
        name = parent_fn(call)
        caller = _function_node(builder, file, name) if name else None
        if caller is None:
            continue
        values = {}
        instances = {}
        # Only lexical constants established before the call in this function
        # or the module are promoted to statically known URL values.
        for declaration in walk(root):
            if declaration.type != "variable_declarator" or declaration.start_byte >= call.start_byte:
                continue
            # Ignore assignments inside unrelated functions.
            ancestor = declaration.parent
            function_name = parent_fn(declaration)
            if function_name and function_name != name:
                continue
            var = declaration.child_by_field_name("name")
            val = declaration.child_by_field_name("value")
            if not var or not val:
                continue
            var_name = _raw(var, source)
            if val.type == "call_expression" and _raw(
                    val.child_by_field_name("function"), source) == "axios.create":
                raw_arg = _raw(val, source)
                base_expr = re.search(
                    r"baseURL\s*:\s*(?:['\"]([^'\"]+)['\"]|(\w+))", raw_arg)
                if base_expr:
                    instances[var_name] = base_expr.group(1) or values.get(base_expr.group(2))
            elif declaration.parent.type == "variable_declaration":
                # Mutable let/var bindings are not asserted.
                continue
            else:
                resolved = _literal_js(val, source, values, env)
                if isinstance(resolved, str):
                    values[var_name] = resolved
        method = "GET" if callee == "fetch" else (
            operation.group(1).upper() if operation else "GET"
        )
        first = args.named_children[0]
        url = _literal_js(first, source, values, env)
        if callee == "axios" and first.type == "object":
            raw_obj = _raw(first, source)
            um = re.search(r"url\s*:\s*['\"]([^'\"]+)['\"]", raw_obj)
            mm = re.search(r"method\s*:\s*['\"]([A-Za-z]+)['\"]", raw_obj)
            url = um.group(1) if um else None
            method = mm.group(1).upper() if mm else "GET"
        if callee == "fetch" and len(args.named_children) > 1:
            option_text = _raw(args.named_children[1], source)
            mm = re.search(r"method\s*:\s*['\"]([A-Za-z]+)['\"]", option_text)
            if mm:
                method = mm.group(1).upper()
        if operation:
            receiver = callee.split(".", 1)[0]
            base = instances.get(receiver)
            if receiver != "axios" and base and isinstance(url, str):
                url = urljoin(base.rstrip("/") + "/", url.lstrip("/"))
            elif receiver != "axios" and receiver not in instances:
                continue
        if method in VERBS and isinstance(url, str) and url.startswith(("http://", "https://")):
            calls.append((caller, url, method, file, call.start_point.row + 1,
                          "js_static_expression"))
    return calls


def _go_calls(builder, file, text, environment):
    """Resolve provable Go constants/env URLs; runtime variables stay unknown."""
    from polyglot import TreeSitterExtractor
    source = text.encode("utf-8")
    root = TreeSitterExtractor(".go").parser.parse(source).root_node

    def raw(n):
        return _raw(n, source) if n else ""

    def walk(node):
        yield node
        for child in node.named_children:
            yield from walk(child)

    results = []
    for call in walk(root):
        if call.type != "call_expression":
            continue
        fn = call.child_by_field_name("function")
        args = call.child_by_field_name("arguments")
        if not fn or not args:
            continue
        callee = raw(fn)
        if callee not in {"http.Get", "http.Post", "http.NewRequest",
                          "http.NewRequestWithContext"}:
            continue
        outer = call.parent
        while outer and outer.type not in {"function_declaration", "method_declaration"}:
            outer = outer.parent
        if outer is None:
            continue
        name = raw(outer.child_by_field_name("name"))
        caller = _function_node(builder, file, name)
        if not caller:
            continue
        values = {}
        # Values from unconditionally executed simple assignments, preceding call.
        for m in re.finditer(
                r'(?m)^\s*(?:const\s+|var\s+)?(\w+)\s*(?::=|=)\s*'
                r'("https?://[^"\r\n]+"|os\.Getenv\("[^"]+"\)|\w+\s*\+\s*"[^"]+")', text):
            if m.start() >= call.start_byte:
                break
            var, expr = m.groups()
            if expr.startswith('"'):
                values[var] = expr[1:-1]
            elif expr.startswith("os.Getenv"):
                envname = re.search(r'"([^"]+)"', expr)
                values[var] = environment.get(envname.group(1)) if envname else None
            else:
                part = re.fullmatch(r'(\w+)\s*\+\s*"([^"]+)"', expr)
                if part and isinstance(values.get(part.group(1)), str):
                    values[var] = values[part.group(1)] + part.group(2)
        positional = [raw(a) for a in args.named_children]

        def eval_arg(expr):
            if expr.startswith('"') and expr.endswith('"'):
                try:
                    return json.loads(expr)
                except ValueError:
                    return None
            if expr in values:
                return values[expr]
            concat = re.fullmatch(r'(\w+)\s*\+\s*"([^"]+)"', expr)
            if concat and isinstance(values.get(concat.group(1)), str):
                return values[concat.group(1)] + concat.group(2)
            return None

        method, index = ("GET" if callee == "http.Get" else "POST", 0)
        if callee.startswith("http.NewRequest"):
            offset = 1 if callee.endswith("WithContext") else 0
            if len(positional) <= offset + 1:
                continue
            method = eval_arg(positional[offset])
            index = offset + 1
        if index >= len(positional):
            continue
        url = eval_arg(positional[index])
        if method in VERBS and isinstance(url, str) and url.startswith(("http://", "https://")):
            results.append((caller, url, method, file, call.start_point.row + 1,
                            "go_static_expression"))
    return results


def extended_requests(builder, environment):
    """Return only statically proven host-bearing client calls."""
    out = []
    for file, lines in sorted(builder.raw_file_lines.items()):
        if not file.endswith((".js", ".jsx", ".ts", ".tsx", ".go")):
            continue
        text = "\n".join(lines)
        if file.endswith(".go"):
            out.extend(_go_calls(builder, file, text, environment))
        else:
            out.extend(_js_calls(builder, file, text, environment))
    return list(dict.fromkeys(out))
