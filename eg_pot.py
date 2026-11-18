"""EG-POT objectives and deterministic beam search over raw code graphs."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
import hashlib
import json
import math
from numbers import Real
import random
import re
from typing import Any, Hashable, Iterable

import networkx as nx
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class EGPOTConfig:
    """Search settings (counts are positive; scores/discounts are in [0, 1]).

    Defaults: select at most 40 nodes, retain a beam of 4, and perform 16
    rollouts of depth 3. Discount hop efficiency by 0.8 per hop. Contract
    matches score 1.0; mismatches score 0.6 (not a subtraction of 0.6).
    Seed 0 provides reproducibility. All four algorithm components are enabled.
    Weighted-sum ablation uses equal objective weights (0.25 each) by default.
    Lookahead blends at weight 0.5, samples with temperature 0.5, and limits
    simulated choices to the best 8 edges at each step.
    """

    node_budget: int = 40
    beam_width: int = 4
    mcts_rollouts: int = 16
    rollout_depth: int = 3
    hop_gamma: float = 0.8
    contract_match_score: float = 1.0
    contract_mismatch_penalty: float = 0.6
    seed: int = 0
    use_pareto: bool = True
    use_entropy: bool = True
    use_contracts: bool = True
    use_mcts: bool = True
    weights: tuple[float, float, float, float] = (0.25, 0.25, 0.25, 0.25)
    lookahead_weight: float = 0.5
    rollout_temperature: float = 0.5
    max_rollout_branching: int = 8

    def __post_init__(self) -> None:
        for name in ("node_budget", "beam_width", "mcts_rollouts", "rollout_depth",
                     "max_rollout_branching"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("seed must be a nonnegative integer")
        for name in ("hop_gamma", "contract_match_score", "contract_mismatch_penalty",
                     "lookahead_weight"):
            value = getattr(self, name)
            if (isinstance(value, bool) or not isinstance(value, Real)
                    or not math.isfinite(value) or not 0 <= value <= 1):
                raise ValueError(f"{name} must be a finite number in [0, 1]")
        temperature = self.rollout_temperature
        if (isinstance(temperature, bool) or not isinstance(temperature, Real)
                or not math.isfinite(temperature) or temperature <= 0):
            raise ValueError("rollout_temperature must be a finite positive number")
        if self.contract_mismatch_penalty > self.contract_match_score:
            raise ValueError("contract mismatch score must not exceed match score")
        for name in ("use_pareto", "use_entropy", "use_contracts", "use_mcts"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be a boolean")
        if (not isinstance(self.weights, (tuple, list)) or len(self.weights) != 4
                or any(isinstance(w, bool) or not isinstance(w, Real)
                       or not math.isfinite(w) or w < 0 for w in self.weights)
                or not math.isclose(sum(self.weights), 1.0, rel_tol=0, abs_tol=1e-9)):
            raise ValueError("weights must contain four finite nonnegative values summing to 1")
        self.weights = tuple(self.weights)


def _sort_id(value: Hashable) -> tuple[str, str]:
    """Sort raw string IDs and NetworkX integer keys without comparing types."""
    return type(value).__name__, str(value)


@dataclass(frozen=True)
class EdgePolicy:
    """Relation eligibility for traversal, contract scoring, and entropy."""

    excluded_relations: frozenset[str] = frozenset()
    no_contract_match_relations: frozenset[str] = frozenset()
    entropy_over_eligible_only: bool = False


LEGACY = EdgePolicy()
CURRENT_V1 = EdgePolicy(
    excluded_relations=frozenset({"DECLARES_FIELD", "EVALUATES"}),
    no_contract_match_relations=frozenset({
        "ACCEPTS_SCHEMA", "RETURNS_SCHEMA", "INVOKES", "POSSIBLE_HTTP_TARGET",
    }),
    entropy_over_eligible_only=True,
)


class GraphView:
    """Read-only access to a raw graph; graph mutations require a new scorer.

    Set ``use_choke_point=False`` to allow backward DEFINES_RPC expansion.
    """

    def __init__(self, graph: nx.MultiDiGraph, use_choke_point: bool = True,
                 *, edge_policy: EdgePolicy = LEGACY):
        if not isinstance(graph, nx.MultiDiGraph):
            raise TypeError("graph must be a networkx.MultiDiGraph")
        self.graph = graph
        self.use_choke_point = use_choke_point
        self.edge_policy = edge_policy

    def entropy_denominator(self) -> float:
        relations = {data.get("relation", "LINK") for _, _, data in self.graph.edges(data=True)}
        if self.edge_policy.entropy_over_eligible_only:
            relations.difference_update(self.edge_policy.excluded_relations)
        return math.log(len(relations)) if len(relations) > 1 else 0.0

    def node_type(self, n: Hashable) -> str:
        return str(self.graph.nodes[n].get("type") or "")

    def node_text(self, n: Hashable) -> str:
        """Name, docstring, file and first 150 code characters for similarity."""
        data = self.graph.nodes[n]
        return " ".join(str(data.get(key) or "") for key in
                        ("name", "docstring", "file")) + " " + str(data.get("code") or "")[:150]

    def edge_meta(self, u: Hashable, v: Hashable, key: Hashable) -> dict[str, Any]:
        """Normalize flattened or nested metadata, including GraphML strings.

        Flattened fields take precedence. Malformed/nonfinite numbers fall
        back to defaults, as do absent values. Return a fresh dictionary.
        """
        data = self.graph.edges[u, v, key]
        nested = data.get("metadata", {})
        if isinstance(nested, str):
            try:
                nested = ast.literal_eval(nested)
            except (ValueError, SyntaxError):
                nested = {}
        if not isinstance(nested, dict):
            nested = {}

        def number(name: str, default: float) -> float:
            try:
                value = float(data.get(name, nested.get(name, default)))
                return value if math.isfinite(value) else default
            except (ValueError, TypeError, OverflowError):
                return default

        ctx = data.get("id_ctx", nested.get("id_ctx", ""))
        return {"c_type": number("c_type", 1.0),
                "f_call": number("f_call", 1.0),
                "d_scope": int(number("d_scope", 0)),
                "id_ctx": str(ctx) if ctx is not None else ""}

    def neighbors(self, n: Hashable) -> list[tuple[Hashable, str, str, Hashable]]:
        """Both directed incidences, preserving parallel edges, in sorted order."""
        result = []
        excluded = self.edge_policy.excluded_relations
        for _, v, key, data in self.graph.out_edges(n, keys=True, data=True):
            relation = data.get("relation", "LINK")
            if relation not in excluded:
                result.append((v, relation, "out", key))
        for u, _, key, data in self.graph.in_edges(n, keys=True, data=True):
            relation = data.get("relation", "LINK")
            if relation in excluded:
                continue
            # Mirror traversal.py: only incoming DEFINES_RPC at rpc_contract.
            if (self.use_choke_point and relation == "DEFINES_RPC"
                    and self.node_type(n) == "rpc_contract"):
                continue
            result.append((u, relation, "in", key))
        return sorted(result, key=lambda item: (
            _sort_id(item[0]), str(item[1]), item[2], _sort_id(item[3])))


def normalize_text(text: str) -> str:
    """Split identifiers and digit boundaries, lowercase, then lightly singularize.

    Camel/Pascal case (including acronym-to-word boundaries) is split before
    lowercasing. Punctuation, underscores and path separators delimit words;
    digit runs remain separate tokens. Trailing 'ies' becomes 'y'; otherwise
    one trailing 's' is removed only for words longer than three characters.
    No additional stemming or vocabulary-specific substitutions are applied.
    """
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    words = re.findall(r"[^\W\d_]+|\d+", text.lower())
    return " ".join(word[:-3] + "y" if word.endswith("ies") else
                    word[:-1] if len(word) > 3 and word.endswith("s") else word
                    for word in words)


class QueryScorer:
    """Fit a deterministic TF-IDF snapshot once; cache vectors by query text.

    Uses CKGBuilder's English stop words and word unigram/bigram settings.
    Both node and query text pass through normalize_text before vectorization.
    Empty graphs or vocabularies and out-of-vocabulary queries score zero.
    Unknown node IDs raise KeyError. score_many returns an ID-to-score dict.
    """

    def __init__(self, graph_view: GraphView):
        self.graph_view = graph_view
        self.node_ids = sorted(graph_view.graph.nodes, key=_sort_id)
        self._rows = {node: i for i, node in enumerate(self.node_ids)}
        self.vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        self.matrix = None
        self._query_vectors: dict[str, Any] = {}
        if self.node_ids:
            try:
                self.matrix = self.vectorizer.fit_transform(
                    [normalize_text(graph_view.node_text(node)) for node in self.node_ids])
            except ValueError as exc:
                if "empty vocabulary" not in str(exc):
                    raise

    def score(self, query: str, node_id: Hashable) -> float:
        return self.score_many(query, [node_id])[node_id]

    def score_many(self, query: str, node_ids: Iterable[Hashable]) -> dict[Hashable, float]:
        nodes = list(node_ids)
        rows = [self._rows[node] for node in nodes]
        if self.matrix is None or not nodes:
            return {node: 0.0 for node in nodes}
        if query not in self._query_vectors:
            self._query_vectors[query] = self.vectorizer.transform([normalize_text(query)])
        scores = cosine_similarity(self._query_vectors[query], self.matrix[rows]).ravel()
        return {node: max(0.0, min(1.0, float(score)))
                for node, score in zip(nodes, scores)}


@dataclass
class CandidateStep:
    """Traversal-oriented endpoints; direction identifies the raw edge orientation."""

    from_node: Hashable
    to_node: Hashable
    relation: str
    direction: str
    edge_key: Hashable
    layer: str


@dataclass
class PathState:
    """An independent path snapshot; extend copies every mutable collection.

    Edges record traversal order, including when walking a raw edge backward.
    """

    ordered_nodes: list[Hashable] = field(default_factory=list)
    edges: list[tuple[Hashable, str, Hashable]] = field(default_factory=list)
    hops_from_start: dict[Hashable, int] = field(default_factory=dict)
    relation_counts: dict[str, int] = field(default_factory=dict)
    visited: set[Hashable] = field(default_factory=set)

    def extend(self, candidate: CandidateStep) -> PathState:
        if candidate.from_node not in self.visited:
            raise ValueError("candidate source must be visited")
        if candidate.to_node in self.visited:
            raise ValueError("candidate target must be unvisited")
        hops = dict(self.hops_from_start)
        hops[candidate.to_node] = hops[candidate.from_node] + 1
        counts = dict(self.relation_counts)
        counts[candidate.relation] = counts.get(candidate.relation, 0) + 1
        return PathState(
            self.ordered_nodes + [candidate.to_node],
            self.edges + [(candidate.from_node, candidate.relation, candidate.to_node)],
            hops, counts, self.visited | {candidate.to_node})


def dominates(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    """True iff a >= b on every objective and a > b on at least one."""
    if len(a) != len(b):
        raise ValueError("objective vectors must have equal dimensions")
    return all(x >= y for x, y in zip(a, b)) and any(x > y for x, y in zip(a, b))


def non_dominated_sort(vectors: list[tuple[float, ...]]) -> list[list[int]]:
    """NSGA-II non-dominated fronts, with stable ascending indices per front."""
    successors = [[] for _ in vectors]
    incoming = [0] * len(vectors)
    for i in range(len(vectors)):
        for j in range(i + 1, len(vectors)):
            if dominates(vectors[i], vectors[j]):
                successors[i].append(j)
                incoming[j] += 1
            elif dominates(vectors[j], vectors[i]):
                successors[j].append(i)
                incoming[i] += 1
    front = [i for i, count in enumerate(incoming) if count == 0]
    fronts = []
    while front:
        fronts.append(front)
        following = []
        for i in front:
            for j in successors[i]:
                incoming[j] -= 1
                if incoming[j] == 0:
                    following.append(j)
        front = sorted(following)
    return fronts


@dataclass
class PathResult:
    """Collected node union plus the best single path as secondary evidence.

    Edges and objective_log describe ordered_path, not the entire union.
    """

    ordered_path: list[Hashable] = field(default_factory=list)
    visited: set[Hashable] = field(default_factory=set)
    edges: list[tuple[Hashable, str, Hashable]] = field(default_factory=list)
    objective_log: list[dict[str, Any]] = field(default_factory=list)
    visited_order: list[Hashable] = field(default_factory=list)


class EGPOT:
    """Four-objective beam traversal; fitted graph snapshot must remain unchanged."""

    def __init__(self, graph: nx.MultiDiGraph, config: EGPOTConfig | None = None,
                 *, edge_policy: EdgePolicy = LEGACY):
        self.config = config if config is not None else EGPOTConfig()
        self.graph_view = GraphView(graph, edge_policy=edge_policy)
        self.scorer = QueryScorer(self.graph_view)
        self._entropy_denominator = self.graph_view.entropy_denominator()
        self._relevance_cache: dict[str, dict[Hashable, float]] = {}
        self._neighbor_cache: dict[str, dict[tuple, tuple[CandidateStep, ...]]] = {}

    def semantic_relevance(self, query: str, candidate_node: Hashable) -> float:
        """QueryScorer.score(query, candidate_node), cosine relevance in [0, 1]."""
        if query not in self._relevance_cache:
            self._relevance_cache[query] = self.scorer.score_many(query, self.scorer.node_ids)
        return self._relevance_cache[query][candidate_node]

    def hop_efficiency(self, hops: int) -> float:
        """config.hop_gamma ** hops, with hops from start to the candidate."""
        if type(hops) is not int or hops < 0:
            raise ValueError("hops must be a nonnegative integer")
        return float(self.config.hop_gamma ** hops)

    def contract_consistency(self, candidate_step: CandidateStep) -> float:
        """Match an eligible contract-layer edge or contract target type."""
        if candidate_step.relation in self.graph_view.edge_policy.no_contract_match_relations:
            return float(self.config.contract_mismatch_penalty)
        match = (candidate_step.layer == "Lcontract" or
                 self.graph_view.node_type(candidate_step.to_node) in {
                     "rpc_contract", "service_contract", "http_endpoint", "topic_contract"})
        return float(self.config.contract_match_score if match
                     else self.config.contract_mismatch_penalty)

    def entropy_gain(self, path_state: PathState, candidate_step: CandidateStep) -> float:
        """Variety times novelty: max(0, H(after)-H(before)) / ln(R),
        where H is Shannon entropy with natural logs, after adds the candidate
        relation, and R is the policy's graph-wide relation count. Novelty is
        1 / (1 + prior uses of that relation). For R <= 1 the gain is zero.
        """
        if not self._entropy_denominator:
            return 0.0

        def entropy(counts: dict[str, int]) -> float:
            total = sum(counts.values())
            return -math.fsum((count / total) * math.log(count / total)
                              for _, count in sorted(counts.items()) if count > 0) if total else 0.0

        counts = dict(path_state.relation_counts)
        used = counts.get(candidate_step.relation, 0)
        counts[candidate_step.relation] = used + 1
        variety = max(0.0, entropy(counts) - entropy(path_state.relation_counts))
        return min(1.0, variety / self._entropy_denominator / (1 + used))

    def objective_vector(self, query: str, path_state: PathState,
                         candidate_step: CandidateStep) -> tuple[float, float, float, float]:
        return (
            self.semantic_relevance(query, candidate_step.to_node),
            self.hop_efficiency(path_state.hops_from_start[candidate_step.from_node] + 1),
            self.contract_consistency(candidate_step) if self.config.use_contracts else 1.0,
            self.entropy_gain(path_state, candidate_step) if self.config.use_entropy else 0.0)

    def _candidate_steps(self, query: str, state: PathState) -> list[CandidateStep]:
        """Cache graph incidences per query; apply path-specific exclusions fresh."""
        current = state.ordered_nodes[-1]
        cache = self._neighbor_cache.setdefault(query, {})
        cache_key = (current, self.graph_view.use_choke_point)
        if cache_key not in cache:
            steps = []
            for neighbor, relation, direction, key in self.graph_view.neighbors(current):
                u, v = (current, neighbor) if direction == "out" else (neighbor, current)
                data = self.graph_view.graph.edges[u, v, key]
                steps.append(CandidateStep(current, neighbor, relation, direction, key,
                                           data.get("layer", "")))
            cache[cache_key] = tuple(steps)
        return [step for step in cache[cache_key] if step.to_node not in state.visited]

    def lookahead_vector(self, query: str, state: PathState,
                         candidate: CandidateStep, trace: dict | None = None) -> tuple[float, float, float, float]:
        """Average bounded softmax rollouts after applying the candidate.

        Only simulated edges contribute to returns: discount at simulated step
        i is hop_gamma ** i (i starts at zero). Divide by the full configured
        depth's maximum discounted sum, including for early dead ends, which
        contribute zero for unused steps. No simulated nodes enter collection.
        Each rollout has an independent Random seeded with config.seed plus a
        SHA-256 digest of the state's tip, candidate target and rollout index.
        """
        base = state.extend(candidate)
        totals = [0.0] * 4
        discounts = [self.config.hop_gamma ** i for i in range(self.config.rollout_depth)]
        denominator = math.fsum(discounts) * self.config.mcts_rollouts
        if trace is not None:
            trace.update(count=self.config.mcts_rollouts, samples=[])
        for rollout in range(self.config.mcts_rollouts):
            payload = json.dumps([str(state.ordered_nodes[-1]), str(candidate.to_node), rollout],
                                 ensure_ascii=True, separators=(",", ":")).encode("utf-8")
            seed = self.config.seed + int.from_bytes(hashlib.sha256(payload).digest(), "big")
            rng = random.Random(seed)
            simulated = base
            sample_return = [0.0] * 4 if trace is not None and rollout < 3 else None
            for discount in discounts:
                choices = self._candidate_steps(query, simulated)
                if not choices:
                    break
                scored = [(step, self.objective_vector(query, simulated, step)) for step in choices]
                scored.sort(key=lambda item: (
                    -sum(item[1]) / 4, str(item[0].to_node), str(item[0].from_node),
                    str(item[0].relation), item[0].direction, _sort_id(item[0].edge_key),
                    str(item[0].layer)))
                scored = scored[:self.config.max_rollout_branching]
                means = [sum(vector) / 4 for _, vector in scored]
                maximum = max(means)
                weights = [math.exp((mean - maximum) / self.config.rollout_temperature)
                           for mean in means]
                step, vector = rng.choices(scored, weights=weights, k=1)[0]
                for i, value in enumerate(vector):
                    totals[i] += discount * value
                    if sample_return is not None:
                        sample_return[i] += discount * value
                simulated = simulated.extend(step)
            if sample_return is not None:
                trace["samples"].append({
                    "nodes": list(simulated.ordered_nodes[len(state.ordered_nodes):]),
                    # Normalized per-rollout returns; their average is the
                    # lookahead vector. Early termination contributes zeros.
                    "return_vector": [max(0.0, min(1.0, v / math.fsum(discounts))) for v in sample_return]})
        return tuple(max(0.0, min(1.0, total / denominator)) for total in totals)

    def candidate_vector(self, query: str, state: PathState,
                         candidate: CandidateStep, trace: dict | None = None) -> tuple[float, float, float, float]:
        """Blend immediate and rollout vectors; disabled/zero weight skips simulation."""
        immediate = self.objective_vector(query, state, candidate)
        if trace is not None:
            trace.update(immediate_vector=list(immediate), lookahead_vector=None, rollouts=None)
        if not self.config.use_mcts or self.config.lookahead_weight == 0:
            if trace is not None:
                trace["final_vector"] = list(immediate)
            return immediate
        if trace is None:
            future = self.lookahead_vector(query, state, candidate)
        else:
            trace["rollouts"] = {}
            future = self.lookahead_vector(query, state, candidate, trace=trace["rollouts"])
            trace["lookahead_vector"] = list(future)
        weight = self.config.lookahead_weight
        result = tuple((1 - weight) * now + weight * later for now, later in zip(immediate, future))
        if trace is not None:
            trace["final_vector"] = list(result)
        return result

    def select_top(self, candidates: list[CandidateStep],
                   vectors: list[tuple[float, ...]], k: int, trace: dict | None = None) -> list[CandidateStep]:
        """Select fronts by mean then target ID; or weighted sum in the ablation.

        Remaining exact ties use source, relation, direction, key and layer,
        followed by stable input order for identical steps from different paths.
        """
        indices = self._select_top_indices(candidates, vectors, k)
        if trace is not None:
            trace["indices"] = indices
        return [candidates[i] for i in indices]

    def _select_top_indices(self, candidates: list[CandidateStep],
                            vectors: list[tuple[float, ...]], k: int) -> list[int]:
        if len(candidates) != len(vectors):
            raise ValueError("each candidate requires one objective vector")
        if type(k) is not int or k < 0:
            raise ValueError("k must be a nonnegative integer")

        def order(i: int) -> tuple:
            step, vector = candidates[i], vectors[i]
            score = (sum(vector) / len(vector) if self.config.use_pareto else
                     sum(w * value for w, value in zip(self.config.weights, vector)))
            return (-score, str(step.to_node), str(step.from_node), str(step.relation),
                    step.direction, _sort_id(step.edge_key), str(step.layer))

        fronts = non_dominated_sort(vectors) if self.config.use_pareto else [list(range(len(vectors)))]
        indices = [i for front in fronts for i in sorted(front, key=order)]
        return indices[:k]

    def _trace_round(self, beam_before, candidates, vectors, details, selected, new_nodes,
                     collected_size, round_number):
        """Bound a round to 60 candidates: all selected, then best remaining
        mean-final-vector scores, with deterministic node/edge/index tie breaks.
        Indexes are remapped to the stored list; empty filtered fronts retain
        their original front index. Configured export beams have width four.
        For beams selecting more than 60 distinct candidates, preserving every
        selection takes precedence over the display cap.
        """
        fronts = non_dominated_sort(vectors) if self.config.use_pareto else [list(range(len(vectors)))]
        front_index = {idx: rank for rank, front in enumerate(fronts) for idx in front}
        kept = set(selected)
        rest = sorted((i for i in range(len(candidates)) if i not in kept), key=lambda i: (
            -sum(vectors[i]) / 4, str(candidates[i].to_node), str(candidates[i].from_node),
            str(candidates[i].relation), candidates[i].direction, _sort_id(candidates[i].edge_key), i))
        kept.update(rest[:max(0, 60 - len(kept))])
        stored = sorted(kept)
        mapping = {original: idx for idx, original in enumerate(stored)}
        rows = []
        for original in stored:
            step = candidates[original]
            rows.append({"idx": mapping[original], "state_id": details[original]["state_id"],
                         "from_node": step.from_node, "to_node": step.to_node,
                         "relation": step.relation, "direction": step.direction, "layer": step.layer,
                         **details[original]["vectors"], "front_index": front_index[original],
                         "selected": original in set(selected)})
        return {"kind": "egpot_round", "round": round_number, "beam_before": beam_before,
                "candidates": rows, "fronts": [[mapping[i] for i in front if i in mapping] for front in fronts],
                "selected": [mapping[i] for i in selected], "new_nodes": new_nodes,
                "collected_size_after": collected_size, "candidates_total": len(candidates),
                "candidates_truncated": len(candidates) - len(stored)}

    def traverse(self, query: str, start_node: Hashable, trace: dict | None = None) -> PathResult:
        """Collect selected nodes across beam branches under one global budget.

        Terminal and pruned branches are retained as completed states, so beam
        pruning never erases collected nodes. visited is their union with the
        final active beam. A first-selection ledger makes budget truncation
        deterministic, including when a round would exceed the remaining budget.
        ordered_path maximizes the sum of per-step objective means; ties use
        ordered node IDs. Edges and logs describe that secondary single path.
        """
        if start_node not in self.graph_view.graph:
            raise KeyError(start_node)
        initial = PathState([start_node], [], {start_node: 0}, {}, {start_node})
        beam = [(initial, [])]
        finals = []
        selected_order = {start_node: None}  # insertion-ordered first selections
        if trace is not None:
            trace["steps"] = []
        round_number, stop_reason = 0, "beam_exhausted"

        def rank(entry: tuple) -> tuple:
            state, log = entry
            total = math.fsum(sum(item["vector"]) / 4 for item in log)
            return (-total, tuple(str(node) for node in state.ordered_nodes))

        while beam:
            if len(selected_order) >= self.config.node_budget:
                finals.extend(beam)
                stop_reason = "budget"
                break
            candidates, vectors, origins = [], [], []
            if trace is not None:
                beam_before = [{"state_id": f"r{round_number}s{i}", "nodes": list(state.ordered_nodes),
                                "last_node": state.ordered_nodes[-1]} for i, (state, _) in enumerate(beam)]
                details = []
            round_number += 1
            for beam_idx, (state, log) in enumerate(beam):
                for step in self._candidate_steps(query, state):
                    if trace is None:
                        vector = self.candidate_vector(query, state, step)
                    else:
                        observed = {}
                        vector = self.candidate_vector(query, state, step, trace=observed)
                        details.append({"state_id": beam_before[beam_idx]["state_id"], "vectors": observed})
                    candidates.append(step)
                    vectors.append(vector)
                    # A cached step can be scored from multiple paths at the same tip.
                    origins.append((state, log))
            if not candidates:
                finals.extend(beam)
                stop_reason = "no_candidates"
                if trace is not None:
                    trace["steps"].append(self._trace_round(beam_before, [], [], [], [], [],
                                                            len(selected_order), round_number))
                break
            previous_beam = beam
            beam, extended = [], set()
            if trace is not None:
                chosen_indices, new_nodes = [], []
            for index in self._select_top_indices(candidates, vectors, self.config.beam_width):
                step, vector = candidates[index], vectors[index]
                state, log = origins[index]
                if trace is not None:
                    chosen_indices.append(index)
                    if step.to_node not in selected_order:
                        new_nodes.append(step.to_node)
                selected_order.setdefault(step.to_node, None)
                extended.add(id(state))
                beam.append((state.extend(step), log + [{
                    "from_node": step.from_node, "to_node": step.to_node,
                    "relation": step.relation, "vector": vector}]))
                if len(selected_order) >= self.config.node_budget:
                    break
            # Keep completed/pruned exploration in the final collection. Parents
            # that did extend are already represented by their child states.
            finals.extend(entry for entry in previous_beam if id(entry[0]) not in extended)
            if trace is not None:
                trace["steps"].append(self._trace_round(beam_before, candidates, vectors, details,
                                                        chosen_indices, new_nodes, len(selected_order), round_number))
        state, log = min(finals, key=rank)
        final_union = set().union(*(entry[0].visited for entry in finals))
        visited = set(node for node in selected_order if node in final_union)
        result = PathResult(list(state.ordered_nodes), visited, list(state.edges), log,
                            [node for node in selected_order if node in visited])
        if trace is not None:
            trace["steps"].append({"kind": "stop", "reason": stop_reason})
            trace["final"] = {"visited_order": list(result.visited_order),
                              "ordered_path": list(result.ordered_path),
                              "edges": [list(edge) for edge in result.edges]}
        return result
