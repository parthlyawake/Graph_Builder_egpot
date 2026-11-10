"""Beam-MCTS tests: graphs and simulations stay entirely in memory."""

from copy import deepcopy

import networkx as nx
import pytest

from eg_pot import CandidateStep, EGPOT, EGPOTConfig, PathState


@pytest.fixture
def trap():
    graph = nx.MultiDiGraph()
    for node, text in {"S": "start", "A": "currency", "B": "currency relay metadata indirection",
                       "C": "currency"}.items():
        graph.add_node(node, name=text, type="function")
    for u, v in (("S", "A"), ("S", "B"), ("B", "C")):
        graph.add_edge(u, v, key=0, relation="CALLS", layer="Ldep")
    return graph


def initial():
    return PathState(["S"], [], {"S": 0}, {}, {"S"})


def candidate():
    return CandidateStep("S", "B", "CALLS", "out", 0, "Ldep")


def test_trap_graph(trap):
    plain = EGPOT(trap, EGPOTConfig(use_mcts=False, beam_width=1, node_budget=3))
    mcts = EGPOT(trap, EGPOTConfig(use_mcts=True, beam_width=1, node_budget=3))
    assert plain.semantic_relevance("currency", "A") == pytest.approx(1.0)
    assert 0 < plain.semantic_relevance("currency", "B") < 0.5
    without = plain.traverse("currency", "S")
    with_mcts = mcts.traverse("currency", "S")
    assert without.ordered_path == ["S", "A"]
    assert "C" not in without.visited
    assert with_mcts.ordered_path == ["S", "B", "C"]
    assert "C" in with_mcts.visited


def test_repeatable_across_instances_and_cached_calls(trap):
    # Add alternative futures so sampling actually has multiple choices.
    trap.add_node("D", name="relay")
    trap.add_node("E", name="currency display")
    trap.add_edge("B", "D", relation="CONTAINS", layer="Lsyn")
    trap.add_edge("D", "E", relation="CALLS", layer="Ldep")
    config = EGPOTConfig(seed=123, beam_width=2, node_budget=5)
    first, second = EGPOT(trap, config), EGPOT(trap, config)
    vector = first.lookahead_vector("currency", initial(), candidate())
    assert vector == second.lookahead_vector("currency", initial(), candidate())
    result = first.traverse("currency", "S")
    assert result == first.traverse("currency", "S")
    assert result == second.traverse("currency", "S")


def test_simulation_does_not_mutate_state_or_graph(trap):
    state = initial()
    before, graph_before = deepcopy(state), deepcopy(trap)
    step = candidate()
    saved_step = deepcopy(step)
    vector = EGPOT(trap).lookahead_vector("currency", state, step)
    assert state == before
    assert step == saved_step
    assert nx.utils.graphs_equal(trap, graph_before)
    assert all(0 <= value <= 1 for value in vector)


@pytest.mark.parametrize("use_mcts, weight", [(False, 0.5), (True, 0.0)])
def test_disabled_modes_never_call_lookahead(trap, monkeypatch, use_mcts, weight):
    plain = EGPOT(trap, EGPOTConfig(use_mcts=False, beam_width=1, node_budget=3))
    engine = EGPOT(trap, EGPOTConfig(use_mcts=use_mcts, lookahead_weight=weight,
                                    beam_width=1, node_budget=3))

    def forbidden(*args):
        raise AssertionError("disabled lookahead must not run")

    monkeypatch.setattr(engine, "lookahead_vector", forbidden)
    assert engine.traverse("currency", "S") == plain.traverse("currency", "S")


@pytest.mark.parametrize("budget", [1, 2, 3, 4])
def test_rollouts_do_not_consume_node_budget(trap, budget):
    engine = EGPOT(trap, EGPOTConfig(node_budget=budget, beam_width=1))
    result = engine.traverse("currency", "S")
    assert len(result.visited) <= budget
    assert set(result.ordered_path) <= result.visited
    if budget == 2:
        # C is simulated when evaluating B, but is never selected in reality.
        assert result.visited == {"S", "B"}
        assert "C" not in result.visited


def test_discount_normalization_blending_and_dead_ends():
    graph = nx.MultiDiGraph()
    for node in ("S", "B", "C", "D"):
        graph.add_node(node, name="currency")
    for u, v in (("S", "B"), ("B", "C"), ("C", "D")):
        graph.add_edge(u, v, key=0, relation="CALLS", layer="Ldep")
    engine = EGPOT(graph)
    state, step = initial(), candidate()
    expected = tuple(value / (1 + 0.8 + 0.8 ** 2) for value in
                     (1 + 0.8, 0.8 ** 2 + 0.8 * 0.8 ** 3, 0.6 + 0.8 * 0.6, 0))
    assert engine.lookahead_vector("currency", state, step) == pytest.approx(expected)
    immediate = engine.objective_vector("currency", state, step)
    assert engine.candidate_vector("currency", state, step) == pytest.approx(
        tuple(0.5 * now + 0.5 * later for now, later in zip(immediate, expected)))
    terminal_state = state.extend(step).extend(CandidateStep("B", "C", "CALLS", "out", 0, "Ldep"))
    terminal = CandidateStep("C", "D", "CALLS", "out", 0, "Ldep")
    assert engine.lookahead_vector("currency", terminal_state, terminal) == (0.,) * 4


def test_rollout_branch_limit_and_query_neighbor_caches(trap, monkeypatch):
    trap.add_node("D", name="unrelated")
    trap.add_edge("B", "D", relation="CALLS", layer="Ldep")
    engine = EGPOT(trap, EGPOTConfig(max_rollout_branching=1, rollout_depth=1))
    expected = engine.objective_vector("currency", initial().extend(candidate()),
                                      CandidateStep("B", "C", "CALLS", "out", 0, "Ldep"))
    assert engine.lookahead_vector("currency", initial(), candidate()) == pytest.approx(expected)

    def forbidden(*args):
        raise AssertionError("cached neighbors and relevance should be reused")

    monkeypatch.setattr(engine.graph_view, "neighbors", forbidden)
    monkeypatch.setattr(engine.scorer, "score_many", forbidden)
    assert engine.lookahead_vector("currency", initial(), candidate()) == pytest.approx(expected)


@pytest.mark.parametrize("kwargs", [
    {"lookahead_weight": -0.1}, {"lookahead_weight": 1.1},
    {"lookahead_weight": float("nan")}, {"lookahead_weight": True},
    {"lookahead_weight": "0.5"}, {"rollout_temperature": 0},
    {"rollout_temperature": -1}, {"rollout_temperature": float("inf")},
    {"rollout_temperature": float("nan")}, {"rollout_temperature": False},
    {"rollout_temperature": "0.5"}, {"max_rollout_branching": 0},
    {"max_rollout_branching": -1}, {"max_rollout_branching": 1.5},
    {"max_rollout_branching": True},
])
def test_new_config_validation(kwargs):
    with pytest.raises(ValueError):
        EGPOTConfig(**kwargs)


def test_new_defaults():
    config = EGPOTConfig()
    assert config.lookahead_weight == config.rollout_temperature == 0.5
    assert config.max_rollout_branching == 8
