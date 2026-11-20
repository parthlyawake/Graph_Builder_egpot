"""Guarded DataHub coverage measurements, with no retrieval or scoring."""
from argparse import ArgumentParser
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from time import perf_counter
from unittest.mock import patch

from bench.map_datahub_coverage import (
    CITATION, EXCLUDED, EVIDENCE, IGNORE, RESULTS, REVISION, ROOTS, SOURCE,
    graph_facts, guard, inspect_links, inventory, markdown_table, peak_memory,
    read_evidence, source_scope, write_graphml,
)
from multi_repo import RepoConfig, WorkspaceCKGBuilder, WorkspaceConfig
import proto_compiler


def scoped_files(source, evidence_path):
    """Keep cited sources and direct imported or same-name Java declarations."""
    pinned = {file for file, _ in CITATION.findall(evidence_path.read_text(encoding='utf8'))
              if (source / file).is_file()}
    qualified_imports = set()
    for file in pinned:
        if file.endswith('.java'):
            text = (source / file).read_text(encoding='utf8')
            qualified_imports.update(re.findall(r'^import\s+([\w.]+)\s*;', text, re.M))
    names = {file.rsplit('/', 1)[-1] for file in pinned if file.endswith('.java')}
    import_paths = tuple('/' + name.replace('.', '/') + '.java' for name in sorted(qualified_imports))
    for root in ROOTS.values():
        for file in (source / root).rglob('*'):
            if not file.is_file() or any(p.lower() in EXCLUDED for p in file.relative_to(source).parts):
                continue
            rel = file.relative_to(source).as_posix()
            if (file.suffix in {'.graphql', '.gql'} or file.name.endswith('.restspec.json') or
                    file.name in names or rel.endswith(import_paths)):
                pinned.add(rel)
    return pinned


def measure(scoped):
    config = WorkspaceConfig(name='datahub-production-coverage-v2', base_dir=str(SOURCE),
                             repositories=[RepoConfig(name, rel) for name, rel in ROOTS.items()],
                             exclude_nonproduction=True, ignore_patterns=list(IGNORE),
                             contract_bindings_v2=True)
    builder = WorkspaceCKGBuilder(config)
    evidence = read_evidence(EVIDENCE)
    files = scoped_files(SOURCE, EVIDENCE) if scoped else None
    start = perf_counter()
    with (source_scope(SOURCE, files),
          patch.object(proto_compiler, 'compile_proto_file', return_value=(None, 'guarded source fallback'))):
        graph = builder.build()
    seconds = perf_counter() - start
    peak = peak_memory()
    links = inspect_links(graph, evidence)
    return graph, dict(
        source=REVISION, roots=ROOTS, ignore_globs=IGNORE, exclude_nonproduction=True,
        excluded_directory_components=sorted(EXCLUDED), build_seconds=seconds,
        build_peak_rss_bytes=peak, scoped=scoped, scoped_files=sorted(files) if files else None,
        inventory=inventory(graph), rules=graph.graph['contract_bindings_v2'], links=links,
        topology=graph_facts(graph, links),
        language_reports={name: b.get_language_report() for name, b in builder.repo_builders.items()},
    )


def coverage_signature(report):
    return {row['id']: row['status'] for row in report['links']}


def summary(before, after):
    pair_counts = {}
    for version, data in (('before', before), ('after', after)):
        for row in data['links']:
            pair_counts.setdefault(row['pair'], Counter())[(version, row['status'])] += 1
    statuses = ('fully covered', 'partly covered', 'not covered')
    lines = ['# DataHub builder v2 coverage', '',
             'Coverage is measured against the same 26 source-verified links. No retrieval or scoring ran.', '',
             '## Module pairs', '']
    lines += markdown_table(['Module pair', 'Before full', 'Before partial', 'Before absent',
                            'After full', 'After partial', 'After absent'], (
        (pair, *(c[version,status] for version in ('before', 'after') for status in statuses))
        for pair,c in sorted(pair_counts.items())))
    lines += ['## Per-link classes', '']
    original = coverage_signature(before)
    lines += markdown_table(['Link', 'Before', 'After', 'Remaining gap'], (
        (r['id'], original[r['id']], r['status'], ', '.join(r['missing']) or '—') for r in after['links']))
    lines += ['## Repo-wide additions', '']
    lines += markdown_table(['Rule', 'Counted additions', 'Count'], (
        (rule, field, value) for rule, values in sorted(after['rules'].items()) for field,value in sorted(values.items())))
    lines += ['Callback counts include new function nodes and their containment edges. The graph also reflects '
              'the normal extraction of callback bodies under their new function scopes.', '']
    if after.get('fixture_verification'):
        lines += ['## Existing source fixture identity', '',
                  'The frozen v1 and enabled v2 builds had identical digests over attributed nodes and keyed edges.', '']
        lines += markdown_table(['Fixture', 'Nodes', 'Edges', 'Graph digest'], (
            (name, row['nodes'], row['edges'], row['sha256'])
            for name, row in sorted(after['fixture_verification'].items())))
    same = not after['scoped_differences']
    lines += ['## Build verification', '',
              f"GraphML SHA-256 `{after['graphml_sha256']}` ({after['graphml_bytes']:,} bytes).", '',
              f"Scoped and full builds {'agreed' if same else 'differed'} on the coverage classes. "
              f"Scoped build {after['scoped_build_seconds']:.2f} s. Full build {after['build_seconds']:.2f} s, "
              f"peak working set {after['build_peak_rss_bytes']/2**30:.2f} GiB.", '',
              f"Nodes {before['inventory']['nodes']:,} → {after['inventory']['nodes']:,}. "
              f"Edges {before['inventory']['edges']:,} → {after['inventory']['edges']:,}. "
              f"SEMANTIC_SIMILAR {sum(before['inventory']['semantic_similar'].values()):,} → "
              f"{sum(after['inventory']['semantic_similar'].values()):,}.", '']
    return '\n'.join(lines)


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--full', action='store_true')
    parser.add_argument('--scoped-reference', type=str)
    parser.add_argument('--fixture-reference', type=str)
    args = parser.parse_args()
    if args.full and not args.scoped_reference:
        parser.error('--full requires the final scoped coverage JSON via --scoped-reference')
    if args.full:
        scoped = json.loads(Path(args.scoped_reference).read_text(encoding='utf8'))
        if not scoped.get('scoped') or scoped.get('source') != REVISION or len(coverage_signature(scoped)) != 26:
            parser.error('the scoped reference must cover the 26 pinned links')
        fixtures = json.loads(Path(args.fixture_reference).read_text(encoding='utf8')) if args.fixture_reference else None
        targets = [RESULTS / name for name in ('datahub_graph_v2.graphml',
            'datahub_coverage_v2.json', 'datahub_coverage_v2.md')]
        if any(path.exists() for path in targets):
            parser.error('refusing to overwrite a DataHub v2 artifact')
    git = ['git', '-c', f'safe.directory={SOURCE.as_posix()}', '-C', str(SOURCE)]
    if (subprocess.check_output([*git, 'rev-parse', 'HEAD'], text=True).strip() != REVISION or
            subprocess.check_output([*git, 'status', '--porcelain'], text=True).strip()):
        parser.error('DataHub source must be clean at the pinned revision')
    active = True

    def audithook(event, values):
        if active:
            guard(event, values)

    sys.addaudithook(audithook)
    try:
        graph, report = measure(not args.full)
    finally:
        active = False
    if not args.full:
        sys.stdout.reconfigure(encoding='utf8')
        print('SCOPED_COVERAGE_JSON=' + json.dumps(report, ensure_ascii=True, sort_keys=True, allow_nan=False))
        return
    full_classes = coverage_signature(report)
    scoped_classes = coverage_signature(scoped)
    differences = {key: (scoped_classes.get(key), full_classes.get(key))
                   for key in sorted(full_classes.keys() | scoped_classes.keys())
                   if scoped_classes.get(key) != full_classes.get(key)}
    report['scoped_differences'] = differences
    report['scoped_build_seconds'] = scoped['build_seconds']
    report['scoped_file_count'] = len(scoped['scoped_files'])
    report['fixture_verification'] = fixtures
    report['evidence_sha256'] = hashlib.sha256(EVIDENCE.read_bytes()).hexdigest()
    report['builder_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    report['graphml_xml_replacements'] = write_graphml(graph, targets[0])
    report['graphml_bytes'] = targets[0].stat().st_size
    with targets[0].open('rb') as stream:
        report['graphml_sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
    before = json.loads((RESULTS / 'datahub_coverage_report.json').read_text(encoding='utf8'))
    for path, contents in zip(targets[1:], (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + '\n',
                                            summary(before, report)), strict=True):
        with path.open('x', encoding='utf8', newline='\n') as stream:
            stream.write(contents)
    print(report['graphml_sha256'], report['graphml_bytes'], full_classes, flush=True)
    if differences:
        raise ValueError(f'Scoped and full coverage differ: {differences}')


if __name__ == '__main__':
    main()
