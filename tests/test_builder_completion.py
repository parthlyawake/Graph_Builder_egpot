"""Regression coverage for graph construction completion workstreams.

These tests compare graph node IDs and typed edge multiplicities with a fresh
build. Passing tests establish coverage of these fixtures, not exhaustive
program-analysis accuracy on arbitrary repositories.
"""
from __future__ import annotations

import contextlib
import io
import tempfile
from collections import Counter
from pathlib import Path

import networkx as nx
import pytest
from sklearn.feature_extraction.text import TfidfVectorizer

from graft_ckg import CKGBuilder
from graphql_links import parse_graphql_operations, link_graphql_operations
from multi_repo import WorkspaceCKGBuilder, WorkspaceConfig, RepoConfig
from proto_parser import ProtoParser
from semantic_neighbors import sparse_semantic_pairs


def quiet(call, *args):
    with contextlib.redirect_stdout(io.StringIO()):
        return call(*args)


def signature(graph):
    nodes = set(graph.nodes)
    edges = Counter(
        (str(u), data.get("relation"), str(v), data.get("layer"))
        for u, v, data in graph.edges(data=True)
    )
    return nodes, edges


def _setup_python_repo(directory):
    (directory / "a.py").write_text(
        "from b import worker\n\ndef caller():\n    return worker(2)\n",
        encoding="utf-8")
    (directory / "b.py").write_text(
        "def worker(x):\n    return x * 2\n",
        encoding="utf-8")
    (directory / "c.py").write_text(
        "def unchanged(x):\n    return x + 1\n\ndef another():\n"
        "    return unchanged(3)\n", encoding="utf-8")


def test_incremental_edit_retains_other_file_dependencies(tmp_path):
    _setup_python_repo(tmp_path)
    current = CKGBuilder(str(tmp_path))
    quiet(current.build)
    (tmp_path / "b.py").write_text(
        "def worker(x):\n    return x * 3\n", encoding="utf-8")
    quiet(current.update_files, ["b.py"])
    fresh = CKGBuilder(str(tmp_path))
    quiet(fresh.build)
    assert signature(current.graph) == signature(fresh.graph)
    assert any(u == "a.py:caller" and v == "b.py:worker"
               and data.get("relation") == "CALLS"
               for u, v, data in current.graph.edges(data=True))
    assert any(u == "c.py:another" and v == "c.py:unchanged"
               and data.get("relation") == "CALLS"
               for u, v, data in current.graph.edges(data=True))


def test_incremental_file_add_delete_and_repeated_edits(tmp_path):
    _setup_python_repo(tmp_path)
    current = CKGBuilder(str(tmp_path))
    quiet(current.build)
    (tmp_path / "d.py").write_text(
        "def introduced():\n    return 4\n", encoding="utf-8")
    (tmp_path / "a.py").write_text(
        "from d import introduced\n\ndef caller():\n"
        "    return introduced()\n", encoding="utf-8")
    quiet(current.update_files, ["a.py", "d.py"])
    fresh = CKGBuilder(str(tmp_path))
    quiet(fresh.build)
    assert signature(current.graph) == signature(fresh.graph)
    (tmp_path / "b.py").unlink()
    quiet(current.update_files, [], ["b.py"])
    fresh = CKGBuilder(str(tmp_path))
    quiet(fresh.build)
    assert signature(current.graph) == signature(fresh.graph)
    for i in (5, 6, 7):
        (tmp_path / "d.py").write_text(
            f"def introduced():\n    return {i}\n", encoding="utf-8")
        quiet(current.update_files, ["d.py"])
        fresh = CKGBuilder(str(tmp_path))
        quiet(fresh.build)
        assert signature(current.graph) == signature(fresh.graph)


def test_full_build_idempotent_and_ignores_preserved(tmp_path):
    _setup_python_repo(tmp_path)
    builder = CKGBuilder(str(tmp_path))
    quiet(builder.build)
    initial = signature(builder.graph)
    quiet(builder.build)
    assert signature(builder.graph) == initial
    builder.ignore_patterns.append("c.py")
    quiet(builder.build)
    assert "file::c.py" not in builder.graph
    quiet(builder.build)
    assert "file::c.py" not in builder.graph


def test_workspace_edit_reuses_unchanged_repository(tmp_path):
    for name in ("alpha", "beta"):
        (tmp_path / name).mkdir()
    (tmp_path / "alpha" / "app.py").write_text(
        "def handle():\n    return 1\n", encoding="utf-8")
    (tmp_path / "beta" / "server.py").write_text(
        "def serve():\n    return 2\n", encoding="utf-8")
    config = WorkspaceConfig(
        name="pair", base_dir=str(tmp_path),
        repositories=[RepoConfig(id="alpha", path="alpha"),
                      RepoConfig(id="beta", path="beta")],
    )
    current = WorkspaceCKGBuilder(config)
    quiet(current.build)
    unchanged = current.repo_builders["beta"]
    original = signature(unchanged.graph)
    for value in (3, 4, 5):
        (tmp_path / "alpha" / "app.py").write_text(
            f"def handle():\n    return {value}\n", encoding="utf-8")
        quiet(current.update_files, "alpha", ["app.py"])
        assert current.repo_builders["beta"] is unchanged
        assert signature(unchanged.graph) == original
        fresh = WorkspaceCKGBuilder(config)
        quiet(fresh.build)
        assert signature(current.graph) == signature(fresh.graph)


def test_sparse_semantic_neighbors_are_repeatable_and_bounded():
    texts = ["winter snow", "winter snow", "sun breeze", "sun breeze"]
    x = TfidfVectorizer().fit_transform(texts)
    call = lambda: list(sparse_semantic_pairs(x, threshold=.95,
                                               max_candidates=3, max_neighbors=2))
    result = call()
    assert result == call()
    assert [(a, b) for a, b, _ in result] == [(0, 1), (2, 3)]
    assert all(.95 <= score <= 1.0 for _, _, score in result)


def test_proto_maps_oneof_and_nested_messages():
    source = """syntax = "proto3";
message Outer {
  map<string, int64> counts = 1;
  oneof choice { string label = 2; int32 rank = 3; }
  message Inner { string inside = 4; }
  enum Status { ACTIVE = 0; }
  optional string display = 5;
}
service Service { rpc Watch(stream Outer) returns (stream Outer) {} }
"""
    pf = ProtoParser.parse_text(source)
    outer = pf.messages["Outer"]
    assert set(outer.fields) == {"counts", "label", "rank", "display"}
    assert outer.fields["counts"].map_key_type == "string"
    assert outer.fields["counts"].map_value_type == "int64"
    assert "inside" not in outer.fields
    assert set(outer.nested_messages["Inner"].fields) == {"inside"}
    assert pf.services["Service"].rpcs["Watch"].request_stream
    assert pf.services["Service"].rpcs["Watch"].response_stream


def test_graphql_operation_schema_link_with_alias_and_nested_fields(tmp_path):
    source = """query GetUser($id: ID!) { alias: user(id: $id) { id name } health }"""
    ops = parse_graphql_operations(source)
    assert len(ops) == 1
    assert ops[0].fields == ("user", "health")
    (tmp_path / "query.graphql").write_text(source, encoding="utf-8")
    from types import SimpleNamespace
    graph = nx.MultiDiGraph()
    graph.add_node("contract::graphql::Query::user", type="contract")
    graph.add_node("contract::graphql::Query::health", type="contract")
    assert link_graphql_operations(SimpleNamespace(graph=graph), tmp_path) == 2
    op_id = "graphqlop::query.graphql:query:GetUser"
    assert graph.has_node(op_id)
    assert graph.has_edge(op_id, "contract::graphql::Query::user")
    assert graph.has_edge(op_id, "contract::graphql::Query::health")


def test_java_overloads_do_not_collapse_to_one_node(tmp_path):
    from polyglot import _JAVA_AVAILABLE
    if not _JAVA_AVAILABLE:
        pytest.skip("Java tree-sitter grammar not installed")
    (tmp_path / "Service.java").write_text(
        "class Service {\n"
        "  void send(String message) {}\n"
        "  void send(int code) {}\n"
        "}\n", encoding="utf-8")
    builder = CKGBuilder(str(tmp_path))
    quiet(builder.build)
    definitions = [(nid, data) for nid, data in builder.graph.nodes(data=True)
                   if data.get("type") == "function" and data.get("name") == "send"]
    assert len(definitions) == 2
    assert len({nid for nid, _ in definitions}) == 2
    assert all(data.get("signature") for _, data in definitions)
    assert all(data.get("http_ambiguous_definition") for _, data in definitions)


def test_graphql_sdl_is_not_a_query_and_default_object_is_not_a_selection():
    schema = "schema { query: Query mutation: Mutation }\n" \
             "type Query { user: User }\nextend type Query { health: String }\n"
    assert parse_graphql_operations(schema) == []
    query = "query Fetch($filter: Input = {status: ACTIVE}) { search(filter: $filter) { id } }"
    operations = parse_graphql_operations(query)
    assert len(operations) == 1
    assert operations[0].fields == ("search",)


def test_incremental_respects_ignored_files(tmp_path):
    (tmp_path / ".ckgignore").write_text("generated/*\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "unused.py").write_text(
        "def ignored():\n    return 4\n", encoding="utf-8")
    builder = CKGBuilder(str(tmp_path))
    quiet(builder.build)
    assert "file::generated/unused.py" not in builder.graph
    (tmp_path / "generated" / "unused.py").write_text(
        "def ignored():\n    return 5\n", encoding="utf-8")
    quiet(builder.update_files, ["generated/unused.py"])
    assert "file::generated/unused.py" not in builder.graph
    fresh = CKGBuilder(str(tmp_path))
    quiet(fresh.build)
    assert signature(builder.graph) == signature(fresh.graph)


def test_proto_change_uses_full_build_and_drops_stale_rpc(tmp_path):
    proto = tmp_path / "api.proto"
    proto.write_text(
        'syntax = "proto3"; service Demo { rpc Old (Req) returns (Resp); }\n',
        encoding="utf-8")
    builder = CKGBuilder(str(tmp_path))
    quiet(builder.build)
    assert "contract::Demo.Old" in builder.graph
    proto.write_text(
        'syntax = "proto3"; service Demo { rpc New (Req) returns (Resp); }\n',
        encoding="utf-8")
    quiet(builder.update_files, ["api.proto"])
    assert "contract::Demo.Old" not in builder.graph
    assert "contract::Demo.New" in builder.graph
    fresh = CKGBuilder(str(tmp_path))
    quiet(fresh.build)
    assert signature(builder.graph) == signature(fresh.graph)


def test_graphql_ast_merges_schema_extensions_and_custom_roots(tmp_path):
    from openapi_graphql_parser import GraphQLContractParser
    source = """schema { query: RootQuery }
type RootQuery { user: String }
extend type RootQuery { search(term: String!): [String!]! }
"""
    spec = GraphQLContractParser.parse_text(source)
    assert spec.root_types.get("query") == "RootQuery"
    assert {"user", "search"}.issubset(spec.types["RootQuery"].fields)
    assert spec.types["RootQuery"].fields["search"].type_name == "[String!]!"
    assert spec.types["RootQuery"].fields["search"].arguments["term"] == "String!"

    from types import SimpleNamespace
    graph = nx.MultiDiGraph()
    graph.graph["graphql_root_types"] = {"query": "RootQuery"}
    graph.add_node("contract::graphql::RootQuery::search", type="contract")
    (tmp_path / "client.graphql").write_text(
        "query Find { search(term: \"test\") }", encoding="utf-8")
    assert link_graphql_operations(SimpleNamespace(graph=graph), tmp_path) == 1
    assert graph.has_edge("graphqlop::client.graphql:query:Find",
                          "contract::graphql::RootQuery::search")


def test_explicit_java_datafetcher_graphql_binding():
    """Match DataHub-style RuntimeWiring without guessing a resolver name."""
    from types import SimpleNamespace
    from graphql_java_bindings import explicit_datafetchers, bind_java_graphql_datafetchers
    source = '''class Wiring {
  private static final String QUERY_TYPE = "Query";
  void configure(RuntimeWiring.Builder builder) {
    builder.type(
      QUERY_TYPE,
      typeWiring ->
        typeWiring.dataFetcher(
          "document",
          new com.example.GetDocumentResolver()));
  }
}'''
    discovered = list(explicit_datafetchers(source))
    assert discovered == [("Query", "document", "GetDocumentResolver", 7)]
    graph = nx.MultiDiGraph()
    resolver = "backend/GetDocumentResolver.java:GetDocumentResolver"
    schema = "contract::graphql::Query::document"
    graph.add_node(resolver, type="class", name="GetDocumentResolver")
    graph.add_node(schema, type="contract", name="Query.document")
    builder = SimpleNamespace(raw_file_lines={"Wiring.java": source.splitlines()})
    workspace = SimpleNamespace(
        graph=graph,
        repo_builders={"backend": builder},
        symbols_by_name={"GetDocumentResolver": [resolver]},
    )
    assert bind_java_graphql_datafetchers(workspace) == 1
    assert graph.has_edge(resolver, schema)
    assert bind_java_graphql_datafetchers(workspace) == 0

    # No confirmed link if multiple candidate Java types share the same name.
    duplicate = "other/GetDocumentResolver.java:GetDocumentResolver"
    graph.add_node(duplicate, type="class", name="GetDocumentResolver")
    graph.remove_edges_from(list(graph.edges(keys=True)))
    workspace.symbols_by_name["GetDocumentResolver"].append(duplicate)
    assert bind_java_graphql_datafetchers(workspace) == 0


def test_standalone_contracts_survive_incremental_source_edit(tmp_path):
    (tmp_path / "api.py").write_text(
        '@app.get("/items")\ndef items():\n    return ["ok"]\n', encoding="utf-8")
    (tmp_path / "openapi.yaml").write_text(
        'openapi: "3.0.0"\ninfo:\n  title: API\n  version: "1"\n'
        'paths:\n  /items:\n    get:\n      operationId: listItems\n'
        '      responses:\n        "200":\n          description: OK\n',
        encoding="utf-8")
    (tmp_path / "schema.graphql").write_text(
        "type Query { user: String }\n", encoding="utf-8")
    (tmp_path / "query.graphql").write_text(
        "query Current { user }\n", encoding="utf-8")

    builder = CKGBuilder(str(tmp_path))
    quiet(builder.build)
    assert "endpoint::GET::/items" in builder.graph
    assert "contract::graphql::Query::user" in builder.graph
    assert "graphqlop::query.graphql:query:Current" in builder.graph
    assert any(
        u == "api.py:items" and v == "endpoint::GET::/items" and
        data.get("relation") == "IMPLEMENTS"
        for u, v, data in builder.graph.edges(data=True)
    )
    (tmp_path / "api.py").write_text(
        '@app.get("/items")\ndef items():\n    return ["updated"]\n',
        encoding="utf-8")
    quiet(builder.update_files, ["api.py"])
    fresh = CKGBuilder(str(tmp_path))
    quiet(fresh.build)
    assert signature(builder.graph) == signature(fresh.graph)
    quiet(builder.build)
    assert signature(builder.graph) == signature(fresh.graph)
