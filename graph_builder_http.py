"""Source-grounded, unambiguous cross-service HTTP binding.

Uses literal client URLs, deployment aliases, HTTP verbs and complete route
segments. Unknown hosts, conflicting services and ambiguous handlers are
deliberately left unresolved. Does not contact services or execute their code.
"""
from __future__ import annotations

import ast
import copy
import json
import os
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit


def path_matches(template, request):
    left, right = template.split("/"), request.split("/")
    if len(left) != len(right):
        return False
    for part, value in zip(left, right):
        if re.fullmatch(r"\{[^{}]+\}|<[^<>]+>", part):
            if not value or "/" in value:
                return False
        elif part != value or any(c in value for c in "{}<>"):
            return False
    return True


def deployment_context(workspace):
    """Compose and Kubernetes configuration, without DNS or runtime guessing."""
    roots = {r.id: Path(workspace._resolve_path(r.path)).resolve()
             for r in workspace.config.repositories}
    aliases, values = defaultdict(set), defaultdict(lambda: defaultdict(set))
    for rid, root in roots.items():
        aliases[rid.lower()].add(rid)
        aliases[root.name.lower()].add(rid)
    try:
        import yaml
    except ImportError:
        return aliases, {}
    docs = []
    for base, dirs, files in os.walk(workspace.config.base_dir):
        dirs[:] = sorted(x for x in dirs if x not in (
            ".git", "node_modules", "vendor", "build", "dist", "target", ".venv"
        ))
        for name in sorted(files):
            if not name.endswith((".yaml", ".yml")):
                continue
            file = Path(base, name)
            if file.stat().st_size > 2_000_000:
                continue
            try:
                docs.extend((file, x) for x in yaml.safe_load_all(
                    file.read_text(encoding="utf-8")
                ) if isinstance(x, dict))
            except (OSError, ValueError, yaml.YAMLError):
                continue
    configmaps = defaultdict(list)
    for _, doc in docs:
        if doc.get("kind") == "ConfigMap":
            configmaps[doc.get("metadata", {}).get("name")].append(doc.get("data", {}))

    def owners(candidates):
        result = set()
        for x in candidates:
            result.update(aliases.get(str(x).lower(), set()))
        return result

    def add_environment(rids, env):
        for rid in rids:
            for k, v in env.items():
                if isinstance(v, (str, int)) and "$" not in str(v):
                    values[rid][k].add(str(v))
    for file, doc in docs:
        services = doc.get("services", {})
        if isinstance(services, dict):
            for name, service in services.items():
                if not isinstance(service, dict):
                    continue
                build = service.get("build", {})
                context = build.get("context") if isinstance(build, dict) else build
                rids = owners([name, service.get("container_name", "")])
                if context and "$" not in str(context):
                    resolved = (file.parent / str(context)).resolve()
                    rids.update(rid for rid, root in roots.items() if root == resolved)
                # Do not accept aliases for a service of ambiguous ownership.
                if len(rids) == 1:
                    aliases[name.lower()].update(rids)
                env = service.get("environment", {})
                if isinstance(env, list):
                    env = dict(x.split("=", 1) for x in env
                               if isinstance(x, str) and "=" in x)
                if isinstance(env, dict):
                    add_environment(rids, env)
        spec = doc.get("spec", {})
        if not isinstance(spec, dict):
            continue
        metadata = doc.get("metadata", {})
        template = spec.get("template", {})
        podspec = template.get("spec", spec) if isinstance(template, dict) else spec
        labels = template.get("metadata", {}).get("labels", {}) if isinstance(template, dict) else {}
        if doc.get("kind") == "Service":
            selector = spec.get("selector", {})
            rids = owners(list(selector.values()) if isinstance(selector, dict) else [])
            aliases[str(metadata.get("name", "")).lower()].update(rids)
        containers = podspec.get("containers", []) if isinstance(podspec, dict) else []
        for container in containers if isinstance(containers, list) else []:
            rids = owners([metadata.get("name", ""), container.get("name", ""), *labels.values()])
            for ref in container.get("envFrom", []):
                for data in configmaps.get(ref.get("configMapRef", {}).get("name"), []):
                    if isinstance(data, dict):
                        add_environment(rids, data)
            for entry in container.get("env", []):
                if "value" in entry:
                    add_environment(rids, {entry.get("name"): entry["value"]})
                else:
                    ref = entry.get("valueFrom", {}).get("configMapKeyRef", {})
                    for data in configmaps.get(ref.get("name"), []):
                        if ref.get("key") in data:
                            add_environment(rids, {entry.get("name"): data[ref["key"]]})
    environment = {rid: {k: next(iter(v)) for k, v in entry.items() if len(v) == 1}
                   for rid, entry in values.items()}
    return aliases, environment


def _caller(builder, file, line):
    candidates = [
        (int(d.get("line_no", 0)), node)
        for node, d in builder.graph.nodes(data=True)
        if node.startswith(f"{builder.repo_prefix}{file}:")
        and d.get("type") == "function"
        and int(d.get("line_no", 0)) <= line
    ]
    return max(candidates, default=(0, None))[1]


def _python_requests(builder, file, text, environment):
    """Bounded source evaluation, including one imported helper module.

    No Python code is executed. Imports must be syntactic, definitions unique,
    and conflicting branch values remain unknown. Objects carry only explicit
    constructor assignments; methods are followed only at an actual call site.
    Host/verb/path uniqueness is still enforced by resolve_workspace_http.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    modules, definitions, globals_, results, active = {file: tree}, {}, {}, [], set()
    local_imports = {}
    # Resolve only files already indexed by this service, across one boundary.
    for node in tree.body:
        names = ([node.module] if isinstance(node, ast.ImportFrom) else
                 [a.name for a in node.names] if isinstance(node, ast.Import) else [])
        for name in names:
            if not name:
                continue
            path = name.replace(".", "/") + ".py"
            possible = {path, (Path(file).parent / path).as_posix()}
            if isinstance(node, ast.ImportFrom) and node.level:
                parent = Path(file).parent
                for _ in range(node.level - 1):
                    parent = parent.parent
                possible = {(parent / path).as_posix()}
            found = [p for p in possible if p in builder.raw_file_lines]
            if len(found) != 1:
                continue
            path = found[0]
            try:
                modules[path] = ast.parse("\n".join(builder.raw_file_lines[path]))
                local_imports[name] = path
            except SyntaxError:
                pass
    for module, parsed in modules.items():
        for item in parsed.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                definitions.setdefault((module, item.name), []).append(item)

    def definition(module, symbol):
        found = definitions.get((module, symbol), [])
        return found[0] if len(found) == 1 else None

    def imports(node, values, module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                key = alias.asname or alias.name.split(".")[0]
                if alias.name in {"os", "requests", "httpx", "urllib", "urllib.request"}:
                    values[key] = ("external", alias.name if alias.asname else key)
                elif module == file and alias.name in local_imports:
                    values[key] = ("module", local_imports[alias.name])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                key = alias.asname or alias.name
                if node.module in {"os", "requests", "httpx", "urllib", "urllib.request"}:
                    values[key] = ("external", node.module + "." + alias.name)
                elif module == file and node.module in local_imports:
                    values[key] = ("definition", local_imports[node.module], alias.name)

    def assign(target, value, values, module, depth):
        values[ast.unparse(target)] = value
        if isinstance(target, ast.Attribute):
            obj = evaluate(target.value, values, module, depth)
            if isinstance(obj, dict):
                obj[target.attr] = value
        elif isinstance(target, ast.Subscript):
            obj = evaluate(target.value, values, module, depth)
            key = evaluate(target.slice, values, module, depth)
            if isinstance(obj, dict) and isinstance(key, (str, int)):
                obj[key] = value

    def evaluate(node, values, module, depth=0, emit=False):
        if isinstance(node, ast.Constant):
            return node.value if isinstance(node.value, (str, int, bool)) else None
        if node is None:
            return None
        if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript)):
            key = ast.unparse(node)
            if key in values:
                return values[key]
        if isinstance(node, ast.Name):
            return globals_.get(module, {}).get(node.id)
        if isinstance(node, ast.Dict):
            pairs = [(evaluate(k, values, module, depth), evaluate(v, values, module, depth))
                     for k, v in zip(node.keys, node.values)]
            return {k: v for k, v in pairs if isinstance(k, (str, int))}
        if isinstance(node, ast.Attribute):
            obj = evaluate(node.value, values, module, depth)
            if isinstance(obj, tuple):
                if obj[0] == "external":
                    return ("external", obj[1] + "." + node.attr)
                if obj[0] == "module":
                    return ("definition", obj[1], node.attr)
            if isinstance(obj, dict):
                if node.attr in obj:
                    return obj[node.attr]
                if "__source_class__" in obj:
                    return ("bound", *obj["__source_class__"], node.attr, obj)
            if isinstance(obj, str) and node.attr == "format":
                return ("format", obj)
        if isinstance(node, ast.Subscript):
            obj = evaluate(node.value, values, module, depth)
            key = evaluate(node.slice, values, module, depth)
            if obj == ("external", "os.environ"):
                return environment.get(key)
            return obj.get(key) if isinstance(obj, dict) and isinstance(key, (str, int)) else None
        if isinstance(node, ast.JoinedStr):
            pieces = [evaluate(v.value if isinstance(v, ast.FormattedValue) else v,
                               values, module, depth) for v in node.values]
            return "".join(map(str, pieces)) if all(isinstance(x, (str, int)) for x in pieces) else None
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            a = evaluate(node.left, values, module, depth)
            b = evaluate(node.right, values, module, depth)
            return a + b if isinstance(a, str) and isinstance(b, str) else None
        if not isinstance(node, ast.Call) or any(k.arg is None for k in node.keywords):
            return None
        ref = evaluate(node.func, values, module, depth)
        args = [evaluate(a, values, module, depth, emit) for a in node.args]
        kwargs = {k.arg: evaluate(k.value, values, module, depth, emit) for k in node.keywords}
        if not isinstance(ref, tuple):
            return None
        if ref[0] == "format":
            try:
                if all(isinstance(x, (str, int)) for x in [*args, *kwargs.values()]):
                    return ref[1].format(*args, **kwargs)
            except (ValueError, IndexError, KeyError):
                pass
            return None
        if ref[0] == "external":
            canonical = ref[1]
            if canonical in {"os.getenv", "os.environ.get"}:
                return environment.get(args[0]) if args else None
            op = canonical.rsplit(".", 1)[-1]
            verb = op.upper() if op in {
                "get", "post", "put", "patch", "delete", "head", "options"
            } else "GET" if op == "urlopen" else None
            url = kwargs.get("url", args[0] if args else None)
            if op == "request":
                verb = kwargs.get("method", args[0] if args else None)
                url = kwargs.get("url", args[1] if len(args) > 1 else None)
            if (emit and caller and canonical.startswith(("requests.", "httpx.", "urllib.request."))
                    and verb and isinstance(url, str) and url.startswith(("http://", "https://"))):
                results.append((caller, url, str(verb).upper(), module, node.lineno,
                                "helper" if module != file or depth else "env_via_config" if environment else "literal_host"))
            return None
        if depth >= 2:
            return None
        if ref[0] == "definition":
            target_module, symbol = ref[1:]
            function = definition(target_module, symbol)
            if isinstance(function, ast.ClassDef):
                obj = {"__source_class__": (target_module, symbol)}
                initializers = [f for f in function.body if isinstance(f, ast.FunctionDef) and f.name == "__init__"]
                if len(initializers) == 1:
                    run(initializers[0], [obj, *args], kwargs, target_module, depth + 1, False)
                return obj
        elif ref[0] == "bound":
            target_module, symbol, method, obj = ref[1:]
            cls = definition(target_module, symbol)
            found = [f for f in cls.body if isinstance(f, ast.FunctionDef) and f.name == method] if cls else []
            function = found[0] if len(found) == 1 else None
            args = [obj, *args]
        else:
            return None
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return None
        return run(function, args, kwargs, target_module, depth + 1, emit)

    def scan(statements, values, module, depth=0, emit=False):
        returns = []
        for node in statements:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports(node, values, module)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                values[node.name] = ("definition", module, node.name)
            elif isinstance(node, ast.If):
                condition = evaluate(node.test, values, module, depth, emit)
                if isinstance(condition, bool):
                    got, stopped = scan(node.body if condition else node.orelse, values, module, depth, emit)
                else:
                    left, right = copy.deepcopy(values), copy.deepcopy(values)
                    a, stop_a = scan(node.body, left, module, depth, emit)
                    b, stop_b = scan(node.orelse, right, module, depth, emit)
                    values.update({k: left.get(k) if left.get(k) == right.get(k) else None
                                   for k in left.keys() | right.keys()})
                    got, stopped = a + b, stop_a and stop_b
                returns.extend(got)
                if stopped:
                    return returns, True
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = evaluate(node.value, values, module, depth, emit)
                for dest in node.targets if isinstance(node, ast.Assign) else [node.target]:
                    assign(dest, value, values, module, depth)
            elif isinstance(node, (ast.Return, ast.Expr)):
                value = evaluate(node.value, values, module, depth, emit)
                if isinstance(node, ast.Return):
                    return [*returns, value], True
            elif isinstance(node, (ast.For, ast.While, ast.Try, ast.With)):
                before, branch = copy.deepcopy(values), copy.deepcopy(values)
                scan(node.body, branch, module, depth, emit)
                branches = [before, branch]
                if isinstance(node, ast.Try):
                    for handler in node.handlers:
                        caught = copy.deepcopy(before)
                        scan(handler.body, caught, module, depth, emit)
                        branches.append(caught)
                otherwise = getattr(node, "orelse", [])
                if otherwise:
                    scan(otherwise, branch, module, depth, emit)
                keys = set().union(*(b.keys() for b in branches))
                values.update({k: branches[0].get(k) if all(b.get(k) == branches[0].get(k)
                              for b in branches) else None for k in keys})
                if isinstance(node, ast.Try):
                    scan(node.finalbody, values, module, depth, emit)
        return returns, False

    def run(function, args, kwargs, module, depth, emit):
        key = (module, function.lineno)
        if key in active:
            return None
        active.add(key)
        try:
            values = copy.deepcopy(globals_.get(module, {}))
            params = [*function.args.posonlyargs, *function.args.args]
            values.update(dict(zip([p.arg for p in params], args)))
            values.update(kwargs)
            returned, stopped = scan(function.body, values, module, depth, emit)
            return returned[0] if stopped and returned and all(v == returned[0] for v in returned) else None
        finally:
            active.remove(key)

    caller = None
    for module, parsed in modules.items():
        values = {name: ("definition", module, name) for m, name in definitions if m == module}
        globals_[module] = values
        scan(parsed.body, values, module)
    for item in ast.walk(tree):
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            caller = _caller(builder, file, item.lineno)
            if caller:
                params = [*item.args.posonlyargs, *item.args.args]
                run(item, ["{*}"] * len(params), {}, file, 0, True)
    return results


def _java_requests(builder, file, text):
    """Java source evaluator: literal/concatenated URLs, helpers and control-flow joins."""
    from polyglot import TreeSitterExtractor

    source = text.encode("utf-8")
    root = TreeSitterExtractor(".java").parser.parse(source).root_node

    def raw(node):
        return source[node.start_byte:node.end_byte].decode("utf-8") if node else ""

    def walk(node):
        yield node
        for child in node.named_children:
            yield from walk(child)

    methods = [node for node in walk(root) if node.type == "method_declaration"]
    helpers = {}
    for method in methods:
        returns = [node for node in walk(method) if node.type == "return_statement"]
        if len(returns) == 1 and returns[0].named_children:
            params = method.child_by_field_name("parameters")
            names = [raw(p.child_by_field_name("name")) for p in params.named_children] if params else []
            helper_name = raw(method.child_by_field_name("name"))
            helpers.setdefault(helper_name, []).append(
                (names, returns[0].named_children[0])
            )

    def evaluate(node, values, depth=0):
        if node is None:
            return None
        if node.type == "string_literal":
            try:
                return json.loads(raw(node))
            except ValueError:
                return None
        if node.type in {"identifier", "field_access"}:
            return values.get(raw(node), "{*}")
        if node.type == "parenthesized_expression" and node.named_children:
            return evaluate(node.named_children[0], values, depth)
        if node.type == "binary_expression":
            operator = node.child_by_field_name("operator")
            if operator is not None and raw(operator) == "+":
                left = evaluate(node.child_by_field_name("left"), values, depth)
                right = evaluate(node.child_by_field_name("right"), values, depth)
                if isinstance(left, str) and isinstance(right, str):
                    return left + right
        if node.type == "method_invocation":
            name = raw(node.child_by_field_name("name"))
            args = node.child_by_field_name("arguments")
            args = list(args.named_children) if args else []
            if name in {"create", "of"} and args and raw(
                node.child_by_field_name("object")) in {"URI", "java.net.URI"}:
                return evaluate(args[0], values, depth)
            options = helpers.get(name, [])
            if depth == 0 and len(options) == 1:
                params, expression = options[0]
                if len(params) == len(args):
                    bound = {p: evaluate(a, values, depth + 1)
                             for p, a in zip(params, args)}
                    return evaluate(expression, bound, depth + 1)
        return "{*}"

    receivers = set(re.findall(
        r"\b(?:RestTemplate|WebClient|HttpClient)\s+(\w+)", text))
    result = []
    for method in methods:
        caller = _caller(builder, file, method.start_point.row + 1)
        if caller is None:
            continue
        values = {}

        def flow(node):
            if node.type == "if_statement":
                before = dict(values)
                consequence = node.child_by_field_name("consequence")
                alternative = node.child_by_field_name("alternative")
                if consequence:
                    yield from flow(consequence)
                left = dict(values)
                values.clear()
                values.update(before)
                if alternative:
                    yield from flow(alternative)
                right = dict(values)
                values.clear()
                values.update({
                    key: left.get(key) if left.get(key) == right.get(key) else None
                    for key in left.keys() | right.keys()
                })
                return
            yield node
            for child in node.named_children:
                yield from flow(child)

        for node in flow(method):
            if node.type == "variable_declarator":
                values[raw(node.child_by_field_name("name"))] = evaluate(
                    node.child_by_field_name("value"), values)
            elif node.type == "assignment_expression":
                values[raw(node.child_by_field_name("left"))] = evaluate(
                    node.child_by_field_name("right"), values)
            if node.type != "method_invocation":
                continue
            name = raw(node.child_by_field_name("name"))
            obj = raw(node.child_by_field_name("object"))
            args = node.child_by_field_name("arguments")
            args = list(args.named_children) if args else []
            verb = url = None
            if obj in receivers and args:
                if name == "exchange" and len(args) > 1:
                    match = re.fullmatch(
                        r"(?:\w+\.)*HttpMethod\.(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)",
                        raw(args[1]))
                    verb = match.group(1) if match else None
                else:
                    match = re.fullmatch(
                        r"(get|post|put|delete|patch|head|options)(?:ForObject|ForEntity)?",
                        name)
                    verb = match.group(1).upper() if match else None
                url = evaluate(args[0], values)
            if name == "uri" and args and any(
                re.match(r"\b" + re.escape(r) + r"\.", obj) for r in receivers
            ):
                match = re.search(
                    r"\.(get|post|put|delete|patch|head|options)\(\)", obj)
                verb = match.group(1).upper() if match else None
                url = evaluate(args[0], values)
            if name == "uri" and args and "HttpRequest.newBuilder(" in obj:
                parent = node
                while parent.parent and parent.parent.type == "method_invocation":
                    parent = parent.parent
                chain = raw(parent)
                match = re.search(r"\.(GET|POST|PUT|DELETE|HEAD)\(", chain)
                declaration = parent.parent
                request_name = (
                    raw(declaration.child_by_field_name("name"))
                    if declaration is not None
                    and declaration.type == "variable_declarator" else None
                )
                if (match and request_name and re.search(
                    r"\b(?:" + "|".join(map(re.escape, receivers))
                    + r")\.send(?:Async)?\(\s*" + re.escape(request_name) + r"\b",
                    raw(method),
                )):
                    verb, url = match.group(1), evaluate(args[0], values)
            if (verb and isinstance(url, str)
                    and url.startswith(("http://", "https://"))):
                helper_used = any(
                    re.search(r"\b" + re.escape(h) + r"\(", raw(method))
                    for h in helpers
                    if h != raw(method.child_by_field_name("name"))
                )
                result.append((
                    caller, url, verb, file, node.start_point.row + 1,
                    "helper" if helper_used else "literal_host",
                ))
    return result


def source_requests(builder, environment):
    out = []
    for path, lines in sorted(builder.raw_file_lines.items()):
        text = "\n".join(x.rstrip("\r\n") for x in lines)
        if path.endswith(".py"):
            out.extend(_python_requests(builder, path, text, environment))
        elif path.endswith(".java"):
            out.extend(_java_requests(builder, path, text))
    return list(dict.fromkeys(out))


def resolve_workspace_http(workspace):
    """Create only unambiguous, source-evidenced HTTP_CALLS in workspace graph."""
    from graft_ckg import HyperEdgeMetadata
    aliases, environments = deployment_context(workspace)
    resolved = 0
    for source_repo, builder in workspace.repo_builders.items():
        requests = source_requests(builder, environments.get(source_repo, {}))
        for caller, url, verb, file, line, kind in requests:
            parsed = urlsplit(url)
            host = (parsed.hostname or "").lower()
            destinations = aliases.get(host, set())
            if not host or "{" in host or len(destinations) != 1:
                continue
            dest = next(iter(destinations))
            if source_repo == dest:
                continue
            matches = set()
            for (method, path), handlers in workspace.http_endpoints.items():
                if method not in {verb, "*"} or not path_matches(path, parsed.path):
                    continue
                matches.update(handler for handler in handlers
                               if handler in workspace.graph
                               and workspace.graph.nodes[handler].get("repo") == dest)
            if len(matches) != 1:
                continue
            target = next(iter(matches))
            if workspace.graph.nodes[target].get("http_ambiguous_definition"):
                continue
            if any(v == target and d.get("relation") == "HTTP_CALLS"
                   for _, v, d in workspace.graph.out_edges(caller, data=True)):
                continue
            meta = HyperEdgeMetadata(d_scope=0, f_call=1, c_type=1.0, id_ctx=file)
            workspace.graph.add_edge(
                caller, target, key=f"w_http_source_{caller}_{target}_{file}_{line}",
                relation="HTTP_CALLS", layer="Ldep", metadata=meta.to_dict(),
                d_scope=0, f_call=1.0, c_type=1.0, id_ctx=file,
                match_kind=kind, source_evidence=f"{file}:{line}",
                http_method=verb, http_url=url,
            )
            resolved += 1

        # Retain JS/TS/Go legacy path-only links only when there is exactly
        # one destination. Java source paths are never guessed from a route.
        for caller, path, method, file in builder.http_calls_to_resolve:
            if file.endswith(".java"):
                continue
            if file.endswith(".py") and any(r[0] == caller for r in requests):
                continue
            targets = list(dict.fromkeys(
                workspace.http_endpoints.get((method.upper(), path), []) +
                workspace.http_endpoints.get(("*", path), [])
            ))
            if len(targets) != 1:
                continue
            target = targets[0]
            if target == caller or target not in workspace.graph or caller not in workspace.graph:
                continue
            if any(v == target and d.get("relation") == "HTTP_CALLS"
                   for _, v, d in workspace.graph.out_edges(caller, data=True)):
                continue
            meta = HyperEdgeMetadata(d_scope=0, f_call=1, c_type=1.0, id_ctx=file)
            workspace.graph.add_edge(
                caller, target, key=f"w_http_{caller}_{target}",
                relation="HTTP_CALLS", layer="Ldep", metadata=meta.to_dict(),
                d_scope=0, f_call=1.0, c_type=1.0, id_ctx=file,
            )
            resolved += 1
    if resolved:
        print(f"[*] Cross-Repository HTTP Resolution: {resolved} verified/unique HTTP bindings created.")
    return resolved
