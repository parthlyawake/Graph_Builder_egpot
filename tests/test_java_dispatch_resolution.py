"""Opt-in source-backed receiver dispatch; no retrieval or benchmark queries."""
from collections import Counter
from dataclasses import asdict
import json

import pytest

from multi_repo import RepoConfig, WorkspaceCKGBuilder, WorkspaceConfig
from polyglot import _JAVA_AVAILABLE

pytestmark = pytest.mark.skipif(not _JAVA_AVAILABLE, reason="Java parser required")

API = 'interface Api { void apply(String id); }'
IMPL = 'class Worker implements Api { public void apply(String id) {} }'


def workspace(tmp_path, files, enabled=True):
    services = set()
    for path, text in files.items():
        file = tmp_path / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")
        services.add(path.split("/", 1)[0])
    config = WorkspaceConfig(base_dir=str(tmp_path), resolve_java_dispatch=enabled,
                             repositories=[RepoConfig(s, s) for s in sorted(services)])
    builder = WorkspaceCKGBuilder(config)
    builder.build()
    return builder


def fixture(tmp_path, client, impl=IMPL, api=API, enabled=True):
    return workspace(tmp_path, {"svc/Api.java": api, "svc/Worker.java": impl,
                               "svc/Client.java": client}, enabled)


def dispatch(builder):
    return [(u, v, key, data) for u, v, key, data in builder.graph.edges(keys=True, data=True)
            if str(key).startswith("java_dispatch_")]


@pytest.mark.parametrize("declaration,body,kind", [
    ("@Autowired private Api worker;", 'void run(){worker.apply("x");}', "single_impl"),
    ("@Resource private Api worker;", 'void run(){this.worker.apply("x");}', "single_impl"),
    ("private final Api worker; Client(Api value){this.worker=value;}",
     'void run(){worker.apply("x");}', "single_impl"),
    ("", 'void run(Api worker){worker.apply("x");}', "single_impl"),
    ("", 'void run(Worker worker){worker.apply("x");}', "direct"),
    ("", 'void run(){Worker worker=new Worker();worker.apply("x");}', "direct"),
    ("", 'void run(){Api worker=new Worker();worker.apply("x");}', "single_impl"),
    ("Worker worker;", 'void run(){worker.apply("x");}', "direct"),
])
def test_explicit_receiver_sources(tmp_path, declaration, body, kind):
    builder = fixture(tmp_path, f'class Client {{{declaration}{body}}}')
    edges = dispatch(builder)
    assert len(edges) == 1
    u, v, _, data = edges[0]
    assert u.endswith("Client.run") and v.endswith("Worker.apply")
    assert data["relation"] == "CALLS" and data["layer"] == "Ldep"
    assert data["match_kind"] == kind
    assert data["source_evidence"] == "Client.java:1"
    assert data["target_source_evidence"] == "Worker.java:1"
    assert data["via"].endswith("Api.apply") if kind == "single_impl" else data["via"] == ""
    assert data["arity"] == 1 and data["c_type"] == 1.0


@pytest.mark.parametrize("client,impl,api", [
    ('class Client {Api worker;void run(){worker.apply("x");}}',
     IMPL+' class Other implements Api {public void apply(String id){}}', API),
    ('class Client {Api worker;void run(){worker.apply("x");}}',
     'class Worker implements Api {public void apply(String x){} public void apply(Integer x){}}', API),
    ('class Client {Api worker;void run(){worker.apply("x");}}', IMPL,
     'interface Api {void apply(String x);void apply(Integer x);}'),
    ('class Client {void run(){unknown.apply("x");}}', IMPL, API),
    ('class Client {void run(){var worker=new Worker();worker.apply("x");}}', IMPL, API),
    ('class Client {Api worker;void run(){var worker=new Worker();worker.apply("x");}}', IMPL, API),
    ('class Client {Api worker;void run(Unknown worker){worker.apply("x");}}', IMPL, API),
    ('class Client {Worker worker;void run(){worker.next().apply("x");}}',
     'class Worker {Worker next(){return this;}void apply(String x){}}', API),
    ('class Client {Api<String> worker;void run(){worker.apply("x");}}',
     'class Worker implements Api<String> {public void apply(String x){}}',
     'interface Api<T>{void apply(T x);}'),
    ('class Client {Api worker;void run(){worker.apply("x");}}',
     'class Worker implements Api<String> {public void apply(String x){}}',
     'interface Api<T>{void apply(T x);}'),
    ('import external.Worker; class Client {Worker worker;void run(){worker.apply("x");}}', IMPL, API),
    ('class Client {void run(Api worker){Runnable r=()->worker.apply("x");}}', IMPL, API),
    ('class Client {Api worker;void run(){worker.apply();}}', IMPL, API),
])
def test_uncertain_calls_abstain(tmp_path, client, impl, api):
    assert not dispatch(fixture(tmp_path, client, impl, api))


def test_same_arity_concrete_overloads_abstain(tmp_path):
    builder = fixture(tmp_path, 'class Client {Worker worker;void run(){worker.apply("x");}}',
                      'class Worker {void apply(String x){} void apply(Integer x){}}')
    assert not dispatch(builder)


def test_different_arity_is_resolved_from_source(tmp_path):
    builder = fixture(tmp_path, 'class Client {Worker worker;void run(){worker.apply("x");}}',
                      'class Worker {void apply(){} void apply(String x){}}')
    assert len(dispatch(builder)) == 1 and dispatch(builder)[0][3]["arity"] == 1


@pytest.mark.parametrize("abstract", [False, True])
def test_abstract_or_interface_single_implementation(tmp_path, abstract):
    api = 'abstract class Api {abstract void apply(String x);}' if abstract else API
    impl = IMPL.replace("implements", "extends") if abstract else IMPL
    builder = fixture(tmp_path, 'class Client {Api worker;void run(){worker.apply("x");}}', impl, api)
    assert len(dispatch(builder)) == 1
    assert dispatch(builder)[0][3]["via"].endswith("Api.apply")


@pytest.mark.parametrize("interface", [False, True])
def test_one_superclass_lookup(tmp_path, interface):
    impl = ('class Base {public void apply(String x){}} '
            'class Worker extends Base' + (' implements Api' if interface else '') + ' {}')
    static = 'Api' if interface else 'Worker'
    builder = fixture(tmp_path, f'class Client {{{static} worker;void run(){{worker.apply("x");}}}}', impl)
    assert len(dispatch(builder)) == 1 and dispatch(builder)[0][1].endswith("Base.apply")


def test_two_superclass_levels_abstain(tmp_path):
    impl = 'class Base {void apply(String x){}} class Middle extends Base{} class Worker extends Middle{}'
    assert not dispatch(fixture(tmp_path, 'class Client {Worker worker;void run(){worker.apply("x");}}', impl))


def test_imported_type_and_service_local_implementor(tmp_path):
    builder = workspace(tmp_path, {
        'svc/Api.java': 'package api; public interface Api {void apply(String x);}',
        'svc/Worker.java': 'package concrete;import api.Api;class Worker implements Api {public void apply(String x){}}',
        'svc/Client.java': 'package client;import api.Api;class Client {Api worker;void run(){worker.apply("x");}}',
        'other/Other.java': 'package other;import api.Api;class Other implements Api {public void apply(String x){}}',
    })
    edges = dispatch(builder)
    assert len(edges) == 1 and edges[0][1].startswith('svc/')


def test_concrete_class_in_another_workspace_repository(tmp_path):
    builder = workspace(tmp_path, {
        'client/Client.java': 'import lib.Worker;class Client {Worker worker;void run(){worker.apply("x");}}',
        'library/Worker.java': 'package lib;public class Worker {public void apply(String x){}}',
    })
    assert len(dispatch(builder)) == 1 and dispatch(builder)[0][1].startswith('library/')


def test_ambiguous_imports_abstain(tmp_path):
    builder = workspace(tmp_path, {
        'svc/A.java': 'package a;class Worker {void apply(String x){}}',
        'svc/B.java': 'package b;class Worker {void apply(String x){}}',
        'svc/Client.java': 'package c;import a.*;import b.*;class Client {Worker worker;void run(){worker.apply("x");}}',
    })
    assert not dispatch(builder)


def test_local_shadow_scope_and_this_field(tmp_path):
    builder = fixture(tmp_path, '''class Client {Api worker;
 void run(){ {var worker=new Worker();worker.apply("x");} this.worker.apply("y");worker.apply("z");}}
''')
    assert len(dispatch(builder)) == 2


def test_off_preserves_legacy_and_on_is_additive(tmp_path):
    client = 'class Client {Api worker;void run(){worker.apply("x");}}'
    off = fixture(tmp_path, client, enabled=False)
    on = WorkspaceCKGBuilder(WorkspaceConfig(**{**asdict(off.config), 'repositories':off.config.repositories,
                                               'resolve_java_dispatch':True}))
    on.build()
    assert not dispatch(off)
    assert dict(off.graph.nodes(data=True)) == dict(on.graph.nodes(data=True))
    for u, v, k, d in off.graph.edges(keys=True, data=True):
        assert on.graph[u][v][k] == d
    assert any(v.startswith('external::worker.apply') for _,v in on.graph.edges())
    before = list(on.graph.edges(keys=True, data=True))
    on._resolve_java_dispatch()
    assert list(on.graph.edges(keys=True, data=True)) == before


def test_incremental_equals_full_and_removes_old_dispatch(tmp_path):
    client = 'class Client {Api worker;void run(){worker.apply("x");}}'
    builder = fixture(tmp_path, client)
    file = tmp_path/'svc'/'Worker.java'
    file.write_text(IMPL+' class Other implements Api {public void apply(String x){}}')
    builder.update_files('svc', ['Worker.java'])
    full = WorkspaceCKGBuilder(builder.config); full.build()
    assert not dispatch(builder) and not dispatch(full)
    def shape(b):
        return Counter((u,v,d['relation'],d['layer'],d.get('match_kind'),d.get('source_evidence'))
                       for u,v,d in b.graph.edges(data=True))
    assert set(builder.graph) == set(full.graph) and shape(builder) == shape(full)


def test_incremental_relocates_dispatch_evidence_and_is_deterministic(tmp_path):
    builder = fixture(tmp_path, 'class Client {Api worker;void run(){worker.apply("x");}}')
    file = tmp_path/'svc'/'Client.java'
    file.write_text('class Client {Api worker;\nvoid run(){worker.apply("x");worker.apply("y");}}')
    builder.update_files('svc', ['Client.java'])
    full = WorkspaceCKGBuilder(builder.config); full.build()
    actual = sorted(dispatch(builder), key=lambda e:e[2])
    expected = sorted(dispatch(full), key=lambda e:e[2])
    assert len(actual) == 2 and actual == expected
    assert all(e[3]['source_evidence'] == 'Client.java:2' for e in actual)


def test_nested_class_uses_lexical_type_before_import(tmp_path):
    builder = workspace(tmp_path, {
        'svc/Outer.java': '''import other.Worker;
class Outer {static class Worker {void apply(String x){}}
 static class Client {Worker worker;void run(){worker.apply("x");}}}''',
        'svc/Other.java': 'package other;class Worker {void apply(String x){}}',
    })
    edges = dispatch(builder)
    assert len(edges) == 1 and edges[0][1].endswith('Outer.Worker.apply')


def test_option_roundtrip_and_export_sidecar(tmp_path):
    builder = fixture(tmp_path, 'class Client {Api worker;void run(){worker.apply("x");}}')
    graph_path = tmp_path/'export'/'tiny.graphml'
    builder.export_graph(str(graph_path), format='graphml')
    config = json.loads(graph_path.with_suffix('.build_config.json').read_text())
    assert config['resolve_java_dispatch'] is True
    assert WorkspaceConfig.from_dict(config, config['base_dir']).resolve_java_dispatch is True
    assert WorkspaceConfig._parse_simple_yaml('resolve_java_dispatch: true')['resolve_java_dispatch'] is True
    builder.config.resolve_java_dispatch = False
    builder.export_graph(str(tmp_path/'off.graphml'), format='graphml')
    assert not (tmp_path/'off.build_config.json').exists()


@pytest.mark.parametrize('value', ['false', 1, None])
def test_option_requires_boolean(value):
    with pytest.raises(ValueError):
        WorkspaceConfig.from_dict({'resolve_java_dispatch':value})
