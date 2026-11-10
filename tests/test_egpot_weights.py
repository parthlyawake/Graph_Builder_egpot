"""In-memory weight sampling, objective selection and observational trace checks."""
import networkx as nx
import numpy as np
import pytest

from bench.egpot_eval import (CandidateAuditRetriever, EGPOTRetriever, main,
                             sample_dirichlet_weights, weight_distribution,
                             weight_experiment_vectors)
from eg_pot import EGPOTConfig, GraphView, QueryScorer


def fixture():
    graph = nx.MultiDiGraph()
    graph.add_node("s", name="start", type="function")
    graph.add_node("z_relevant", name="currency exchange", type="function")
    graph.add_node("a_contract", name="postal parcel", type="rpc_contract")
    graph.add_edge("s", "z_relevant", relation="CALLS", layer="Ldep")
    graph.add_edge("s", "a_contract", relation="CONSUMES", layer="Lcontract")
    view = GraphView(graph)
    return view, QueryScorer(view)


def content(result):
    return result.visited, result.discovery_order, result.ordered_path, result.edges


def test_all_experiment_vectors_validate_and_control_is_separate():
    vectors = weight_experiment_vectors()
    assert len(vectors) == 55
    assert len([k for k in vectors if k != "equal"]) == 54
    assert len([k for k in vectors if k.startswith("dirichlet_")]) == 50
    assert vectors["equal"] == (.25, .25, .25, .25)
    for weights in vectors.values():
        assert len(weights) == 4
        assert all(w >= 0 for w in weights)
        assert sum(weights) == pytest.approx(1, abs=1e-9)
        assert EGPOTConfig(weights=weights).weights == weights


@pytest.mark.parametrize("invalid", [(1, 0, 0), (-.1, .5, .3, .3), (.5, .5, .5, .5),
                                     (float("nan"), 0, 0, 1)])
def test_invalid_weights_rejected(invalid):
    with pytest.raises(ValueError):
        EGPOTConfig(weights=invalid)


def test_dirichlet_determinism_and_round_then_renormalize():
    first = sample_dirichlet_weights(seed=0)
    assert first == sample_dirichlet_weights(seed=0)
    assert len(first) == 50
    raw = np.round(np.random.RandomState(0).dirichlet(np.ones(4), size=50), 4)
    expected = raw / raw.sum(axis=1, keepdims=True)
    assert np.array_equal(np.array(first), expected)
    assert first != sample_dirichlet_weights(seed=1)
    for row in first:
        EGPOTConfig(weights=row)


def test_pareto_ignores_weights():
    view, scorer = fixture()
    results = [EGPOTRetriever(EGPOTConfig(use_mcts=False, beam_width=1, use_pareto=True,
                                        weights=w), view, scorer).retrieve("currency", "s", 2)
               for w in [(1., 0., 0., 0.), (0., 0., 1., 0.)]]
    assert content(results[0]) == content(results[1])


def test_weighted_sum_can_choose_different_candidates():
    view, scorer = fixture()
    relevance = EGPOTRetriever(EGPOTConfig(use_mcts=False, use_pareto=False, beam_width=1,
                                          weights=(1., 0., 0., 0.)), view, scorer)
    contract = EGPOTRetriever(EGPOTConfig(use_mcts=False, use_pareto=False, beam_width=1,
                                         weights=(0., 0., 1., 0.)), view, scorer)
    assert relevance.retrieve("currency", "s", 2).ordered_path == ["s", "z_relevant"]
    assert contract.retrieve("currency", "s", 2).ordered_path == ["s", "a_contract"]


@pytest.mark.parametrize("pareto", [True, False])
def test_trace_and_complete_candidate_audit_preserve_results(pareto):
    view, scorer = fixture()
    config = EGPOTConfig(use_mcts=False, use_pareto=pareto)
    normal = EGPOTRetriever(config, view, scorer).retrieve("currency", "s", 2)
    retriever = CandidateAuditRetriever(config, view, scorer)
    untraced = retriever.retrieve("currency", "s", 2)
    trace = {}
    traced = retriever.retrieve("currency", "s", 2, trace=trace)
    assert content(normal) == content(untraced) == content(traced)
    assert set(retriever.engine.first_candidate_round) == {"z_relevant", "a_contract"}
    assert set(retriever.engine.first_candidate_round.values()) == {1}
    assert trace["final"]["visited_order"] == traced.discovery_order


def test_candidate_audit_includes_nodes_omitted_by_display_cap():
    graph = nx.MultiDiGraph()
    graph.add_node("s", name="root", type="function")
    for i in range(80):
        node = f"n{i:03}"
        graph.add_node(node, name="currency exchange", type="function")
        graph.add_edge("s", node, relation="CALLS")
    view = GraphView(graph)
    engine = CandidateAuditRetriever(EGPOTConfig(use_mcts=False), view, QueryScorer(view))
    trace = {}
    engine.retrieve("currency", "s", 2, trace=trace)
    first = trace["steps"][0]
    assert first["candidates_total"] == 80
    assert len(first["candidates"]) == 60
    assert len(engine.engine.first_candidate_round) == 80
    assert engine.engine.first_candidate_round["n079"] == 1


def test_distribution_counts_and_type_splits():
    records = [{"method": method, "type": kind, "hit": hit}
               for method, values in [("a", [1, 0]), ("b", [1, 1])]
               for kind, hit in zip(["explicit", "indirect"], values)]
    reference = [{"type": "explicit", "hit": 1}, {"type": "indirect", "hit": 0}]
    all_rows = weight_distribution(records, ["a", "b"], reference)
    assert all_rows["mean"] == 1.5
    assert (all_rows["below"], all_rows["equal"], all_rows["above"]) == (0, 1, 1)
    assert all_rows["q25"] == 1.25
    explicit = weight_distribution(records, ["a", "b"], reference, "explicit")
    assert (explicit["queries"], explicit["equal"], explicit["above"]) == (1, 2, 0)


def test_weights_mode_refuses_test_even_with_confirmation():
    with pytest.raises(SystemExit):
        main(["--mode", "weights", "--split", "test", "--confirm-test"])
