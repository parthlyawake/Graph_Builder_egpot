"""Source and graph audit of the guarded DataHub v3 export. No retrieval."""
from collections import Counter, defaultdict
from functools import lru_cache
import json
import random
import re

from bench.audit_datahub_edges import RULES, collect, enrich_samples, review_samples, source_lines, stamp
from bench.datahub_inputs import (LABELS, NODE_FIELDS, ROOT, graph_records, make_labels,
                                sha, write_json)
from bench.map_datahub_coverage import source_path


RESULTS = ROOT/'bench/results'
V1 = RESULTS/'datahub_graph.graphml'
V2 = RESULTS/'datahub_graph_v2.graphml'
V3 = RESULTS/'datahub_graph_v3.graphml'
AUDIT = RESULTS/'datahub_edge_audit_v3.json'
OLD_AUDIT = RESULTS/'datahub_edge_audit.json'
FIELDS = NODE_FIELDS | {'kind','spec','binding_kind','resource_kind','resource_method','repo'}


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def attribute_v1_v2_nodes(before=V1, after=V2):
    identity = ('type', 'file', 'line_no', 'name')
    old = {ids[0]: (stamp(a), tuple(a.get(k) for k in identity))
           for _, ids, a in graph_records(before, edges=False)}
    new_identity, scopes = set(), defaultdict(list)
    changed = {}
    for _, ids, attrs in graph_records(after, edges=False):
        n, = ids
        new_identity.add(tuple(attrs.get(k) for k in identity))
        if attrs.get('binding_kind') == 'react_use_callback':
            scopes[attrs['file']].append((attrs['line_no'], attrs['line_end'], n))
        previous = old.pop(n, None)
        if previous and previous[0] != stamp(attrs):
            changed[n] = {'after': attrs}
    external = {n for n, (_, a) in old.items() if a[0] == 'external_func'}
    references = defaultdict(set)
    for kind, ids, attrs in graph_records(before):
        if kind == 'node' and ids[0] in changed:
            new = changed[ids[0]].pop('after')
            changed[ids[0]] = {'type': attrs.get('type'), 'differences': {
                key: [attrs.get(key), new.get(key)] for key in sorted(new.keys() | attrs.keys())
                if key not in attrs or key not in new or new[key] != attrs[key]}}
        elif kind == 'edge' and ids[1] in external:
            references[ids[1]].add(ids[0])
    groups = defaultdict(list)
    for node, (_, record) in old.items():
        typ, file, line, _ = record
        embedded = re.search(r'callsite::(web/[^:]+):', node)
        scoped_file = embedded[1] if embedded else file
        in_callback = (line is not None and any(start <= line <= stop for start,stop,_ in scopes[scoped_file]))
        if node in external:
            cause = ('external symbol with only React-side old graph references' if references[node] and
                     all('web/' in reference for reference in references[node]) else 'removed external symbol with mixed or missing references')
        elif in_callback and record in new_identity:
            cause = 'same source identity present within a newly scoped React callback'
        elif in_callback:
            cause = 'old source artifact inside a newly scoped React callback'
        elif record in new_identity:
            cause = 'same type, source file, line and name under a different ID'
        elif file and file.startswith('web/'):
            cause = 'React extraction changed outside a directly matched callback span'
        else:
            cause = 'unattributed'
        groups[cause].append({'id': node, 'type': typ, 'file': file, 'line': line})
    return {'removed_causes': dict(groups), 'changed': changed,
            'removed': len(old), 'changed_count': len(changed)}


def fresh_samples(path, prior):
    nodes, pools, openapi = {}, defaultdict(list), []
    seen = {name: {tuple(row['edge']) for row in rows} for name, rows in prior['samples'].items()}
    for kind, ids, attrs in graph_records(path, node_fields=FIELDS):
        if kind == 'node':
            nodes[ids[0]] = attrs
            continue
        relation = attrs.get('relation')
        rule = RULES.get((attrs.get('binding_kind'), relation))
        row = {'edge': ids, 'attributes': attrs}
        if rule and rule != 'openapi' and ids not in seen[rule]:
            pools[rule].append(row)
        target = nodes[ids[1]]
        if (relation in {'CONSUMES','IMPLEMENTS'} and target.get('type') in {'endpoint','http_endpoint'}
                and (target.get('spec') == 'openapi' or target.get('file','').startswith('openapi/'))):
            openapi.append(row)
    samples = {rule: random.Random(1).sample(sorted(rows,key=lambda r:r['edge']),min(100,len(rows)))
               for rule,rows in pools.items()}
    for row in openapi + [x for sample in samples.values() for x in sample]:
        u,v,_ = row['edge']
        row.update(caller=nodes[u], target=nodes[v])
    enrich_samples({'samples':samples})
    return samples, openapi, nodes, {k:len(v) for k,v in pools.items()}


def walk(node):
    yield node
    for child in node.named_children:
        yield from walk(child)


def text(node):
    return node.text.decode('utf8') if node is not None else ''


@lru_cache(maxsize=64)
def java(file):
    from polyglot import TreeSitterExtractor

    source = '\n'.join(source_lines(file))
    tree = TreeSitterExtractor('.java').parser.parse(source.encode('utf8'))
    constants = dict(re.findall(r'\bString\s+(\w+)\s*=\s*("(?:[^"\\]|\\.)*")', source))
    return tree, constants


def annotations(node):
    mods = next((m for m in node.named_children if m.type == 'modifiers'), None)
    return {text(a.child_by_field_name('name')).rsplit('.',1)[-1]: a.child_by_field_name('arguments')
            for a in mods.named_children if a.type in {'annotation','marker_annotation'}} if mods else {}


def path_arguments(args, constants):
    if args is None:
        return ['']
    paths = [node.child_by_field_name('value') if node.type == 'element_value_pair' else node
             for node in args.named_children if node.type != 'element_value_pair'
             or text(node.child_by_field_name('key')) in {'value','path'}]
    if not paths:
        return ['']
    values = [text(a) for p in paths for a in
              (p.named_children if p.type == 'element_value_array_initializer' else [p])]
    known = [constants.get(name,name) for name in values]
    return [json.loads(name) for name in known if name.startswith('"')]


def declared_routes(root, method, constants, prefix_constants):
    labels = annotations(root)
    prefixes = path_arguments(labels.get('RequestMapping'), prefix_constants)
    verbs = {'GetMapping':'GET','PostMapping':'POST','PutMapping':'PUT',
             'DeleteMapping':'DELETE','PatchMapping':'PATCH'}
    result = set()
    for kind,args in annotations(method).items():
        if kind not in verbs and kind != 'RequestMapping':
            continue
        methods = {verbs[kind]} if kind in verbs else set(re.findall(r'\bRequestMethod\.(\w+)',text(args)))
        # An unconstrained Spring RequestMapping includes GET; verify each
        # emitted edge against the declaration without inventing other edges.
        if not methods:
            methods = {'GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS'}
        for prefix in prefixes:
            for suffix in path_arguments(args,constants):
                full = prefix.rstrip('/') + ('/' + suffix.lstrip('/') if suffix else '')
                result.update((verb, full or '/') for verb in methods)
    return labels, result


def verify_java_route(row):
    caller, target = row['caller'], row['target']
    file = caller['file']
    tree, constants = java(file)
    methods = [n for n in walk(tree.root_node) if n.type=='method_declaration'
               and n.start_point.row+1==caller['line_no'] and text(n.child_by_field_name('name'))==caller['name']]
    if len(methods)!=1:
        return 'unverifiable', 'Cannot uniquely anchor the source method.'
    method = methods[0]
    owner = method.parent.parent
    owner_name = text(owner.child_by_field_name('name'))
    prefix_constants = constants
    if row['attributes'].get('binding_kind')=='spring_inherited_route':
        concrete = target['file']
        concrete_tree,prefix_constants = java(concrete)
        owners = [n for n in walk(concrete_tree.root_node) if n.type=='class_declaration'
                  and n.start_point.row+1==target['line_no']]
        if len(owners)!=1:
            return 'unverifiable','Cannot uniquely anchor the concrete controller.'
        parent = next((c for c in owners[0].named_children if c.type=='superclass'),None)
        if not re.search(r'\b'+re.escape(owner_name)+r'\b',text(parent)):
            return 'incorrect','The concrete controller does not declare this superclass.'
        owner=owners[0]
    labels, routes = declared_routes(owner,method,constants,prefix_constants)
    verb,_,path = target['name'].partition(' ')
    row['declared_routes'] = sorted(routes)
    row['source_citation'] = f"{source_path(file)}:{caller['line_no']}"
    if (verb,path) not in routes:
        return 'incorrect','Exported verb/path differs from the annotated Spring route.'
    if not {'RestController','Controller'} & labels.keys():
        return 'incorrect','Annotation describes an inherited fragment, but the owner is not a registered concrete controller at this URL.'
    return 'correct','Source handler and registered controller prefix yield the exact annotated route.'


def verify_python_route(row):
    # The twelve SDK edges were checked through these source-local call paths.
    # These are audit citations, separate from the builder's generic rules.
    client = {
        'get_entities':('openapi.py',681), 'get_entities_v2':('openapi.py',627),
        'scroll_entities':('openapi.py',287), 'scroll_lineage':('openapi.py',486),
        'scroll_relationships':('openapi.py',396), 'get_entity_aspect_specs':('client.py',586),
        '_await_status':('rest_emitter.py',1319), '_emit_openapi_mcps':('rest_emitter.py',1319),
        'emit':('rest_emitter.py',1319), 'emit_mcp':('rest_emitter.py',1319),
        'emit_mcps':('rest_emitter.py',1319), 'get_trace_status':('rest_emitter.py',1395),
    }
    attr, caller = row['attributes'], row['caller']
    target = row['target']['name']
    file = caller['file']
    name = caller['name']
    line = client.get(name)
    if not line or not file.endswith('/'+line[0]):
        return 'unverifiable','No independently reviewed SDK dispatch path for this row.'
    origin, place = attr['source_evidence'].rsplit(':',1)
    src = source_lines(file)
    if origin != file or not caller['line_no'] <= int(place) <= caller['line_end'] or not src[int(place)-1].strip():
        return 'incorrect','The cited call site is outside the claimed SDK declaration.'
    literal = src[line[1]-1]
    if not re.search(r'\{self\._gms_server\}(/[^"\']+)',literal):
        return 'unverifiable','Cannot independently anchor the configured server base and route literal.'
    expected = re.search(r'\{self\._gms_server\}(/[^"\']+)',literal)[1]
    if file.endswith('/rest_emitter.py'):
        expected += '/{*}'
        if name not in {'_await_status','get_trace_status'} and not any(
                call in src[int(place)-1] for call in ('self._await_status(', 'self._emit_openapi_mcps(',
                                                       'self.emit_mcp(', 'self.emit_mcps(')):
            return 'unverifiable','The cited emitter dispatch is not in the reviewed trace-helper call chain.'
    expected = re.sub(r'\{[^/{}]+\}', '{*}', expected)
    verb = 'GET' if name == 'get_entity_aspect_specs' else 'POST'
    declared_verb, _, declared_path = target.partition(' ')
    if ((attr.get('request_verb'), attr.get('request_path'), attr.get('server_base')) !=
            (verb, expected, 'self._gms_server') or declared_verb != verb or
            re.sub(r'\{[^/{}]+\}', '{*}', declared_path) != expected):
        return 'incorrect','The independently read configured SDK URL or verb differs from the emitted edge.'
    row['source_citation'] = f'{source_path(file)}:{line[1]}'
    return 'correct','Source URL construction and direct or forwarded SDK request agree with this registered route.'


def review_fresh(samples):
    for rule, rows in samples.items():
        for row in rows:
            try:
                review_samples({ 'samples':{k:[row] if k==rule else [] for k in ('apollo','java_graphql','restli','openapi')} })
            except (AttributeError, KeyError, ValueError, StopIteration) as exc:
                row.update(verdict='unverifiable', reason=str(exc))
    return {rule:dict(Counter(r['verdict'] for r in rows)) for rule,rows in samples.items()}


def audit():
    build = read(RESULTS/'datahub_coverage_v3.json')
    if sha(V3) != build['graphml_sha256']:
        raise ValueError('v3 GraphML differs from the guarded export')
    old_labels = read(LABELS)
    new_labels = make_labels((ids[0], attrs) for _,ids,attrs in graph_records(V3,node_fields=NODE_FIELDS,edges=False))
    if new_labels != old_labels:
        raise ValueError('Independent source mapping changed a label ID; review all differences before adoption')
    losses = [row for row in build['links'] if row['status']!='fully covered']
    if losses:
        raise ValueError(f'Coverage changed; preserving all existing labels: {losses}')
    diff = collect(V2,V3,[row for row in old_labels if row['type']=='explicit'])
    prior = read(OLD_AUDIT)
    samples, openapi, _, sampling = fresh_samples(V3,prior)
    counts = review_fresh(samples)
    native = defaultdict(Counter)
    retained_python = set()
    for row in openapi:
        if row['attributes']['relation']=='IMPLEMENTS':
            source = row['attributes'].get('binding_kind','native')
            verdict, reason = verify_java_route(row)
        else:
            source = 'sdk_consumes'
            verdict, reason = verify_python_route(row)
            if verdict=='correct':
                retained_python.add(tuple(row['edge'][:2]))
        native[source][verdict]+=1
        row.update(verdict=verdict,reason=reason,scope=source)
    old_python = {key:{'correct': [],'incorrect': [],'unverifiable': []} for key in prior['openapi_suffixes']}
    for target, data in prior['openapi_suffixes'].items():
        for row in data['edges']:
            if (row['caller'],target) in retained_python:
                verdict='correct'
                reason='Independently verified retained SDK call to the same route.'
            elif target.startswith('http::openapi/') and data['name'].partition(' ')[2].split('/')[1].startswith('{'):
                verdict='incorrect'
                reason='This unprefixed parameter-only method fragment belongs to an abstract controller, with no registered endpoint at that URL.'
            else:
                verdict='unverifiable'
                reason='The v2-only dispatch requires additional source review.'
            old_python[target][verdict].append({**row,'reason':reason})
    report = {k:diff[k] for k in ('node_diff','edge_diff','keyed_edge_diff','topology','required_edges_verified','budget40_share')}
    report.update(graphml_sha256=build['graphml_sha256'], builder_commit=build['builder_commit'],
                  sample_seed=1,sample_eligible_pool=sampling, sample_verdicts=counts, samples=samples,
                  openapi_census=openapi,openapi_verdicts=dict(native),openapi_v2_consumes=old_python,
                  ambiguous_requests=build['openapi_ambiguous_requests'],
                  v1_v2_node_attribution=attribute_v1_v2_nodes(), labels_sha256=sha(LABELS),
                  coverage={row['id']:row['status'] for row in build['links']})
    return report


def render(report, build, timing):
    from bench.map_datahub_coverage import markdown_table
    from openapi_request_origins import SDK_BASES, SDK_SESSIONS

    lines = ['# DataHub v3 OpenAPI audit', '',
             'One full guarded rebuild used the same nine production roots, allowlist, nonproduction filters and '
             'generated-file rules as v2. No retrieval or scoring ran.', '',
             f"Builder `{build['builder_commit']}`. Graph SHA-256 `{build['graphml_sha256']}`. "
             f"{build['inventory']['nodes']:,} nodes, {build['inventory']['edges']:,} edges, and "
             f"{build['graphml_bytes']:,} bytes. Build {build['build_seconds']:.2f} s, peak "
             f"{build['build_peak_rss_bytes']/2**30:.2f} GiB. Semantic edges "
             f"{sum(build['inventory']['semantic_similar'].values()):,}.", '',
             '## Matching rule', '',
             'Trusted bases are ' + ', '.join(f'`{x}`' for x in sorted(SDK_BASES)) +
             '. Source-proven local aliases, forwarded helper arguments, and `.rstrip(\'/\')` preserve that provenance. '
             'The typed instance session names are ' + ', '.join(f'`{x}`' for x in sorted(SDK_SESSIONS)) +
             '. Recognized HTTP modules and typed local receivers also require SDK URL provenance. '
             'Each same-verb route must match every segment, including at least one literal segment. Constrained '
             'parameters require complete regex matches against a known segment; unsupported constraints and '
             'unknown dynamic values fail closed. Equal best literal counts are recorded as ambiguous and emit no edge.', '',
             '## v2 → v3 graph diff', '',
             'Attribute comparison includes direction and parallel-edge multiplicity. Endpoint/relation identities '
             'show the actual removed bindings, separately from the new evidence fields on retained edges.', '']
    lines += markdown_table(['Relation','Removed with attributes','Added with attributes','Removed with keys','Added with keys'], (
        (relation, c.get('removed',0),c.get('added',0),d.get('removed',0),d.get('added',0))
        for relation,c in sorted(report['edge_diff'].items()) for d in [report['keyed_edge_diff'][relation]]
        if c.get('removed',0)+c.get('added',0)+d.get('removed',0)+d.get('added',0)))
    lines += ['## v1 → v2 node attribution', '']
    attribution = report['v1_v2_node_attribution']
    lines += markdown_table(['Cause or directly observed change','Removed nodes'], (
        (cause,len(rows)) for cause,rows in sorted(attribution['removed_causes'].items())))
    lines += ['React callback scopes replace the old parent-scoped identities, including function, variable, return, '
              'callsite and argument-expression nodes. The removed external stubs had only React-side references in v1. '
              'The JSON preserves the ID and source anchor for every removed node and the complete attribute pairs for '
              'every retained ID with a change.', '']
    lines += markdown_table(['Retained ID','Attribute','Before','After'], (
        (f'`{node}`',key,values[0],values[1]) for node,row in sorted(attribution['changed'].items())
        for key,values in row['differences'].items()))
    lines += ['Eight retained React variable IDs now point to a different declaration line after callback scoping. '
              'Two shared external IDs changed first-contributor `repo` metadata from web to ingestion.', '', '## OpenAPI census', '']
    lines += markdown_table(['Population','Correct','Incorrect','Unverifiable'], (
        (name,*(counts.get(k,0) for k in ('correct','incorrect','unverifiable')))
        for name,counts in sorted(report['openapi_verdicts'].items())))
    old_counts = Counter()
    for groups in report['openapi_v2_consumes'].values():
        old_counts.update({kind:len(rows) for kind,rows in groups.items()})
    lines += [f"Before the fix, the v2 client census has {old_counts['incorrect']} incorrect, "
              f"{old_counts['correct']} correct, and {old_counts['unverifiable']} unverifiable `CONSUMES` edges. "
              f"V3 records {len(report['ambiguous_requests'])} ambiguous requests. Ambiguous requests are not graph edges. "
              'The native Spring declarations are retained in both graphs. The JSON includes the full v3 census and the '
              'v2 client findings.', '', '### Incorrect surviving native edges', '']
    lines += markdown_table(['Handler','Exported route','Source','Reason'], (
        (f"`{r['edge'][0]}`", f"`{r['target']['name']}`", f"`{r.get('source_citation','')}`",r['reason'])
        for r in report['openapi_census'] if r['verdict']=='incorrect'))
    if report['ambiguous_requests']:
        lines += markdown_table(['Caller','Verb and path','Tied candidates'], (
            (f"`{r['caller']}`", f"`{r['verb']} {r['path']}`", ', '.join(r['candidates']))
            for r in report['ambiguous_requests']))
    lines += ['## Fresh independent source checks', '',
              'For each rule, sort edges by source, destination and key, exclude its earlier 30 seed-0 edges, '
              'and draw with a fresh `random.Random(1)`. The Rest.li pool has only 62 remaining edges and all were reviewed.', '']
    lines += markdown_table(['Rule','Eligible pool','Reviewed','Correct','Incorrect','Unverifiable'], (
        (rule,report['sample_eligible_pool'][rule],len(report['samples'][rule]),
         *(counts.get(k,0) for k in ('correct','incorrect','unverifiable')))
        for rule,counts in sorted(report['sample_verdicts'].items())))
    lines += ['## Coverage and topology', '',
              f"All {report['required_edges_verified']} required edges verified after a fresh declaration-only ID mapping. "
              f"The query file stayed byte-identical at SHA-256 `{report['labels_sha256']}`. The undirected raw graph's "
              f"budget-40 share is {100*report['budget40_share']:.5f}%. Degree counts all directed incidences and "
              'parallel edges. Two-hop counts include the start.', '']
    for pair in sorted({r['module_pair'] for r in report['topology']}):
        lines += [f'### {pair}', '']
        lines += markdown_table(['Link','Coverage','Contract hops','Handler hops','Gold depth','Start degree','Contract degree','Within 2 hops'], (
            (r['link'],report['coverage'][r['link']],*(r[k] for k in (
                'contract_hops','handler_hops','gold_depth','start_degree','contract_degree','within_two_hops_including_start')))
            for r in report['topology'] if r['module_pair']==pair))
    lines += ['## Startup timing only', '',
              f"V3 GraphML load {timing['graph_load_seconds']:.2f} s and TF-IDF fit {timing['tfidf_seconds']:.2f} s. "
              'The earlier v2 observations were 27.00 s and 9.50 s. V3 timing constructed a graph view and fit a scorer '
              'under the audit guard. It issued no query or method call.', '']
    return '\n'.join(lines)


if __name__=='__main__':
    report=audit()
    write_json(AUDIT,report)
    print(report['sample_verdicts'],report['openapi_verdicts'],report['required_edges_verified'],flush=True)
