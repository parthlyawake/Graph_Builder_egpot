"""Recover HTTP verbs and route suffixes from statically evidenced Python calls."""
import ast
from collections import defaultdict
from dataclasses import dataclass
from itertools import product
from urllib.parse import parse_qsl, urlsplit


VERBS = frozenset({'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'})
CLIENTS = {'requests', 'httpx', 'aiohttp', 'urllib3'}
CLIENT_TYPES = {'Session', 'Client', 'AsyncClient', 'ClientSession', 'PoolManager'}
FUNCTION = (ast.FunctionDef, ast.AsyncFunctionDef)
LIMIT = 8


@dataclass(frozen=True)
class Parameter:
    name: str


UNKNOWN = ((None,),)


def alternatives(values):
    result = tuple(dict.fromkeys(values))
    return result if len(result) <= LIMIT else UNKNOWN


def concatenate(left, right):
    return alternatives(a + b for a, b in product(left, right))


def expression(node, values):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return ((node.value,),)
    if isinstance(node, ast.Name):
        return values.get(node.id, UNKNOWN)
    if isinstance(node, ast.JoinedStr):
        result = ((),)
        for item in node.values:
            result = concatenate(result, expression(item.value if isinstance(item, ast.FormattedValue) else item, values))
        return result
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return concatenate(expression(node.left, values), expression(node.right, values))
    if isinstance(node, ast.IfExp):
        return alternatives((*expression(node.body, values), *expression(node.orelse, values)))
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == 'str' and len(node.args) == 1:
            return expression(node.args[0], values)
        if isinstance(node.func, ast.Attribute) and node.func.attr in {'lower', 'upper'} and not node.args:
            return expression(node.func.value, values)
    return UNKNOWN


def annotate_name(node):
    return node.id if isinstance(node, ast.Name) else None


def _spelling(node):
    return ast.unparse(node) if node is not None else ''


def _client_type(node, imports):
    name = _spelling(node)
    head, sep, tail = name.partition('.')
    expanded = imports.get(head, '') + (sep + tail if sep else '')
    return expanded.split('.')[0] in CLIENTS and expanded.rsplit('.', 1)[-1] in CLIENT_TYPES


def _scope_walk(node):
    yield node
    for child in ast.iter_child_nodes(node):
        if not isinstance(child, (*FUNCTION, ast.ClassDef, ast.Lambda)):
            yield from _scope_walk(child)


def _parameters(fn):
    return [a.arg for a in (*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs)]


def _defaults(fn):
    positional = (*fn.args.posonlyargs, *fn.args.args)
    values = dict(zip((a.arg for a in positional[len(positional)-len(fn.args.defaults):]), fn.args.defaults))
    values.update((a.arg, d) for a, d in zip(fn.args.kwonlyargs, fn.args.kw_defaults) if d is not None)
    return {name: expression(value, {}) for name, value in values.items()}


def _abstract(fn):
    return all(isinstance(s, ast.Pass) or (isinstance(s, ast.Expr) and
               isinstance(s.value, ast.Constant)) for s in fn.body)


def _merge(states):
    settings = set().union(*(s.keys() for s in states))
    return {key: alternatives(value for state in states for value in state.get(key, UNKNOWN)) for key in settings}


def _bindings(callee, call, values, bound):
    positions = [a.arg for a in (*callee.args.posonlyargs, *callee.args.args)]
    if bound:
        positions = positions[1:]
    if any(isinstance(arg, ast.Starred) for arg in call.args):
        return None
    result = _defaults(callee)
    result.update((name, expression(arg, values)) for name, arg in zip(positions, call.args))
    result.update((kw.arg, expression(kw.value, values)) for kw in call.keywords if kw.arg)
    return result


def _substitute(parts, bindings):
    value = ((),)
    for part in parts:
        value = concatenate(value, bindings.get(part.name, UNKNOWN) if isinstance(part, Parameter) else ((part,),))
    return value


def _route(parts):
    # Only an opaque host prefix is stripped. A dynamic path component must
    # occupy exactly one segment and is matched only to a declared parameter.
    raw = ''.join(piece if isinstance(piece, str) else '{*}' for piece in parts)
    if raw.startswith('{*}/'):
        raw = raw[3:]
    try:
        url = urlsplit(raw)
    except ValueError:
        return None
    if url.scheme and (url.scheme not in {'http', 'https'} or not url.netloc):
        return None
    if not url.path.startswith('/') or url.path.startswith('//') or not all(
        ('{' not in part and '}' not in part) or part == '{*}' for part in url.path.split('/')):
        return None
    query = parse_qsl(url.query, keep_blank_values=True)
    selectors = [(key, value) for key, value in query if key in {'action', 'ids', 'q'}]
    if any(key == 'action' and ('{*}' in value or not value) for key, value in selectors):
        return None
    return url.path, tuple(selectors)


class PythonRequests:
    def __init__(self, builder):
        self.builder = builder
        self.functions, self.classes, self.imports = {}, {}, {}
        self.members, self.receivers, self.children = defaultdict(dict), defaultdict(set), defaultdict(set)
        self.summaries = {}
        for file, lines in sorted(builder.raw_file_lines.items()):
            if not file.endswith('.py'):
                continue
            try:
                tree = ast.parse('\n'.join(lines))
            except SyntaxError:
                continue
            imports = {}
            for node in tree.body:
                if isinstance(node, ast.Import):
                    imports.update((item.asname or item.name.split('.')[0], item.name) for item in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.update((item.asname or item.name, f'{node.module}.{item.name}') for item in node.names)
            self.imports[file] = imports
            for node in tree.body:
                if isinstance(node, FUNCTION):
                    self.functions[file, '', node.name] = node
                elif isinstance(node, ast.ClassDef):
                    owner = (file, node.name)
                    self.classes[owner] = node
                    for child in node.body:
                        if isinstance(child, FUNCTION):
                            key = (*owner, child.name)
                            self.functions[key] = child
                            self.members[owner][child.name] = key
                        elif isinstance(child, ast.AnnAssign) and _client_type(child.annotation, imports):
                            self.receivers[owner].add('self.' + _spelling(child.target))
                    init = self.members[owner].get('__init__')
                    if init:
                        for child in _scope_walk(self.functions[init]):
                            if isinstance(child, ast.Assign) and isinstance(child.value, ast.Call) and _client_type(child.value.func, imports):
                                self.receivers[owner].update(_spelling(target) for target in child.targets)
        self.bases = {owner: self._bases(owner, node) for owner, node in self.classes.items()}
        for owner, parents in self.bases.items():
            for parent in parents:
                self.children[parent].add(owner)

    def _bases(self, owner, node):
        file, _ = owner
        result = []
        for base in node.bases:
            name = _spelling(base)
            parent = (file, name)
            if parent in self.classes:
                result.append(parent)
                continue
            full = self.imports[file].get(name)
            if full:
                module, _, clazz = full.rpartition('.')
                suffix = '/' + module.replace('.', '/')
                matches = [key for key in self.classes if key[1] == clazz and (
                    ('/' + key[0]).endswith(suffix + '.py') or ('/' + key[0]).endswith(suffix + '/__init__.py'))]
                if len(matches) == 1:
                    result.extend(matches)
        return result

    def _method(self, owner, name):
        pending = [owner]
        seen = set()
        while pending:
            current = pending.pop(0)
            if current in seen:
                continue
            seen.add(current)
            key = self.members[current].get(name)
            if key is not None and not _abstract(self.functions[key]):
                return key
            pending.extend(self.bases.get(current, ()))
        # A protocol/mixin call may have its implementation on a subclass.
        pending = list(self.children[owner]); seen = {owner}; matches = set()
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            method = self.members[current].get(name)
            if method is not None and not _abstract(self.functions[method]):
                matches.add(method)
            pending.extend(self.children[current])
        return next(iter(matches)) if len(matches) == 1 else None

    def _registered_receiver(self, owner, spelling, local):
        file, _ = owner
        if spelling in local or self.imports[file].get(spelling, '') in CLIENTS:
            return True
        pending = [owner]; seen = set()
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            if spelling in self.receivers.get(current, ()):
                return True
            pending.extend(self.bases.get(current, ()))
        return False

    def _summarize(self, key, remaining=LIMIT):
        if (key, remaining) in self.summaries:
            return self.summaries[key, remaining]
        if not remaining:
            return ()
        file, clazz, _ = key
        owner = file, clazz
        fn = self.functions[key]
        values = {name: ((Parameter(name),),) for name in _parameters(fn)}
        local = {arg.arg for arg in (*fn.args.args, *fn.args.kwonlyargs) if _client_type(arg.annotation, self.imports[file])}
        dynamic = {}
        found = set()

        def call(node, state):
            verb = url = None
            if isinstance(node.func, ast.Attribute) and self._registered_receiver(owner, _spelling(node.func.value), local):
                attr = node.func.attr.upper()
                if attr in VERBS:
                    verb = ((attr,),)
                    url = node.args[0] if node.args else None
                elif attr == 'REQUEST':
                    method = next((kw.value for kw in node.keywords if kw.arg == 'method'), node.args[0] if node.args else None)
                    verb = expression(method, state)
                    url = node.args[1] if len(node.args) >= 2 else None
            elif isinstance(node.func, ast.Name) and node.func.id in dynamic:
                verb = expression(dynamic[node.func.id], state)
                url = node.args[0] if node.args else None
            if verb is not None:
                url = next((kw.value for kw in node.keywords if kw.arg == 'url'), url)
                for v, p in product(verb, expression(url, state)):
                    found.add((v, p, node.lineno))
                return
            bound = isinstance(node.func, ast.Attribute) and _spelling(node.func.value) == 'self'
            callee = self._method(owner, node.func.attr) if bound else (file, '', _spelling(node.func))
            if callee not in self.functions:
                return
            passed = _bindings(self.functions[callee], node, state, bound)
            if passed is not None:
                for v, p, _ in self._summarize(callee, remaining - 1):
                    for verb_part, path in product(_substitute(v, passed), _substitute(p, passed)):
                        found.add((verb_part, path, node.lineno))

        def scan(block, state):
            for item in block:
                if isinstance(item, (*FUNCTION, ast.ClassDef)):
                    continue
                if isinstance(item, (ast.If, ast.For, ast.While, ast.AsyncFor, ast.Try, ast.With, ast.AsyncWith)):
                    for name in ('test', 'iter'):
                        sub = getattr(item, name, None)
                        if sub is not None:
                            for node in _scope_walk(sub):
                                if isinstance(node, ast.Call):
                                    call(node, state)
                    parts = [scan(body, dict(state)) for body in [item.body, getattr(item, 'orelse', [])]]
                    parts.extend(scan(handler.body, dict(state)) for handler in getattr(item, 'handlers', []))
                    state = scan(getattr(item, 'finalbody', []), _merge(parts))
                    continue
                for node in _scope_walk(item):
                    if isinstance(node, ast.Call):
                        call(node, state)
                if isinstance(item, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                    targets = item.targets if isinstance(item, ast.Assign) else [item.target]
                    for target in targets:
                        name = annotate_name(target)
                        if not name:
                            continue
                        value = expression(item.value, state)
                        if isinstance(item, ast.AugAssign) and isinstance(item.op, ast.Add):
                            value = concatenate(state.get(name, UNKNOWN), value)
                        state[name] = value
                        if isinstance(item.value, ast.Call):
                            args = item.value.args
                            if _client_type(item.value.func, self.imports[file]):
                                local.add(name)
                            if (_spelling(item.value.func) == 'getattr' and len(args) == 2 and
                                    self._registered_receiver(owner, _spelling(args[0]), local)):
                                dynamic[name] = args[1]
            return state

        scan(fn.body, values)
        result = tuple(sorted(found, key=repr))
        self.summaries[key, remaining] = result
        return result

    def requests(self):
        for key, fn in self.functions.items():
            file, clazz, name = key
            endpoint = f'{self.builder.repo_prefix}{file}:' + (f'{clazz}.' if clazz else '') + name
            if endpoint not in self.builder.graph:
                continue
            defaults = _defaults(fn)
            for v, p, line in self._summarize(key):
                for verb_bits, path in product(_substitute(v, defaults), _substitute(p, defaults)):
                    if not all(isinstance(bit, str) for bit in verb_bits):
                        continue
                    verb = ''.join(verb_bits).upper()
                    route = _route(path)
                    if verb in VERBS and route:
                        yield endpoint, verb, *route, f'{self.builder.repo_prefix}{file}:{line}'


def workspace_python_requests(workspace):
    if workspace._python_contract_requests is None:
        workspace._python_contract_requests = sorted({row for builder in workspace.repo_builders.values()
                                                     for row in PythonRequests(builder).requests()})
    return workspace._python_contract_requests
