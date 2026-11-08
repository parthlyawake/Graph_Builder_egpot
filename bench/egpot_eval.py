"""Exact-ID EG-POT comparisons; read-only inputs and console-only output.

Run: python -B -m bench.egpot_eval
The test split requires both --split test and --confirm-test.
"""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass, field, replace
import hashlib
import json
import math
from pathlib import Path
from statistics import fmean
import sys
import weakref
from time import perf_counter
from typing import Protocol

import networkx as nx
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from eg_pot import EGPOT, EGPOTConfig, GraphView, QueryScorer
from eg_pot import CandidateStep, PathState


@dataclass
class RetrievalResult:
    visited: set[str]
    ordered_path: list[str]
    latency_s: float
    discovery_order: list[str]
    edges: list[tuple[str, str, str]] = field(default_factory=list)


class Retriever(Protocol):
    def retrieve(self, query: str, start_node: str, node_budget: int, trace: dict | None = None) -> RetrievalResult: ...


def _finish_trace(trace: dict | None, result: RetrievalResult) -> RetrievalResult:
    if trace is not None:
        trace["final"] = {"visited_order": list(result.discovery_order),
                          "ordered_path": list(result.ordered_path),
                          "edges": [list(edge) for edge in result.edges]}
    return result


class _SharedScorerEGPOT(EGPOT):
    """Inject the shared fitted scorer without invoking EGPOT's fitting constructor.

    Only initialization is adapted; traversal/objectives/selection are inherited.
    """

    def __init__(self, config: EGPOTConfig, view: GraphView, scorer: QueryScorer):
        self.config = config
        self.graph_view = view
        self.scorer = scorer
        count = len({d.get("relation", "LINK") for _, _, d in view.graph.edges(data=True)})
        self._entropy_denominator = math.log(count) if count > 1 else 0.0
        self._relevance_cache = {}
        self._neighbor_cache = {}


class _RetrieverBase:
    def __init__(self, graph_view: GraphView, scorer: QueryScorer):
        if scorer.graph_view is not graph_view:
            raise ValueError("retrievers must share the scorer's GraphView")
        if not graph_view.use_choke_point:
            raise ValueError("RPC choke-point rule must be enabled")
        self.graph_view, self.scorer = graph_view, scorer

    def _validate(self, start_node: str, node_budget: int) -> None:
        if type(node_budget) is not int or node_budget < 1:
            raise ValueError("node_budget must be a positive integer")
        if start_node not in self.graph_view.graph:
            raise KeyError(start_node)


class EGPOTRetriever(_RetrieverBase):
    def __init__(self, config: EGPOTConfig, graph_view: GraphView, scorer: QueryScorer,
                 *, use_choke_point: bool = True):
        super().__init__(graph_view, scorer)
        if not use_choke_point:
            # The sole view-setting ablation: same graph and fitted text scorer.
            self.graph_view = GraphView(graph_view.graph, use_choke_point=False)
        self.config = replace(config)
        self.engine = _SharedScorerEGPOT(self.config, self.graph_view, scorer)

    def retrieve(self, query: str, start_node: str, node_budget: int, trace: dict | None = None) -> RetrievalResult:
        began = perf_counter()
        self._validate(start_node, node_budget)
        self.engine.config = replace(self.config, node_budget=node_budget)
        # Each retrieval includes its own graph/relevance-cache work; neither
        # a repeated query nor the second budget gets warm engine caches.
        self.engine._relevance_cache.clear()
        self.engine._neighbor_cache.clear()
        result = (self.engine.traverse(query, start_node) if trace is None else
                  self.engine.traverse(query, start_node, trace=trace))
        return RetrievalResult(set(result.visited), list(result.ordered_path), perf_counter() - began,
                               list(result.visited_order), list(result.edges))


class VectorTopK(_RetrieverBase):
    """Reserve one budget slot for start, then rank all other nodes globally.

    ordered_path is start followed by relevance order, not a graph walk.
    discovery_order ranks the selected set by relevance, including the forced
    start node, which can therefore appear anywhere in discovery_order.
    """

    def retrieve(self, query: str, start_node: str, node_budget: int, trace: dict | None = None) -> RetrievalResult:
        began = perf_counter()
        self._validate(start_node, node_budget)
        scores = self.scorer.score_many(query, self.scorer.node_ids)
        ranked = sorted((n for n in scores if n != start_node), key=lambda n: (-scores[n], str(n)))
        ordered = [start_node, *ranked[:node_budget - 1]]
        discovery = sorted(ordered, key=lambda n: (-scores[n], str(n)))
        if trace is not None:
            trace["steps"] = [{"kind": "vector_rank", "ranking": [
                {"node": n, "score": float(scores[n])} for n in discovery]}]
        return _finish_trace(trace, RetrievalResult(set(ordered), ordered, perf_counter() - began, discovery))


class BFS(_RetrieverBase):
    """Bidirectional BFS; ordered_path records discovery order, not one walk."""

    def retrieve(self, query: str, start_node: str, node_budget: int, trace: dict | None = None) -> RetrievalResult:
        began = perf_counter()
        self._validate(start_node, node_budget)
        ordered, visited, queue = [start_node], {start_node}, deque([start_node])
        edges = []
        if trace is not None:
            trace["steps"] = []
            depths, layers = {start_node: 0}, {}
        while queue and len(visited) < node_budget:
            current = queue.popleft()
            if trace is not None:
                depth = depths[current]
                if depth not in layers:
                    layers[depth] = {"kind": "bfs_layer", "layer": depth,
                                     "frontier": [current, *[n for n in queue if depths[n] == depth]], "added": []}
                    trace["steps"].append(layers[depth])
            for neighbor, relation, _, _ in self.graph_view.neighbors(current):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                ordered.append(neighbor)
                queue.append(neighbor)
                edges.append((current, relation, neighbor))
                if trace is not None:
                    depths[neighbor] = depth + 1
                    layers[depth]["added"].append(neighbor)
                if len(visited) == node_budget:
                    break
        return _finish_trace(trace, RetrievalResult(visited, ordered, perf_counter() - began, list(ordered), edges))


class GreedyWalk(_RetrieverBase):
    def retrieve(self, query: str, start_node: str, node_budget: int, trace: dict | None = None) -> RetrievalResult:
        began = perf_counter()
        self._validate(start_node, node_budget)
        scores = self.scorer.score_many(query, self.scorer.node_ids)
        ordered, visited = [start_node], {start_node}
        edges = []
        if trace is not None:
            trace["steps"] = []
        while len(visited) < node_budget:
            neighbors = {n for n, _, _, _ in self.graph_view.neighbors(ordered[-1]) if n not in visited}
            if not neighbors:
                if trace is not None:
                    trace["steps"].append({"kind": "greedy_step", "from": ordered[-1], "options": [], "chosen": None})
                break
            chosen = min(neighbors, key=lambda n: (-scores[n], str(n)))
            current = ordered[-1]
            relation = next(rel for n, rel, _, _ in self.graph_view.neighbors(current) if n == chosen)
            edges.append((current, relation, chosen))
            if trace is not None:
                trace["steps"].append({"kind": "greedy_step", "from": current,
                    "options": [{"to": n, "score": float(scores[n])} for n in
                                sorted(neighbors, key=lambda n: (-scores[n], str(n)))[:10]], "chosen": chosen})
            visited.add(chosen)
            ordered.append(chosen)
        return _finish_trace(trace, RetrievalResult(visited, ordered, perf_counter() - began, list(ordered), edges))


class VectorBFS(_RetrieverBase):
    """Multi-source traversal, with a capped start-first vector seed prefix."""

    def __init__(self, graph_view, scorer, k):
        super().__init__(graph_view, scorer)
        if type(k) is not int or k < 0:
            raise ValueError("k must be a nonnegative integer")
        self.k = k

    def retrieve(self, query, start_node, node_budget, trace=None):
        began = perf_counter()
        self._validate(start_node, node_budget)
        scores = self.scorer.score_many(query, self.scorer.node_ids)
        # Top three globally, including start if it ranks there; union removes
        # duplicates. A small budget truncates this seed prefix before BFS.
        ranked = sorted(scores, key=lambda n: (-scores[n], str(n)))[:3]
        ordered = list(dict.fromkeys([start_node, *ranked]))[:node_budget]
        visited, queue, edges = set(ordered), deque((n, 0) for n in ordered), []
        while queue and len(visited) < node_budget:
            current, depth = queue.popleft()
            if depth >= self.k:
                continue
            for neighbor, relation, _, _ in self.graph_view.neighbors(current):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                ordered.append(neighbor)
                edges.append((current, relation, neighbor))
                queue.append((neighbor, depth + 1))
                if len(visited) == node_budget:
                    break
        return _finish_trace(trace, RetrievalResult(visited, list(ordered), perf_counter()-began, ordered, edges))


def _move_graph(view):
    """Weighted directed permitted moves; parallel neighbor records add weight.

    'in' describes the raw edge orientation, not a reversed traversal move:
    each permitted GraphView move is current -> neighbor. This is necessary
    for the RPC choke-point filter to survive conversion to a directed graph.
    """
    graph = nx.DiGraph()
    graph.add_nodes_from(sorted(view.graph, key=str))
    for node in graph:
        for neighbor, _, _, _ in view.neighbors(node):
            weight = graph[node][neighbor]["weight"] + 1.0 if graph.has_edge(node, neighbor) else 1.0
            graph.add_edge(node, neighbor, weight=weight)
    return graph


class PersonalizedPageRank(_RetrieverBase):
    def __init__(self, graph_view, scorer):
        super().__init__(graph_view, scorer)
        self.move_graph = _move_graph(graph_view)
        self._scores = {}

    def scores(self, start_node):
        if start_node not in self._scores:
            personalization = {n: float(n == start_node) for n in self.move_graph}
            self._scores[start_node] = nx.pagerank(self.move_graph, alpha=0.85,
                personalization=personalization, tol=1e-10, max_iter=500, weight="weight")
        return dict(self._scores[start_node])

    def retrieve(self, query, start_node, node_budget, trace=None):
        began = perf_counter()
        self._validate(start_node, node_budget)
        # Include the solve in every retrieval's measured latency, rather than
        # giving the paired query or second budget a cached ranking advantage.
        self._scores.pop(start_node, None)
        scores = self.scores(start_node)
        ordered = [start_node, *sorted((n for n in scores if n != start_node),
                                      key=lambda n: (-scores[n], str(n)))[:node_budget-1]]
        return _finish_trace(trace, RetrievalResult(set(ordered), list(ordered), perf_counter()-began, ordered))


class ScalarBeam(_RetrieverBase):
    """Path relevance sum, width four, and the EG-POT collected-union budget."""

    def retrieve(self, query, start_node, node_budget, trace=None):
        began = perf_counter()
        self._validate(start_node, node_budget)
        scores = self.scorer.score_many(query, self.scorer.node_ids)
        beam = [(PathState([start_node], [], {start_node: 0}, {}, {start_node}), scores[start_node])]
        ordered, visited = [start_node], {start_node}
        while beam and len(visited) < node_budget:
            candidates = []
            for state, total in beam:
                current = state.ordered_nodes[-1]
                for neighbor, relation, direction, key in self.graph_view.neighbors(current):
                    if neighbor in state.visited:
                        continue
                    step = CandidateStep(current, neighbor, relation, direction, key, "")
                    extended = state.extend(step)
                    candidates.append((extended, total + scores[neighbor]))
            if not candidates:
                break
            candidates.sort(key=lambda item: (-item[1], str(item[0].ordered_nodes[-1]),
                                               tuple(map(str, item[0].ordered_nodes)),
                                               tuple(tuple(map(str, e)) for e in item[0].edges)))
            selected = []
            for state, total in candidates[:4]:
                last = state.ordered_nodes[-1]
                if last not in visited:
                    if len(visited) == node_budget:
                        continue
                    visited.add(last)
                    ordered.append(last)
                selected.append((state, total))
            if not selected:
                break
            beam = selected
        best = min(beam, key=lambda item: (-item[1], tuple(map(str, item[0].ordered_nodes))))[0]
        return _finish_trace(trace, RetrievalResult(visited, list(best.ordered_nodes), perf_counter()-began,
                                                   ordered, list(best.edges)))


_COMMUNITY_PARTITIONS = weakref.WeakKeyDictionary()


class CommunityGraphRAG(_RetrieverBase):
    def __init__(self, graph_view, scorer):
        super().__init__(graph_view, scorer)
        louvain = getattr(nx.community, "louvain_communities", None)
        if not callable(louvain):
            raise ImportError("CommunityGraphRAG requires networkx.community.louvain_communities")
        simple = nx.Graph()
        simple.add_nodes_from(sorted(graph_view.graph, key=str))
        simple.add_edges_from(sorted({tuple(sorted((u, v), key=str))
            for u in graph_view.graph for v, _, _, _ in graph_view.neighbors(u)}, key=lambda e: tuple(map(str, e))))
        fingerprint = (tuple(simple.nodes), tuple(simple.edges))
        cached = _COMMUNITY_PARTITIONS.get(graph_view.graph)
        if cached is None or cached[0] != fingerprint:
            try:
                groups = louvain(simple, seed=0, resolution=1.0, weight=None)
            except ImportError as exc:
                raise ImportError("CommunityGraphRAG requires Louvain and its optional dependencies") from exc
            partition = tuple(sorted((tuple(sorted(c, key=str)) for c in groups),
                                     key=lambda c: tuple(map(str, c))))
            _COMMUNITY_PARTITIONS[graph_view.graph] = (fingerprint, partition)
        self.partition = _COMMUNITY_PARTITIONS[graph_view.graph][1]

    def retrieve(self, query, start_node, node_budget, trace=None):
        began = perf_counter()
        self._validate(start_node, node_budget)
        scores = self.scorer.score_many(query, self.scorer.node_ids)
        communities = []
        for group in self.partition:
            nodes = sorted(group, key=lambda n: (-scores[n], str(n)))
            relevance = fmean(scores[n] for n in nodes[:5])
            communities.append((relevance, nodes))
        communities.sort(key=lambda item: (-item[0], tuple(map(str, item[1]))))
        ordered = [start_node]
        for _, nodes in communities:
            for node in nodes:
                if node != start_node and len(ordered) < node_budget:
                    ordered.append(node)
            if len(ordered) == node_budget:
                break
        return _finish_trace(trace, RetrievalResult(set(ordered), list(ordered), perf_counter()-began, ordered))


@dataclass
class _UCTNode:
    node: str
    path: tuple
    parent: object = None
    children: list = field(default_factory=list)
    unexpanded: list | None = None
    visits: int = 0
    reward: float = 0.0


class StandardMCTS(_RetrieverBase):
    """Classic UCT, not beam search; only expanded tree nodes are returned.

    Uniform choices are over distinct unvisited neighbors. Repeated graph IDs
    at different tree positions are ranked by their strongest tree occurrence
    (sort tree nodes first, then deduplicate). The rollout includes its leaf.
    """

    def __init__(self, graph_view, scorer, *, seed=0, query_ids=None):
        super().__init__(graph_view, scorer)
        self.seed = seed
        self.query_ids = dict(query_ids or {})

    def retrieve(self, query, start_node, node_budget, trace=None):
        began = perf_counter()
        self._validate(start_node, node_budget)
        query_id = self.query_ids.get((query, start_node), query)
        stable = hashlib.sha256(json.dumps([query_id, start_node], ensure_ascii=False).encode()).digest()
        rng = np.random.RandomState((self.seed + int.from_bytes(stable[:8], "big")) % (2**32))
        scores = self.scorer.score_many(query, self.scorer.node_ids)
        neighbor_cache = {}

        def neighbors(node):
            if node not in neighbor_cache:
                neighbor_cache[node] = sorted({n for n, _, _, _ in self.graph_view.neighbors(node)}, key=str)
            return neighbor_cache[node]

        root = _UCTNode(start_node, (start_node,))
        tree = [root]
        for _ in range(300):
            node = root
            while True:
                if node.unexpanded is None:
                    node.unexpanded = [n for n in neighbors(node.node) if n not in node.path]
                if node.unexpanded:
                    chosen = node.unexpanded.pop(int(rng.randint(len(node.unexpanded))))
                    child = _UCTNode(chosen, (*node.path, chosen), node)
                    node.children.append(child)
                    tree.append(child)
                    node = child
                    break
                if not node.children:
                    break
                node = min(node.children, key=lambda c: (
                    -(c.reward/c.visits + 1.4*math.sqrt(math.log(node.visits)/c.visits)),
                    str(c.node), tuple(map(str, c.path))))
            simulated = set(node.path)
            current, reward = node.node, scores[node.node]
            for _ in range(3):
                options = [n for n in neighbors(current) if n not in simulated]
                if not options:
                    break
                current = options[int(rng.randint(len(options)))]
                simulated.add(current)
                reward = max(reward, scores[current])
            cursor = node
            while cursor is not None:
                cursor.visits += 1
                cursor.reward += reward
                cursor = cursor.parent
        self.last_tree = tree
        ranked = sorted(tree, key=lambda n: (-n.visits, str(n.node), tuple(map(str, n.path))))
        ordered = list(dict.fromkeys([start_node, *(n.node for n in ranked)]))[:node_budget]
        return _finish_trace(trace, RetrievalResult(set(ordered), list(ordered), perf_counter()-began, ordered))


NEW_BASELINES = (*[f"vector_bfs_k{k}" for k in (2, 3, 4, 5)], "ppr", "scalar_beam",
                 "community_graphrag", "mcts_standard")


def make_comparison_retrievers(view, scorer, *, query_ids=None):
    """Additional registry; existing registries/retrievers remain unchanged."""
    methods = {
        "egpot_full": EGPOTRetriever(EGPOTConfig(use_mcts=False), view, scorer),
        "egpot_full_mcts": EGPOTRetriever(EGPOTConfig(use_mcts=True), view, scorer),
        "egpot_no_pareto": EGPOTRetriever(EGPOTConfig(use_mcts=False, use_pareto=False), view, scorer),
        "vector_topk": VectorTopK(view, scorer), "bfs": BFS(view, scorer),
        "greedy_walk": GreedyWalk(view, scorer),
    }
    factories = {**{f"vector_bfs_k{k}": lambda k=k: VectorBFS(view, scorer, k) for k in (2, 3, 4, 5)},
        "ppr": lambda: PersonalizedPageRank(view, scorer), "scalar_beam": lambda: ScalarBeam(view, scorer),
        "community_graphrag": lambda: CommunityGraphRAG(view, scorer),
        "mcts_standard": lambda: StandardMCTS(view, scorer, seed=0, query_ids=query_ids)}
    for name, factory in factories.items():
        began = perf_counter()
        methods[name] = factory()
        methods[name].setup_latency_s = perf_counter()-began
    return methods


class _NoChokeVariant:
    """Explicit opt-in wrapper; the original constructors still require ON.

    Text relevance uses the original shared scorer. Only allowed adjacency
    changes. One OFF view can be supplied to every variant in an experiment.
    """

    def __init__(self, graph_view, scorer, *args, no_choke_view=None, **kwargs):
        super().__init__(graph_view, scorer, *args, **kwargs)
        off = no_choke_view if no_choke_view is not None else GraphView(graph_view.graph, use_choke_point=False)
        if off.graph is not graph_view.graph or off.use_choke_point:
            raise ValueError("no-choke variants require the same graph with the rule OFF")
        self.graph_view = off
        if isinstance(self, PersonalizedPageRank):
            self.move_graph = _move_graph(off)
            self._scores.clear()


class BFSNoChoke(_NoChokeVariant, BFS):
    pass


class VectorBFSNoChoke(_NoChokeVariant, VectorBFS):
    pass


class PPRNoChoke(_NoChokeVariant, PersonalizedPageRank):
    pass


class ScalarBeamNoChoke(_NoChokeVariant, ScalarBeam):
    pass


class StandardMCTSNoChoke(_NoChokeVariant, StandardMCTS):
    pass


class GreedyWalkNoChoke(_NoChokeVariant, GreedyWalk):
    pass


FAIRNESS_METHODS = ("egpot_full", "egpot_full_mcts", "egpot_no_pareto", "ppr",
                    "mcts_standard", "scalar_beam", "vector_topk", "bfs", "greedy_walk",
                    "vector_bfs_k2", "community_graphrag")
FAIRNESS_BUDGETS = (5, 10, 15, 20, 30, 40)
STOCHASTIC_METHODS = ("mcts_standard", "egpot_full_mcts", "egpot_no_pareto_mcts")
CHOKE_PAIRS = (("bfs", "bfs_no_choke"), ("vector_bfs_k2", "vector_bfs_k2_no_choke"),
               ("ppr", "ppr_no_choke"), ("scalar_beam", "scalar_beam_no_choke"),
               ("mcts_standard", "mcts_standard_no_choke"), ("greedy_walk", "greedy_walk_no_choke"),
               ("egpot_full", "egpot_no_choke_point"))


def make_fairness_retrievers(view, scorer, *, seed=0, query_ids=None):
    """Seed only stochastic engines; deterministic configurations stay intact."""
    comparison = make_comparison_retrievers(view, scorer, query_ids=query_ids)
    methods = {name: comparison[name] for name in FAIRNESS_METHODS}
    methods["mcts_standard"].seed = seed
    methods["egpot_full_mcts"].config = replace(methods["egpot_full_mcts"].config, seed=seed)
    methods["egpot_no_pareto_mcts"] = EGPOTRetriever(
        EGPOTConfig(use_mcts=True, use_pareto=False, seed=seed), view, scorer)
    off = GraphView(view.graph, use_choke_point=False)
    factories = {
        "bfs_no_choke": lambda: BFSNoChoke(view, scorer, no_choke_view=off),
        "vector_bfs_k2_no_choke": lambda: VectorBFSNoChoke(view, scorer, 2, no_choke_view=off),
        "ppr_no_choke": lambda: PPRNoChoke(view, scorer, no_choke_view=off),
        "scalar_beam_no_choke": lambda: ScalarBeamNoChoke(view, scorer, no_choke_view=off),
        "mcts_standard_no_choke": lambda: StandardMCTSNoChoke(view, scorer, seed=seed,
                                                              query_ids=query_ids, no_choke_view=off),
        "greedy_walk_no_choke": lambda: GreedyWalkNoChoke(view, scorer, no_choke_view=off),
    }
    methods.update({name: factory() for name, factory in factories.items()})
    reference = EGPOTRetriever(EGPOTConfig(use_mcts=False), view, scorer, use_choke_point=False)
    reference.graph_view = off
    reference.engine.graph_view = off
    methods["egpot_no_choke_point"] = reference
    return methods


def matched_node_budget(records):
    values = [r["nodes_returned"] for r in records
              if r["method"] == "egpot_full" and r["node_budget"] == 40]
    if not values:
        raise ValueError("matching requires egpot_full at budget 40")
    return round(fmean(values))


def ordered_path_match(ordered_path: list[str], gold_path: list[str]) -> int:
    """Exact-ID ordered subsequence; adjacency is not required."""
    position = 0
    for node in ordered_path:
        if position < len(gold_path) and node == gold_path[position]:
            position += 1
    return int(position == len(gold_path))


def nodes_to_hit(discovery_order: list[str], gold_nodes: list[str]) -> int | None:
    """One-based position of the last first-found exact gold ID; None on misses."""
    remaining = set(gold_nodes)
    if not remaining:
        raise ValueError("gold_nodes must be nonempty")
    for position, node in enumerate(discovery_order, 1):
        remaining.discard(node)
        if not remaining:
            return position
    return None


def metrics(result: RetrievalResult, gold_nodes: list[str], gold_path: list[str]) -> dict:
    """Gold alternatives are intentionally absent: only exact labeled IDs count."""
    gold, path_nodes = set(gold_nodes), set(gold_path)
    if not gold or not path_nodes:
        raise ValueError("gold_nodes and gold_path must be nonempty")
    overlap = len(result.visited & gold)
    hit_position = nodes_to_hit(result.discovery_order, gold_nodes)
    return {
        "gold_recall": overlap / len(gold),
        "precision": overlap / len(result.visited) if result.visited else 0.0,
        "hit": int(gold <= result.visited),
        "path_coverage": len(result.visited & path_nodes) / len(path_nodes),
        "ordered_path_match": ordered_path_match(result.ordered_path, gold_path),
        "nodes_returned": len(result.visited),
        "latency_s": result.latency_s,
        "nodes_to_hit": hit_position,
        "precision_at_hit": len(gold) / hit_position if hit_position is not None else None,
    }


def split_by_link(rows: list[dict]) -> dict[str, list[dict]]:
    links = sorted({row["link_id"] for row in rows},
                   key=lambda link: hashlib.sha256(str(link).encode("utf-8")).hexdigest())
    dev = set(links[::2])
    return {"dev": [r for r in rows if r["link_id"] in dev],
            "test": [r for r in rows if r["link_id"] not in dev]}


def make_retrievers(view: GraphView, scorer: QueryScorer) -> dict[str, Retriever]:
    return {
        "EGPOT(no MCTS)": EGPOTRetriever(EGPOTConfig(use_mcts=False), view, scorer),
        "EGPOT(MCTS)": EGPOTRetriever(EGPOTConfig(use_mcts=True), view, scorer),
        "VectorTopK": VectorTopK(view, scorer),
        "BFS": BFS(view, scorer),
        "GreedyWalk": GreedyWalk(view, scorer),
    }


@dataclass(frozen=True)
class AblationConfig:
    config: EGPOTConfig
    use_choke_point: bool = True


FULL_PLAIN = "full(no MCTS/no_mcts_rollout)"
FULL_MCTS = "full(MCTS)"
SWEEP_BUDGETS = (20, 40, 60, 100, 200)


def ablation_configs() -> dict[str, AblationConfig]:
    """One full/no-rollout row, plus each component disabled in both MCTS modes."""
    specs = {}
    for mode in (False, True):
        suffix = "MCTS" if mode else "no MCTS"
        base = EGPOTConfig(seed=0, use_mcts=mode)
        specs[FULL_MCTS if mode else FULL_PLAIN] = AblationConfig(base)
        for component in ("pareto", "entropy", "contracts"):
            specs[f"no_{component}({suffix})"] = AblationConfig(
                replace(base, **{f"use_{component}": False}))
        specs[f"no_choke_point({suffix})"] = AblationConfig(replace(base), False)
    return specs


def make_ablations(view: GraphView, scorer: QueryScorer) -> dict[str, Retriever]:
    return {name: EGPOTRetriever(spec.config, view, scorer, use_choke_point=spec.use_choke_point)
            for name, spec in ablation_configs().items()}


def evaluate(rows: list[dict], retrievers: dict[str, Retriever], node_budget: int) -> list[dict]:
    records = []
    for row in sorted(rows, key=lambda r: r["id"]):
        # Explicit allowlist: labels, IDs, gold targets, paths, alternatives and
        # evidence never cross the retriever's three-argument boundary.
        request = {"query": row["query"], "start_node": row["start_node"], "node_budget": node_budget}
        for method, retriever in retrievers.items():
            result = retriever.retrieve(**request)
            if row["start_node"] not in result.visited or len(result.visited) > node_budget:
                raise ValueError(f"{method} violated start-node/budget rules")
            if not set(result.ordered_path) <= result.visited:
                raise ValueError(f"{method} returned path nodes outside visited")
            if (set(result.discovery_order) != result.visited
                    or len(result.discovery_order) != len(result.visited)):
                raise ValueError(f"{method} violated discovery-order invariant")
            if not isinstance(retriever, VectorTopK) and result.discovery_order[0] != row["start_node"]:
                raise ValueError(f"{method} must discover start first")
            if not math.isfinite(result.latency_s) or result.latency_s < 0:
                raise ValueError(f"{method} returned invalid latency")
            records.append({"id": row["id"], "link_id": row["link_id"], "type": row["type"],
                            "method": method, "node_budget": node_budget,
                            **metrics(result, row["gold_nodes"], row["gold_path"])})
    return records


def summarize(records: list[dict]) -> dict:
    hits = [r for r in records if r["nodes_to_hit"] is not None]
    values = {name: fmean(r[name] for r in records) for name in
              ("gold_recall", "hit", "path_coverage", "nodes_returned", "latency_s")}
    values.update(hit_count=len(hits),
                  nodes_to_hit=fmean(r["nodes_to_hit"] for r in hits) if hits else None,
                  precision_at_hit=fmean(r["precision_at_hit"] for r in hits) if hits else None)
    return values


def print_table(records: list[dict], methods: list[str], budget: int, query_type: str | None = None) -> None:
    selected = [r for r in records if query_type is None or r["type"] == query_type]
    count = len({r["id"] for r in selected})
    print(f"\nBudget {budget} | {query_type or 'all'} | {count} queries")
    print("| Method | Recall | Hit | Path coverage | Nodes | Nodes-to-hit (hits only) | Hits | Precision-at-hit | Latency s |", flush=True)
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|", flush=True)
    for method in methods:
        values = [r for r in selected if r["method"] == method]
        summary = summarize(values)
        columns = ("gold_recall", "hit", "path_coverage", "nodes_returned", "nodes_to_hit",
                   "hit_count", "precision_at_hit", "latency_s")
        formatted = ["—" if summary[c] is None else
                     str(summary[c]) if c == "hit_count" else f"{summary[c]:.6f}" for c in columns]
        print(f"| {method} | " + " | ".join(formatted) + " |", flush=True)


def run_budget_sweep(rows: list[dict], retrievers: dict[str, Retriever], *,
                     cached: dict[tuple[str, int], list[dict]] | None = None,
                     budgets=SWEEP_BUDGETS, mcts_limit_s: float = 600.0) -> list[dict]:
    """Reuse identical full runs; cap the optional MCTS-200 experiment at ~10 min.

    The estimate for 200 is twice measured MCTS-100 latency plus prior sweep
    latency. If it exceeds the allowance, skip 200. Also check elapsed time
    between queries at 200; discard incomplete budget results, never average a
    partial query subset. Full <=100 runs always finish.
    """
    cached = {} if cached is None else cached
    records, mcts_seconds, measured = [], 0.0, {}
    for budget in budgets:
        for method, retriever in retrievers.items():
            if method == FULL_MCTS and budget == 200:
                estimate = 2 * measured.get(100, 0.0)
                if mcts_seconds + estimate > mcts_limit_s:
                    print(f"MCTS-200 SKIPPED: measured prior sweep MCTS {mcts_seconds:.3f}s; "
                          f"estimated additional {estimate:.3f}s exceeds {mcts_limit_s:.0f}s total allowance.", flush=True)
                    continue
            key = (method, budget)
            reused = key in cached
            if reused:
                current = cached[key]
            elif method == FULL_MCTS and budget == 200:
                current = []
                began = perf_counter()
                for row in rows:
                    if mcts_seconds + perf_counter() - began >= mcts_limit_s:
                        print(f"MCTS-200 STOPPED: prior {mcts_seconds:.3f}s + partial "
                              f"{perf_counter()-began:.3f}s; {len(current)}/{len(rows)} queries. "
                              "Incomplete budget omitted from table.", flush=True)
                        current = []
                        break
                    current.extend(evaluate([row], {method: retriever}, budget))
            else:
                current = evaluate(rows, {method: retriever}, budget)
            if not current:
                continue
            records.extend(current)
            elapsed = sum(r["latency_s"] for r in current)
            if method == FULL_MCTS:
                mcts_seconds += elapsed
                measured[budget] = elapsed
            print(f"SWEEP budget={budget} method={method} queries={len(current)} "
                  f"retrieval_total_s={elapsed:.3f}" + (" (reused identical run)" if reused else ""), flush=True)
    return records


def print_sweep(records: list[dict], methods: list[str], budgets=SWEEP_BUDGETS) -> None:
    print("\nDEV budget sweep: cells = hit rate / mean nodes returned", flush=True)
    print("| Method | " + " | ".join(str(b) for b in budgets) + " |", flush=True)
    print("|---|" + "---:|" * len(budgets), flush=True)
    for method in methods:
        cells = []
        for budget in budgets:
            rows = [r for r in records if r["method"] == method and r["node_budget"] == budget]
            cells.append(f"{fmean(r['hit'] for r in rows):.4f} / {fmean(r['nodes_returned'] for r in rows):.2f}" if rows else "not run")
        print(f"| {method} | " + " | ".join(cells) + " |", flush=True)


def print_comparison_table(records, methods, budget, query_type=None):
    selected = [r for r in records if query_type is None or r["type"] == query_type]
    n = len({r["id"] for r in selected})
    print(f"\nCOMPARISON budget={budget} type={query_type or 'all'} queries={n}", flush=True)
    print("| Method | Hit rate | Recall | Path coverage | Nodes | Nodes-to-hit (hits only) | Hit count | Precision-at-hit | Latency s |", flush=True)
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|", flush=True)
    for method in methods:
        s = summarize([r for r in selected if r["method"] == method])
        hit = f"{100*s['hit']:.2f}% ({s['hit_count']}/{n})"
        values = ["—" if s[k] is None else str(s[k]) if k == "hit_count" else f"{s[k]:.6f}"
                  for k in ("gold_recall", "path_coverage", "nodes_returned", "nodes_to_hit",
                            "hit_count", "precision_at_hit", "latency_s")]
        print(f"| {method} | {hit} | " + " | ".join(values) + " |", flush=True)


def run_comparison(rows, methods):
    """Console-only experiment. Gold remains inside evaluate/metrics."""
    records, wall = [], {}
    for name in NEW_BASELINES:
        print(f"SETUP method={name} wall_s={methods[name].setup_latency_s:.6f}", flush=True)
    for budget in (20, 40):
        current = []
        for name, retriever in methods.items():
            began = perf_counter()
            current.extend(evaluate(rows, {name: retriever}, budget))
            wall[name, budget] = perf_counter()-began
            print(f"RUN method={name} budget={budget} queries={len(rows)} wall_s={wall[name,budget]:.6f}", flush=True)
        records.extend(current)
        print_comparison_table(current, methods, budget)
        if budget == 40:
            for query_type in ("explicit", "indirect"):
                print_comparison_table(current, methods, budget, query_type)
    print("\nNew-method wall seconds: setup is separate, query totals include metrics/harness; shared fit/load excluded.", flush=True)
    print("| Method | Setup s | Budget 20 / all queries s | Budget 40 / all queries s |", flush=True)
    print("|---|---:|---:|---:|", flush=True)
    for name in NEW_BASELINES:
        print(f"| {name} | {methods[name].setup_latency_s:.6f} | {wall[name,20]:.6f} | {wall[name,40]:.6f} |", flush=True)
    for budget in (20, 40):
        selected = [r for r in records if r["node_budget"] == budget]
        base = summarize([r for r in selected if r["method"] == "egpot_full"])
        matches = []
        for method in methods:
            if method == "egpot_full":
                continue
            s = summarize([r for r in selected if r["method"] == method])
            if s["hit"] >= base["hit"]:
                matches.append(f"{method} ({s['hit_count']}/{len(rows)})")
        print(f"MATCHES_OR_BEATS budget={budget} egpot_full={base['hit_count']}/{len(rows)}: " + "; ".join(matches), flush=True)
    selected = [r for r in records if r["node_budget"] == 40 and r["type"] == "indirect"]
    count = len({r["id"] for r in selected})
    base = summarize([r for r in selected if r["method"] == "egpot_full"])
    beats = []
    for method in methods:
        s = summarize([r for r in selected if r["method"] == method])
        if s["hit"] > base["hit"]:
            beats.append(f"{method} ({s['hit_count']}/{count})")
    print(f"BEATS_INDIRECT budget=40 egpot_full={base['hit_count']}/{count}: " + "; ".join(beats), flush=True)
    return records, wall


def run_fairness(rows, view, scorer):
    """Three DEV-only experiments, with an in-memory cache and console tables."""
    ids = {(r["query"], r["start_node"]): r["id"] for r in rows}
    methods = make_fairness_retrievers(view, scorer, seed=0, query_ids=ids)
    cache = {}

    def run(name, budget, seed=0, registry=None):
        key = (name, budget, seed)
        if key not in cache:
            began = perf_counter()
            registry = methods if registry is None else registry
            cache[key] = evaluate(rows, {name: registry[name]}, budget)
            print(f"FAIRNESS_RUN method={name} budget={budget} seed={seed} "
                  f"queries={len(rows)} wall_s={perf_counter()-began:.6f}", flush=True)
        return cache[key]

    def summary(name, budget, seed=0):
        return summarize(cache[name, budget, seed])

    n = len(rows)
    budgets = list(FAIRNESS_BUDGETS)
    for budget in budgets:
        for name in FAIRNESS_METHODS:
            run(name, budget)
    matched = matched_node_budget(cache["egpot_full", 40, 0])
    if matched not in budgets:
        budgets = sorted([*budgets, matched])
        for name in FAIRNESS_METHODS:
            run(name, matched)

    print("\nEXPERIMENT 1A: hit rates (successful queries / all queries)", flush=True)
    print("| Method | " + " | ".join(map(str, budgets)) + " |", flush=True)
    print("|---|" + "---:|"*len(budgets), flush=True)
    for name in FAIRNESS_METHODS:
        print("| " + name + " | " + " | ".join(f"{summary(name,b)['hit_count']}/{n}" for b in budgets) + " |", flush=True)
    print("\nEXPERIMENT 1B: mean nodes returned", flush=True)
    print("| Method | " + " | ".join(map(str, budgets)) + " |", flush=True)
    print("|---|" + "---:|"*len(budgets), flush=True)
    for name in FAIRNESS_METHODS:
        print("| " + name + " | " + " | ".join(f"{summary(name,b)['nodes_returned']:.6f}" for b in budgets) + " |", flush=True)
    print("\nEXPERIMENT 1C: first listed budget meeting the hit threshold", flush=True)
    print(f"| Method | >= {n-1}/{n} | {n}/{n} |", flush=True)
    print("|---|---:|---:|", flush=True)
    for name in FAIRNESS_METHODS:
        first = [next((b for b in budgets if summary(name,b)["hit_count"] >= target), "never") for target in (n-1, n)]
        print(f"| {name} | {first[0]} | {first[1]} |", flush=True)
    print("\nEXPERIMENT 1D: budget 40, nodes-to-hit excludes misses", flush=True)
    print("| Method | Mean nodes-to-hit | Hit count |", flush=True)
    print("|---|---:|---:|", flush=True)
    for name in FAIRNESS_METHODS:
        s = summary(name,40)
        value = "—" if s["nodes_to_hit"] is None else f"{s['nodes_to_hit']:.6f}"
        print(f"| {name} | {value} | {s['hit_count']}/{n} |", flush=True)
    reference = summary("egpot_full",40)
    print(f"\nEXPERIMENT 1E: M=round({reference['nodes_returned']:.6f})={matched}; "
          f"reference egpot_full@40={reference['hit_count']}/{n}", flush=True)
    print("| Method at cap M | Hit | Mean nodes returned |", flush=True)
    print("|---|---:|---:|", flush=True)
    matching = []
    for name in FAIRNESS_METHODS:
        s = summary(name,matched)
        print(f"| {name} | {s['hit_count']}/{n} | {s['nodes_returned']:.6f} |", flush=True)
        if s["hit_count"] >= reference["hit_count"]:
            matching.append(name)
    print("MATCHED_MEETS_EGPOT40_REFERENCE: " + ", ".join(matching), flush=True)

    for budget in (20,40):
        for normal, off in CHOKE_PAIRS:
            run(normal,budget)
            run(off,budget)
        print(f"\nEXPERIMENT 2: budget={budget}; delta=OFF minus ON in successful queries", flush=True)
        print("| Normal / OFF variant | ON hit | OFF hit | ON nodes | OFF nodes | Delta queries |", flush=True)
        print("|---|---:|---:|---:|---:|---:|", flush=True)
        for normal, off in CHOKE_PAIRS:
            a,b = summary(normal,budget),summary(off,budget)
            print(f"| {normal} / {off} | {a['hit_count']}/{n} | {b['hit_count']}/{n} | "
                  f"{a['nodes_returned']:.6f} | {b['nodes_returned']:.6f} | {b['hit_count']-a['hit_count']:+d} |", flush=True)

    deterministic = [name for name in methods if name not in STOCHASTIC_METHODS and name != "mcts_standard_no_choke"]
    print("\nEXPERIMENT 3: deterministic methods are seed-independent (not rerun): " + ", ".join(deterministic), flush=True)
    seed_summaries = {}
    for seed in range(5):
        registry = methods if seed == 0 else {
            "mcts_standard": StandardMCTS(view, scorer, seed=seed, query_ids=ids),
            "egpot_full_mcts": EGPOTRetriever(EGPOTConfig(use_mcts=True, seed=seed), view, scorer),
            "egpot_no_pareto_mcts": EGPOTRetriever(EGPOTConfig(use_mcts=True, use_pareto=False, seed=seed), view, scorer),
        }
        for budget in (20,40):
            for name in STOCHASTIC_METHODS:
                records = run(name,budget,seed,registry)
                seed_summaries[name,budget,seed] = summarize(records)
    print("\nEXPERIMENT 3A: per-seed results", flush=True)
    print("| Method | Budget | Seed | Hit | Mean nodes returned |", flush=True)
    print("|---|---:|---:|---:|---:|", flush=True)
    for name in STOCHASTIC_METHODS:
        for budget in (20,40):
            for seed in range(5):
                s = seed_summaries[name,budget,seed]
                print(f"| {name} | {budget} | {seed} | {s['hit_count']}/{n} | {s['nodes_returned']:.6f} |", flush=True)
    print("\nEXPERIMENT 3B: across seeds; fractional mean hits are averages of query counts", flush=True)
    print("| Method | Budget | Mean hits | Min hits | Max hits | Mean nodes | Min nodes | Max nodes |", flush=True)
    print("|---|---:|---:|---:|---:|---:|---:|---:|", flush=True)
    for name in STOCHASTIC_METHODS:
        for budget in (20,40):
            values = [seed_summaries[name,budget,seed] for seed in range(5)]
            hits,nodes = [s["hit_count"] for s in values],[s["nodes_returned"] for s in values]
            print(f"| {name} | {budget} | {fmean(hits):.6f}/{n} | {min(hits)}/{n} | {max(hits)}/{n} | "
                  f"{fmean(nodes):.6f} | {min(nodes):.6f} | {max(nodes):.6f} |", flush=True)
    return cache


def sample_dirichlet_weights(seed=0, count=50):
    """Round Dirichlet(1,1,1,1) draws to four places, then renormalize."""
    if type(count) is not int or count < 1:
        raise ValueError("count must be a positive integer")
    draws = np.round(np.random.RandomState(seed).dirichlet(np.ones(4), size=count), 4)
    normalized = draws / draws.sum(axis=1, keepdims=True)
    result = [tuple(float(v) for v in row) for row in normalized]
    for vector in result:
        EGPOTConfig(weights=vector)
    return result


def weight_experiment_vectors():
    vectors = {f"emphasis_{name}": tuple(.7 if i == j else .1 for i in range(4))
               for j, name in enumerate(("relevance", "hop", "contract", "entropy"))}
    vectors.update({f"dirichlet_{i+1:02d}": vector
                    for i, vector in enumerate(sample_dirichlet_weights())})
    vectors["equal"] = (.25, .25, .25, .25)
    for vector in vectors.values():
        EGPOTConfig(weights=vector)
    return vectors


def weight_distribution(records, names, pareto_records, query_type=None):
    """Summarize hit *counts*, using the existing per-query metric records."""
    selected = [r for r in records if query_type is None or r["type"] == query_type]
    reference = [r for r in pareto_records if query_type is None or r["type"] == query_type]
    counts = [sum(r["hit"] for r in selected if r["method"] == name) for name in names]
    if not counts or not reference:
        raise ValueError("distribution requires vectors and reference query records")
    quartiles = np.percentile(counts, [0, 25, 50, 75, 100], method="linear")
    pareto = sum(r["hit"] for r in reference)
    return {"vectors": len(counts), "queries": len(reference), "pareto": pareto,
            "min": float(quartiles[0]), "q25": float(quartiles[1]),
            "median": float(quartiles[2]), "q75": float(quartiles[3]), "max": float(quartiles[4]),
            "mean": fmean(counts), "below": sum(n < pareto for n in counts),
            "equal": sum(n == pareto for n in counts), "above": sum(n > pareto for n in counts)}


class _CandidateAuditEGPOT(_SharedScorerEGPOT):
    """Observe all candidate IDs before the normal trace's display truncation.

    This audit does not receive gold IDs and runs after candidate selection.
    It prevents 'never a candidate' from meaning merely omitted by the normal
    sixty-candidate display cap. Normal traversal and returned traces remain
    unchanged; the complete first-round map is separate observational state.
    """

    def __init__(self, config, view, scorer):
        super().__init__(config, view, scorer)
        self.first_candidate_round = {}

    def _trace_round(self, beam_before, candidates, vectors, details, selected,
                     new_nodes, collected_size, round_number):
        for candidate in candidates:
            self.first_candidate_round.setdefault(candidate.to_node, round_number)
        return super()._trace_round(beam_before, candidates, vectors, details, selected,
                                    new_nodes, collected_size, round_number)


class CandidateAuditRetriever(EGPOTRetriever):
    """EG-POT with observational candidate auditing when trace is supplied."""

    def __init__(self, config, graph_view, scorer):
        super().__init__(config, graph_view, scorer)
        self.engine = _CandidateAuditEGPOT(self.config, self.graph_view, self.scorer)

    def retrieve(self, query, start_node, node_budget, trace=None):
        self.engine.first_candidate_round.clear()
        return super().retrieve(query, start_node, node_budget, trace=trace)


def run_weight_misses(rows, view, scorer):
    methods = {
        "egpot_full": CandidateAuditRetriever(EGPOTConfig(use_mcts=False), view, scorer),
        "egpot_no_pareto": CandidateAuditRetriever(EGPOTConfig(use_mcts=False, use_pareto=False), view, scorer),
        "scalar_beam": ScalarBeam(view, scorer), "ppr": PersonalizedPageRank(view, scorer),
    }
    print("\nEXPERIMENT B: misses at budget 20, no MCTS. Candidate audit observes every candidate before display truncation.", flush=True)
    misses = []
    for name, retriever in methods.items():
        count = 0
        for row in sorted(rows, key=lambda r: r["id"]):
            trace = {} if isinstance(retriever, CandidateAuditRetriever) else None
            # Same gold-free query/start/budget boundary as evaluate().
            result = retriever.retrieve(row["query"], row["start_node"], 20, trace=trace)
            missing = sorted(set(row["gold_nodes"]) - result.visited)
            if not missing:
                continue
            count += 1
            audit = dict(retriever.engine.first_candidate_round) if trace is not None else {}
            print(f"MISS method={name} query_id={row['id']} query={row['query']}", flush=True)
            appearances = {node: audit.get(node) for node in missing}
            for node in missing:
                note = ("round " + str(appearances[node]) if appearances[node] is not None else "never a candidate") if trace is not None else "not applicable (not EG-POT)"
                print(f"  missing={node} first_candidate={note}", flush=True)
            misses.append({"method": name, "query_id": row["id"], "query": row["query"],
                           "missing": missing, "first_candidate": appearances if trace is not None else None})
        print(f"MISS_COUNT method={name} queries={count}/{len(rows)}", flush=True)
    return misses


def run_weights(rows, view, scorer):
    print("\nWEIGHT DISTRIBUTION STUDY ONLY: no best vector will be selected or saved for later use.", flush=True)
    print("Count clarification: 4 emphasized + 50 Dirichlet = 54 study vectors; equal weights is a separate control, 55 evaluated total.", flush=True)
    print("Both 54-vector and inclusive 55-vector summaries are reported; extremes use the 54-vector study pool.", flush=True)
    print("Dirichlet: RandomState(seed=0), alpha=(1,1,1,1), round to four decimals before renormalizing. Printed weights use ten decimals.", flush=True)
    print("Quantiles use NumPy's linear percentile interpolation. Table sorted by budget-20 hits, then budget-10 hits, then ID.", flush=True)
    vectors = weight_experiment_vectors()
    records, references = {}, {}
    for budget in (10,20):
        references[budget] = evaluate(rows, {"pareto": EGPOTRetriever(EGPOTConfig(use_mcts=False), view, scorer)}, budget)
        for name, vector in vectors.items():
            began = perf_counter()
            records[name,budget] = evaluate(rows, {name: EGPOTRetriever(
                EGPOTConfig(use_mcts=False, use_pareto=False, weights=vector), view, scorer)}, budget)
            print(f"WEIGHT_RUN id={name} budget={budget} wall_s={perf_counter()-began:.6f}", flush=True)

    def hits(name,budget):
        return sum(r["hit"] for r in records[name,budget])

    def weight_text(name):
        return "(" + ",".join(f"{v:.10f}" for v in vectors[name]) + ")"

    print("\nEXPERIMENT A1: every vector; order = relevance, hop, contract, entropy", flush=True)
    print("| ID | Effective weights | Hit@10 | Mean nodes@10 | Hit@20 | Mean nodes@20 |", flush=True)
    print("|---|---|---:|---:|---:|---:|", flush=True)
    for budget in (10,20):
        reference = summarize(references[budget])
        print(f"PARETO_REFERENCE budget={budget} hit={reference['hit_count']}/{len(rows)} mean_nodes={reference['nodes_returned']:.6f}", flush=True)
    for name in sorted(vectors, key=lambda name: (-hits(name,20), -hits(name,10), name)):
        print(f"| {name} | {weight_text(name)} | {hits(name,10)}/{len(rows)} | "
              f"{summarize(records[name,10])['nodes_returned']:.6f} | {hits(name,20)}/{len(rows)} | "
              f"{summarize(records[name,20])['nodes_returned']:.6f} |", flush=True)

    study = [name for name in vectors if name != "equal"]
    print("\nEXPERIMENT A2/A4: hit-count distributions, including type splits", flush=True)
    print("| Pool | Budget | Type | Queries | Vectors | Pareto hits | Min | Q25 | Median | Q75 | Max | Mean | Below | Equal | Above |", flush=True)
    print("|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|", flush=True)
    summaries = []
    for pool,names in (("study", study), ("inclusive_equal", list(vectors))):
        for budget in (10,20):
            combined = [r for name in names for r in records[name,budget]]
            for query_type in (None,"explicit","indirect"):
                s = weight_distribution(combined,names,references[budget],query_type)
                summaries.append({"pool":pool,"budget":budget,"type":query_type or "all",**s})
                values = [f"{s[key]:.6f}" for key in ("min","q25","median","q75","max","mean")]
                print(f"| {pool} | {budget} | {query_type or 'all'} | {s['queries']} | {s['vectors']} | {s['pareto']} | "
                      + " | ".join(values) + f" | {s['below']} | {s['equal']} | {s['above']} |", flush=True)
    print("\nEXPERIMENT A3: five highest/lowest study vectors at each budget; hit ties ordered by ID only, for reporting.", flush=True)
    print("| Budget | Group | ID | Effective weights | Hit |", flush=True)
    print("|---:|---|---|---|---:|", flush=True)
    for budget in (10,20):
        best = sorted(study, key=lambda name: (-hits(name,budget), name))[:5]
        worst = sorted(study, key=lambda name: (hits(name,budget), name))[:5]
        for group,names in (("highest",best),("lowest",worst)):
            for name in names:
                print(f"| {budget} | {group} | {name} | {weight_text(name)} | {hits(name,budget)}/{len(rows)} |", flush=True)
    misses = run_weight_misses(rows,view,scorer)
    return vectors,records,summaries,misses


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, default=ROOT / "bench/results/online_boutique_graph_fresh.graphml")
    parser.add_argument("--queries", type=Path, default=ROOT / "bench/labels/online_boutique_egpot_queries.json")
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    parser.add_argument("--confirm-test", action="store_true")
    parser.add_argument("--mode", choices=("all", "ablations", "sweep", "comparison", "fairness", "weights"), default="all")
    args = parser.parse_args(argv)
    if args.split == "test" and not args.confirm_test:
        parser.error("--split test requires --confirm-test; no test data was evaluated")
    if args.mode in {"fairness", "weights"} and args.split != "dev":
        parser.error(f"{args.mode} experiments are DEV only; no test queries were evaluated")
    graph = nx.read_graphml(args.graph, force_multigraph=True)
    with args.queries.open(encoding="utf-8") as stream:
        rows = json.load(stream)
    if len(rows) != 30 or {r["link_id"] for r in rows} != set(range(1, 16)):
        parser.error("expected 30 query rows covering link IDs 1 through 15")
    if len({r["id"] for r in rows}) != len(rows):
        parser.error("query IDs must be unique")
    for link in range(1, 16):
        if sorted(r["type"] for r in rows if r["link_id"] == link) != ["explicit", "indirect"]:
            parser.error(f"link {link} requires one explicit and one indirect query")
    for row in rows:
        if any(n not in graph for n in [row["start_node"], *row["gold_nodes"], *row["gold_path"]]):
            parser.error(f"{row['id']} references a missing exact graph node ID")
    splits = split_by_link(rows)
    for split, tasks in splits.items():
        print(f"{split.upper()} links: {sorted({r['link_id'] for r in tasks})}")
    print(f"Evaluating {args.split.upper()} ONLY. RPC choke-point rule: ON except explicit no_choke_point ablations.")
    print("One shared GraphView and one QueryScorer fit. Fit/load excluded from latency; per-call engine caches reset.")
    print("VectorTopK reserves start but discovery_order ranks it with the selected nodes; others discover start first.")
    print("Nodes-to-hit and precision-at-hit means exclude misses; hit counts are shown. " +
          ("Fairness experiments 1/2 use seed 0; experiment 3 uses seeds 0 through 4." if args.mode == "fairness" else "All seeds=0."))
    view = GraphView(graph, use_choke_point=True)
    scorer = QueryScorer(view)
    if args.mode == "weights":
        run_weights(splits["dev"],view,scorer)
        return 0
    if args.mode == "fairness":
        print("Identical seed-0 runs are reused across experiments, with in-memory records only.")
        print("No-choke variants share one OFF view and the original scorer; default retrievers remain ON.")
        print("Only stochastic engines receive changed seeds. M uses Python round(mean nodes), including ties-to-even.")
        run_fairness(splits["dev"], view, scorer)
        return 0
    if args.mode == "comparison":
        tasks = splits[args.split]
        query_ids = {(r["query"], r["start_node"]): r["id"] for r in tasks}
        print("Comparison uses the requested fourteen named methods; every new graph method has choke-point ON.")
        print("PPR transitions follow allowed traversal moves, weighted by parallel-edge multiplicity; query ignored.")
        print("VectorBFS seeds are start union the literal global top three; small budgets cap seeds first.")
        print("Community partition uses undirected, unweighted simple adjacency; setup/partition cost reported separately.")
        print("ScalarBeam is width four, path-score sum; StandardMCTS uses query-ID/start seeds and ranks tree occurrences before deduplication.")
        methods = make_comparison_retrievers(view, scorer, query_ids=query_ids)
        run_comparison(tasks, methods)
        return 0
    ablations = make_ablations(view, scorer)
    cached = {}
    if args.mode in {"all", "ablations"}:
        for budget in (20, 40):
            records = []
            for method, retriever in ablations.items():
                current = evaluate(splits[args.split], {method: retriever}, budget)
                cached[method, budget] = current
                records.extend(current)
                print(f"ABLATION budget={budget} method={method} retrieval_total_s="
                      f"{sum(r['latency_s'] for r in current):.3f}", flush=True)
            print_table(records, list(ablations), budget)
            if budget == 40:
                for kind in ("explicit", "indirect"):
                    print_table(records, list(ablations), budget, kind)
    if args.mode in {"all", "sweep"}:
        methods = {FULL_PLAIN: ablations[FULL_PLAIN], FULL_MCTS: ablations[FULL_MCTS],
                   "VectorTopK": VectorTopK(view, scorer), "BFS": BFS(view, scorer)}
        records = run_budget_sweep(splits[args.split], methods, cached=cached)
        print_sweep(records, list(methods))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
