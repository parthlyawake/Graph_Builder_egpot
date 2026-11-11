"""
Test Suite: Advanced Polyglot Architecture & Contract Layer
===========================================================
Validates:
- P1: Robust AST ProtoParser (services, rpcs, streaming, messages, fields, enums)
- P2: Full C# Extractor (ASP.NET routes, constructor DI, using directives)
- P3: Type-Aware Dispatch (type signatures, partition of unity sum(c_type) == 1.0)
- P4: Inter-Service Dataflow (Lflow crossing service boundaries via contract RPCs)
- P5: OpenAPI and GraphQL Contract Layer (endpoint and graphql contract nodes)
- P6: Kotlin Language Support (Spring annotations, gRPC servicers, imports)
- P7: LSP Augmentation (promotion of uncertain call to exact c_type=1.0)
- P8: Cross-Language Proto Type Identity (type-to-contract message links)
"""

import os
import sys
import unittest
import tempfile
import networkx as nx

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from proto_parser import ProtoParser
from openapi_graphql_parser import OpenAPIContractParser, GraphQLContractParser
from lsp_augmenter import LSPIndexProvider
from polyglot import TreeSitterExtractor, _KOTLIN_AVAILABLE, _CSHARP_AVAILABLE
from graft_ckg import CKGBuilder
from multi_repo import WorkspaceCKGBuilder


class AdvancedPolyglotArchitectureTests(unittest.TestCase):

    def test_p1_proto_parser_ast_completeness(self):
        """P1: Verifies ProtoParser extracts services, streaming RPCs, nested messages, and fields."""
        proto_content = """
        syntax = "proto3";
        package test.ecommerce;

        import "google/protobuf/empty.proto";

        service OrderService {
            // Unary RPC
            rpc CreateOrder (CreateOrderRequest) returns (OrderResponse);
            // Streaming RPC
            rpc StreamOrders (stream OrderFilter) returns (stream OrderResponse) {}
        }

        message Item {
            string item_id = 1;
            int32 quantity = 2;
        }

        message CreateOrderRequest {
            string customer_id = 1;
            repeated Item items = 2;
            oneof payment_method {
                string credit_card = 3;
                string paypal = 4;
            }
        }

        message OrderResponse {
            string order_id = 1;
            string status = 2;
        }

        enum OrderStatus {
            PENDING = 0;
            CONFIRMED = 1;
            SHIPPED = 2;
        }
        """
        pf = ProtoParser.parse_text(proto_content)
        self.assertEqual(pf.package, "test.ecommerce")
        self.assertIn("OrderService", pf.services)
        svc = pf.services["OrderService"]
        self.assertEqual(len(svc.rpcs), 2)
        self.assertIn("CreateOrder", svc.rpcs)
        self.assertIn("StreamOrders", svc.rpcs)

        create_rpc = svc.rpcs["CreateOrder"]
        self.assertEqual(create_rpc.request_type, "CreateOrderRequest")
        self.assertEqual(create_rpc.response_type, "OrderResponse")
        self.assertFalse(create_rpc.request_stream)

        stream_rpc = svc.rpcs["StreamOrders"]
        self.assertEqual(stream_rpc.request_type, "OrderFilter")
        self.assertTrue(stream_rpc.request_stream)
        self.assertTrue(stream_rpc.response_stream)

        self.assertIn("CreateOrderRequest", pf.messages)
        req_msg = pf.messages["CreateOrderRequest"]
        self.assertIn("customer_id", req_msg.fields)
        self.assertIn("items", req_msg.fields)
        self.assertTrue(req_msg.fields["items"].repeated)

        self.assertIn("OrderStatus", pf.enums)
        self.assertEqual(pf.enums["OrderStatus"], ["PENDING", "CONFIRMED", "SHIPPED"])

    def test_p2_csharp_aspnet_routes_and_di(self):
        """P2: Verifies C# extractor extracts ASP.NET MVC routes and constructor DI for gRPC clients."""
        if not _CSHARP_AVAILABLE:
            self.skipTest("tree-sitter-c-sharp not available")

        cs_code = """
        using System;
        using Microsoft.AspNetCore.Mvc;

        namespace Boutique.Controllers {
            [ApiController]
            [Route("api/[controller]")]
            public class CheckoutController : ControllerBase {
                private readonly ICartServiceClient _cartClient;
                private readonly IPaymentService _paymentService;

                public CheckoutController(ICartServiceClient cartClient, IPaymentService paymentService) {
                    _cartClient = cartClient;
                    _paymentService = paymentService;
                }

                [HttpGet("summary/{id}")]
                public IActionResult GetSummary(string id) {
                    var cart = _cartClient.GetCart(id);
                    return Ok(cart);
                }

                [HttpPost("place-order")]
                public IActionResult PlaceOrder([FromBody] OrderRequest req) {
                    _paymentService.Charge(req);
                    return Ok();
                }
            }
        }
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "CheckoutController.cs")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(cs_code)

            builder = CKGBuilder(tmpdir)
            builder.build()

            # Check ASP.NET routes registered in http_endpoints
            self.assertIn(("GET", "/api/checkout/summary/{id}"), builder.http_endpoints)
            self.assertIn(("POST", "/api/checkout/place-order"), builder.http_endpoints)

            # Check constructor DI registered in grpc_client_vars
            rel_path = "CheckoutController.cs"
            client_vars = builder.grpc_client_vars.get(rel_path, {})
            self.assertTrue(any("cartClient" in k or "_cartClient" in k for k in client_vars))
            self.assertTrue(any("paymentService" in k or "_paymentService" in k for k in client_vars))

    def test_p3_type_aware_dispatch_partition_of_unity(self):
        """P3: Verifies type-aware dispatch preserves partition of unity (sum(c_type) == 1.0)."""
        builder = CKGBuilder(".")
        caller_id = "svc/handler.py:ProcessOrder"
        cand1 = "svc/cart.py:CartManager.Process"
        cand2 = "svc/payment.py:PaymentGateway.Process"

        builder.graph.add_node(caller_id, name="ProcessOrder", docstring="Processes customer order", code="def ProcessOrder(order: OrderRequest):")
        builder.graph.add_node(cand1, name="Process", docstring="Processes cart item checkout", code="def Process(cart: CartItem):")
        builder.graph.add_node(cand2, name="Process", docstring="Processes order credit payment", code="def Process(order: OrderRequest):")

        builder.type_signatures[caller_id] = {"param_types": ["OrderRequest"]}
        builder.type_signatures[cand1] = {"param_types": ["CartItem"]}
        builder.type_signatures[cand2] = {"param_types": ["OrderRequest"]}

        candidates = [cand1, cand2]
        confidences = builder._compute_polymorphic_confidences(caller_id, candidates, tau=0.2)

        self.assertEqual(len(confidences), 2)
        # Theorem 2: Partition of unity
        self.assertAlmostEqual(sum(confidences), 1.0, places=3)
        # Type-matching candidate cand2 must have strictly higher confidence than cand1
        self.assertGreater(confidences[1], confidences[0])

    def test_p4_inter_service_dataflow_and_reachability(self):
        """P4: Verifies Lflow edges connect callers to handlers through the canonical contract RPC."""
        boutique_ws = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "repos", "online-boutique", "workspace.yaml"
        )
        if not os.path.isfile(boutique_ws):
            self.skipTest("Online Boutique workspace not found.")

        builder = WorkspaceCKGBuilder(boutique_ws)
        builder.build()

        # Check an active RPC like CartService.GetCart or ProductCatalogService.GetProduct
        rpc_node = "contract::CartService.GetCart"
        self.assertIn(rpc_node, builder.graph.nodes)

        # Check incoming Lflow edge (PASSES_ARG from caller to rpc)
        in_flow_args = [
            (u, v, d) for u, v, d in builder.graph.in_edges(rpc_node, data=True)
            if d.get("layer") == "Lflow" and d.get("relation") == "PASSES_ARG"
        ]
        self.assertGreaterEqual(len(in_flow_args), 1, "Expected caller -[PASSES_ARG]-> rpc")

        # Check outgoing Lflow edge (FLOWS_TO from rpc to handler)
        out_flows = [
            (u, v, d) for u, v, d in builder.graph.out_edges(rpc_node, data=True)
            if d.get("layer") == "Lflow" and d.get("relation") == "FLOWS_TO"
        ]
        self.assertGreaterEqual(len(out_flows), 1, "Expected rpc -[FLOWS_TO]-> handler")

        # Check handler return flow (RETURNS from handler to rpc)
        in_returns = [
            (u, v, d) for u, v, d in builder.graph.in_edges(rpc_node, data=True)
            if d.get("layer") == "Lflow" and d.get("relation") == "RETURNS"
        ]
        self.assertGreaterEqual(len(in_returns), 1, "Expected handler -[RETURNS]-> rpc")

    def test_p5_openapi_and_graphql_parsers(self):
        """P5: Verifies OpenAPI 3.x and GraphQL SDL contracts are parsed into canonical nodes."""
        openapi_yaml = """
        openapi: 3.0.0
        info:
          title: Boutique Store API
          version: 1.0.0
        paths:
          /api/v1/cart/{userId}:
            get:
              operationId: GetCartByUser
              responses:
                '200':
                  description: Cart retrieved
          /api/v1/cart/items:
            post:
              operationId: AddCartItem
              responses:
                '201':
                  description: Item added
        """
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write(openapi_yaml)
            tmp_oa = f.name

        try:
            oa_spec = OpenAPIContractParser.parse_file(tmp_oa)
            self.assertIsNotNone(oa_spec)
            self.assertEqual(len(oa_spec.operations), 2)
            ops_by_method = {op.method: op for op in oa_spec.operations}
            self.assertIn("GET", ops_by_method)
            self.assertEqual(ops_by_method["GET"].operation_id, "GetCartByUser")
            self.assertIn("POST", ops_by_method)
            self.assertEqual(ops_by_method["POST"].operation_id, "AddCartItem")
        finally:
            if os.path.exists(tmp_oa):
                os.remove(tmp_oa)

        graphql_sdl = """
        type Query {
            getCart(userId: ID!): Cart
            listProducts: [Product]
        }
        type Mutation {
            addItem(userId: ID!, productId: ID!, count: Int!): Cart
        }
        """
        gql_spec = GraphQLContractParser.parse_text(graphql_sdl)
        self.assertIn("Query", gql_spec.types)
        self.assertIn("Mutation", gql_spec.types)
        self.assertIn("getCart", gql_spec.types["Query"].fields)
        self.assertEqual(gql_spec.types["Query"].fields["getCart"].type_name, "Cart")

    def test_p6_kotlin_spring_and_servicer_extraction(self):
        """P6: Verifies Kotlin extractor handles Spring annotations and gRPC servicer inheritance."""
        if not _KOTLIN_AVAILABLE:
            self.skipTest("tree-sitter-kotlin not available")

        kt_code = """
        package com.boutique.service

        import org.springframework.web.bind.annotation.GetMapping
        import org.springframework.web.bind.annotation.PostMapping
        import org.springframework.web.bind.annotation.RestController

        @RestController
        class AdController : AdServiceCoroutineImplBase() {
            @GetMapping("/ads")
            fun getAds(): String {
                return "shoes, watches"
            }
        }
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "AdController.kt")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(kt_code)

            builder = CKGBuilder(tmpdir)
            builder.build()

            # Check endpoint registered
            self.assertIn(("GET", "/ads"), builder.http_endpoints)

            # Check Kotlin gRPC servicer registered in grpc_servicer_records
            servicer_classes = [s[1] for s in builder.grpc_servicer_records]
            self.assertIn("AdService", servicer_classes)

    def test_p7_lsp_augmentation_promotes_uncertain_call(self):
        """P7: Verifies LSP augmentation promotes an uncertain stub (c_type=0.5) to exact (c_type=1.0)."""
        builder = CKGBuilder(".")
        caller_id = "order/main.py:create_order"
        target_id = "cart/service.py:CartStore.get"

        builder.graph.add_node(caller_id, type="function", layer="Lsyn", name="create_order")
        builder.graph.add_node(target_id, type="function", layer="Lsyn", name="get")

        # Register LSP definition
        lsp = LSPIndexProvider()
        lsp.register("order/main.py", "CartStore.get", target_id)
        builder.lsp_provider = lsp

        # Record deferred call
        builder.calls_to_resolve.append((caller_id, "CartStore.get", 0, "order/main.py"))
        builder._resolve_dependency_layer()

        # Check edge created with c_type == 1.0
        edge_data = builder.graph.get_edge_data(caller_id, target_id)
        self.assertIsNotNone(edge_data)
        edge = list(edge_data.values())[0]
        self.assertEqual(edge.get("c_type"), 1.0)
        self.assertEqual(edge.get("relation"), "CALLS")

    def test_p8_cross_language_proto_type_identity(self):
        """P8: Verifies canonical contract::message::* nodes link across language models."""
        boutique_ws = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "repos", "online-boutique", "workspace.yaml"
        )
        if not os.path.isfile(boutique_ws):
            self.skipTest("Online Boutique workspace not found.")

        builder = WorkspaceCKGBuilder(boutique_ws)
        builder.build()

        # Verify canonical proto message nodes exist
        message_nodes = [n for n in builder.graph.nodes if n.startswith("contract::message::")]
        self.assertGreater(len(message_nodes), 0, "Expected canonical proto message contract nodes.")
        self.assertIn("contract::message::CartItem", builder.graph.nodes)


if __name__ == "__main__":
    unittest.main()
