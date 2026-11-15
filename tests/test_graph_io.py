"""Graph exports round-trip without losing contract, provenance or multiedges."""
import json
import networkx as nx
import pytest
from graph_io import load_graph_json
from traversal import SCKGTraversal


def test_graph_json_roundtrip_and_event_delivery(tmp_path):
    path = tmp_path / "export.json"
    data = {
        "format_version": "1.1",
        "graph_metadata": {"workspace": "integration"},
        "nodes": [
            {"id": "producer", "name": "send"},
            {"id": "queue::amqp::ship", "name": "ship"},
            {"id": "consumer", "name": "receive"},
        ],
        "edges": [
            {"source": "producer", "target": "queue::amqp::ship", "key": "publish",
             "relation": "PRODUCES_EVENT", "layer": "Lcontract"},
            {"source": "consumer", "target": "queue::amqp::ship", "key": "consume",
             "relation": "CONSUMES_EVENT", "layer": "Lcontract"},
        ],
    }
    path.write_text(json.dumps(data))
    graph = load_graph_json(path)
    assert isinstance(graph, nx.MultiDiGraph)
    assert graph.graph["workspace"] == "integration"
    assert graph.number_of_edges() == 2
    traversal = SCKGTraversal(graph)
    assert traversal.event_delivery_paths("producer")["path_count"] == 1


def test_json_loader_rejects_dangling_edges(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({
        "nodes": [{"id": "sender"}],
        "edges": [{"source": "sender", "target": "missing", "key": "x",
                   "relation": "CALLS", "layer": "Ldep"}],
    }))
    with pytest.raises(ValueError, match="dangling"):
        load_graph_json(path)
