"""HTTP binding precision and conservative fallback regression tests.

Tests use small synthetic graphs to isolate the cross-service resolver without
network access or external Train-Ticket source trees.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import networkx as nx
import pytest

from graph_builder_http import resolve_workspace_http
from multi_repo import RepoConfig, WorkspaceConfig


def _workspace(tmp_path, *, source="", legacy=False, strict=False, ambiguous=False):
    source_id = "client/client.py:fetch" if source else "client/client.js:fetch"
    handler_id = "orders/Controller.java:Controller.read"
    graph = nx.MultiDiGraph()
    graph.add_node(
        source_id, type="function", name="fetch", repo="client",
        http_ambiguous_definition=ambiguous,
    )
    graph.add_node(handler_id, type="function", name="read", repo="orders")
    client_graph = nx.MultiDiGraph()
    client_graph.add_node(source_id, type="function", name="fetch", line_no=2)
    client = SimpleNamespace(
        repo_prefix="client/",
        graph=client_graph,
        raw_file_lines={"client.py": source.splitlines()} if source else {},
        http_calls_to_resolve=[(source_id, "/api/items", "GET", "client.js")]
        if legacy else [],
    )
    config = WorkspaceConfig(
        base_dir=str(tmp_path),
        repositories=[RepoConfig(id="client", path="client"),
                      RepoConfig(id="orders", path="orders")],
        strict_http_source_evidence=strict,
    )
    workspace = SimpleNamespace(
        config=config, graph=graph, repo_builders={"client": client},
        http_endpoints={("GET", "/api/items"): [handler_id]},
        _resolve_path=lambda path: str(Path(tmp_path) / path),
    )
    return workspace, source_id, handler_id


def _http_edges(workspace):
    return [(u, v, data) for u, v, data in workspace.graph.edges(data=True)
            if data.get("relation") == "HTTP_CALLS"]


@pytest.mark.parametrize("import_line, invocation", [
    ("import urllib.request", "urllib.request.urlopen"),
    ("import urllib.request as req", "req.urlopen"),
    ("import urllib as url", "url.request.urlopen"),
    ("from urllib import request", "request.urlopen"),
    ("from urllib import request as req", "req.urlopen"),
    ("from urllib.request import urlopen", "urlopen"),
    ("from urllib.request import urlopen as fetch_url", "fetch_url"),
])
def test_urllib_import_styles_resolve_to_unique_http_handler(
        tmp_path, import_line, invocation):
    source = (
        f"{import_line}\n"
        "def fetch():\n"
        f'    return {invocation}("http://orders/api/items")\n'
    )
    workspace, caller, handler = _workspace(tmp_path, source=source, strict=True)
    assert resolve_workspace_http(workspace) == 1
    edges = _http_edges(workspace)
    assert len(edges) == 1
    assert edges[0][0:2] == (caller, handler)
    assert edges[0][2]["http_method"] == "GET"
    assert edges[0][2]["source_evidence"] == "client.py:3"
    assert resolve_workspace_http(workspace) == 0
    assert len(_http_edges(workspace)) == 1


@pytest.mark.parametrize("strict, candidate_count", [(False, 1), (True, 0)])
def test_strict_mode_controls_legacy_path_only_linking(tmp_path, strict, candidate_count):
    # A path alone is not evidence that the client calls another service.
    workspace, caller, handler = _workspace(tmp_path, legacy=True, strict=strict)
    assert resolve_workspace_http(workspace) == 0
    assert not _http_edges(workspace)
    weak = [(u, v, d) for u, v, d in workspace.graph.edges(data=True)
            if d.get("relation") == "POSSIBLE_HTTP_TARGET"]
    assert len(weak) == candidate_count
    if weak:
        assert weak[0][:2] == (caller, handler)
        assert weak[0][2]["match_kind"] == "path_only"


@pytest.mark.parametrize("legacy", [False, True])
def test_ambiguous_java_overload_caller_is_not_confirmed(tmp_path, legacy):
    if legacy:
        workspace, _, _ = _workspace(tmp_path, legacy=True, ambiguous=True)
    else:
        source = (
            "import requests\n"
            "def fetch():\n"
            '    return requests.get("http://orders/api/items")\n'
        )
        workspace, _, _ = _workspace(tmp_path, source=source, ambiguous=True)
    assert resolve_workspace_http(workspace) == 0
    assert not _http_edges(workspace)


def test_strict_mode_defaults_off_and_loads_from_workspace_config():
    assert WorkspaceConfig().strict_http_source_evidence is False
    assert WorkspaceConfig.from_dict(
        {"strict_http_source_evidence": True}
    ).strict_http_source_evidence is True
    assert WorkspaceConfig.from_dict(
        {"strict_http_source_evidence": False}
    ).strict_http_source_evidence is False
    assert WorkspaceConfig.from_dict(
        {"strict_http_source_evidence": "false"}
    ).strict_http_source_evidence is False
