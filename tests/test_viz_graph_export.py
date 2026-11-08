"""Read-only real inputs; output fixtures are isolated under tmp_path."""

import json
from pathlib import Path
import re

import networkx as nx

from bench.export_viz_graph import export, graph_payload

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "bench/results/online_boutique_graph_fresh.graphml"
QUERIES = ROOT / "bench/labels/online_boutique_egpot_queries.json"


def parse_script(data, name):
    prefix = f"window.{name} = "
    text = data.decode("utf-8")
    assert text.startswith(prefix) and text.endswith(";\n")
    return json.loads(text[len(prefix):-2])


def test_export_counts_fields_and_no_code(tmp_path):
    files = export(GRAPH, QUERIES, tmp_path)
    graph = nx.read_graphml(GRAPH, force_multigraph=True)
    data = parse_script(files["graph.js"], "VIZ_GRAPH")
    assert (tmp_path / "graph.js").read_bytes() == files["graph.js"]
    assert data["meta"]["node_count"] == len(data["nodes"]) == len(graph)
    assert data["meta"]["edge_count"] == len(data["edges"]) == graph.number_of_edges()
    for node in data["nodes"]:
        assert set(node) == {"id", "type", "repo", "name", "file", "line_no", "layer", "docstring"}
        assert len(node["docstring"]) <= 200
    assert {node["id"] for node in data["nodes"]} == set(graph)
    assert [s["name"] for s in data["meta"]["services"]] == sorted(s["name"] for s in data["meta"]["services"])
    for edge in data["edges"]:
        assert type(edge["c_type"]) is float and type(edge["f_call"]) is float
        assert graph.has_edge(edge["source"], edge["target"], edge["key"])


def test_query_export_has_only_public_fields(tmp_path):
    files = export(GRAPH, QUERIES, tmp_path)
    queries = parse_script(files["queries.js"], "VIZ_QUERIES")
    assert (tmp_path / "queries.js").read_bytes() == files["queries.js"]
    assert len(queries) == 30
    for query in queries:
        assert set(query) == {"id", "link_id", "type", "query", "start_node", "split"}
        assert query["split"] in {"dev", "test"}
    assert sum(q["split"] == "dev" for q in queries) == 16


def test_export_bytes_are_deterministic(tmp_path):
    first = export(GRAPH, QUERIES, tmp_path / "one")
    second = export(GRAPH, QUERIES, tmp_path / "two")
    assert first == second
    for name in first:
        assert (tmp_path / "one" / name).read_bytes() == (tmp_path / "two" / name).read_bytes()


def test_graphml_numeric_strings_missing_metadata_and_stable_colors():
    graph = nx.MultiDiGraph()
    graph.add_node("b", repo="beta", docstring="x" * 300)
    graph.add_node("a", repo="alpha")
    graph.add_edge("b", "a", key="k", c_type="0.34567891", f_call="2")
    graph.add_edge("a", "b", key="m")
    data = graph_payload(graph)
    assert data["edges"][1]["c_type"] == 0.345679
    assert data["edges"][1]["f_call"] == 2.0
    assert data["edges"][0]["c_type"] == data["edges"][0]["f_call"] == 1.0
    reordered = nx.MultiDiGraph()
    reordered.add_nodes_from(reversed(list(graph.nodes(data=True))))
    for u, v, k, d in reversed(list(graph.edges(keys=True, data=True))):
        reordered.add_edge(u, v, key=k, **d)
    assert graph_payload(reordered) == data


def test_site_is_offline_and_scripts_are_local():
    files = [ROOT / "viz/index.html", *sorted((ROOT / "viz/js").glob("*.js")),
             *sorted((ROOT / "viz/css").glob("*.css"))]
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"fetch\s*\(|XMLHttpRequest|https?://", text, re.IGNORECASE), path
    html = (ROOT / "viz/index.html").read_text(encoding="utf-8")
    for reference in re.findall(r'(?:src|href)="([^"]+)"', html):
        assert not reference.startswith(("/", "//"))
        assert (ROOT / "viz" / reference).is_file(), reference
    assert 'data-tab="graph"' in html
    assert html.count('role="tab"') == 6
