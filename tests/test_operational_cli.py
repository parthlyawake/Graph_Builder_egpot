"""End-to-end smoke: existing graph export -> operational enrichment -> reload."""
import json
from graph_io import load_graph_json
from bench.ingest_operational_manifest import main


def test_cli_roundtrip(tmp_path):
    src = tmp_path / "code.json"
    manifest = tmp_path / "evidence.json"
    output = tmp_path / "combined.json"
    report_path = tmp_path / "report.json"
    src.write_text(json.dumps({"format_version": "1.1", "graph_metadata": {"workspace": "fixture"},
                               "nodes": [{"id": "a.py:f", "type": "function"}], "edges": []}), encoding="utf-8")
    manifest.write_text(json.dumps({"schema_version": 1, "builds": [{
        "id": "ci1", "repo_id": "checkout", "service_name": "checkout", "commit_sha": "a"*40,
        "artifact_digest": "sha256:"+"b"*64, "timestamp": "2026-11-15T09:00:00Z",
        "builder_id": "https://ci.example/builder"}]}), encoding="utf-8")
    main(["--graph", str(src), "--manifest", str(manifest), "--output", str(output),
          "--report", str(report_path)])
    graph = load_graph_json(output)
    assert graph.graph["workspace"] == "fixture"
    assert "a.py:f" in graph
    assert graph.has_edge("source_revision::checkout::"+"a"*40, "build::ci1")
    assert json.loads(report_path.read_text())["builds"] == 1
