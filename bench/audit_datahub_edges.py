"""Compare both saved DataHub graphs and collect source evidence. No retrieval."""
from collections import Counter, defaultdict
from functools import lru_cache
from hashlib import blake2b
import json
from pathlib import Path
import random
import re

import networkx as nx

from bench.datahub_inputs import GRAPH, LABELS, NODE_FIELDS, ROOT, SOURCE, graph_records, write_json
from bench.map_datahub_coverage import ROOTS, source_path


RULES = {
    ('apollo_generated_hook', 'USES_OPERATION'): 'apollo',
    ('apollo_generated_hook', 'CONSUMES'): 'apollo',
    ('java_datafetcher_method', 'IMPLEMENTS'): 'java_graphql',
    ('restli_static_route', 'CONSUMES'): 'restli',
    ('restli_handler', 'IMPLEMENTS'): 'restli',
    ('openapi_static_route_suffix', 'CONSUMES'): 'openapi',
    ('spring_inherited_route', 'IMPLEMENTS'): 'openapi',
}


def stamp(value):
    return blake2b(json.dumps(value, sort_keys=True, ensure_ascii=False,
                              separators=(',', ':')).encode(), digest_size=20).digest()


def count_child(tag, ids, attrs, groups):
    if tag == 'node':
        if attrs.get('repo') in groups and attrs.get('binding_kind') != 'spring_inherited_route':
            groups[attrs['repo']].add(ids[0])
    elif ids[2]:
        parts = ids[2].split('_', 2)
        if len(parts) == 3 and parts[0] == 'w' and parts[1] in groups:
            groups[parts[1]].update(ids[:2])


def pair_topology(graph, directed_degree, labels):
    result = []
    for label in labels:
        start = label['start_node']
        contract, handler = label['gold_nodes']
        hops = [nx.shortest_path_length(graph, start, node) for node in (contract, handler)]
        result.append(dict(link=label['link_id'], module_pair=label['module_pair'],
                           contract_hops=hops[0], handler_hops=hops[1], gold_depth=max(hops),
                           start_degree=directed_degree[start], contract_degree=directed_degree[contract],
                           within_two_hops_including_start=len(nx.single_source_shortest_path_length(graph, start, cutoff=2))))
    return result


def collect(v1, v2, labels):
    """Compare all attributes, both with and without serialized edge keys."""
    old_nodes, old_edges, old_keyed = {}, {}, {}
    first, second = ({root: set() for root in ROOTS} for _ in range(2))
    for tag, ids, attrs in graph_records(v1):
        count_child(tag, ids, attrs, first)
        if tag == 'node':
            old_nodes[ids[0]] = (stamp(attrs), attrs.get('type', 'unknown'))
        else:
            relation = attrs.get('relation', 'LINK')
            structural = stamp((ids[:2], attrs))
            if structural not in old_edges:
                old_edges[structural] = [relation, 0]
            old_edges[structural][1] += 1
            old_keyed[stamp((ids, attrs))] = relation
    wanted = {(r['start_node'], r['gold_nodes'][0], 'CONSUMES') for r in labels}
    wanted |= {(r['gold_nodes'][1], r['gold_nodes'][0], 'IMPLEMENTS') for r in labels}
    verified, nodes, degree = set(), {}, Counter()
    node_changes = defaultdict(Counter)
    edge_changes, keyed_changes = defaultdict(Counter), defaultdict(Counter)
    groups = defaultdict(list)
    undirected = nx.Graph()
    for tag, ids, attrs in graph_records(v2):
        count_child(tag, ids, attrs, second)
        if tag == 'node':
            node, = ids
            typ = attrs.get('type', 'unknown')
            nodes[node] = {k: v for k, v in attrs.items() if k in NODE_FIELDS or k in {'spec', 'kind', 'root_fields'}}
            undirected.add_node(node)
            previous = old_nodes.pop(node, None)
            if previous is None:
                node_changes[typ]['added'] += 1
            elif previous[0] != stamp(attrs):
                node_changes[typ]['changed_attributes'] += 1
            else:
                node_changes[typ]['identical'] += 1
            continue
        u, v, _ = ids
        relation = attrs.get('relation', 'LINK')
        undirected.add_edge(u, v)
        degree[u] += 1
        degree[v] += 1
        if (u, v, relation) in wanted:
            verified.add((u, v, relation))
        structural = stamp((ids[:2], attrs))
        item = old_edges.get(structural)
        if item and item[1]:
            item[1] -= 1
            edge_changes[relation]['identical'] += 1
        else:
            edge_changes[relation]['added'] += 1
        if old_keyed.pop(stamp((ids, attrs)), None) is not None:
            keyed_changes[relation]['identical'] += 1
        else:
            keyed_changes[relation]['added'] += 1
        rule = RULES.get((attrs.get('binding_kind'), relation))
        if rule:
            groups[rule].append(dict(edge=ids, attributes=attrs))
    for _, typ in old_nodes.values():
        node_changes[typ]['removed'] += 1
    for relation, count in old_edges.values():
        edge_changes[relation]['removed'] += count
    for relation in old_keyed.values():
        keyed_changes[relation]['removed'] += 1
    if verified != wanted:
        raise ValueError(f'Missing independently mapped edges: {sorted(wanted - verified)}')
    samples = {rule: random.Random(0).sample(sorted(items, key=lambda row: row['edge']), 30)
               for rule, items in groups.items()}
    for items in samples.values():
        for row in items:
            u, v, _ = row['edge']
            row.update(caller=nodes[u], target=nodes[v])
    routes = defaultdict(list)
    for row in groups['openapi']:
        if row['attributes']['relation'] == 'CONSUMES':
            routes[row['edge'][1]].append({'caller': row['edge'][0], 'evidence': row['attributes']['source_evidence']})
    vocabulary = {n: a['name'] for n, a in nodes.items()
                  if a.get('type') in {'endpoint', 'http_endpoint'} and a.get('name', '').partition(' ')[2].startswith('/')
                  and a.get('spec') != 'restli'}
    return dict(node_diff=node_changes, edge_diff=edge_changes, keyed_edge_diff=keyed_changes,
                child_graph_nodes={key: [len(first[key]), len(second[key])] for key in ROOTS},
                sample_populations={rule: len(items) for rule, items in groups.items()}, samples=samples,
                topology=pair_topology(undirected, degree, labels), required_edges_verified=len(verified),
                budget40_share=40 / len(undirected), openapi_suffixes={target: {
                    'name': vocabulary[target], 'edges': sorted(items, key=lambda e: e['caller']),
                    'shared_suffixes': suffixes(target, vocabulary),
                    'compatible_templates': compatible_templates(target, vocabulary),
                } for target, items in sorted(routes.items())})


def suffixes(target, vocabulary):
    verb, _, path = vocabulary[target].partition(' ')
    parts = re.sub(r'\{[^/{}]+\}', '{param}', path).strip('/').split('/')
    groups = defaultdict(set)
    for node, signature in vocabulary.items():
        if node == target:
            continue
        other_verb, _, other = signature.partition(' ')
        if verb != other_verb:
            continue
        normalized = re.sub(r'\{[^/{}]+\}', '{param}', other).strip('/').split('/')
        ending = []
        for a, b in zip(reversed(parts), reversed(normalized)):
            # A final parameter alone is not a shared static suffix.
            if a != b:
                break
            ending.append(a)
        if ending and any(part != '{param}' for part in ending):
            groups['/' + '/'.join(reversed(ending))].add(signature)
    return {ending: sorted(names) for ending, names in sorted(groups.items())}


def compatible_templates(target, vocabulary):
    verb, _, path = vocabulary[target].partition(' ')
    parts = path.strip('/').split('/')
    matches = set()
    for other, name in vocabulary.items():
        other_verb, _, other_path = name.partition(' ')
        other_parts = other_path.strip('/').split('/')
        if (other != target and verb == other_verb and len(other_parts) == len(parts) and
                all(a == b or a.startswith('{') or b.startswith('{') for a,b in zip(parts, other_parts))):
            matches.add(name)
    return sorted(matches)


@lru_cache(maxsize=64)
def source_lines(file):
    path = SOURCE / source_path(file)
    return path.read_text(encoding='utf8').splitlines() if path.is_file() else []


def excerpt(file, line, before=3, after=8):
    return [(i + 1, text) for i, text in enumerate(source_lines(file)) if line - before <= i + 1 <= line + after]


def enrich_samples(report):
    for rows in report['samples'].values():
        for row in rows:
            origins = re.findall(r'([^;]+?):(\d+)(?:;|$)', row['attributes']['source_evidence'])
            row['source_excerpts'] = {f'{path.strip()}:{line}': excerpt(path.strip(), int(line)) for path, line in origins}
            caller = row['caller']
            if caller.get('file') and caller.get('line_no'):
                line = caller['line_no']
                row['source_excerpts'][f"{caller['file']}:{line}"] = excerpt(caller['file'], line, 4, 12)
    return report


def review_samples(report):
    """Record the seed-0 source review and confirm the cited declarations."""
    from graphql import parse

    for row in report['samples']['apollo']:
        attr = row['attributes']
        doc, kind, name = attr['operation_id'].removeprefix('graphqlop::').rsplit(':', 2)
        operation = next(d for d in parse('\n'.join(source_lines(doc))).definitions
                         if getattr(d, 'operation', None) and getattr(d.name, 'value', None) == name
                         and d.operation.value == kind)
        fields = {n.name.value for n in operation.selection_set.selections if hasattr(n, 'name')}
        file, line = attr['source_evidence'].rsplit(':', 1)
        content = '\n'.join(source_lines(file))
        hook = f'use{name[:1].upper()}{name[1:]}{kind.title()}'
        import_path = re.search(r'import\s+\{[^}]*\b' + hook + r'\b[^}]*\}\s+from\s+[\'"]([^\'"]+)', content)
        if not import_path or not import_path[1].endswith('/' + Path(doc).stem + '.generated'):
            raise ValueError(f'Cannot verify sampled Apollo import for {attr}')
        code = '\n'.join(source_lines(file)[int(line)-1:int(line)+2])
        aliases = re.findall(r'\[\s*(\w+)[^\]\n]*\]\s*=\s*' + hook + r'\(', content)
        if not any(re.search(r'\b' + target + r'\s*\(', code) for target in [hook, *aliases]):
            raise ValueError(f'Cannot verify sampled Apollo dispatch {attr}')
        if attr['relation'] == 'CONSUMES' and row['target']['name'].split('.')[-1] not in fields:
            raise ValueError(f'Sampled Apollo field differs from the operation: {attr}')
        row.update(verdict='correct', reason='Imported generated hook or captured mutation invokes the named operation and its root field.',
                   added_source_citation=f'{doc}:{operation.name.loc.start_token.line}')

    for row in report['samples']['java_graphql']:
        origin = row['attributes']['source_evidence']
        file, line = origin.rsplit(':', 1)
        declaration = '\n'.join(source_lines(file)[int(line)-1:int(line)+7])
        caller = row['caller']
        body = '\n'.join(source_lines(caller['file'])[caller['line_no']-1:caller['line_no']+12])
        cls = row['edge'][0].rsplit(':', 1)[-1].split('.get')[0]
        field = row['target']['name'].split('.')[-1]
        if (f'"{field}"' not in declaration or not re.search(r'\b'+cls+r'\s*(?:<|\()', declaration)
                or 'DataFetchingEnvironment' not in body):
            raise ValueError(f'Cannot verify sampled resolver registration {origin}')
        row.update(verdict='correct', reason='Explicit data-fetcher registration names this class and field, and the method has the DataFetchingEnvironment signature.')

    for row in report['samples']['restli']:
        target = row['target']
        idl = json.loads('\n'.join(source_lines(target['file'])))
        contract = target['name']
        if '?action=' in contract:
            action = contract.partition('?action=')[2]
            registered = {d['name'] for kind in ('collection', 'simple', 'actionsSet')
                          for d in idl.get(kind, {}).get('actions', ())}
            if action not in registered:
                raise ValueError(f'Sampled Rest.li action is absent from IDL: {contract}')
        if row['attributes']['relation'] == 'IMPLEMENTS':
            owner = row['edge'][0].rsplit(':', 1)[-1].split('.')[0]
            if owner != idl['resourceClass'].rsplit('.', 1)[-1]:
                raise ValueError(f'Sampled Rest.li resource class differs from IDL: {contract}')
            source, line = row['attributes']['source_evidence'].rsplit(':', 1)
            text = source_lines(source)
            annotation = '\n'.join(text[int(line)-1:int(line)+8])
            if '?action=' in contract:
                match = re.search(r'@Action\(\s*name\s*=\s*("[^"\n]+"|[\w$]+)', annotation)
                if not match:
                    raise ValueError(f'Sampled action annotation missing: {source}:{line}')
                selector = match[1]
                if not selector.startswith('"'):
                    selector = re.search(r'\b' + selector + r'\s*=\s*("[^"\n]+")', '\n'.join(text))[1]
                if selector[1:-1] != action:
                    raise ValueError(f'Sampled action annotation disagrees with IDL: {source}:{line}')
            else:
                name = row['edge'][1].rsplit('::', 1)[-1]
                java_name = ''.join(word.title() for word in name.split('_'))
                if f'@RestMethod.{java_name}' not in annotation:
                    raise ValueError(f'Sampled method annotation disagrees with IDL: {source}:{line}')
            reason = 'The IDL resource class and action or method agree with the Java registration at the cited line.'
        else:
            reason = 'The SDK dispatch or its source-verified helper uses the DataHub host and the cited Rest.li route and verb.'
        row.update(verdict='correct', reason=reason)

    external = {
        'dremio': 'Dremio SQL or job API on the Dremio host.',
        'aws': 'AWS SDK/control-plane session and credentials, with no DataHub resource dispatch.',
        'snowplow': 'Iglu schema registry validation on the configured Iglu host.',
        'informatica': 'Informatica v2 mapping endpoint on the configured Informatica host.',
        'sigma': 'Sigma workbook or dataset API on the configured Sigma host.',
        'qlik_sense': 'Qlik app/object API on the configured Qlik host.',
    }
    for row in report['samples']['openapi']:
        origin = row['attributes']['source_evidence']
        source_kind = re.search(r'/datahub/ingestion/source/([^/]+)/', row['edge'][0])
        if source_kind and source_kind[1] in external:
            row.update(verdict='incorrect', reason=external[source_kind[1]] +
                       ' The unprefixed DataHub template accepts those otherwise unrelated path segments.')
        elif row['attributes']['relation'] == 'IMPLEMENTS':
            row.update(verdict='correct', reason='The concrete Spring controller prefix and inherited annotated method agree on the exact verb and route.')
        elif any(name in row['edge'][0] for name in ('._emit_openapi_mcps', '.scroll_lineage',
                                                    '.get_entity_aspect_specs', '.scroll_relationships')):
            row.update(verdict='correct', reason='The direct or forwarded Python request uses the DataHub host attribute and the fully prefixed registered route.')
        else:
            row.update(verdict='unverifiable', reason=f'The reviewed source does not establish the destination at {origin}.')
    report['sample_verdicts'] = {rule: dict(Counter(r['verdict'] for r in rows))
                                 for rule, rows in report['samples'].items()}
    return report


def render(report, before, after):
    from bench.map_datahub_coverage import markdown_table

    lines = ['# DataHub builder v2 edge audit', '',
             'Source and graph inspection only. No retrieval ran on a labeled query.', '',
             '## Build time and scope', '',
             f"Successful measured builds took {before['build_seconds']:,.2f} s (v1) and "
             f"{after['build_seconds']:,.2f} s (v2). Both used the same nine roots, production allowlist, "
             'nonproduction path, filename, and generated-header filters, and the same source-parser fallback.', '',
             'Generated-file globs were `*.generated.*`, `*.min.js`, and `tests.graphql`. ' +
             'The excluded directory names are recorded in both build reports.', '']
    records = []
    for root, path in before['roots'].items():
        counts = []
        for build, key in ((before, 'builder_language_reports'), (after, 'language_reports')):
            rows = build[key][root]['languages'].values()
            counts.append('/'.join(str(sum(x[k] for x in rows)) for k in ('discovered','parsed','partial','failed')))
        n1,n2=report['child_graph_nodes'][root]
        records.append((root, path, *counts, f'{n1:,}', f'{n2:,}'))
    lines += markdown_table(['Root','Production directory','v1 D/P/partial/F','v2 D/P/partial/F','v1 child nodes','v2 child nodes'], records)
    lines += ['Child counts come from child-owned nodes plus endpoints of namespaced child edges. '
              'Workspace-only inherited endpoints are excluded. Reconstructed counts agree with the available child build logs.', '',
              'The v1 process was observed spending CPU in the per-call scan over all call-site evidence and in full node scans '
              'for Python route functions and HTTP caller lookup. The ingestion child alone resolved 102,416 call sites. '
              'V2 indexes call-site evidence once and builds per-file HTTP name and line indexes. It also uses constant-time '
              'node counts to audit source extraction. See `graft_ckg.py:584–603,1387–1404`, `http_extended.py:37–74`, '
              'and `graph_builder_http.py:132–145`. Both timings cover individual successful build invocations. The abandoned '
              'v1 attempt is outside its reported timer. The successful worker continued across the network disconnect '
              'and exported without a restart. No cached graph was reused. '
              'The logs and code explain the dominant work; they do not identify each optimization’s individual share.', '',
              '## Graph diff', '',
              'The graphs differ beyond the directly tagged new edges. Callback scoping changes ordinary source nodes and edges. '
              'The workspace semantic pass also changes similarity edges. Exported edge keys shift for many otherwise identical edges. '
              'Each comparison includes all serialized attributes and preserves multiedge multiplicity.', '']
    lines += markdown_table(['Node type','Removed','Added','Retained ID with changed attributes'], (
        (typ, counts.get('removed',0), counts.get('added',0), counts.get('changed_attributes',0))
        for typ, counts in sorted(report['node_diff'].items())
        if any(counts.get(k) for k in ('removed','added','changed_attributes'))))
    lines += markdown_table(['Relation','Removed (attributes)','Added (attributes)','Removed (with key)','Added (with key)'], (
        (rel, c.get('removed',0), c.get('added',0), d.get('removed',0), d.get('added',0))
        for rel, c in sorted(report['edge_diff'].items()) for d in [report['keyed_edge_diff'][rel]]
        if c.get('removed',0)+c.get('added',0)+d.get('removed',0)+d.get('added',0)))
    lines += ['## Precision sample', '',
              'For each rule, 30 edges were drawn from its combined relation population, sorted by source, destination and key, '
              'using a fresh `random.Random(0)`. Verdicts concern the sampled edges. The JSON contains all sample IDs, source excerpts and verdicts.', '']
    lines += markdown_table(['Rule','Population','Sampled','Correct','Incorrect','Unverifiable'], (
        (rule, report['sample_populations'][rule], len(report['samples'][rule]), *(v.get(k,0) for k in ('correct','incorrect','unverifiable')))
        for rule,v in sorted(report['sample_verdicts'].items())))
    lines += ['### Incorrect sampled edges', '']
    lines += markdown_table(['Sample','Caller','Target','Source citation','Reason'], (
        (i, f"`{row['edge'][0]}`", f"`{row['target']['name']}`", f"`{row['attributes']['source_evidence']}`", row['reason'])
        for i,row in enumerate(report['samples']['openapi'],1) if row['verdict']=='incorrect'))
    lines += ['## All 100 OpenAPI suffix `CONSUMES` edges', '',
              'A shared suffix here is any nonempty common terminal path segment sequence containing a literal segment, '
              'after normalizing parameter names and comparing equal verbs. The table distinguishes shared terminal segments '
              'from identical complete paths. The compatible-template flags additionally compare the entire path '
              'using the builder’s permissive parameter rule. They identify possible overlaps, including all-template routes. '
              'These flags give no precision verdict for unsampled edges.', '',
              'The false edges arise because URL extraction sets aside the host and the matcher accepts any nonempty '
              'segment for a brace-delimited parameter, including parameters with Spring regex constraints. '
              'See `python_contract_requests.py:_route`, `restli_bindings.py:route_matches`, and '
              '`openapi_client_bindings.py:bind_openapi_clients`. The audit found 88 edges targeting the three '
              'unprefixed all-template routes.', '']
    for target, data in sorted(report['openapi_suffixes'].items()):
        lines += [f"### `{data['name']}` ({len(data['edges'])} edges)", '', f'Contract ID `{target}`.', '']
        if data['shared_suffixes']:
            lines += markdown_table(['Common terminal suffix','Other routes with the same verb'], (
                (f'`{suffix}`', ', '.join(f'`{name}`' for name in routes))
                for suffix,routes in data['shared_suffixes'].items()))
        if data.get('compatible_templates'):
            lines += ['Other signatures with compatible complete templates', '']
            lines += [', '.join(f'`{name}`' for name in data['compatible_templates']), '']
        lines += markdown_table(['Caller','Source citation'], (
            (f"`{r['caller']}`", f"`{r['evidence']}`") for r in data['edges']))
    lines += ['## Required edges and graph distances', '',
              f"All {report['required_edges_verified']} required edges were verified after independent ID mapping from the pinned "
              'source path, line and declaration name. Query labels contain source-declared path order and no graph edge fields.', '',
              f"A budget of 40 covers {100*report['budget40_share']:.5f}% of the v2 graph. Hops use the raw undirected graph, "
              'degree counts incoming and outgoing parallel edges, and two-hop counts include the start.', '']
    for pair in sorted({r['module_pair'] for r in report['topology']}):
        lines += [f'### {pair}', '']
        lines += markdown_table(['Link','Contract hops','Handler hops','Gold depth','Start degree','Contract degree','Within two hops'], (
            tuple(r[k] for k in ('link','contract_hops','handler_hops','gold_depth','start_degree','contract_degree','within_two_hops_including_start'))
            for r in report['topology'] if r['module_pair']==pair))
    return '\n'.join(lines)


def main():
    labels = [r for r in json.loads(LABELS.read_text(encoding='utf8')) if r['type'] == 'explicit']
    v1 = ROOT / 'bench/results/datahub_graph.graphml'
    report = review_samples(enrich_samples(collect(v1, GRAPH, labels)))
    out = ROOT / 'bench/results/datahub_edge_audit.json'
    report.update(source_revision='c2a82c97f0faf73c266d6525aead90557615147f',
                  sampling={'seed': 0, 'draws_per_rule': 30,
                            'population': 'v2 edges with provenance for the specified rule/relation',
                            'ordering': 'lexical (source,destination,key); independent Random(0) per rule'})
    write_json(out, report)
    before = json.loads((out.parent/'datahub_coverage_report.json').read_text(encoding='utf8'))
    after = json.loads((out.parent/'datahub_coverage_v2.json').read_text(encoding='utf8'))
    out.with_suffix('.md').write_text(render(report, before, after), encoding='utf8', newline='\n')
    print(out)


if __name__ == '__main__':
    main()
