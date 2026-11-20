"""Build the DataHub v3 production graph once, without retrieval."""
import argparse
import hashlib
import subprocess
import sys

from bench.build_datahub_v2 import measure
from bench.datahub_inputs import ROOT, write_json
from bench.egpot_width_sweep_dev import guard
from bench.map_datahub_coverage import EVIDENCE, REVISION, SOURCE, write_graphml


BUILDER_TAG = 'egpot-bench-builder-v3'
GRAPH = ROOT / 'bench/results/datahub_graph_v3.graphml'
REPORT = ROOT / 'bench/results/datahub_coverage_v3.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scoped', action='store_true')
    args = parser.parse_args()
    git = ['git', '-c', f'safe.directory={SOURCE.as_posix()}', '-C', str(SOURCE)]
    if (subprocess.check_output([*git, 'rev-parse', 'HEAD'], text=True).strip() != REVISION or
            subprocess.check_output([*git, 'status', '--porcelain'], text=True).strip()):
        parser.error('DataHub source must be clean at the pinned revision')
    if not args.scoped:
        if GRAPH.exists() or REPORT.exists():
            parser.error('refusing to overwrite a DataHub v3 artifact')
        pin = subprocess.check_output(['git', 'rev-parse', f'{BUILDER_TAG}^{{commit}}'], text=True).strip()
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
        if pin != head or subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], text=True).strip():
            parser.error('the full build must start from the clean tagged builder tree')
    active = True

    def audit(event, args):
        if active:
            guard(event, args)

    sys.addaudithook(audit)
    try:
        graph, report = measure(args.scoped)
        report['openapi_ambiguous_requests'] = graph.graph['openapi_ambiguous_requests']
    finally:
        active = False
    print({row['id']: row['status'] for row in report['links']}, flush=True)
    if args.scoped:
        print(report['rules'], report['openapi_ambiguous_requests'], flush=True)
        return
    report['builder_commit'] = pin
    report['builder_tag'] = BUILDER_TAG
    report['evidence_sha256'] = hashlib.sha256(EVIDENCE.read_bytes()).hexdigest()
    report['graphml_xml_replacements'] = write_graphml(graph, GRAPH)
    report['graphml_bytes'] = GRAPH.stat().st_size
    with GRAPH.open('rb') as stream:
        report['graphml_sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
    write_json(REPORT, report)
    print(report['graphml_sha256'], report['graphml_bytes'], flush=True)


if __name__ == '__main__':
    main()
