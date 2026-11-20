"""Prepare DataHub inputs from source citations and GraphML node declarations."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from xml.etree.ElementTree import iterparse

from bench.map_datahub_coverage import CITATION, SourceIndex, read_evidence


ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / 'bench/results/datahub_graph_v2.graphml'
GRAPH_SHA = '71067cb3598e40b2be00c3a4f8b3f3557f03172a3dcd9b9a462cba59894dd162'
LABELS = ROOT / 'bench/labels/datahub_egpot_queries.json'
SOURCE = Path('C:/dev/egpot_repos/datahub')
DRAFTS = SOURCE.parent / 'labels_draft'
EVIDENCE = DRAFTS / 'datahub_source_evidence_v2.md'
QUERIES = DRAFTS / 'datahub_label_draft_v1.md'
NS = '{http://graphml.graphdrawing.org/xmlns}'
NODE_FIELDS = {'type', 'file', 'name', 'line_no', 'line_end', 'method', 'path', 'overload_group'}


def graph_records(path, *, node_fields=None, edges=True):
    """Stream scalar GraphML values without retaining the XML document tree."""
    keys = {}
    cast = {'boolean': lambda x: x.lower() in {'true', '1'}, 'int': int, 'long': int,
            'float': float, 'double': float, 'string': str}
    for event, elem in iterparse(path, events=('start', 'end')):
        tag = elem.tag.removeprefix(NS)
        if event == 'start':
            if tag == 'graph':
                parent = elem
            continue
        if tag == 'key':
            keys[elem.get('id')] = (elem.get('attr.name'), cast[elem.get('attr.type', 'string')])
        if tag not in {'node', 'edge'}:
            continue
        if tag == 'edge' and not edges:
            break  # These exports declare all nodes before their edges.
        attrs = {}
        for child in elem:
            if child.tag != NS + 'data':
                continue
            name, convert = keys[child.get('key')]
            if tag == 'edge' or node_fields is None or name in node_fields:
                attrs[name] = convert(child.text if child.text is not None else '')
        identity = (elem.get('id'),) if tag == 'node' else (elem.get('source'), elem.get('target'), elem.get('id'))
        yield tag, identity, attrs
        parent.remove(elem)


def markdown_rows(path):
    for line in path.read_text(encoding='utf8').splitlines():
        cells = [cell.strip() for cell in line.split('|')[1:-1]]
        if len(cells) == 7 and re.fullmatch(r'DH\d\d', cells[0]):
            yield cells


def lookalike(index, evidence, root):
    text = evidence['lookalike']
    file, line = CITATION.search(text).groups()
    line = int(line)
    quoted = text.split('`')[1]
    contents = (root / file).read_text(encoding='utf8')
    if file.endswith(('.graphql', '.gql')):
        from graphql import parse

        names = [f'{definition.name.value}.{field.name.value}' for definition in parse(contents).definitions
                 for field in getattr(definition, 'fields', ()) or () if field.name.value == quoted and
                 contents.count('\n', 0, field.name.loc.start) + 1 == line]
        if len(names) != 1:
            raise ValueError(f'Cannot resolve SDL lookalike {file}:{line}: {quoted}')
        return index.contract(names[0], [(file, line)])['id']
    if ' ' in quoted:
        words = quoted.split()
        quoted = words[0] + ''.join(word.title() for word in words[1:])
        if not re.search(r'\b' + re.escape(quoted) + r'\s*\(', '\n'.join(contents.splitlines()[line-1:line+8])):
            raise ValueError(f'Cannot verify prose lookalike at {file}:{line}')
    return index.declaration((file, line, quoted))['id']


def make_labels(nodes, source=SOURCE, evidence_path=EVIDENCE, queries_path=QUERIES):
    index = SourceIndex(nodes)
    evidence = read_evidence(evidence_path)
    drafts = {row[0]: row[-2:] for row in markdown_rows(queries_path)}
    scopes = {row[0]: row[-2] for row in markdown_rows(evidence_path)}
    out = []
    for row in evidence:
        link = row['id']
        start = index.declaration(row['caller'])['id']
        contract = index.contract(row['contract_name'], row['contract_citations'])['id']
        handler = index.declaration(row['handler'])['id']
        decoy = lookalike(index, row, source)
        if not all((start, contract, handler, decoy)):
            raise ValueError(f'{link}: at least one cited declaration did not resolve')
        guard = re.match(r'[A-Za-z]+', scopes[link])[0].lower()
        if guard not in {'guarded', 'unconditional'}:
            raise ValueError(f'{link}: unknown scope class {guard!r}')
        for kind, query in zip(('explicit', 'indirect'), drafts[link], strict=True):
            out.append(dict(id=f'{link}-{kind}', link_id=link, type=kind, query=query,
                            start_node=start, gold_nodes=[contract, handler], gold_path=[start, contract, handler],
                            lookalike_ids=[decoy], module_pair=row['pair'], guard_class=guard,
                            label_status='source_verified'))
    return out


def identifier_leaks(query, evidence):
    """Flag identifier literals and separated camel/snake spellings, not common words."""
    identifiers = [evidence['caller'][2], evidence['contract_name'], evidence['handler'][2]]
    if 'hook' in evidence:
        identifiers.extend((evidence['hook'], evidence['operation'][1]))

    def tokens(text):
        text = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', text)
        text = re.sub(r'([a-z\d])([A-Z])', r'\1 \2', text)
        return re.findall(r'[a-z\d]+', text.lower())

    raw = query.lower()
    words = ' '.join(tokens(query))
    result = set()
    for identifier in identifiers:
        for atom in (identifier, *re.findall(r'[\w]+', identifier)):
            parts = tokens(atom)
            identifier_like = len(parts) > 1 or bool(re.search(r'[/_.]|[a-z][A-Z]', atom))
            if not identifier_like:
                continue
            if re.search(r'(?<!\w)' + re.escape(atom.lower()) + r'(?!\w)', raw):
                result.add(atom)
            elif len(parts) > 1 and re.search(r'\b' + ' '.join(parts) + r'\b', words):
                result.add(atom)
    return sorted(result)


def validate_labels(rows, evidence):
    pairs = Counter((r['link_id'], r['type']) for r in rows)
    expected = {(r['id'], kind) for r in evidence for kind in ('explicit', 'indirect')}
    if set(pairs) != expected or set(pairs.values()) != {1}:
        raise ValueError('expected one explicit and indirect query per source link')
    by_id = {r['id']: r for r in evidence}
    return {r['id']: leaks for r in rows if r['type'] == 'indirect'
            and (leaks := identifier_leaks(r['query'], by_id[r['link_id']]))}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + '\n',
                    encoding='utf8', newline='\n')


def main():
    if sha(GRAPH) != GRAPH_SHA:
        raise ValueError('DataHub graph hash mismatch')
    rows = make_labels((key[0], attrs) for _, key, attrs in graph_records(
        GRAPH, node_fields=NODE_FIELDS, edges=False))
    evidence = read_evidence(EVIDENCE)
    if leaks := validate_labels(rows, evidence):
        raise ValueError(f'Indirect identifier leaks: {leaks}')
    write_json(LABELS, rows)
    write_json(LABELS.with_suffix('.provenance.json'), {
        'graphml_sha256': GRAPH_SHA, 'query_file_sha256': sha(LABELS),
        'source_evidence_sha256': sha(EVIDENCE), 'query_draft_sha256': sha(QUERIES),
        'mapping': 'source path, line and qualified declaration name; no graph edges read',
        'leak_audit_source_identifiers': [{k: row[k] for k in (
            'id', 'caller', 'handler', 'contract_name', 'hook', 'operation') if k in row}
            for row in evidence],
    })
    print(len(rows), sha(LABELS))


if __name__ == '__main__':
    main()
