"""Kafka schema binding requires unique source-declared message types."""
import networkx as nx
from kafka_schema_links import bind_kafka_payload_schemas


class Stub:
    raw_file_lines = {
        "Consumer.java": [
            '@KafkaListener(topics = "metadata")',
            'public void handle(MetadataChangeEvent event) {}',
        ],
        "Producer.java": [
            'KafkaTemplate<String, MetadataChangeEvent> kafka;',
            'void publish() { kafka.send("metadata", event); }',
        ],
    }


def test_kafka_value_schema_links_only_to_unique_contract():
    graph = nx.MultiDiGraph()
    topic = "topic::kafka::metadata"
    graph.add_node(topic, type="topic_contract")
    contract = "contract::avro::demo.MetadataChangeEvent"
    graph.add_node(contract, name="MetadataChangeEvent", type="schema_contract")
    assert bind_kafka_payload_schemas(graph, [Stub()]) == 2
    assert [d["relation"] for _, _, d in graph.out_edges(topic, data=True)] == [
        "PAYLOAD_SCHEMA", "PAYLOAD_SCHEMA"
    ]
    assert bind_kafka_payload_schemas(graph, [Stub()]) == 0
    graph.add_node("contract::pdl::another.MetadataChangeEvent",
                   name="MetadataChangeEvent", type="schema_contract")
    other = nx.MultiDiGraph(graph)
    other.remove_edges_from(list(other.out_edges(topic, keys=True)))
    assert bind_kafka_payload_schemas(other, [Stub()]) == 0
