"""Source-grounded depth regression tests (dispatch, flow, contracts, BPE, LSP).

Tests create actual source files and assert nodes/relations, not only parser
return values. Skips are explicit for missing optional compiler runtimes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import networkx as nx
import pytest

from graft_ckg import CKGBuilder
from multi_repo import WorkspaceCKGBuilder
from openapi_graphql_parser import OpenAPIContractParser
from proto_compiler import compile_proto_file
from static_dispatch import parameter_types, literal_kind
from token_grafting import pack_context
from traversal import SCKGTraversal
from compiler_resolution import LanguageServer


def edges(graph, relation):
    return [(u, v, d) for u, v, d in graph.edges(data=True)
            if d.get("relation") == relation]


def test_bpe_graft_strict_root_and_repeatability():
    import tiktoken
    graph = nx.MultiDiGraph()
    graph.add_node("root.py:start", type="function", name="start",
                   file="root.py", line_no=1, code="x = 1000\n" * 1000)
    for i in range(5):
        graph.add_node(f"f{i}", type="function", file=f"f{i}.py",
                       line_no=2, code="return 5")
        graph.add_edge("root.py:start", f"f{i}", relation="CALLS", layer="Ldep")
    traversal = SCKGTraversal(SimpleNamespace(graph=graph))
    for limit in (1, 7, 20, 150, 1024):
        one = traversal.deterministic_subtree_graft("root.py:start", max_tokens=limit)
        two = traversal.deterministic_subtree_graft("root.py:start", max_tokens=limit)
        assert one == two
        assert one["bpe_tokens"] == len(
            tiktoken.get_encoding("cl100k_base").encode(one["grafted_context"]))
        assert one["bpe_tokens"] <= limit
        assert one["node_count"] == len(one["selected_nodes"])
        assert one["edge_count"] == len(one["relations"])
        assert all(e["source"] in one["selected_nodes"] and
                   e["target"] in one["selected_nodes"] for e in one["relations"])
    with pytest.raises(ValueError):
        pack_context(graph, "root.py:start", [], [], 0)


def test_literal_classification_and_generics():
    assert parameter_types("(Map<String, Integer> values, int count)") == (
        "Map<String, Integer>", "int")
    assert literal_kind('"message"') == "string"
    assert literal_kind("123") == "int"
    assert literal_kind("false") == "bool"


def test_java_overloads_use_individual_callsite_types(tmp_path):
    (tmp_path / "S.java").write_text(
        "class S {\n"
        "  void invoke() { send(\"test\"); send(5); }\n"
        "  void send(String s) { }\n"
        "  void send(int i) { }\n"
        "}\n", encoding="utf-8")
    builder = CKGBuilder(str(tmp_path))
    builder.build()
    declared = {node: d for node, d in builder.graph.nodes(data=True)
                if d.get("type") == "function" and d.get("name") == "send"}
    assert len(declared) == 2
    assert {tuple(d["param_types"]) for d in declared.values()} == {
        ("String",), ("int",)}
    calls = [(u, v, d) for u, v, d in edges(builder.graph, "CALLS")
             if u == "S.java:S.invoke" and v in declared]
    assert len(calls) == 2
    assert {target for _, target, _ in calls} == set(declared)
    assert all(d.get("c_type") == 1.0 for _, _, d in calls)


def test_java_unknown_argument_retains_uncertain_dispatch(tmp_path):
    (tmp_path / "S.java").write_text(
        "class S {\n"
        "  void invoke(Object x) { send(x); }\n"
        "  void send(String s) { }\n"
        "  void send(int i) { }\n"
        "}\n", encoding="utf-8")
    builder = CKGBuilder(str(tmp_path))
    builder.build()
    calls = [(u, v, d) for u, v, d in edges(builder.graph, "POLYMORPHIC_CALL")
             if u == "S.java:S.invoke"]
    assert len(calls) == 2
    assert abs(sum(d["c_type"] for _, _, d in calls) - 1.0) <= .001


def test_interprocedural_python_arg_and_return(tmp_path):
    (tmp_path / "worker.py").write_text(
        "def double(n):\n"
        "    return n * 2\n\n"
        "def run(x):\n"
        "    result = double(x)\n"
        "    return result\n", encoding="utf-8")
    builder = CKGBuilder(str(tmp_path))
    builder.build()
    flow = {(u, v) for u, v, _ in edges(builder.graph, "FLOWS_TO")}
    assert ("worker.py:run.var::x", "worker.py:double.var::n") in flow
    assert ("worker.py:double.return::2", "worker.py:run.var::result") in flow
    assert any(d.get("flow_kind") == "interprocedural"
               for _, _, d in edges(builder.graph, "FLOWS_TO"))


def test_protoc_descriptors_oneof_map_nested_and_imports(tmp_path):
    pytest.importorskip("grpc_tools")
    (tmp_path / "api.proto").write_text(
        'syntax = "proto3";\n'
        'import "google/protobuf/timestamp.proto";\n'
        'package example;\n'
        'message Packet {\n'
        '  map<string, int64> counts = 1;\n'
        '  oneof choice { string title = 2; int32 id = 3; }\n'
        '  message Inner { google.protobuf.Timestamp created = 1; }\n'
        '  Inner body = 4;\n'
        '}\n'
        'service Stream { rpc Exchange(stream Packet) returns (stream Packet); }\n',
        encoding="utf-8")
    parsed, source = compile_proto_file(tmp_path / "api.proto", tmp_path)
    assert source == "protoc"
    packet = parsed.messages["Packet"]
    assert packet.fields["counts"].map_key_type == "string"
    assert packet.fields["counts"].map_value_type == "int64"
    assert set(packet.fields) >= {"title", "id", "body"}
    assert "Inner" in packet.nested_messages
    assert parsed.services["Stream"].rpcs["Exchange"].request_stream
    assert parsed.services["Stream"].rpcs["Exchange"].response_stream
    builder = CKGBuilder(str(tmp_path))
    builder.build()
    assert builder.graph.graph["proto_parse_modes"]["api.proto"] == "protoc"


def test_openapi_ref_request_response_and_contract_graph(tmp_path):
    (tmp_path / "openapi.yaml").write_text(
        'openapi: "3.0.3"\n'
        'info:\n  title: Example\n  version: "1"\n'
        'components:\n  schemas:\n'
        '    Product:\n      type: object\n'
        '      properties:\n        name:\n          type: string\n'
        'paths:\n  /products/{id}:\n'
        '    parameters:\n      - name: id\n        in: path\n        required: true\n'
        '        schema:\n          type: string\n'
        '    post:\n      operationId: updateProduct\n'
        '      requestBody:\n        content:\n'
        '          application/json:\n'
        '            schema:\n              $ref: "#/components/schemas/Product"\n'
        '      responses:\n'
        '        "200":\n          description: OK\n'
        '          content:\n            application/json:\n'
        '              schema:\n                $ref: "#/components/schemas/Product"\n',
        encoding="utf-8")
    spec = OpenAPIContractParser.parse_file(str(tmp_path / "openapi.yaml"))
    assert len(spec.operations) == 1
    op = spec.operations[0]
    assert op.parameters[0]["name"] == "id"
    assert op.request_schema["application/json"]["properties"]["name"]["type"] == "string"
    assert op.response_schemas["200"]["application/json"]["type"] == "object"
    builder = CKGBuilder(str(tmp_path))
    builder.build()
    assert "endpoint::POST::/products/{id}" in builder.graph
    assert any(u == "endpoint::POST::/products/{id}"
               for u, _, _ in edges(builder.graph, "ACCEPTS_SCHEMA"))
    assert any(u == "endpoint::POST::/products/{id}"
               for u, _, _ in edges(builder.graph, "RETURNS_SCHEMA"))


def test_local_scip_index_resolves_call_to_exact_file(tmp_path):
    (tmp_path / "definition.py").write_text(
        "def target():\n    return 42\n", encoding="utf-8")
    (tmp_path / "caller.py").write_text(
        "def invoke():\n    return target()\n", encoding="utf-8")
    (tmp_path / "index.json").write_text(json.dumps({"documents": [
        {"relative_path": "definition.py", "occurrences": [
            {"symbol": "scip-python pkg target().", "symbol_roles": 1,
             "range": [0, 4, 10]}]},
        {"relative_path": "caller.py", "occurrences": [
            {"symbol": "scip-python pkg target().", "symbol_roles": 0,
             "range": [1, 11, 17]}]}
    ]}), encoding="utf-8")
    (tmp_path / ".sckg_lsp.json").write_text(
        json.dumps({"scip_indexes": ["index.json"]}), encoding="utf-8")
    builder = CKGBuilder(str(tmp_path))
    builder.build()
    assert any(u == "caller.py:invoke" and v == "definition.py:target"
               and d.get("c_type") == 1.0
               for u, v, d in edges(builder.graph, "CALLS"))


def test_lsp_json_rpc_stream_against_mock_server(tmp_path):
    server_code = r'''
import json, sys
root = None
def send(packet):
    data = json.dumps(packet).encode()
    sys.stdout.buffer.write(
        b"Content-Length: " + str(len(data)).encode() + b"\r\n\r\n" + data)
    sys.stdout.buffer.flush()
while True:
    size = None
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            sys.exit(0)
        if line in (b"\r\n", b"\n"):
            break
        if line.lower().startswith(b"content-length:"):
            size = int(line.split(b":",1)[1])
    if size is None:
        continue
    request = json.loads(sys.stdin.buffer.read(size))
    method = request.get("method")
    if method == "initialize":
        root = request["params"]["rootUri"]
        send({"jsonrpc":"2.0","id":request["id"],"result":{"capabilities":{}}})
    elif method == "textDocument/definition":
        send({"jsonrpc":"2.0","id":request["id"],"result":{
            "uri": root + "/definition.py",
            "range": {"start":{"line":0,"character":4},
                      "end":{"line":0,"character":10}}}})
    elif method == "shutdown":
        send({"jsonrpc":"2.0","id":request["id"],"result":None})
    elif method == "exit":
        sys.exit(0)
'''
    path = tmp_path / "mock.py"
    path.write_text(server_code, encoding="utf-8")
    (tmp_path / "definition.py").write_text("def target(): pass\n")
    (tmp_path / "caller.py").write_text("def invoke():\n    return target()\n")
    session = LanguageServer([sys.executable, "-u", str(path)], tmp_path, timeout=3)
    try:
        result = session.definition("caller.py", 2, 11)
        assert result["uri"].endswith("/definition.py")
        assert result["range"]["start"]["line"] == 0
    finally:
        session.close()


def test_proto_field_contracts_and_rpc_schema_direction(tmp_path):
    (tmp_path / "order.proto").write_text(
        'syntax = "proto3";\n'
        'message OrderReq { string id = 1; map<string, int32> quantities = 2; '
        'message Nested { bool active = 1; } }\n'
        'message OrderResp { string result = 1; }\n'
        'service Order { rpc Send(OrderReq) returns(OrderResp); }\n',
        encoding="utf-8")
    builder = CKGBuilder(str(tmp_path))
    builder.build()
    graph = builder.graph
    assert "contract::message::OrderReq.field::id" in graph
    assert "contract::message::OrderReq.field::quantities" in graph
    field = graph.nodes["contract::message::OrderReq.field::quantities"]
    assert field["map_key_type"] == "string"
    assert field["map_value_type"] == "int32"
    assert "contract::message::OrderReq.Nested.field::active" in graph
    assert any(
        u == "contract::message::OrderReq" and
        v == "contract::Order.Send"
        for u, v, _ in edges(graph, "ACCEPTS_SCHEMA")
    )
    assert any(
        u == "contract::Order.Send" and
        v == "contract::message::OrderResp"
        for u, v, _ in edges(graph, "RETURNS_SCHEMA")
    )


def test_interprocedural_cross_file_explicit_import(tmp_path):
    (tmp_path / "mathlib.py").write_text(
        "def triple(n):\n    return n * 3\n", encoding="utf-8")
    (tmp_path / "app.py").write_text(
        "from mathlib import triple\n"
        "def compute(x):\n"
        "    result = triple(x)\n"
        "    return result\n", encoding="utf-8")
    builder = CKGBuilder(str(tmp_path))
    builder.build()
    flow = {(u, v) for u, v, _ in edges(builder.graph, "FLOWS_TO")}
    assert ("app.py:compute.var::x", "mathlib.py:triple.var::n") in flow
    assert ("mathlib.py:triple.return::2", "app.py:compute.var::result") in flow


def test_auto_configured_lsp_resolves_qualified_source_call(tmp_path, monkeypatch):
    monkeypatch.setenv("SCKG_ALLOW_LSP_SUBPROCESS", "1")
    """End-to-end from .sckg_lsp.json through actual JSON-RPC to CALLS edge."""
    mock = tmp_path / "local_lsp_helper.txt"
    mock.write_text(
        'import json,sys\n'
        'root=""\n'
        'while True:\n'
        '    size=None\n'
        '    while True:\n'
        '        line=sys.stdin.buffer.readline()\n'
        '        if not line: sys.exit(0)\n'
        '        if line in (b"\\r\\n",b"\\n"): break\n'
        '        if line.lower().startswith(b"content-length:"):\n'
        '            size=int(line.split(b":",1)[1])\n'
        '    if size is None: continue\n'
        '    obj=json.loads(sys.stdin.buffer.read(size))\n'
        '    method=obj.get("method")\n'
        '    if method=="initialize": root=obj["params"]["rootUri"]\n'
        '    if method=="exit": sys.exit(0)\n'
        '    if "id" not in obj: continue\n'
        '    result=({"capabilities":{}} if method=="initialize" else\n'
        '            {"uri":root+"/definition.py",\n'
        '             "range":{"start":{"line":0,"character":4},\n'
        '                      "end":{"line":0,"character":10}}}\n'
        '            if method=="textDocument/definition" else None)\n'
        '    payload=json.dumps({"jsonrpc":"2.0","id":obj["id"],\n'
        '                        "result":result}).encode()\n'
        '    sys.stdout.buffer.write(b"Content-Length: "+str(len(payload)).encode()\n'
        '                            +b"\\r\\n\\r\\n"+payload)\n'
        '    sys.stdout.buffer.flush()\n', encoding="utf-8")
    (tmp_path / "definition.py").write_text(
        "def target():\n    return 100\n", encoding="utf-8")
    (tmp_path / "caller.py").write_text(
        "def invoke():\n    return remote.target()\n", encoding="utf-8")
    (tmp_path / ".sckg_lsp.json").write_text(json.dumps({
        "servers": {"python": [sys.executable, "-u", str(mock)]},
        "timeout_seconds": 3,
    }), encoding="utf-8")
    builder = CKGBuilder(str(tmp_path))
    try:
        builder.build()
        assert any(
            source == "caller.py:invoke" and target == "definition.py:target"
            and attrs.get("c_type") == 1.0
            and attrs.get("callsite_spelling") == "remote.target"
            for source, target, attrs in edges(builder.graph, "CALLS")
        )
    finally:
        resolver = getattr(builder, "compiler_resolver", None)
        if resolver:
            resolver.close()


def test_repository_cannot_launch_lsp_command_without_host_optin(tmp_path, monkeypatch):
    """A checkout may contain a manifest; indexing must not run its commands."""
    monkeypatch.delenv("SCKG_ALLOW_LSP_SUBPROCESS", raising=False)
    (tmp_path / "main.py").write_text(
        "def start():\n    return external.api()\n", encoding="utf-8")
    (tmp_path / ".sckg_lsp.json").write_text(json.dumps({
        "servers": {"python": ["/nonexistent/sckg-do-not-run"]},
        "timeout_seconds": 1
    }), encoding="utf-8")
    builder = CKGBuilder(str(tmp_path))
    builder.build()
    assert not hasattr(builder, "compiler_resolver")
    assert "main.py:start" in builder.graph
