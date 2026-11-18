"""Extra DEV payload schema, harness reuse, determinism and offline loading."""
import json
from pathlib import Path
import re

import networkx as nx
import pytest

from bench.egpot_eval import split_by_link, weight_experiment_vectors
from bench.export_results_extra_js import build_extra, encode, OLD_METHODS, OFF_METHODS, BUDGETS

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "viz/data/online_boutique"


def read_payload(name, global_name):
    text = (DATA / name).read_text(encoding="utf-8")
    prefix = f"window.{global_name} = "
    assert text.startswith(prefix)
    return json.loads(text[len(prefix):].rstrip(";\n"))


@pytest.fixture(scope="module")
def payload():
    return read_payload("results_extra.js", "VIZ_RESULTS_EXTRA")


def test_expected_dev_rows_and_original_keys_disjoint(payload):
    labels = json.loads((ROOT / "bench/labels/online_boutique_egpot_queries.json").read_text(encoding="utf-8"))
    dev = {q["id"] for q in split_by_link(labels)["dev"]}
    original = read_payload("results.js", "VIZ_RESULTS")
    key = lambda r: (r["query_id"], r["method"], r["budget"])
    assert len(payload["rows"]) == 1152
    assert len({key(r) for r in payload["rows"]}) == 1152
    assert not ({key(r) for r in payload["rows"]} & {key(r) for r in original["rows"]})
    assert {r["query_id"] for r in payload["rows"]} == dev
    assert payload["meta"]["split"] == "dev"
    assert payload["meta"]["note"] == "latency measured on the exporting machine"
    for method in {r["method"] for r in payload["rows"]}:
        expected = set(BUDGETS) - ({20,40} if method in OLD_METHODS else set())
        assert {r["budget"] for r in payload["rows"] if r["method"] == method} == expected


def test_row_schema_no_gold_lists_beyond_found(payload):
    schema = set(read_payload("results.js", "VIZ_RESULTS")["rows"][0])
    labels = {q["id"]: q for q in json.loads((ROOT / "bench/labels/online_boutique_egpot_queries.json").read_text(encoding="utf-8"))}
    for row in payload["rows"] + payload["choke"]:
        assert set(row) == schema
        assert set(row["gold_found"]) <= set(labels[row["query_id"]]["gold_nodes"])
        assert not {"gold_nodes", "gold_path", "handler_node", "contract_node"} & row.keys()
        assert 1 <= row["nodes_returned"] <= row["budget"]
        assert row["hit"] == int(len(row["gold_found"]) == row["n_gold"])
        assert row["latency_s"] >= 0


def test_weight_vectors_exactly_reuse_harness(payload):
    assert len(payload["weights"]) == 56
    actual = {r["id"]: r for r in payload["weights"]}
    expected = weight_experiment_vectors()
    assert set(actual) == set(expected) | {"pareto_reference"}
    for name, vector in expected.items():
        row = actual[name]
        assert row["weights"] == list(vector)
        assert len(vector) == 4 and all(v >= 0 for v in vector)
        assert sum(vector) == pytest.approx(1, abs=1e-6)
        assert row["hit_b20"] == row["explicit_hit_b20"] + row["indirect_hit_b20"]
    assert "weights" not in actual["pareto_reference"]


def test_choke_and_seed_complete(payload):
    assert len(payload["choke"]) == 192
    assert {r["method"] for r in payload["choke"]} == set(OFF_METHODS)
    assert len(payload["seeds"]) == 480
    keys = {(r["method"],r["budget"],r["seed"],r["query_id"]) for r in payload["seeds"]}
    assert len(keys) == 480
    assert {r["seed"] for r in payload["seeds"]} == set(range(5))
    assert {r["budget"] for r in payload["seeds"]} == {20,40}
    assert all(set(r) == {"method","budget","seed","query_id","hit","nodes_returned"} for r in payload["seeds"])


def tiny_fixture():
    graph = nx.MultiDiGraph()
    graph.add_node("start", type="function", name="currency client")
    graph.add_node("rpc", type="rpc_contract", name="GetCurrency")
    graph.add_node("handler", type="function", name="currency implementation")
    graph.add_edge("start", "rpc", relation="CONSUMES", layer="Lcontract")
    graph.add_edge("handler", "rpc", relation="IMPLEMENTS", layer="Lcontract")
    labels = [{"id":f"q{link}_{kind}","link_id":link,"type":kind,"query":"currency implementation",
               "start_node":"start","gold_nodes":["rpc","handler"],"gold_path":["start","rpc","handler"]}
              for link in (1,2) for kind in ("explicit","indirect")]
    return graph, labels


def test_non_latency_subset_determinism():
    graph, labels = tiny_fixture()
    options = dict(row_methods=("bfs","ppr","scalar_beam","egpot_full"), row_budgets=(5,10), panels=False)
    assert encode(build_extra(graph,labels,**options),omit_latency=True) == encode(build_extra(graph,labels,**options),omit_latency=True)


@pytest.mark.parametrize("flags", [{"include_test":True}, {"confirm_test":True}])
def test_test_split_guard(flags):
    graph, labels = tiny_fixture()
    with pytest.raises(ValueError, match="both"):
        build_extra(graph,labels,**flags)


def test_glossary_and_local_only_resources(payload):
    glossary_text = (ROOT / "viz/js/glossary.js").read_text(encoding="utf-8")
    glossary = json.loads(glossary_text.split("=",1)[1].rstrip(";\n"))
    assert {r["method"] for r in payload["rows"] + payload["choke"]} <= glossary.keys()
    assert {"weighting","seed"} <= glossary.keys()
    sources = [ROOT/"viz/index.html", *sorted((ROOT/"viz/js").glob("*.js")), *sorted((ROOT/"viz/css").glob("*.css"))]
    for source in sources:
        assert not re.search(r"fetch\s*\(|XMLHttpRequest|https?://|\bCDN\b",source.read_text(encoding="utf-8"),re.I), source
    for ref in re.findall(r'(?:src|href)="([^"]+)"',sources[0].read_text(encoding="utf-8")):
        assert not ref.startswith(("/","//"))
        assert (ROOT/"viz"/ref).is_file()
