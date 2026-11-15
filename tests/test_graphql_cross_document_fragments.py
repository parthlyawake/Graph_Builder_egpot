"""GraphQL spreads bind only to unique, explicitly typed external fragments."""
import networkx as nx
from graphql_embedded import cross_document_fragments, bind_selections


def test_cross_document_fragment_registry_and_cycle_protection(tmp_path):
    (tmp_path / "a.graphql").write_text(
        "fragment Shared on Dataset { name ...Self } "
        "fragment Self on Dataset { description ...Shared }")
    (tmp_path / "operation.graphql").write_text(
        "query Find { dataset { ...Shared } }")
    graph = nx.MultiDiGraph()
    graph.add_node("graphqlop::operation", kind="query", name="Find",
                   file="operation.graphql")
    for key, ret in [
        ("Query::dataset", "Dataset!"),
        ("Dataset::name", "String"),
        ("Dataset::description", "String"),
    ]:
        graph.add_node("contract::graphql::" + key, return_type=ret)
    registry = cross_document_fragments(tmp_path)
    assert len(registry) == 2
    document = (tmp_path / "operation.graphql").read_text()
    assert bind_selections(graph, "graphqlop::operation", document, registry) == 3


def test_ambiguous_fragment_names_are_excluded(tmp_path):
    (tmp_path / "one.graphql").write_text("fragment Duplicated on X { a }")
    (tmp_path / "two.graphql").write_text("fragment Duplicated on X { b }")
    assert "Duplicated" not in cross_document_fragments(tmp_path)
