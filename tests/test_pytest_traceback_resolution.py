"""Regression for reported Pytest file:line: in function resolution."""
import contextlib
import io
import pytest
from graft_ckg import CKGBuilder
from contracts.sckg_provider import SCKGGraphProvider
from contracts.graph_types import TelemetryEvent
from contracts.stack_frames import parse_stack_frames


@pytest.fixture
def provider(tmp_path):
    src = tmp_path / "microservices/rest-api/utils/auth_utils.py"
    src.parent.mkdir(parents=True)
    src.write_text("\n" * 60 +
        "def verify_token(token):\n" +
        "    if not token:\n        return False\n" +
        "    if isinstance(token, str):\n        token = token.strip()\n" +
        "    if token == 'bad':\n        raise ValueError('bad')\n" +
        "    return token\n")
    with contextlib.redirect_stdout(io.StringIO()):
        b = CKGBuilder(str(tmp_path), repo_id="python-test-repo")
        b.build()
    return SCKGGraphProvider(b)


@pytest.mark.parametrize("trace", [
    "microservices/rest-api/utils/auth_utils.py:68: in verify_token",
    '  File "microservices/rest-api/utils/auth_utils.py", line 68, in verify_token',
    '  File "/work/microservices/rest-api/utils/auth_utils.py", line 68, in verify_token',
    "microservices/rest-api/utils/auth_utils.py:61: in verify_token",
    "microservices/rest-api/utils/auth_utils.py:68",
    "C:\\work\\microservices\\rest-api\\utils\\auth_utils.py:68: in verify_token",
])
def test_reported_frame_formats(provider, trace):
    target = "python-test-repo/microservices/rest-api/utils/auth_utils.py:verify_token"
    assert target in provider.graph
    assert provider.graph.nodes[target]["line_no"] == 61
    assert provider.graph.nodes[target]["line_end"] == 68
    found = provider.resolve_symptom(TelemetryEvent(service_name="rest-api",
        message="HTTPException: 401: Invalid token type", stack_trace=trace))
    assert [node.node_id for node in found] == [target]


@pytest.mark.parametrize("trace", [
    "microservices/rest-api/utils/auth_utils.py:69",
    "microservices/rest-api/utils/auth_utils.py:68: in missing_method",
    'File "/unknown/fake.py", line 68, in verify_token',
])
def test_unresolvable_frames_never_fallback_to_service(provider, trace):
    assert provider.resolve_symptom(TelemetryEvent(
        service_name="rest-api", message="verify_token", stack_trace=trace)) == []


def test_specific_frames_do_not_reparse_generically():
    assert parse_stack_frames(
        "microservices/rest-api/utils/auth_utils.py:68: in verify_token\n"
        '  File "other/a.py", line 3, in parse\n'
        "other/b.go:42\n") == [
        ("microservices/rest-api/utils/auth_utils.py", 68, "verify_token"),
        ("other/a.py", 3, "parse"),
        ("other/b.go", 42, ""),
    ]


def test_ast_spans_include_async_nested_and_class(tmp_path):
    (tmp_path / "service.py").write_text(
        "class Handler:\n    async def run(self):\n"
        "        value = 1\n        return value\n"
        "\ndef outer():\n    def inner():\n"
        "        return 2\n    return inner()\n")
    with contextlib.redirect_stdout(io.StringIO()):
        b = CKGBuilder(str(tmp_path))
        b.build()
    for symbol, end in (("Handler", 4), ("Handler.run", 4),
                        ("outer", 9), ("outer.inner", 8)):
        assert b.graph.nodes["service.py:" + symbol]["line_end"] == end


def test_line_only_frame_prefers_innermost_function(tmp_path):
    (tmp_path / "service.py").write_text(
        "def outer():\n    def inner():\n"
        "        return 2\n    return inner()\n")
    with contextlib.redirect_stdout(io.StringIO()):
        builder = CKGBuilder(str(tmp_path))
        builder.build()
    provider = SCKGGraphProvider(builder)
    matches = provider.resolve_symptom(TelemetryEvent(stack_trace="service.py:3"))
    assert [item.node_id for item in matches] == ["service.py:outer.inner"]


def test_duplicate_source_basename_does_not_invent_identity():
    import networkx as nx
    graph = nx.MultiDiGraph()
    for repo, path in [("api", "service-a/auth.py"), ("billing", "service-b/auth.py")]:
        nid = repo + "/" + path + ":verify_token"
        graph.add_node(nid, type="function", name="verify_token",
                       file=path, repo=repo, line_no=2, line_end=12)
    provider = SCKGGraphProvider(graph)
    trace = "auth.py:9: in verify_token"
    assert provider.resolve_symptom(TelemetryEvent(stack_trace=trace)) == []
    found = provider.resolve_symptom(TelemetryEvent(
        service_name="api", stack_trace=trace))
    assert [item.node_id for item in found] == ["api/service-a/auth.py:verify_token"]


@pytest.mark.parametrize("filename,source,body_line", [
    ("service.go", "package sample\nfunc verifyToken(v string) bool {\n    if v == \"\" {\n        return false\n    }\n    return true\n}\n", 4),
    ("Demo.java", "class Demo {\n    void verifyToken() {\n        int x = 1;\n    }\n}\n", 3),
    ("utils.ts", "export function verifyToken(value: string): boolean {\n  return value.length > 0;\n}\n", 2),
])
def test_polyglot_body_lines_recover_bare_frames(tmp_path, filename, source, body_line):
    (tmp_path / filename).write_text(source, encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        builder = CKGBuilder(str(tmp_path))
        builder.build()
    expected = [n for n, a in builder.graph.nodes(data=True)
                if a.get("type") == "function" and a.get("name") == "verifyToken"]
    assert len(expected) == 1
    node = expected[0]
    assert builder.graph.nodes[node]["line_end"] >= body_line
    matches = SCKGGraphProvider(builder).resolve_symptom(
        TelemetryEvent(stack_trace=f"{filename}:{body_line}"))
    assert [item.node_id for item in matches] == [node]


@pytest.mark.parametrize("filename,initial,updated,target_line", [
    ("service.py", "def work():\n    return 1\n",
     "def work():\n    value = 2\n    return value\n", 3),
    ("service.go", "package x\nfunc work() int {\n  return 1\n}\n",
     "package x\nfunc work() int {\n  value := 2\n  return value\n}\n", 4),
])
def test_source_ranges_rebuilt_after_incremental_edits(
        tmp_path, filename, initial, updated, target_line):
    target = tmp_path / filename
    target.write_text(initial, encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        b = CKGBuilder(str(tmp_path))
        b.build()
        target.write_text(updated, encoding="utf-8")
        b.update_files([filename])
        fresh = CKGBuilder(str(tmp_path))
        fresh.build()
    for graph in (b.graph, fresh.graph):
        nid = filename + ":work"
        assert graph.nodes[nid]["line_end"] >= target_line
        matches = SCKGGraphProvider(graph).resolve_symptom(
            TelemetryEvent(stack_trace=f"{filename}:{target_line}"))
        assert [node.node_id for node in matches] == [nid]
    assert b.graph.nodes[filename + ":work"]["line_end"] == (
        fresh.graph.nodes[filename + ":work"]["line_end"])
