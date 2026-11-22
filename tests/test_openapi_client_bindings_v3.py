import pytest

from multi_repo import RepoConfig, WorkspaceCKGBuilder, WorkspaceConfig
from openapi_client_bindings import route_specificity


@pytest.mark.parametrize('template,path,rank', [
    ('/{entityName}', '/sql', None),
    ('/values/{key}', '/values/{*}', 1),
    ('/values/literal', '/values/{*}', None),
    ('/values/{key:[0-9]{2,3}}', '/values/20', 1),
    ('/values/{key:[0-9]{2,3}}', '/values/abc', None),
    ('/values/{key:[0-9]{2,3}}', '/values/{*}', None),
    ('/values/{key:[^/]+}/read', '/values/abc/read', 2),
    ('/values/{key}/read', '/values/abc/other', None),
])
def test_template_requires_literal_match_and_respects_constraints(template, path, rank):
    assert route_specificity(template, path) == rank


def test_dremio_sql_does_not_bind_to_datahub_endpoint_templates(tmp_path):
    (tmp_path / 'Server.java').write_text('''@RestController class Server {
    @PostMapping("/{entityName}") String save(String entityName) { return entityName; }
    @PostMapping("/sql") String sql() { return ""; }
}''')
    (tmp_path / 'clients.py').write_text('''from requests import Session
class Dremio:
    _session: Session
    def execute_query(self, query):
        return self._session.post(f"{self.dremio_base}/sql", json={"sql": query})
class SDK:
    _session: Session
    external: Session
    def matching(self):
        return self._session.post(f"{self._gms_server}/sql")
    def unrelated_host(self):
        return self._session.post("https://third.example/sql")
    def unrelated_client(self):
        return self.external.post(f"{self._gms_server}/sql")
    def parameter_only(self):
        return self._session.post(f"{self._gms_server}/arbitrary")
''')
    graph = WorkspaceCKGBuilder(WorkspaceConfig(base_dir=str(tmp_path),
        repositories=[RepoConfig('data', '.')], contract_bindings_v2=True)).build()
    result = {u: set() for u in graph}
    for u, v, attrs in graph.edges(data=True):
        if attrs.get('binding_kind') == 'openapi_static_route_suffix':
            result[u].add(v)
    assert result['data/clients.py:SDK.matching'] == {'http::data/POST:/sql'}
    for name in ('Dremio.execute_query', 'SDK.unrelated_host', 'SDK.unrelated_client', 'SDK.parameter_only'):
        assert not result[f'data/clients.py:{name}']
