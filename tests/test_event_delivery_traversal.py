"""Message traversal follows routing edges and excludes invented delivery."""
import networkx as nx
from traversal import SCKGTraversal


class Builder:
    def __init__(self, graph):
        self.graph = graph


def test_trace_through_explicit_amqp_queue_binding():
    graph = nx.MultiDiGraph()
    for node in ("send", "topic::amqp::orders/created", "queue::amqp::ship",
                 "consume"):
        graph.add_node(node, name=node)
    graph.add_edge("send", "topic::amqp::orders/created",
                   relation="PRODUCES_EVENT", layer="Lcontract")
    graph.add_edge("topic::amqp::orders/created", "queue::amqp::ship",
                   relation="ROUTES_TO", layer="Lcontract",
                   source_evidence="setup.js:3")
    graph.add_edge("consume", "queue::amqp::ship",
                   relation="CONSUMES_EVENT", layer="Lcontract")
    traverse = SCKGTraversal(Builder(graph))
    result = traverse.event_delivery_paths("send")
    assert result["path_count"] == 1
    assert result["paths"][0]["consumer"] == "consume"
    assert result["paths"][0]["routing_evidence"] == "setup.js:3"
