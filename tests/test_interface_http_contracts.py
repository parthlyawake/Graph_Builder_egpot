"""First-class interface and HTTP contract graph regression tests."""

import tempfile
import unittest
from pathlib import Path

from graft_ckg import CKGBuilder


class InterfaceHttpContractTests(unittest.TestCase):
    def test_typescript_interface_members_and_explicit_implementation(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, "types.ts").write_text(
                "export interface Store { get(id: string): string; name: string; }\n"
                "export interface NamedStore extends Store { display(): string; }\n"
                "export class MemoryStore implements Store {\n"
                "  name = 'memory';\n  get(id: string) { return id; }\n}\n",
                encoding="utf-8",
            )
            graph = CKGBuilder(root).build()
            self.assertEqual(graph.nodes["types.ts:Store"]["type"], "interface")
            self.assertEqual(graph.nodes["types.ts:Store.get"]["type"], "method")
            self.assertEqual(graph.nodes["types.ts:Store.name"]["type"], "property")
            contracts = {
                (u, v, d["relation"]) for u, v, d in graph.edges(data=True)
                if d.get("layer") == "Lcontract"
            }
            self.assertIn(("types.ts:MemoryStore", "types.ts:Store", "IMPLEMENTS"), contracts)
            self.assertIn(("types.ts:NamedStore", "types.ts:Store", "EXTENDS"), contracts)

    def test_file_route_has_contract_and_literal_consumer(self):
        with tempfile.TemporaryDirectory() as root:
            route = Path(root, "app", "api", "orders", "route.ts")
            route.parent.mkdir(parents=True)
            route.write_text("export async function POST() { return Response.json({ok:true}); }\n", encoding="utf-8")
            Path(root, "client.ts").write_text(
                "export async function submit() { return fetch('/api/orders', { method: 'POST' }); }\n",
                encoding="utf-8",
            )
            graph = CKGBuilder(root).build()
            contract = "http::POST:/api/orders"
            self.assertEqual(graph.nodes[contract]["type"], "http_endpoint")
            edges = {(u, v, d["relation"]) for u, v, d in graph.edges(data=True)}
            self.assertIn(("app/api/orders/route.ts:POST", contract, "IMPLEMENTS"), edges)
            self.assertIn(("client.ts:submit", contract, "CONSUMES"), edges)
            self.assertIn(("client.ts:submit", "app/api/orders/route.ts:POST", "HTTP_CALLS"), edges)

    def test_root_api_route_and_go_interface_are_typed(self):
        with tempfile.TemporaryDirectory() as root:
            route = Path(root, "app", "api", "route.ts")
            route.parent.mkdir(parents=True)
            route.write_text("export function GET() { return Response.json({ok:true}); }\n", encoding="utf-8")
            Path(root, "store.go").write_text(
                "package store\ntype Reader interface { Read() string }\n",
                encoding="utf-8",
            )
            graph = CKGBuilder(root).build()
            self.assertEqual(graph.nodes["http::GET:/api"]["type"], "http_endpoint")
            self.assertEqual(graph.nodes["store.go:Reader"]["type"], "interface")


if __name__ == "__main__":
    unittest.main()
