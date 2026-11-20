"""Materialize and bind action-specific and resource-method Rest.li contracts."""
from collections import defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
import re

from java_contract_declarations import annotation_string, workspace_java_declarations
from python_contract_requests import workspace_python_requests


METHODS = {'get': 'GET', 'batch_get': 'GET', 'get_all': 'GET', 'create': 'POST', 'batch_create': 'POST',
           'delete': 'DELETE', 'batch_delete': 'DELETE', 'update': 'PUT', 'batch_update': 'PUT',
           'partial_update': 'POST', 'batch_partial_update': 'POST'}
ENTITY_METHODS = {'get', 'delete', 'update', 'partial_update'}


@dataclass(frozen=True)
class Route:
    verb: str
    path: str
    kind: str
    name: str
    selector: tuple = ()

    @property
    def display_path(self):
        return self.path + ('?' + '='.join(self.selector) if self.selector else '')


def _routes(data):
    collection = data.get('path')
    if not isinstance(collection, str) or not collection.startswith('/'):
        return
    for shape_name in ('collection', 'simple', 'actionsSet'):
        shape = data.get(shape_name)
        if not isinstance(shape, dict):
            continue
        entity = shape.get('entity', {})
        entity_path = entity.get('path', collection)
        for method in sorted(set(shape.get('supports', ())) | {m.get('method', '') for m in shape.get('methods', ())}):
            if method in METHODS:
                path = entity_path if method in ENTITY_METHODS else collection
                selector = ('ids', '*') if method.startswith('batch_') else ()
                yield Route(METHODS[method], path, 'method', method, selector)
        for action in shape.get('actions', ()):
            if name := action.get('name'):
                yield Route('POST', collection, 'action', name, ('action', name))
        if entity_path != collection:
            for action in entity.get('actions', ()):
                if name := action.get('name'):
                    yield Route('POST', entity_path, 'entity_action', name, ('action', name))
        for finder in shape.get('finders', ()):
            if name := finder.get('name'):
                yield Route('GET', collection, 'finder', name, ('q', name))


def route_matches(path, request):
    a, b = path.strip('/').split('/'), request.strip('/').split('/')
    return len(a) == len(b) and all(
        (bool(right) if re.fullmatch(r'\{[^/{}]+\}', left) else left == right != '{*}')
        for left, right in zip(a, b))


def _registered_routes(method):
    for annotation, instances in method.annotations.items():
        if annotation == 'Action' or annotation.endswith('.Action'):
            for args in instances:
                if name := annotation_string(args, method.constants, 'name', positional=True):
                    kind = 'entity_action' if re.search(r'\bresou?rceLevel\s*=\s*(?:\w+\.)?ENTITY\b', args) else 'action'
                    yield kind, name
        if re.search(r'(?:^|\.)RestMethod\.\w+$', annotation):
            name = re.sub(r'(?<!^)(?=[A-Z])', '_', annotation.rsplit('.', 1)[-1]).lower()
            yield 'method', name
        if annotation == 'Finder' or annotation.endswith('.Finder'):
            for args in instances:
                if name := annotation_string(args, method.constants, 'value', positional=True):
                    yield 'finder', name


def bind_restli(workspace):
    counts = {'contract_nodes': 0, 'idl_file_nodes': 0, 'defines_edges': 0,
              'contains_edges': 0, 'implements_edges': 0, 'consumes_edges': 0}
    root = Path(workspace.config.base_dir)
    graph = workspace.graph
    definitions = []
    for path in sorted(root.rglob('*.restspec.json')):
        if set(path.relative_to(root).parts) & {'node_modules', '.git', 'vendor', 'dist', 'build', 'target'}:
            continue
        try:
            data = json.loads(path.read_text(encoding='utf8'))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get('name') and data.get('resourceClass'):
            for route in _routes(data):
                definitions.append((path.relative_to(root).as_posix(), data, route))
    if not definitions:
        return counts
    by_class = defaultdict(list)
    for name, decl in workspace_java_declarations(workspace):
        by_class[name].append(decl)
    by_verb = defaultdict(list)
    for file, data, route in definitions:
        namespace = data.get('namespace', '')
        contract = f"restli::{namespace}::{data['path']}::{route.kind}::{route.name}"
        if contract in graph:
            continue
        graph.add_node(contract, id=contract, name=f'{route.verb} {route.display_path}',
                       type='http_endpoint', layer='Lcontract', spec='restli', file=file,
                       method=route.verb, path=route.display_path, collection=data['path'],
                       resource_method=route.name, resource_kind=route.kind)
        counts['contract_nodes'] += 1
        file_id = f'file::{file}'
        if file_id not in graph:
            graph.add_node(file_id, id=file_id, name=Path(file).name, file=file, type='file', layer='Lsyn', line_no=1)
            counts['idl_file_nodes'] += 1
        graph.add_edge(file_id, contract, key=f'restli_idl::{contract}', relation='CONTAINS', layer='Lsyn')
        counts['contains_edges'] += 1
        by_verb[route.verb].append((contract, route))
        owners = by_class[data['resourceClass']]
        if len(owners) != 1:
            continue
        resource = owners[0]
        annotations = [args for name, entries in resource.annotations.items()
                       if name.rsplit('.', 1)[-1] in {'RestLiCollection','RestLiSimpleResource','RestLiActions'}
                       for args in entries]
        if not any(annotation_string(args, resource.constants, 'name') == data['name'] and
                   annotation_string(args, resource.constants, 'namespace') in (None, namespace) for args in annotations):
            continue
        graph.add_edge(resource.id, contract, key=f'restli_resource::{contract}', relation='DEFINES',
                       layer='Lcontract', source_evidence=f'{resource.file}:{resource.line}', binding_kind='restli_resource')
        counts['defines_edges'] += 1
        handlers = [m for m in resource.methods if (route.kind, route.name) in _registered_routes(m)]
        if len(handlers) == 1:
            method = handlers[0]
            graph.add_edge(method.id, contract, key=f'restli_impl::{contract}', relation='IMPLEMENTS',
                           layer='Lcontract', source_evidence=f'{method.file}:{method.line}', binding_kind='restli_handler')
            counts['implements_edges'] += 1

    for caller, verb, path, selectors, origin in workspace_python_requests(workspace):
        lookup = dict(selectors)
        if len(lookup) != len(selectors):
            continue
        matched = []
        for contract, route in by_verb[verb]:
            if not route_matches(route.path, path):
                continue
            if route.selector:
                key, expected = route.selector
                if set(lookup) != {key} or (expected != '*' and lookup[key] != expected):
                    continue
            elif lookup:
                continue
            matched.append(contract)
        if len(matched) == 1:
            target = matched[0]
            key = f'restli_consume::{target}'
            if not graph.has_edge(caller, target, key):
                graph.add_edge(caller, target, key=key, relation='CONSUMES', layer='Lcontract',
                               source_evidence=origin, binding_kind='restli_static_route')
                counts['consumes_edges'] += 1
    return counts
