"""Source-grounded regressions from SOP remediation review (2026-11-13).

Negative cases must stay negative: a path match without host evidence does not
prove that one service calls another, and a duplicate file basename does not
identify a frame or imported module across repositories.
"""
from __future__ import annotations

from pathlib import Path

import networkx as nx
import pytest

from contracts.graph_types import TelemetryEvent, TraversalPolicy
from contracts.sckg_provider import SCKGGraphProvider
from graft_ckg import CKGBuilder
from graph_builder_http import path_matches
from multi_repo import WorkspaceCKGBuilder


@pytest.fixture(scope="module")
def reviewed_workspace(tmp_path_factory):
    root = tmp_path_factory.mktemp("sop_review")
    sources = {
        "orders/app/main.py": '''
from flask import Flask
app = Flask(__name__)
@app.get("/health")
def health():
    return "ok"
@app.get("/api/items")
def handler():
    return compute()
def compute():
    return [1]
''',
        "billing/app/main.py": '''
from flask import Flask
app = Flask(__name__)
@app.get("/health")
def health():
    return "ok"
@app.get("/api/items")
def handler():
    return compute()
def compute():
    return [2]
''',
        "go_client/main.go": '''
package main
import "net/http"
func Check() { http.Get("http://orders:8000/health") }
''',
        "web/client.py": '''
import requests
def check_orders():
    return requests.get("http://orders:8000/health")
def check_unknown():
    return requests.get("http://unknown:8000/health")
def relative():
    return requests.get("/health")
''',
        "web/broken.py": "def ok():\n    return 1\n\ndef broken(:\n    pass\n",
        "web/Legacy.java": "public class Legacy { public int price() { return 1; } }\n",
        "ui/server.js": '''
const express = require("express");
const app = express();
function listItems(req, res) { res.json([]); }
app.get("/api/list", listItems);
''',
        "ui/client.js": '''
async function relative() { return fetch("/api/list"); }
async function absolute() { return fetch("http://ui:3000/api/list"); }
async function wrongHost() { return fetch("http://missing:3000/api/list"); }
''',
    }
    for file, contents in sources.items():
        destination = root / file
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(contents.strip() + "\n", encoding="utf-8")
    manifest = root / "workspace.yaml"
    manifest.write_text(
        "name: review_workspace\nversion: '1.0'\nrepositories:\n"
        + "".join(
            f"  - id: {name}\n    path: ./{name}\n"
            for name in ("orders", "billing", "web", "ui", "go_client")
        ), encoding="utf-8")
    builder = WorkspaceCKGBuilder(str(manifest))
    builder.build()
    return builder


def _edge_targets(graph, caller, relation):
    return {
        str(v) for _, v, d in graph.out_edges(caller, data=True)
        if d.get("relation") == relation
    }


def test_literal_host_does_not_link_every_service(reviewed_workspace):
    g = reviewed_workspace.graph
    caller = "web/client.py:check_orders"
    targets = _edge_targets(g, caller, "HTTP_CALLS")
    assert "orders/app/main.py:health" in targets
    assert "billing/app/main.py:health" not in targets
    assert _edge_targets(g, "web/client.py:check_unknown", "HTTP_CALLS") == set()


def test_ambiguous_path_has_only_weak_candidates(reviewed_workspace):
    g = reviewed_workspace.graph
    caller = "web/client.py:relative"
    assert not _edge_targets(g, caller, "HTTP_CALLS")
    candidates = _edge_targets(g, caller, "POSSIBLE_HTTP_TARGET")
    assert "orders/app/main.py:health" in candidates
    assert "billing/app/main.py:health" in candidates


def test_weak_targets_are_not_in_operational_blast_radius(reviewed_workspace):
    provider = SCKGGraphProvider(reviewed_workspace)
    src = "web/client.py:relative"
    result = provider.forward_traverse(
        provider.get_node_detail(src), TraversalPolicy(max_depth=2, max_nodes=80))
    ids = {n.node_id for n in result.nodes}
    assert "orders/app/main.py:health" not in ids
    assert "billing/app/main.py:health" not in ids



def test_go_host_literal_is_source_resolved(reviewed_workspace):
    targets = _edge_targets(reviewed_workspace.graph, "go_client/main.go:Check", "HTTP_CALLS")
    assert "orders/app/main.py:health" in targets
    assert "billing/app/main.py:health" not in targets


def test_js_absolute_url_and_relative_fetch(reviewed_workspace):
    g = reviewed_workspace.graph
    target = "ui/server.js:listItems"
    assert target in _edge_targets(g, "ui/client.js:absolute", "HTTP_CALLS")
    assert target in _edge_targets(g, "ui/client.js:relative", "HTTP_CALLS")
    assert not _edge_targets(g, "ui/client.js:wrongHost", "HTTP_CALLS")


def test_stack_frames_select_correct_service(reviewed_workspace):
    provider = SCKGGraphProvider(reviewed_workspace)
    for frame in ('app/main.py', '/work/app/main.py'):
        trace = f'File "{frame}", line 6, in handler'
        event = TelemetryEvent(service_name="orders", stack_trace=trace,
                               error_type="KeyError", message="price")
        matches = provider.resolve_symptom(event)
        assert [m.node_id for m in matches] == ["orders/app/main.py:handler"]


def test_stack_frame_mismatch_never_falls_back_to_arbitrary_service(reviewed_workspace):
    provider = SCKGGraphProvider(reviewed_workspace)
    event = TelemetryEvent(service_name="orders", stack_trace=
                           'File "/unknown/nonexistent.py", line 10, in missing',
                           error_type="KeyError", message="price")
    assert provider.resolve_symptom(event) == []


def test_report_exposes_failed_source_and_language_coverage(reviewed_workspace):
    report = reviewed_workspace.verify_graph()
    assert report["skipped_file_count"] >= 1
    assert not report["source_coverage_complete"]
    skipped = report["repositories"]["web"]["skipped_files"]
    assert any(item["file"] == "broken.py" and item["repo"] == "web"
               for item in skipped)
    assert report["repositories"]["web"]["source_coverage_complete"] is False
    # Grammar for Java is mandatory and declared even on systems where a
    # different source subset is being indexed.
    assert "java" in reviewed_workspace.repo_builders["web"].get_language_report()["languages"]


def test_forward_traverse_is_strictly_bounded_and_stable():
    g = nx.MultiDiGraph()
    root = "big/mod.py:hub"
    g.add_node(root, type="function", name="hub", repo="big", file="big/mod.py")
    for i in reversed(range(80)):
        src = f"big/mod.py:f{i}"
        g.add_node(src, type="function", name=f"f{i}", repo="big", file="big/mod.py")
        g.add_edge(src, root, relation="CALLS", layer="Ldep")
    semantic = "big/mod.py:unrelated"
    g.add_node(semantic, type="function", name="unrelated", repo="big", file="big/mod.py")
    g.add_edge(root, semantic, relation="SEMANTIC_SIMILAR", layer="Lsem")
    provider = SCKGGraphProvider(g)
    policy = TraversalPolicy(max_depth=4, max_nodes=50)
    first = provider.forward_traverse(provider.get_node_detail(root), policy)
    second = provider.forward_traverse(provider.get_node_detail(root), policy)
    ids = [item.node_id for item in first.nodes]
    assert ids == [item.node_id for item in second.nodes]
    assert len(ids) == 50
    assert ids[0] == root
    assert semantic not in ids
    assert ids[1:] == sorted(ids[1:])
    only_semantics = provider.forward_traverse(
        provider.get_node_detail(root),
        TraversalPolicy(max_depth=1, max_nodes=5, include_layers=["Lsem"]),
    )
    assert [x.node_id for x in only_semantics.nodes] == [root, semantic]
    assert provider.forward_traverse(provider.get_node_detail(root),
                                     TraversalPolicy(max_nodes=0)).node_count == 0


def test_service_alias_not_substring_and_production_test_prefix():
    provider = SCKGGraphProvider(nx.MultiDiGraph())
    assert provider._service_matches("author-service", "author_service")
    assert not provider._service_matches("auth", "author-service")
    assert not provider._service_matches("api", "payments-api")
    assert not provider._is_test_node(
        "prod/app.py:TestimonialService",
        {"name":"TestimonialService", "file":"prod/app.py"},
    )


def test_ignore_globs_do_not_match_embedded_path_fragments(tmp_path):
    builder = CKGBuilder(str(tmp_path))
    builder._load_ignore_patterns()
    assert builder._is_ignored("build/foo.py")
    assert not builder._is_ignored("rebuild/foo.py")
    assert not builder._is_ignored("internal/build/foo.py")


def test_ambiguous_module_basename_is_not_assigned(tmp_path):
    for name in ("a/utils.py", "b/utils.py"):
        f = tmp_path / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("def helper():\n    return 1\n",encoding="utf-8")
    builder = CKGBuilder(str(tmp_path))
    builder.build()
    assert "utils" not in builder.module_to_file
    assert builder.module_to_file["a.utils"] == "a/utils.py"
    assert builder.module_to_file["b.utils"] == "b/utils.py"


def test_route_parameter_spellings_match_only_whole_segments():
    assert path_matches("/users/{id}", "/users/42")
    assert path_matches("/users/<id>", "/users/42")
    assert path_matches("/users/:id", "/users/42")
    assert not path_matches("/users/:id", "/users/42/edit")
    assert not path_matches("/users/:id", "/products/42")
