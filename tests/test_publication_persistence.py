"""Durable snapshot and source-object bridge regression; no external attestation claims."""
from __future__ import annotations

import subprocess
import networkx as nx
import pytest

from sqlite_graph_store import SQLiteGraphStore
from lineage_bridge import bridge_git_lineage


def fixture_graph():
    g = nx.MultiDiGraph()
    g.graph["workspace"] = "source-inspected-fixture"
    g.add_node("src/api.py:handle", id="src/api.py:handle", type="function",
               line_no=3, line_end=7, meta={"source": "api.py"})
    g.add_node("contract::API.Fetch", type="rpc_contract", layer="Lcontract")
    g.add_edge("src/api.py:handle", "contract::API.Fetch", key="edge-1",
               relation="CONSUMES", layer="Lcontract",
               metadata={"id_ctx": "src/api.py", "c_type": 0.85})
    return g


def assert_exact_graph(left, right):
    assert dict(left.graph) == dict(right.graph)
    assert dict(left.nodes(data=True)) == dict(right.nodes(data=True))
    assert {(a, b, k): d for a, b, k, d in left.edges(keys=True, data=True)} == {
        (a, b, k): d for a, b, k, d in right.edges(keys=True, data=True)}


def test_sqlite_restart_history_and_exact_attribute_round_trip(tmp_path):
    file = tmp_path / "ckg.sqlite"
    graph = fixture_graph()
    one = SQLiteGraphStore(file)
    a = one.save("commit-a", graph)
    assert len(a["sha256"]) == 64
    assert one.head() == "commit-a"
    assert_exact_graph(graph, one.load("commit-a"))
    graph.nodes["src/api.py:handle"]["line_end"] = 9
    graph.edges["src/api.py:handle", "contract::API.Fetch", "edge-1"]["metadata"]["c_type"] = 0.65
    two = one.save("commit-b", graph, parent="commit-a")
    reopened = SQLiteGraphStore(file)
    assert reopened.head() == "commit-b"
    assert reopened.lineage() == [
        {"revision": "commit-b", "parent": "commit-a", "sha256": two["sha256"]},
        {"revision": "commit-a", "parent": None, "sha256": a["sha256"]},
    ]
    assert_exact_graph(graph, reopened.load())
    assert reopened.load("commit-a").nodes["src/api.py:handle"]["line_end"] == 7
    with pytest.raises(ValueError, match="revision conflict"):
        reopened.save("commit-c", graph, parent="commit-a")
    with pytest.raises(ValueError, match="already exists"):
        reopened.save("commit-b", graph, parent="commit-b")


def test_sqlite_detects_tampering_and_rejects_non_json(tmp_path):
    db = SQLiteGraphStore(tmp_path / "g.sqlite")
    good = fixture_graph()
    with pytest.raises(TypeError):
        good.nodes["src/api.py:handle"]["unserializable"] = {1, 2}
        db.save("bad", good)
    good.nodes["src/api.py:handle"].pop("unserializable")
    db.save("ok", good)
    with db._connect() as conn:
        conn.execute("UPDATE graph_snapshots SET payload=? WHERE revision='ok'", ('{}',))
    with pytest.raises(ValueError, match="digest mismatch"):
        SQLiteGraphStore(tmp_path / "g.sqlite").load("ok")


def _run(*args, cwd):
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def test_lineage_bridge_requires_local_exact_git_commit(tmp_path):
    _run("init", "-q", cwd=tmp_path)
    _run("config", "user.name", "Fixture", cwd=tmp_path)
    _run("config", "user.email", "fixture@example.test", cwd=tmp_path)
    (tmp_path / "api.py").write_text("print(1)\n")
    _run("add", ".", cwd=tmp_path)
    _run("commit", "-qm", "source fixture", cwd=tmp_path)
    sha = _run("rev-parse", "HEAD", cwd=tmp_path)
    graph = fixture_graph()
    graph.add_node("commit::" + sha[:12], type="commit", layer="Llineage", sha=sha)
    graph.add_node("source_revision::service::" + sha, type="source_revision",
                   layer="Loperational", sha=sha, repo_id="service")
    graph.add_edge("commit::" + sha[:12], "src/api.py:handle", key="touch",
                   relation="TOUCHES", layer="Llineage")
    bridged, report = bridge_git_lineage(graph, repo_id="service", checkout=tmp_path)
    assert report["linked"][0]["sha"] == sha
    assert bridged.has_edge("source_revision::service::" + sha, "commit::" + sha[:12])
    assert graph.number_of_edges() + 1 == bridged.number_of_edges()
    assert bridged.edges["source_revision::service::" + sha,
                         "commit::" + sha[:12],
                         "Loperational:EXACT_GIT_OBJECT:commit::" + sha[:12]]["verification"] == "git_commit_object_present"
    second, _ = bridge_git_lineage(bridged, repo_id="service", checkout=tmp_path)
    assert second.number_of_edges() == bridged.number_of_edges()
    # No short-hash collision is acceptable as a source identity proof.
    ambiguous = graph.copy()
    ambiguous.add_node("another-commit", type="commit", sha=sha)
    result, status = bridge_git_lineage(ambiguous, repo_id="service", checkout=tmp_path)
    assert status["linked"] == [] and status["unmatched"][0]["reason"] == "no_unique_commit_node"
    assert not result.has_edge("source_revision::service::" + sha, "commit::" + sha[:12])
