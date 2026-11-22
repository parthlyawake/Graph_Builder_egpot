import networkx as nx

from bench.map_datahub_coverage import SourceIndex, http_dispatch_paths, inspect_links, peak_memory, write_graphml


def test_declaration_selection_uses_source_not_connectivity():
    graph = nx.MultiDiGraph()
    graph.add_node("ingestion/client.py:client.read", file="ingestion/client.py",
                   name="read", line_no=20, type="function")
    graph.add_node("ingestion/client.py:other.read", file="ingestion/client.py",
                   name="read", line_no=20, type="function")
    graph.add_node("openapi/Handler.java:Handler.get", file="openapi/Handler.java",
                   name="get", line_no=42, type="function")
    graph.add_node("contract", name="GET /first", type="http_endpoint")
    row = {"id": "DH00", "pair": "Python → OpenAPI", "contract_name": "GET /first",
           "contract_citations": [], "caller": ("metadata-ingestion/src/client.py", 20, "client.read"),
           "handler": ("metadata-service/openapi-servlet/src/main/java/Handler.java", 44, "Handler.get")}
    expected = inspect_links(graph, [row])[0]
    graph.add_edge("ingestion/client.py:other.read", "contract", relation="CONSUMES")
    graph.add_edge("openapi/Handler.java:Handler.get", "contract", relation="IMPLEMENTS")
    after = inspect_links(graph, [row])[0]
    for field in ("caller", "contract", "handler"):
        assert after[field] == expected[field]
    assert after["caller"]["id"] == "ingestion/client.py:client.read"
    assert after["handler"]["graph_line"] == 42
    assert after["start_to_contract"] == []
    assert after["handler_to_contract"] == ["IMPLEMENTS"]


def test_ambiguous_or_wrong_line_declarations_are_not_guessed():
    graph = nx.MultiDiGraph()
    for node in ("web/screen.ts:a.render", "web/screen.ts:b.render"):
        graph.add_node(node, name="render", type="function", file="web/screen.ts", line_no=25)
    graph.add_node("nearby", name="render", type="function", file="web/other.ts", line_no=28)
    index = SourceIndex(graph.nodes(data=True))
    ambiguous = index.declaration(("datahub-web-react/src/screen.ts", 25, "render"))
    assert ambiguous["id"] is None and len(ambiguous["candidates"]) == 2
    assert index.declaration(("datahub-web-react/src/screen.ts", 28, "render"))["candidates"] == []


def test_restli_generic_collection_does_not_match_action():
    graph = nx.MultiDiGraph()
    graph.add_node("generic", type="http_endpoint", method="POST", path="/operations")
    index = SourceIndex(graph.nodes(data=True))
    assert index.contract("POST /operations", [])["id"] == "generic"
    assert index.contract("POST /operations?action=restore", [])["id"] is None


def test_java_overload_is_matched_by_the_declaration_span():
    first = "openapi/Handler.java:Handler.get"
    second = first + "@overload:2"
    common = {"name": "get", "type": "function", "file": "openapi/Handler.java", "overload_group": first}
    index = SourceIndex([(first, {**common, "line_no": 30, "line_end": 40}),
                         (second, {**common, "line_no": 50, "line_end": 80})])
    file = "metadata-service/openapi-servlet/src/main/java/Handler.java"
    assert index.declaration((file, 61, "Handler.get"))["id"] == second


def test_streamed_graphml_preserves_parallel_edges_and_scalar_types(tmp_path):
    graph = nx.MultiDiGraph()
    graph.add_node("u", line_no=4, code="a\nb<c", named=True)
    graph.add_edge("u", "v", key="first", weight=0.75, relation="CONSUMES")
    graph.add_edge("u", "v", key="second", relation="CALLS")
    path = tmp_path / "graph.graphml"
    assert write_graphml(graph, path) == 0
    result = nx.read_graphml(path, force_multigraph=True)
    assert result.nodes["u"] == graph.nodes["u"]
    assert dict(result["u"]["v"]) == dict(graph["u"]["v"])


def test_peak_working_set_is_reported_in_bytes():
    assert peak_memory() > 1024 * 1024


def test_http_dispatch_distinguishes_confirmed_and_possible_wrapper_calls():
    graph = nx.MultiDiGraph()
    graph.add_edge("ingestion/client.py:start", "ingestion/client.py:wrapper", relation="CALLS")
    graph.add_edge("ingestion/client.py:wrapper", "callsite", relation="HTTP_REQUEST")
    graph.add_edge("callsite", "handler", relation="POSSIBLE_HTTP_TARGET")
    before = http_dispatch_paths(graph, "ingestion/client.py:start", "contract", "handler")
    assert set(before) == {"POSSIBLE_HTTP_TARGET"}
    graph.add_edge("ingestion/client.py:wrapper", "handler", relation="HTTP_CALLS")
    after = http_dispatch_paths(graph, "ingestion/client.py:start", "contract", "handler")
    assert len(after["HTTP_CALLS"]) == 2
    assert after["POSSIBLE_HTTP_TARGET"] == before["POSSIBLE_HTTP_TARGET"]
