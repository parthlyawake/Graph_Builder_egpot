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
