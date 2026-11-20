from multi_repo import RepoConfig, WorkspaceCKGBuilder, WorkspaceConfig


def test_placeholder_client_and_two_inherited_route_prefixes(tmp_path):
    (tmp_path / 'Server.java').write_text('''package server;
class SharedController {
  @PostMapping(value = "/values/{key}") public String save(String key) { return key; }
  @PostMapping(value = "/values/bulk") public String bulk() { return ""; }
  @GetMapping(value = "/values/{key}") public String read(String key) { return key; }
}
@RestController @RequestMapping(path = "/first")
class First extends SharedController {}
@RestController @RequestMapping(path = "/second")
class Second extends SharedController {}
''')
    (tmp_path / 'sdk.py').write_text('''from requests import Session
class Common:
    _session: Session
    def send(self, url): ...
    def update(self, key):
        base = self._gms_server.rstrip('/')
        return self.send(f"{base}/second/values/{key}")
    def read(self, key):
        return self._session.get(f"{self.gms_server}/first/values/{key}")
    def bulk(self):
        return self.send(f"{self.config.gms_server}/second/values/bulk")
class SDK(Common):
    def send(self, url):
        return self._session.post(url)
''')
    graph = WorkspaceCKGBuilder(WorkspaceConfig(base_dir=str(tmp_path),
        repositories=[RepoConfig('service', '.')], contract_bindings_v2=True)).build()
    post = 'http::service/POST:/second/values/{key}'
    first_post = 'http::service/POST:/first/values/{key}'
    get = 'http::service/GET:/first/values/{key}'
    save = 'service/Server.java:SharedController.save'
    caller = 'service/sdk.py:Common.update'
    assert graph.has_edge(save, post) and graph.has_edge(save, first_post)
    assert graph.has_edge(caller, post) and not graph.has_edge(caller, first_post)
    assert graph.has_edge('service/sdk.py:Common.read', get)
    assert graph.has_edge('service/sdk.py:Common.bulk', 'http::service/POST:/second/values/bulk')
    assert not graph.has_edge('service/sdk.py:Common.bulk', post)
    assert not graph.has_edge(caller, save)


def test_signature_ambiguity_does_not_create_a_binding(tmp_path):
    for dirname in ('a', 'b'):
        folder = tmp_path / dirname
        folder.mkdir()
        (folder / 'Server.java').write_text('''@RestController class Server {
    @GetMapping("/values/{key}") public String read(String key) { return key; }
}''')
    (tmp_path / 'client').mkdir()
    (tmp_path / 'client' / 'sdk.py').write_text('''import requests
class SDK:
    def read(self, key):
        return requests.get(f"{self._gms_server}/values/{key}")
''')
    graph = WorkspaceCKGBuilder(WorkspaceConfig(base_dir=str(tmp_path), repositories=[
        RepoConfig(name, name) for name in ('client', 'a', 'b')], contract_bindings_v2=True)).build()
    caller = 'client/sdk.py:SDK.read'
    assert not any(d.get('binding_kind') == 'openapi_static_route_suffix'
                   for _, _, d in graph.out_edges(caller, data=True))
    assert graph.graph['openapi_ambiguous_requests'][0]['candidates'] == [
        'http::a/GET:/values/{key}', 'http::b/GET:/values/{key}']


def test_http_source_index_preserves_name_ambiguity_and_line_ties():
    import networkx as nx
    from types import SimpleNamespace

    from graph_builder_http import _caller
    from http_extended import HTTPSourceIndex, _function_node

    builder = SimpleNamespace(repo_prefix='repo/', graph=nx.MultiDiGraph())
    for suffix, line, kind in [('C.execute', 10, 'function'), ('B.execute', 10, 'function'),
                               ('D.scan', 20, 'function'), ('OnlyMethod', 11, 'method')]:
        builder.graph.add_node('repo/src.py:' + suffix, line_no=line, type=kind)
    calls = [(file, line) for file in ('src.py', 'other.py') for line in (1, 10, 15, 20)]
    names = ('execute', 'B.execute', 'scan', 'OnlyMethod', 'missing')
    expected_calls = [_caller(builder, *args) for args in calls]
    expected_names = [_function_node(builder, 'src.py', name) for name in names]
    builder._http_source_index = HTTPSourceIndex(builder)
    assert [_caller(builder, *args) for args in calls] == expected_calls
    assert [_function_node(builder, 'src.py', name) for name in names] == expected_names
