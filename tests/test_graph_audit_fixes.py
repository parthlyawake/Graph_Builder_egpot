"""Regressions found by source-to-graph checks on real polyglot repositories."""

import tempfile
import unittest
from pathlib import Path

from graft_ckg import CKGBuilder


def relations(graph, source, relation):
    return [target for _, target, data in graph.out_edges(source, data=True)
            if data.get("relation") == relation]


class GraphAuditFixTests(unittest.TestCase):
    def test_java_qualified_system_call_does_not_bind_to_same_named_method(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, "Controller.java").write_text(
                "class Controller {\n"
                "  String getenv(String key) { return System.getenv(key); }\n"
                "}\n", encoding="utf-8")
            graph = CKGBuilder(root).build()
        caller = "Controller.java:Controller.getenv"
        self.assertNotIn(caller, relations(graph, caller, "CALLS"))
        self.assertIn("external::System.getenv", relations(graph, caller, "CALLS"))

    def test_go_struct_field_resolves_right_method_among_same_named_methods(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, "api.go").write_text(
                "package demo\ntype CatalogAPI struct {}\n"
                "func (a *CatalogAPI) Reindex() {}\n", encoding="utf-8")
            Path(root, "repo.go").write_text(
                "package demo\ntype Repository struct {}\n"
                "func (r *Repository) Reindex() {}\n", encoding="utf-8")
            Path(root, "controller.go").write_text(
                "package demo\ntype Controller struct { api *CatalogAPI }\n"
                "func (c *Controller) ReindexProducts() { c.api.Reindex() }\n",
                encoding="utf-8")
            graph = CKGBuilder(root).build()
        caller = "controller.go:Controller.ReindexProducts"
        targets = relations(graph, caller, "CALLS")
        self.assertIn("api.go:CatalogAPI.Reindex", targets)
        self.assertNotIn("repo.go:Repository.Reindex", targets)
        self.assertNotIn("external::c.api.Reindex", targets)

    def test_spring_route_has_one_canonical_contract(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, "Orders.java").write_text(
                "import org.springframework.web.bind.annotation.*;\n"
                "@RestController @RequestMapping(\"/orders\")\n"
                "class Orders { @GetMapping(\"/list\") String list() { return \"ok\"; } }\n",
                encoding="utf-8")
            graph = CKGBuilder(root).build()
        handler = "Orders.java:Orders.list"
        contract = "http::GET:/orders/list"
        self.assertEqual(relations(graph, handler, "IMPLEMENTS"), [contract])
        self.assertEqual(relations(graph, contract, "PRODUCES"), [handler])
        self.assertFalse(any(node.startswith("contract::HTTP.") for node in graph))

    def test_csharp_interface_member_has_declaration_edge(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, "IStore.cs").write_text(
                "public interface IStore { bool Ping(); }\n", encoding="utf-8")
            graph = CKGBuilder(root).build()
        self.assertIn("IStore.cs:IStore.Ping", relations(graph, "IStore.cs:IStore", "DECLARES"))

    def test_invoked_go_closure_is_not_an_external_source_blob(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, "main.go").write_text(
                "package main\nfunc main() { func() {}() }\n", encoding="utf-8")
            graph = CKGBuilder(root).build()
        self.assertFalse(any(target.startswith("external::func()")
                             for target in relations(graph, "main.go:main", "CALLS")))

    def test_dynamic_python_host_keeps_path_as_possible_target(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, "api.py").write_text(
                "from flask import Flask\napp = Flask(__name__)\n"
                "@app.post('/orders')\ndef create(): return 'ok'\n",
                encoding="utf-8")
            Path(root, "client.py").write_text(
                "def send(session, base):\n    session.post(base + '/orders')\n",
                encoding="utf-8")
            graph = CKGBuilder(root).build()
        callsites = relations(graph, "client.py:send", "HTTP_REQUEST")
        self.assertEqual(len(callsites), 1)
        self.assertEqual(graph.nodes[callsites[0]]["name"], "POST /orders (host unresolved)")
        self.assertIn("http::POST:/orders", relations(graph, callsites[0], "POSSIBLE_HTTP_TARGET"))
        self.assertEqual(relations(graph, "client.py:send", "HTTP_CALLS"), [])

    def test_dynamic_go_host_keeps_method_and_path(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, "client.go").write_text(
                "package demo\nimport \"net/http\"\n"
                "func send(base string) { http.NewRequest(\"POST\", base+\"/ship-order\", nil) }\n",
                encoding="utf-8")
            graph = CKGBuilder(root).build()
        callsites = relations(graph, "client.go:send", "HTTP_REQUEST")
        self.assertEqual(len(callsites), 1)
        self.assertEqual(graph.nodes[callsites[0]]["name"], "POST /ship-order (host unresolved)")


if __name__ == "__main__":
    unittest.main()
