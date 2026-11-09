"""HTTP source evidence and unambiguous target tests (no grammar required)."""
import unittest
from collections import defaultdict
from types import SimpleNamespace

import networkx as nx

from graph_builder_http import path_matches, deployment_context, resolve_workspace_http


class FakeWorkspace:
    def __init__(self, tmp):
        self.config = SimpleNamespace(base_dir=tmp, repositories=[
            SimpleNamespace(id="client", path="client"),
            SimpleNamespace(id="orders", path="orders"),
        ])
        self.graph = nx.MultiDiGraph()
        self.repo_builders = {}
        self.http_endpoints = {}
    def _resolve_path(self, path):
        from pathlib import Path
        return str(Path(self.config.base_dir) / path)


class ReviewHTTPTests(unittest.TestCase):
    def test_route_segments_and_no_partial_match(self):
        self.assertTrue(path_matches("/api/items/{id}", "/api/items/42"))
        self.assertFalse(path_matches("/api/items/{id}", "/api/items/42/extra"))
        self.assertFalse(path_matches("/api/items", "/api/items-extra"))
        self.assertFalse(path_matches("/api/items/{id}", "/api/items/"))

    def test_unique_host_and_verb_binding(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "client").mkdir()
            (root / "orders").mkdir()
            w = FakeWorkspace(tmp)
            w.graph.add_node("client/main.py:send", type="function", file="main.py",
                             line_no=2, repo="client")
            w.graph.add_node("orders/Controller.java:Controller.read",
                             type="function", repo="orders")
            w.http_endpoints[("GET", "/api/items/{id}")] = [
                "orders/Controller.java:Controller.read"
            ]
            w.repo_builders["client"] = SimpleNamespace(
                repo_prefix="client/", graph=w.graph,
                raw_file_lines={"main.py": [
                    "import requests",
                    "def send():",
                    '    return requests.get("http://orders/api/items/42")',
                ]}, http_calls_to_resolve=[])
            w.repo_builders["orders"] = SimpleNamespace(
                repo_prefix="orders/", graph=w.graph,
                raw_file_lines={}, http_calls_to_resolve=[])
            self.assertEqual(resolve_workspace_http(w), 1)
            self.assertEqual(resolve_workspace_http(w), 0)
            found = [d for u, v, d in w.graph.edges(data=True)
                     if d.get("relation") == "HTTP_CALLS"]
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]["http_method"], "GET")

    def test_unknown_host_has_no_fallback(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "client").mkdir()
            (root / "orders").mkdir()
            w = FakeWorkspace(tmp)
            w.graph.add_node("client/main.py:send", type="function", line_no=2,
                             file="main.py", repo="client")
            w.graph.add_node("orders/controller.py:read", type="function", repo="orders")
            w.http_endpoints[("GET", "/api/items/{id}")] = ["orders/controller.py:read"]
            w.repo_builders["client"] = SimpleNamespace(
                repo_prefix="client/", graph=w.graph,
                raw_file_lines={"main.py": [
                    "import requests", "def send():",
                    '    return requests.get("http://unknown/api/items/42")',
                ]}, http_calls_to_resolve=[])
            w.repo_builders["orders"] = SimpleNamespace(
                repo_prefix="orders/", graph=w.graph,
                raw_file_lines={}, http_calls_to_resolve=[])
            self.assertEqual(resolve_workspace_http(w), 0)


if __name__ == "__main__":
    unittest.main()
