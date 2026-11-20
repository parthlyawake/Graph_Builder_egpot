from multi_repo import RepoConfig, WorkspaceCKGBuilder, WorkspaceConfig


def test_datafetcher_retains_class_binding_and_adds_only_typed_get(tmp_path):
    (tmp_path / 'schema.graphql').write_text('type Query { systemStatus: String }')
    (tmp_path / 'Wiring.java').write_text('''
class Wiring {
  void setup() { wiring.type("Query", t -> t.dataFetcher("systemStatus", new StatusResolver())); }
}
''')
    (tmp_path / 'StatusResolver.java').write_text('''
class StatusResolver implements DataFetcher<String> {
  public String get(String wrong) { return "wrong"; }
  @Override public String get(DataFetchingEnvironment env) { return "running"; }
}
''')

    def build(v2):
        return WorkspaceCKGBuilder(WorkspaceConfig(base_dir=str(tmp_path),
            repositories=[RepoConfig('service', '.')], contract_bindings_v2=v2)).build()

    old, graph = build(False), build(True)
    owner = 'service/StatusResolver.java:StatusResolver'
    contract = 'contract::graphql::Query::systemStatus'
    assert old.has_edge(owner, contract) and graph.has_edge(owner, contract)
    assert not graph.has_edge(owner + '.get', contract)
    methods = [n for n, _, attr in graph.in_edges(contract, data=True)
               if attr.get('binding_kind') == 'java_datafetcher_method']
    assert len(methods) == 1 and methods[0].startswith(owner + '.get@overload:')
    assert methods[0] in old and not old.has_edge(methods[0], contract)
