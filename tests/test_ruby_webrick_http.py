"""Ruby WEBrick route mounting and concrete cross-service source evidence."""
from pathlib import Path

from multi_repo import WorkspaceCKGBuilder


def test_webrick_prefix_mount_links_only_proven_host(tmp_path):
    files = {
        "details/service.rb": """
require 'webrick'
server = WEBrick::HTTPServer.new(Port: 9080)
server.mount_proc '/details' do |req, res|
  res.body = 'ok'
end
# server.mount_proc '/fake' do |req, res| end
""",
        "client/app.py": """
import requests
def load():
    return requests.get("http://details:9080/details/123")
def unmatched():
    return requests.get("http://other:9080/details/123")
""",
    }
    for file, source in files.items():
        path = tmp_path / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source.lstrip(), encoding="utf-8")
    (tmp_path / "workspace.yaml").write_text(
        "name: webrick\nrepositories:\n"
        "  - id: details\n    path: ./details\n"
        "  - id: client\n    path: ./client\n",
        encoding="utf-8",
    )
    builder = WorkspaceCKGBuilder(str(tmp_path / "workspace.yaml"))
    builder.build()
    graph = builder.graph
    routes = {
        v for u, v, d in graph.edges(data=True)
        if u == "client/app.py:load" and d.get("relation") == "HTTP_CALLS"
    }
    assert len(routes) == 1
    target = next(iter(routes))
    assert target.startswith("details/service.rb:http_route@")
    assert graph.nodes[target]["http_prefix_mount"] is True
    assert ("*", "/details") in builder.http_endpoints
    assert ("*", "/fake") not in builder.http_endpoints
    assert not [
        1 for _, _, d in graph.out_edges("client/app.py:unmatched", data=True)
        if d.get("relation") == "HTTP_CALLS"
    ]
