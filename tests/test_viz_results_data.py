"""Results export parity, split guard, and offline resource checks."""
import json
from pathlib import Path
import re

import networkx as nx
import pytest

from bench.egpot_eval import metrics, RetrievalResult, split_by_link
from bench.export_results_js import METHODS, SWEEP, build_results, encode

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def payload():
    text = (ROOT / "viz/data/online_boutique/results.js").read_text(encoding="utf-8")
    assert text.startswith("window.VIZ_RESULTS = ")
    return json.loads(text[len("window.VIZ_RESULTS = "):].rstrip(";\n"))


def test_expected_rows_and_dev_only(payload):
    labels = json.loads((ROOT / "bench/labels/online_boutique_egpot_queries.json").read_text(encoding="utf-8"))
    dev = split_by_link(labels)["dev"]
    assert payload["meta"]["split"] == "dev"
    assert payload["meta"]["n_queries"] == 16
    assert payload["meta"]["n_links"] == 8
    actual = {(r["query_id"], r["method"], r["budget"]) for r in payload["rows"]}
    expected = {(q["id"], m, b) for q in dev for m in METHODS for b in (20, 40)}
    expected |= {(q["id"], m, b) for q in dev for m in SWEEP for b in (60, 100, 200)}
    if "Skipped:" in payload["meta"]["generated_note"]:
        expected -= {(q["id"], "egpot_full_mcts", 200) for q in dev}
    assert actual == expected
    assert len(payload["rows"]) == len(expected)


def test_fields_and_gold_consistency(payload):
    labels = {q["id"]: q for q in json.loads((ROOT / "bench/labels/online_boutique_egpot_queries.json").read_text(encoding="utf-8"))}
    required = {"query_id", "link_id", "type", "method", "budget", "hit", "gold_recall", "precision",
                "path_coverage", "ordered_path_match", "nodes_returned", "nodes_to_hit", "latency_s", "gold_found", "n_gold"}
    for row in payload["rows"]:
        assert set(row) == required
        assert set(row["gold_found"]) <= set(labels[row["query_id"]]["gold_nodes"])
        assert row["n_gold"] == len(labels[row["query_id"]]["gold_nodes"])
        assert row["hit"] == int(len(row["gold_found"]) == row["n_gold"])
        assert row["gold_recall"] == len(row["gold_found"]) / row["n_gold"]
        assert row["precision"] == len(row["gold_found"]) / row["nodes_returned"]
        assert 1 <= row["nodes_returned"] <= row["budget"]
        assert row["latency_s"] >= 0
        assert (row["nodes_to_hit"] is not None) == bool(row["hit"])


def tiny_fixture():
    graph = nx.MultiDiGraph()
    graph.add_node("start", name="client", type="function")
    graph.add_node("rpc", name="GetCurrency", type="rpc_contract")
    graph.add_node("handler", name="GetCurrency implementation", type="function")
    graph.add_edge("start", "rpc", relation="CONSUMES", layer="Lcontract")
    graph.add_edge("handler", "rpc", relation="IMPLEMENTS", layer="Lcontract")
    rows = [{"id": f"q{link}_{kind}", "link_id": link, "type": kind, "query": "currency implementation",
             "start_node": "start", "gold_nodes": ["rpc", "handler"], "gold_path": ["start", "rpc", "handler"]}
            for link in (1, 2) for kind in ("explicit", "indirect")]
    return graph, rows


def test_non_latency_bytes_deterministic_and_metrics_reused():
    graph, labels = tiny_fixture()
    kwargs = {"method_names": ("egpot_full", "egpot_full_mcts", "vector_topk", "bfs", "greedy_walk"), "budgets": (20,)}
    one = build_results(graph, labels, **kwargs)
    two = build_results(graph, labels, **kwargs)
    assert encode(one, omit_latency=True) == encode(two, omit_latency=True)
    bfs = next(r for r in one["rows"] if r["method"] == "bfs")
    expected = metrics(RetrievalResult({"start", "rpc", "handler"}, ["start", "rpc", "handler"], 0,
                                       ["start", "rpc", "handler"]), ["rpc", "handler"], ["start", "rpc", "handler"])
    for key in ("hit", "gold_recall", "precision", "path_coverage", "ordered_path_match", "nodes_returned", "nodes_to_hit"):
        assert bfs[key] == expected[key]


@pytest.mark.parametrize("kwargs", [{"include_test": True}, {"confirm_test": True}])
def test_split_guard(kwargs):
    graph, rows = tiny_fixture()
    with pytest.raises(ValueError, match="both"):
        build_results(graph, rows, **kwargs)


def test_offline_resources():
    sources = [ROOT / "viz/index.html", *sorted((ROOT / "viz/js").glob("*.js")),
               *sorted((ROOT / "viz/css").glob("*.css"))]
    for source in sources:
        assert not re.search(r"fetch\s*\(|XMLHttpRequest|https?://|\bCDN\b", source.read_text(encoding="utf-8"), re.I), source
    for ref in re.findall(r'(?:src|href)="([^"]+)"', sources[0].read_text(encoding="utf-8")):
        assert not ref.startswith(("/", "//"))
        assert (ROOT / "viz" / ref).is_file()
