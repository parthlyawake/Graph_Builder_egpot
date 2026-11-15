"""Typed graph provider must retain exact polyglot and protocol node identities."""
import networkx as nx

from contracts.graph_types import Language, NodeType, EdgeType
from contracts.sckg_provider import SCKGGraphProvider


def test_all_new_languages_and_contract_types():
    graph = nx.MultiDiGraph()
    samples = {
        "js/index.js:handler": ("function", "javascript", "index.js", NodeType.FUNCTION, Language.JAVASCRIPT),
        "java/Service.java:handle": ("function", "java", "Service.java", NodeType.FUNCTION, Language.JAVA),
        "ruby/handler.rb:handle": ("function", "ruby", "handler.rb", NodeType.FUNCTION, Language.RUBY),
        "go/app.go:handle": ("function", "go", "app.go", NodeType.FUNCTION, Language.GO),
        "cpp/main.cpp:handle": ("function", "cpp", "main.cpp", NodeType.FUNCTION, Language.CPP),
        "scala/main.scala:run": ("function", "scala", "main.scala", NodeType.FUNCTION, Language.SCALA),
        "queue::amqp::ship": ("queue_contract", None, None, NodeType.QUEUE_CONTRACT, Language.UNKNOWN),
        "graphqlop::query:Find": ("graphql_operation", None, None, NodeType.GRAPHQL_OPERATION, Language.UNKNOWN),
        "contract::avro::Event.field::value": ("schema_field", None, None, NodeType.SCHEMA_FIELD, Language.UNKNOWN),
    }
    for nid, (kind, lang, file, _, _) in samples.items():
        graph.add_node(nid, type=kind, language=lang, file=file, name=nid)
    provider = SCKGGraphProvider(graph)
    for nid, (_, _, _, expected_node, expected_lang) in samples.items():
        node = provider.get_node_detail(nid)
        assert node.node_type == expected_node
        assert node.language == expected_lang


def test_broker_relations_remain_typed():
    provider = SCKGGraphProvider(nx.MultiDiGraph())
    assert provider._map_edge_type("ROUTES_TO") == EdgeType.ROUTES_TO
    assert provider._map_edge_type("PAYLOAD_SCHEMA") == EdgeType.PAYLOAD_SCHEMA
