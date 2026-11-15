"""RabbitMQ route edges require actual broker binding evidence."""
import networkx as nx
from message_topology import bind_amqp_topology


class Stub:
    def __init__(self, entries):
        self.raw_file_lines = {k: v.splitlines() for k, v in entries.items()}


def test_topic_routing_and_comment_masking():
    graph = nx.MultiDiGraph()
    for name in ("events/order.created", "events/item.updated", "unrelated/order.created"):
        graph.add_node("topic::amqp::" + name)
    setup = Stub({
        "worker.js": 'channel.bindQueue("ship", "events", "order.*");\n'
                     '// channel.bindQueue("fake", "events", "item.*");',
        "exchange.js": 'channel.assertExchange("events", "topic");',
    })
    first = bind_amqp_topology(graph, [setup])
    assert first == {"explicit_bindings": 1, "routed_edges": 1}
    assert bind_amqp_topology(graph, [setup])["routed_edges"] == 0
    assert not list(graph.out_edges("topic::amqp::unrelated/order.created"))


def test_spring_binding_builder():
    graph = nx.MultiDiGraph()
    graph.add_node("topic::amqp::shipping/ship.started")
    builder = Stub({"Messaging.java": """
        public Queue shippingQueue() { return new Queue("ship.tasks"); }
        public DirectExchange shippingExchange() { return new DirectExchange("shipping"); }
        public Binding wiring() { return BindingBuilder.bind(shippingQueue())
            .to(shippingExchange()).with("ship.started"); }
    """})
    report = bind_amqp_topology(graph, [builder])
    assert report["routed_edges"] == 1
