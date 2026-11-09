"""Source-grounded, unambiguous cross-service HTTP binding.

Uses literal client URLs, deployment aliases, HTTP verbs and complete route
segments. Unknown hosts, conflicting services and ambiguous handlers are
deliberately left unresolved. Does not contact services or execute their code.
"""
from __future__ import annotations

import ast
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
    """Source AST evaluation of constants, simple local variables and env URLs."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    results = []
    imported = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in {"requests", "httpx", "urllib.request"}:
                    imported[alias.asname or alias.name] = alias.name
        if isinstance(node, ast.ImportFrom) and node.module in {
                "requests", "httpx", "urllib.request"}:
            for alias in node.names:
                imported[alias.asname or alias.name] = node.module + "." + alias.name

    def literal(node, values):
        if isinstance(node, ast.Constant):
            return node.value if isinstance(node.value, str) else None
        if isinstance(node, ast.Name):
            return values.get(node.id)
        if isinstance(node, ast.JoinedStr):
            pieces = [literal(v.value, values) if isinstance(v, ast.FormattedValue)
                      else literal(v, values) for v in node.values]
            return "".join(pieces) if all(isinstance(x, str) for x in pieces) else None
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            a, b = literal(node.left, values), literal(node.right, values)
            return a + b if isinstance(a, str) and isinstance(b, str) else None
        if isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            if name in ("os.getenv", "os.environ.get") and node.args:
                key = literal(node.args[0], values)
                return environment.get(key) if key else None
            if isinstance(node.func, ast.Attribute) and node.func.attr == "format":
                fmt = literal(node.func.value, values)
                args = [literal(x, values) for x in node.args]
                if isinstance(fmt, str) and all(isinstance(x, str) for x in args):
                    try:
                        return fmt.format(*args)
                    except (ValueError, IndexError, KeyError):
                        pass
        return None

    # Track source-level literals before each call. Branch-dependent values
    # are deliberately not promoted to confirmed links.
    def scan(node, values, caller):
        if isinstance(node, ast.If):
            before = dict(values)
            left, right = dict(before), dict(before)
            for s in node.body:
                scan(s, left, caller)
            for s in node.orelse:
                scan(s, right, caller)
            for key in set(left) | set(right):
                values[key] = left.get(key) if left.get(key) == right.get(key) else None
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return
        if isinstance(node, ast.Assign):
            result = literal(node.value, values)
            for target in node.targets:
                if isinstance(target, ast.Name):
                    values[target.id] = result
        if isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            head, _, rest = name.partition(".")
            canonical = imported.get(head, "") + ("." + rest if rest else "")
            op = canonical.rsplit(".", 1)[-1]
            verb = op.upper() if op in {
                "get", "post", "put", "patch", "delete", "head", "options"
            } else "GET" if op == "urlopen" else None
            if op == "request":
                method_node = node.args[0] if node.args else None
                verb = literal(method_node, values) if method_node else None
            if canonical.startswith(("requests.", "httpx.", "urllib.request.")) and verb:
                url_node = node.args[1] if op == "request" and len(node.args) > 1 else (
                    node.args[0] if op != "request" and node.args else None
                )
                for kw in node.keywords:
                    if kw.arg == "url":
                        url_node = kw.value
                    if kw.arg == "method" and op == "request":
                        verb = literal(kw.value, values)
                url = literal(url_node, values) if url_node else None
                if isinstance(url, str) and url.startswith(("http://", "https://")):
                    results.append((caller, url, str(verb).upper(), file, node.lineno,
                                    "env_via_config" if environment else "literal_host"))
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                scan(child, values, caller)

    globals_ = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    globals_[target.id] = literal(stmt.value, globals_)
    for item in ast.walk(tree):
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            caller = _caller(builder, file, item.lineno)
            if caller:
                values = dict(globals_)
                for stmt in item.body:
                    scan(stmt, values, caller)
    return results


def _java_requests(builder, file, text):
    """Use the existing Java grammar for method-scoped HTTP expressions."""
    from polyglot import TreeSitterExtractor
    parser = TreeSitterExtractor(".java").parser
    source = text.encode("utf-8")
    root = parser.parse(source).root_node

    def raw(node):
        return source[node.start_byte:node.end_byte].decode("utf-8") if node else ""

    def walk(node):
        yield node
        for child in node.named_children:
            yield from walk(child)

    receivers = set(re.findall(r"\b(?:RestTemplate|WebClient|HttpClient)\s+(\w+)", text))
    methods = [n for n in walk(root) if n.type == "method_declaration"]
    result = []
    for method in methods:
        caller = _caller(builder, file, method.start_point.row + 1)
        if not caller:
            continue
        values = {}
        for node in walk(method):
            if node.type == "variable_declarator":
                name = raw(node.child_by_field_name("name"))
                val = node.child_by_field_name("value")
                if val and val.type == "string_literal":
                    try:
                        values[name] = json.loads(raw(val))
                    except ValueError:
                        pass
            if node.type != "method_invocation":
                continue
            name = raw(node.child_by_field_name("name"))
            obj = raw(node.child_by_field_name("object"))
            args = node.child_by_field_name("arguments")
            args = list(args.named_children) if args else []
            if obj not in receivers or not args:
                continue
            verb = None
            if name == "exchange" and len(args) >= 2:
                match = re.fullmatch(
                    r"(?:\w+\.)*HttpMethod\.(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)",
                    raw(args[1])
                )
                verb = match.group(1) if match else None
            else:
                match = re.fullmatch(
                    r"(get|post|put|delete|patch|head|options)(?:ForObject|ForEntity)?",
                    name
                )
                verb = match.group(1).upper() if match else None
            if not verb:
                continue
            url = None
            if args[0].type == "string_literal":
                try:
                    url = json.loads(raw(args[0]))
                except ValueError:
                    pass
            elif args[0].type == "identifier":
                url = values.get(raw(args[0]))
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                result.append((caller, url, verb, file, node.start_point.row + 1, "literal_host"))
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
