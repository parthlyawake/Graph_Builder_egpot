import json
from types import SimpleNamespace

import networkx as nx
import pytest

from bench import egpot_eval as benchmark
from bench import egpot_width_sweep_dev as sweep
from eg_pot import EGPOTConfig, GraphView, QueryScorer


@pytest.fixture
def workspace():
    graph = nx.MultiDiGraph()
    graph.add_node("root", name="request handler")
    for i in range(7):
        graph.add_node(f"target{i}", name=f"request handler {i}")
        graph.add_edge("root", f"target{i}", relation="CALLS", layer="Ldep")
    view = GraphView(graph)
    return view, QueryScorer(view)


def test_default_width_matches_previous_constructor_and_trace(workspace):
    view, scorer = workspace
    names = ("egpot_full",)
    previous = benchmark.EGPOTRetriever(EGPOTConfig(use_mcts=False), view, scorer)
    implicit = benchmark.make_comparison_retrievers(view, scorer, method_names=names)["egpot_full"]
    explicit = benchmark.make_comparison_retrievers(
        view, scorer, method_names=names, beam_width=4)["egpot_full"]

    def evaluate(engine):
        trace = {}
        result = engine.retrieve("request handler", "root", 10, trace=trace)
        return json.dumps([result.discovery_order, result.ordered_path, trace],
                          separators=(",", ":"), allow_nan=False).encode()

    assert evaluate(previous) == evaluate(implicit) == evaluate(explicit)
    assert "egpot_no_contracts" not in benchmark.make_comparison_retrievers(view, scorer)


def test_width_reaches_beam_and_leaves_baseline_width_independent(workspace):
    view, scorer = workspace
    names = ("egpot_full", "egpot_no_pareto", "egpot_full_mcts", "egpot_no_contracts", "bfs")
    small, wide = [benchmark.make_comparison_retrievers(
        view, scorer, method_names=names, beam_width=width) for width in (4, 6)]
    for width, registry in ((4, small), (6, wide)):
        trace = {}
        registry["egpot_full"].retrieve("request handler", "root", 10, trace=trace)
        assert len(trace["steps"][0]["selected"]) == width
        for name in names[:-1]:
            assert registry[name].config.beam_width == width
        assert not registry["egpot_no_contracts"].config.use_contracts
    assert small["bfs"].retrieve("request", "root", 10).discovery_order == wide[
        "bfs"].retrieve("request", "root", 10).discovery_order


def test_nondefault_cli_width_rejects_test_before_loading_inputs(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("graph opened before DEV-only check")

    monkeypatch.setattr(benchmark.nx, "read_graphml", forbidden)
    with pytest.raises(SystemExit, match="2"):
        benchmark.main(["--mode", "comparison", "--split", "test", "--confirm-test", "--beam-width", "6"])
    assert "Non-default --beam-width requires DEV comparison" in capsys.readouterr().err


def test_cli_passes_explicit_width_to_comparison(workspace, tmp_path, monkeypatch):
    view, _ = workspace
    path = tmp_path / "labels.json"
    labels = [{"id": f"q{link}_{kind}", "link_id": link, "type": kind,
               "query": "request", "start_node": "root", "gold_nodes": ["target0"],
               "gold_path": ["root", "target0"]}
              for link in range(1, 16) for kind in ("explicit", "indirect")]
    path.write_text(json.dumps(labels), encoding="utf-8")
    monkeypatch.setattr(benchmark.nx, "read_graphml", lambda *args, **kwargs: view.graph)
    observed = {}

    def comparison(rows, methods):
        observed["links"] = {row["link_id"] for row in rows}
        observed["width"] = methods["egpot_full"].config.beam_width

    monkeypatch.setattr(benchmark, "run_comparison", comparison)
    assert benchmark.main(["--mode", "comparison", "--methods", "egpot_full",
                           "--beam-width", "6", "--queries", str(path)]) == 0
    assert observed == {"links": set(sweep.LINKS), "width": 6}


def test_record_capture_exposes_only_request_fields_to_method():
    class Spy:
        def retrieve(self, *, query, start_node, node_budget):
            assert (query, start_node, node_budget) == ("query", "root", 10)
            return SimpleNamespace(discovery_order=["root", "handler"], ordered_path=["root", "handler"],
                                   visited={"root", "handler"}, latency_s=0.0)

    label = {"id": "q1", "link_id": 1, "type": "explicit", "query": "query", "start_node": "root",
             "gold_nodes": ["handler"], "gold_path": ["root", "handler"], "secret": "never exposed"}
    row, = sweep.method_records([label], "egpot_full", 10, 0, Spy())
    assert row["returned_nodes"] == ["root", "handler"]
    assert row["hit"] == 1


def test_selection_rule_requires_improvement_and_train_ticket_floor():
    def counts(values):
        return [{"width": width, "hits": hits, "method": "egpot_full", "budget": 40, "seed": 0}
                for width, hits in zip(sweep.WIDTHS, values, strict=True)]

    train = counts((12, 10, 11, 14, 14))
    eligible = sweep.recommendation({"online_boutique": counts((10, 16, 15, 13, 11)), "train_ticket": train})
    assert eligible["recommended_width"] == 8  # Width 6 costs two Train-Ticket hits.
    no_change = sweep.recommendation({"online_boutique": counts((15, 16, 16, 14, 14)),
                                      "train_ticket": counts((12, 12, 12, 12, 12))})
    assert no_change["verdict"] == "no change recommended"
