"""Index Java class and method declarations used by contract binders."""
from collections import defaultdict
from dataclasses import dataclass
import re


@dataclass
class Declaration:
    id: str
    name: str
    file: str
    line: int
    annotations: dict
    constants: dict
    methods: tuple = ()
    base: str | None = None


def _text(node, source):
    return source[node.start_byte:node.end_byte].decode('utf8', errors='replace') if node else ''


def _annotations(node, source):
    modifiers = next((child for child in node.named_children if child.type == 'modifiers'), None)
    if modifiers is None:
        return {}
    values = defaultdict(list)
    for child in modifiers.named_children:
        if child.type in {'annotation', 'marker_annotation'}:
            name = _text(child.child_by_field_name('name'), source)
            args = _text(child.child_by_field_name('arguments'), source)
            values[name].append(args[1:-1])
    return dict(values)


def annotation_string(arguments, constants, key=None, *, positional=False):
    literal = r'("[^"\\]*"|[A-Za-z_$][\w$]*)'
    match = re.search(r'(?:^|,)\s*' + re.escape(key) + r'\s*=\s*' + literal, arguments) if key else None
    if match is None and positional:
        match = re.match(r'\s*' + literal + r'\s*(?:,|$)', arguments)
    if not match:
        return None
    value = match[1]
    return value[1:-1] if value.startswith('"') else constants.get(value)


def java_declarations(workspace):
    from polyglot import TreeSitterExtractor

    try:
        parser = TreeSitterExtractor('.java').parser
    except RuntimeError:
        return
    for builder in workspace.repo_builders.values():
        methods = defaultdict(list)
        for n, attrs in builder.graph.nodes(data=True):
            if attrs.get('type') == 'function' and attrs.get('file', '').endswith('.java'):
                methods[attrs['file'], attrs.get('line_no'), attrs.get('name')].append(n)
        for file, lines in builder.raw_file_lines.items():
            if not file.endswith('.java'):
                continue
            source = '\n'.join(lines).encode('utf8')
            if not any(marker in source for marker in (b'RestLi', b'Mapping', b'extends')):
                continue
            root = parser.parse(source).root_node
            package = next((_text(n, source).split()[1].rstrip(';') for n in root.named_children
                            if n.type == 'package_declaration'), '')
            imports = {}
            for entry in root.named_children:
                if entry.type == 'import_declaration':
                    match = re.fullmatch(r'\s*import\s+([\w.]+)\s*;\s*', _text(entry, source))
                    if match:
                        imports[match[1].rsplit('.', 1)[-1]] = match[1]
            graph_file = builder.repo_prefix + file

            def walk(node, scope=()):
                if node.type in {'class_declaration', 'interface_declaration', 'record_declaration'}:
                    name = _text(node.child_by_field_name('name'), source)
                    body = node.child_by_field_name('body')
                    if not body or not name:
                        return
                    qualified = (*scope, name)
                    owner = graph_file + ':' + '.'.join(qualified)
                    constants = {}
                    functions = []
                    for entry in body.named_children:
                        if entry.type == 'field_declaration':
                            line = _text(entry, source)
                            match = re.search(r'\bString\s+([\w$]+)\s*=\s*"([^"\\]*)"', line)
                            if match and re.search(r'\bstatic\b', line) and re.search(r'\bfinal\b', line):
                                constants[match[1]] = match[2]
                        elif entry.type == 'method_declaration':
                            method = _text(entry.child_by_field_name('name'), source)
                            line = entry.start_point.row + 1
                            ids = [n for n in methods[graph_file, line, method] if n.startswith(owner + '.')]
                            if len(ids) == 1:
                                functions.append(Declaration(ids[0], method, graph_file, line,
                                                             _annotations(entry, source), constants))
                        elif entry.type.endswith('_declaration'):
                            yield from walk(entry, qualified)
                    if owner in workspace.graph:
                        canonical = '.'.join(part for part in (package, *qualified) if part)
                        superclass = next((child for child in node.named_children if child.type == 'superclass'), None)
                        base = re.match(r'extends\s+([\w.$]+)', _text(superclass, source))
                        parent = None
                        if base:
                            parent = imports.get(base[1], '.'.join(filter(None, (package, base[1])))
                                                 if '.' not in base[1] else base[1])
                        yield canonical, Declaration(owner, name, graph_file, node.start_point.row + 1,
                                                     _annotations(node, source), constants, tuple(functions), parent)
                elif node.type == 'program':
                    for child in node.named_children:
                        yield from walk(child)

            yield from walk(root)


def workspace_java_declarations(workspace):
    if workspace._java_contract_declarations is None:
        workspace._java_contract_declarations = list(java_declarations(workspace))
    return workspace._java_contract_declarations
