import json

from multi_repo import RepoConfig, WorkspaceCKGBuilder, WorkspaceConfig


def test_restli_separates_collections_and_uses_typed_client_helpers(tmp_path):
    for name in ('items','records'):
        cls = name.title()
        spec = {'name': name, 'path': '/' + name, 'namespace': 'test', 'resourceClass': 'server.' + cls,
                'collection': {'supports': ['get'], 'actions': [{'name': 'remove'}],
                               'entity': {'path': '/' + name + '/{resourceKey}'}}}
        (tmp_path / f'{name}.restspec.json').write_text(json.dumps(spec))
        (tmp_path / f'{cls}.java').write_text(f'''package server;
@RestLiCollection(name = "{name}", namespace = "test")
class {cls} {{
  static final String REMOVE = "remove";
  @Action(name = REMOVE) public void deleteRecords() {{ }}
  @RestMethod.Get public String read(String key) {{ return key; }}
}}
''')
    (tmp_path / 'client.py').write_text('''import requests
class Client:
    client: requests.Session
    def _send(self, verb, url):
        return self.client.request(verb, url)
    def remove_items(self):
        url = f"{self.base}/items?action=remove"
        return self._send("POST", url)
    def remove_records(self):
        return self._emit(f"{self.base}/records?action=remove")
    def _emit(self, url, method="POST"):
        send = getattr(self.client, method.lower())
        return send(url)
    def read(self, identifier):
        return self.client.get(f"{self.base}/items/{identifier}?expand=true")
    def fake(self):
        return self.cache.post(f"{self.base}/items?action=remove")
    def unknown_action(self, action):
        return self.client.post(f"{self.base}/items?action={action}")
''')
    graph = WorkspaceCKGBuilder(WorkspaceConfig(base_dir=str(tmp_path),
        repositories=[RepoConfig('repo', '.')], contract_bindings_v2=True)).build()
    items = 'restli::test::/items::action::remove'
    records = 'restli::test::/records::action::remove'
    read = 'restli::test::/items::method::get'
    prefix = 'repo/client.py:Client.'
    assert graph.has_edge(prefix + 'remove_items', items)
    assert graph.has_edge(prefix + 'remove_records', records)
    assert graph.has_edge(prefix + 'read', read)
    assert graph.has_edge('repo/Items.java:Items.deleteRecords', items)
    assert graph.has_edge('repo/Items.java:Items.read', read)
    assert graph.has_edge('repo/Records.java:Records.deleteRecords', records)
    for caller in ('remove_records', 'fake', 'unknown_action'):
        assert not graph.has_edge(prefix + caller, items)
