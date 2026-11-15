"""Handoff reports must distinguish construction from edge precision."""
import json
from bench.build_workspace import run


def test_working_multi_service_graph_report(tmp_path):
    client = tmp_path / "client"
    server = tmp_path / "server"
    client.mkdir()
    server.mkdir()
    (client / "main.py").write_text(
        "import requests\n"
        "def get(): return requests.get('http://server:8000/api/items')\n"
    )
    (server / "app.py").write_text(
        "from flask import Flask\napp = Flask(__name__)\n"
        "@app.get('/api/items')\ndef items(): return []\n"
    )
    manifest = tmp_path / "workspace.json"
    manifest.write_text(json.dumps({
        "name": "tiny",
        "repositories": [
            {"id": "client", "path": "./client"},
            {"id": "server", "path": "./server"},
        ]
    }))
    result = run(manifest, tmp_path / "report.json", min_http=1)
    assert result["gate"]["passed"]
    assert result["relations"]["HTTP_CALLS"] >= 1
    assert result["verification"]["total_repositories"] == 2
