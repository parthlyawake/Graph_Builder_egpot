"""Bind unique OpenAPI and Spring route signatures from Python HTTP calls."""
from collections import defaultdict
import re

from java_contract_declarations import annotation_string, workspace_java_declarations
from python_contract_requests import VERBS, workspace_python_requests
from restli_bindings import route_matches


MAPPING = {name.title() + 'Mapping': name for name in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE')}


def _annotations(declaration, names):
    return [(name.rsplit('.', 1)[-1], args)
            for name, values in declaration.annotations.items() if name.rsplit('.', 1)[-1] in names
            for args in values]


def _paths(arguments, constants):
    """Read positional and named literal paths, including literal alternatives."""
    bracket = re.search(r'(?:^\s*|(?:^|,)\s*(?:path|value)\s*=\s*)\{([^{}]*)\}', arguments)
    if bracket:
        values = [annotation_string(item, constants, positional=True) for item in bracket[1].split(',')]
    else:
        value = annotation_string(arguments, constants, 'path')
        if value is None:
            value = annotation_string(arguments, constants, 'value', positional=True)
        if value is None:
            if re.match(r'\s*[^,=]+\s*(?:,|$)', arguments) or re.search(r'\b(?:path|value)\s*=', arguments):
                return ()
            value = ''
        values = [value]
    return tuple(s for s in values if s is not None and '${' not in s and '#{' not in s and '*' not in s)


def _verb_paths(method):
    for annotation, args in _annotations(method, MAPPING.keys() | {'RequestMapping'}):
        verbs = [MAPPING[annotation]] if annotation in MAPPING else [
            word for word in re.findall(r'\bRequestMethod\.([A-Z]+)\b', args) if word in VERBS]
        for verb in verbs:
            for path in _paths(args, method.constants):
                yield verb, path


def _inherited_routes(workspace, declarations):
    graph = workspace.graph
    by_type = defaultdict(list)
    for canonical, owner in declarations:
        by_type[canonical].append(owner)

    def signature(method):
        return method.name, tuple(graph.nodes[method.id].get('param_types', ()))

    staged = defaultdict(list)
    for _, owner in declarations:
        if not _annotations(owner, {'RestController', 'Controller'}):
            continue
        prefixes = [path for _, args in _annotations(owner, {'RequestMapping'})
                    for path in _paths(args, owner.constants)]
        parent = owner.base
        if not prefixes or not parent:
            continue
        seen_types = set()
        overridden = {signature(method) for method in owner.methods}
        while parent and parent not in seen_types and len(by_type[parent]) == 1:
            seen_types.add(parent)
            declaration = by_type[parent][0]
            for method in declaration.methods:
                sig = signature(method)
                if sig in overridden:
                    continue
                overridden.add(sig)
                for verb, route in _verb_paths(method):
                    for prefix in prefixes:
                        path = '/' + '/'.join(p.strip('/') for p in (prefix, route) if p.strip('/'))
                        repo = graph.nodes[owner.id].get('repo', '')
                        staged[repo, verb, path].append((owner, method))
            parent = declaration.base
    return staged


def bind_openapi_clients(workspace):
    graph = workspace.graph
    counts = {'inherited_contract_nodes': 0, 'implements_edges': 0, 'produces_edges': 0, 'consumes_edges': 0}
    declarations = workspace_java_declarations(workspace)
    for (repo, verb, path), candidates in sorted(_inherited_routes(workspace, declarations).items()):
        if len({method.id for _, method in candidates}) != 1:
            continue
        owner, method = candidates[0]
        contract = f'http::{repo + "/" if repo else ""}{verb}:{path}'
        if contract in graph:
            continue
        graph.add_node(contract, id=contract, name=f'{verb} {path}', type='http_endpoint', layer='Lcontract',
                       file=owner.file, line_no=owner.line, repo=repo, method=verb, path=path,
                       binding_kind='spring_inherited_route')
        counts['inherited_contract_nodes'] += 1
        evidence = f'{owner.file}:{owner.line}; {method.file}:{method.line}'
        for src, dst, relation in ((method.id, contract, 'IMPLEMENTS'), (contract, method.id, 'PRODUCES')):
            graph.add_edge(src, dst, key=f'spring_inherited::{relation}::{contract}', relation=relation,
                           layer='Lcontract', source_evidence=evidence, binding_kind='spring_inherited_route')
            counts[relation.lower() + '_edges'] += 1

    routes = defaultdict(list)
    for node, attrs in graph.nodes(data=True):
        if attrs.get('type') not in {'http_endpoint', 'endpoint'} or attrs.get('spec') == 'restli':
            continue
        if attrs.get('spec') != 'openapi' and not attrs.get('file', '').endswith('.java'):
            continue
        verb = attrs.get('method')
        path = attrs.get('path')
        if verb is None or path is None:
            verb, _, path = attrs.get('name', '').partition(' ')
        if verb in VERBS and path.startswith('/'):
            routes[verb].append((node, path))
    if not routes:
        return counts
    for caller, verb, path, selectors, evidence in workspace_python_requests(workspace):
        if any(key == 'action' for key, _ in selectors):
            continue
        matches = [(sum(not part.startswith('{') for part in template.split('/')), n)
                   for n, template in routes[verb] if route_matches(template, path)]
        if not matches:
            continue
        # A literal route takes precedence over one that treats that same
        # segment as a path parameter. Preserve ambiguity among equal matches.
        specificity = max(rank for rank, _ in matches)
        candidates = [n for rank, n in matches if rank == specificity]
        if len(candidates) != 1:
            continue
        target = candidates[0]
        key = f'openapi_suffix::{target}'
        if not graph.has_edge(caller, target, key):
            # The contract signature is known. The server's deployment identity is still unknown.
            graph.add_edge(caller, target, key=key, relation='CONSUMES', layer='Lcontract',
                           source_evidence=evidence, binding_kind='openapi_static_route_suffix')
            counts['consumes_edges'] += 1
    return counts
