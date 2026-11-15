"""Nested GraphQL paths are resolved via SDL types, never by field names alone."""
import networkx as nx
from graphql_embedded import bind_selections, literal_templates


def test_typed_selections_and_fragments():
    graph = nx.MultiDiGraph()
    graph.graph["graphql_root_types"] = {"query": "Query"}
    graph.add_node("graphqlop::x", name="Find", kind="query", file="web.ts")
    for name, value in [("Query::dataset", "Dataset!"),
                        ("Dataset::name", "String"),
                        ("Dataset::description", "String")]:
        graph.add_node("contract::graphql::" + name, return_type=value)
    document = "query Find { dataset { name ...Info } } fragment Info on Dataset { description }"
    assert bind_selections(graph, "graphqlop::x", document) == 3
    assert bind_selections(graph, "graphqlop::x", document) == 0


def test_embedded_literal_excludes_dynamic_interpolation():
    literal = "const q = gql" + chr(96) + "query Find { dataset { name } }" + chr(96)
    dynamic = "const q = gql" + chr(96) + "query Find { " + chr(36) + "{fields} }" + chr(96)
    assert len(list(literal_templates(literal))) == 1
    assert not list(literal_templates(dynamic))
