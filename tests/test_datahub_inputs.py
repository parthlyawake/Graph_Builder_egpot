import json

import pytest

from bench import egpot_multi_eval as locked
from bench.datahub_inputs import GRAPH, GRAPH_SHA, LABELS, identifier_leaks, sha, validate_labels
from bench.datahub_protocol import settings


def test_paired_source_labels_have_no_edge_derived_fields_or_identifier_leaks():
    labels = json.loads(LABELS.read_text(encoding='utf8'))
    meta = json.loads(LABELS.with_suffix('.provenance.json').read_text(encoding='utf8'))
    assert len(labels) == len({r['id'] for r in labels}) == 52
    assert sha(LABELS) == meta['query_file_sha256']
    assert locked.REGISTRY['datahub'].graph == GRAPH
    assert meta['graphml_sha256'] == GRAPH_SHA
    expected = {'id', 'link_id', 'type', 'query', 'start_node', 'gold_nodes', 'gold_path',
                'lookalike_ids', 'module_pair', 'guard_class', 'label_status'}
    for row in labels:
        assert set(row) == expected
        assert row['gold_path'] == [row['start_node'], *row['gold_nodes']]
        assert len(row['gold_nodes']) == 2 and row['lookalike_ids']
        assert set(row['lookalike_ids']).isdisjoint(row['gold_nodes'])
    evidence = meta['leak_audit_source_identifiers']
    assert validate_labels(labels, evidence) == {}
    assert identifier_leaks('which routine calls on create domain', evidence[0])


@pytest.mark.parametrize('mode', ['smoke', 'regress-ob-dev'])
def test_datahub_refuses_ordinary_modes_before_input_io(mode, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail('ordinary DataHub run reached input loading')

    for name in ('load_settings', 'verify_inputs', 'initialize_worker', 'run_locked'):
        monkeypatch.setattr(locked, name, unexpected)
    with pytest.raises(SystemExit) as caught:
        locked.main(['--mode', mode, '--repo', 'datahub'])
    assert caught.value.code == 2


def test_datahub_draft_refuses_input_loading(tmp_path, monkeypatch):
    draft = tmp_path / 'draft.md'
    draft.write_text('Status: DRAFT\n')
    repo = locked.Repo(tmp_path/'graph', tmp_path/'graphmeta', tmp_path/'labels', tmp_path/'labelmeta', draft)
    monkeypatch.setattr(locked, 'git', lambda *a, **k: 'a' * 40 if a == ('rev-parse', 'HEAD') else '')
    monkeypatch.setattr(locked, 'verify_inputs', lambda *a, **k: pytest.fail('draft opened an input'))
    with pytest.raises(ValueError, match='draft'):
        locked.locked_preflight('datahub', repo, tmp_path)


def test_datahub_job_matrix_declares_widths_budgets_seed_and_weights():
    spec = settings()
    for name in ('egpot_full', 'egpot_no_pareto', 'egpot_full_tiebreak'):
        for width in (4, 12):
            main = spec['main'][f'{name}_w{width}']
            assert main['budgets'] == [10, 20, 40]
            assert main['config']['beam_width'] == width
    assert all(set(seeds) == set(map(str, range(6))) for seeds in spec['seeds'].values())
    assert len(spec['weights']) == 55
    assert 'equal' in spec['weights'] and spec['pareto_reference_method'] == 'egpot_full_w4'
