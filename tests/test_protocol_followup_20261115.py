"""Regression coverage for newly source-grounded protocol patterns."""
import networkx as nx

from thrift_bindings import _typed_local_clients
from kafka_schema_links import bind_kafka_payload_schemas
from message_topology import bind_amqp_topology
from graphql_embedded import literal_templates


class Source:
    def __init__(self, files):
        self.raw_file_lines = {path: text.splitlines() for path, text in files.items()}


def test_thrift_smart_pointer_client_identity():
    source = (
        "std::shared_ptr<InventoryServiceClient> client;\n"
        "auto audit = std::make_shared<AuditServiceClient>(transport);\n"
        "client->Reserve(42); audit->Reserve(42);\n"
    )
    typed = _typed_local_clients(source)
    assert typed["client"] == {"InventoryService"}
    assert typed["audit"] == {"AuditService"}


def test_kafka_multi_topic_array_and_no_runtime_config_guess():
    graph = nx.MultiDiGraph()
    for topic in ("alpha", "beta", "dynamic"):
        graph.add_node("topic::kafka::" + topic, type="topic_contract")
    graph.add_node("contract::avro::example.Event", type="schema_contract", name="Event")
    src = Source({"Consumer.java": '''
        @KafkaListener(topics = {"alpha", "beta"})
        public void consume(Event event) {}
        @KafkaListener(topics = "${dynamic.topic}")
        public void dynamic(Event event) {}
    '''})
    assert bind_kafka_payload_schemas(graph, [src]) == 2
    assert graph.number_of_edges("topic::kafka::alpha", "contract::avro::example.Event") == 1
    assert graph.number_of_edges("topic::kafka::beta", "contract::avro::example.Event") == 1
    assert graph.number_of_edges("topic::kafka::dynamic", "contract::avro::example.Event") == 0
    assert bind_kafka_payload_schemas(graph, [src]) == 0


def test_rabbitmq_default_exchange_only_delivers_to_declared_queue_consumer():
    graph = nx.MultiDiGraph()
    graph.add_node("topic::amqp::/shipping")
    graph.add_node("topic::amqp::/unknown")
    graph.add_node("queue::amqp::shipping")
    graph.add_node("worker:handle", type="function")
    graph.add_edge("worker:handle", "queue::amqp::shipping", relation="CONSUMES_EVENT")
    result = bind_amqp_topology(graph, [Source({})])
    assert result["routed_edges"] == 1
    assert graph.number_of_edges("topic::amqp::/shipping", "queue::amqp::shipping") == 1
    assert bind_amqp_topology(graph, [Source({})])["routed_edges"] == 0


def test_graphql_literal_call_template_forms():
    source = "const x = gql(\x60query Find { viewer { id } }\x60);"
    assert len(list(literal_templates(source))) == 1
    source = "const y = graphql(\x60query Find { ${field} }\x60);"
    assert list(literal_templates(source)) == []
