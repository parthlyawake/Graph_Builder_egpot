"""
Unit tests for polyglot Java Spring REST, event-driven messaging contracts,
and cross-file dependency resolution.
"""

import os
import tempfile
import unittest

from graft_ckg import CKGBuilder


class PolyglotSpringAndEventsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = self.temp_dir.name

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_spring_rest_endpoint_and_kafka_contracts(self):
        """Verify that Spring REST endpoints and Kafka event contracts are extracted into Lcontract."""
        order_java = """
        package com.ecom.order.controller;

        import org.springframework.web.bind.annotation.*;
        import org.springframework.kafka.annotation.KafkaListener;
        import org.springframework.kafka.core.KafkaTemplate;

        @RestController
        @RequestMapping("/api/orders")
        public class OrderController {

            private final KafkaTemplate<String, Object> kafkaTemplate;

            public OrderController(KafkaTemplate<String, Object> kafkaTemplate) {
                this.kafkaTemplate = kafkaTemplate;
            }

            @PostMapping("/create")
            public String createOrder(@RequestBody String payload) {
                kafkaTemplate.send("order-created-events", payload);
                return "CREATED";
            }

            @GetMapping("/{id}")
            public String getOrder(@PathVariable String id) {
                return "ORDER_" + id;
            }

            @KafkaListener(topics = "payment-completed-events")
            public void handlePaymentCompleted(String paymentMsg) {
                System.out.println(paymentMsg);
            }
        }
        """
        src_path = os.path.join(self.repo_dir, "src", "main", "java", "com", "ecom", "order", "controller")
        os.makedirs(src_path, exist_ok=True)
        file_path = os.path.join(src_path, "OrderController.java")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(order_java)

        builder = CKGBuilder(self.repo_dir)
        graph = builder.build()

        # 1. Verify HTTP endpoints registered
        self.assertIn(("POST", "/api/orders/create"), builder.http_endpoints)
        self.assertIn(("GET", "/api/orders/{id}"), builder.http_endpoints)

        # 2. Verify REST contract nodes in Lcontract
        post_contract = "http::POST:/api/orders/create"
        get_contract = "http::GET:/api/orders/{id}"
        self.assertTrue(graph.has_node(post_contract))
        self.assertTrue(graph.has_node(get_contract))
        self.assertEqual(graph.nodes[post_contract].get("layer"), "Lcontract")
        self.assertEqual(graph.nodes[post_contract].get("type"), "http_endpoint")
        self.assertFalse(any(n.startswith("contract::HTTP.") for n in graph.nodes))

        # 3. Verify IMPLEMENTS and PRODUCES edges for REST endpoints
        implements_edges = [
            (u, v) for u, v, d in graph.edges(data=True)
            if d.get("relation") == "IMPLEMENTS" and d.get("layer") == "Lcontract"
        ]
        self.assertTrue(len(implements_edges) >= 2)

        # 4. Verify Kafka topic contract nodes
        self.assertTrue(graph.has_node("topic::order-created-events"))
        self.assertTrue(graph.has_node("topic::payment-completed-events"))
        self.assertEqual(graph.nodes["topic::order-created-events"].get("type"), "topic_contract")

        # 5. Verify PRODUCES_EVENT edge from createOrder to order-created-events
        produces_edges = [
            (u, v) for u, v, d in graph.edges(data=True)
            if d.get("relation") == "PRODUCES_EVENT" and v == "topic::order-created-events"
        ]
        self.assertEqual(len(produces_edges), 1)

        # 6. Verify CONSUMES_EVENT edge from handlePaymentCompleted to payment-completed-events
        consumes_edges = [
            (u, v) for u, v, d in graph.edges(data=True)
            if d.get("relation") == "CONSUMES_EVENT" and v == "topic::payment-completed-events"
        ]
        self.assertEqual(len(consumes_edges), 1)

    def test_java_method_invocation_dependency_layer(self):
        """Verify that Java method calls are registered into Ldep."""
        service_java = """
        package com.ecom.order.service;

        public class PaymentHelper {
            public boolean processCard(String token) {
                return true;
            }
        }
        """
        caller_java = """
        package com.ecom.order.service;

        public class OrderService {
            private PaymentHelper helper;

            public boolean checkout(String token) {
                return helper.processCard(token);
            }
        }
        """
        src_path = os.path.join(self.repo_dir, "src", "main", "java", "com", "ecom", "order", "service")
        os.makedirs(src_path, exist_ok=True)
        with open(os.path.join(src_path, "PaymentHelper.java"), "w", encoding="utf-8") as f:
            f.write(service_java)
        with open(os.path.join(src_path, "OrderService.java"), "w", encoding="utf-8") as f:
            f.write(caller_java)

        builder = CKGBuilder(self.repo_dir)
        graph = builder.build()

        # Verify calls_to_resolve was populated
        self.assertTrue(len(builder.calls_to_resolve) > 0)

        # Verify Ldep CALLS edge is established
        calls_edges = [
            (u, v, d) for u, v, d in graph.edges(data=True)
            if d.get("layer") == "Ldep" and d.get("relation") in ("CALLS", "POLYMORPHIC_CALL")
        ]
        self.assertTrue(len(calls_edges) > 0)


if __name__ == "__main__":
    unittest.main()
