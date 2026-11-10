"""Registration-aware producer binding checks without requiring a parser runtime."""
import unittest
from types import SimpleNamespace
import networkx as nx
from graph_builder_bindings import bind_managed_grpc


class ManagedProducerBindingTests(unittest.TestCase):
    def test_csharp_requires_registration_and_override(self):
        graph = nx.MultiDiGraph()
        cls = "svc/Cart.cs:CartService"
        method = cls + ".GetCart"
        graph.add_node(cls, type="class", grpc_language="csharp",
                       grpc_service="CartService", grpc_qualified_name="CartService")
        graph.add_node(method, type="function", is_override=True)
        graph.add_node(cls + ".NotOverride", type="function")
        graph.add_node("contract::CartService", type="service_contract")
        graph.add_node("contract::CartService.GetCart", type="rpc_contract")
        builder = SimpleNamespace(graph=graph, repo_prefix="svc/",
            managed_grpc_registrations=[])
        contracts = {"CartService": {"node_id": "contract::CartService",
            "rpcs": {"GetCart": "contract::CartService.GetCart"}}}
        self.assertEqual(bind_managed_grpc(builder, graph, contracts), 0)
        builder.managed_grpc_registrations = [
            ("csharp", "CartService", "Startup.cs", "svc/Startup.cs:Startup.Configure")]
        self.assertEqual(bind_managed_grpc(builder, graph, contracts), 2)
        self.assertEqual(bind_managed_grpc(builder, graph, contracts), 0)
        self.assertTrue(graph.has_edge(method, "contract::CartService.GetCart"))
        attrs = next(d for d in graph.get_edge_data(
            method, "contract::CartService.GetCart").values()
            if d.get("relation") == "IMPLEMENTS")
        self.assertEqual(attrs["layer"], "Lcontract")
        self.assertEqual(attrs["metadata"]["id_ctx"], "svc/Startup.cs")
        self.assertEqual(attrs["c_type"], 1.0)

    def test_wrong_qualified_type_is_not_selected(self):
        graph = nx.MultiDiGraph()
        graph.add_node("svc/Cart.cs:CartService", type="class", grpc_language="csharp",
                       grpc_service="CartService", grpc_qualified_name="Shop.CartService")
        graph.add_node("contract::CartService", type="service_contract")
        builder = SimpleNamespace(graph=graph, repo_prefix="svc/",
            managed_grpc_registrations=[("csharp", "Wrong.CartService", "Startup.cs", "")])
        contracts = {"CartService": {"node_id": "contract::CartService", "rpcs": {}}}
        self.assertEqual(bind_managed_grpc(builder, graph, contracts), 0)


if __name__ == "__main__":
    unittest.main()
