"""Configurable hybrid retrieval for GRAFT-CKG.

The module deliberately keeps every experiment on the same candidate corpus,
token budget, and output schema.  It implements the research matrix described
in ``HYBRID_RETRIEVAL_EXPERIMENTS.md``:

R0  lexical BM25                 R7  static + tests
R1  low-rank semantic vectors    R8  static + Git lineage
R2  lexical + semantic RRF       R9  static + API / gRPC contracts
R3  R2 + AST scope               R10 R9 + runtime traces
R4  R2 + dependency graph        R11 static + documentation
R5  static hybrid (R3 + R4)      R12 adaptive query router
R6  R5 + data flow               R13 R12 + deterministic reranker

The built-in semantic retriever is latent semantic analysis (LSA) over code
and documentation.  It is deterministic and dependency-light.  A future
neural embedding adapter can replace only ``_semantic_scores`` without
changing experiments, labels, or metrics.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

import networkx as nx
import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

try:
    from rank_bm25 import BM25Okapi
except ImportError:  # pragma: no cover - the deterministic fallback is tested
    BM25Okapi = None

try:
    from traversal import count_tokens
except ImportError:  # pragma: no cover
    def count_tokens(text: str, model: str = "cl100k_base") -> int:
        return max(1, int(len(text.split()) * 1.3))


SOURCE_TYPES = {
    "function", "method", "class", "module", "interface", "service_contract",
    "rpc_contract", "http_endpoint", "file", "enum", "struct",
}
DOC_EXTENSIONS = {".md", ".rst", ".txt", ".adoc"}
SKIP_DIRECTORIES = {".git", "node_modules", ".venv", "venv", "__pycache__", "repos"}


def _tokens(text: str) -> List[str]:
    """Split prose, paths, camelCase, and snake_case into retrieval tokens."""
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text or "")
    expanded = expanded.replace("_", " ").replace("/", " ").replace(".", " ")
    return [token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9]*|\d+", expanded)]


def _identifier_words(value: str) -> str:
    return " ".join(_tokens(value))


def _normalise(values: Mapping[str, float]) -> Dict[str, float]:
    maximum = max(values.values(), default=0.0)
    if maximum <= 0:
        return {key: 0.0 for key in values}
    return {key: float(value) / maximum for key, value in values.items()}


@dataclass(frozen=True)
class RetrievalConfig:
    id: str
    title: str
    lexical: bool = True
    semantic: bool = False
    symbol: bool = False
    ast: bool = False
    dependency: bool = False
    dataflow: bool = False
    tests: bool = False
    history: bool = False
    contracts: bool = False
    runtime: bool = False
    documents: bool = False
    adaptive: bool = False
    rerank: bool = False


CONFIGS: Dict[str, RetrievalConfig] = {
    "R0": RetrievalConfig("R0", "BM25 lexical"),
    "R1": RetrievalConfig("R1", "LSA semantic vectors", lexical=False, semantic=True),
    "R2": RetrievalConfig("R2", "BM25 + LSA reciprocal-rank fusion", semantic=True),
    "R3": RetrievalConfig("R3", "R2 + AST scope", semantic=True, symbol=True, ast=True),
    "R4": RetrievalConfig("R4", "R2 + dependency graph", semantic=True, dependency=True),
    "R5": RetrievalConfig("R5", "Static hybrid", semantic=True, symbol=True, ast=True, dependency=True),
    "R6": RetrievalConfig("R6", "Static hybrid + data flow", semantic=True, symbol=True, ast=True, dependency=True, dataflow=True),
    "R7": RetrievalConfig("R7", "Static hybrid + tests", semantic=True, symbol=True, ast=True, dependency=True, tests=True),
    "R8": RetrievalConfig("R8", "Static hybrid + Git lineage", semantic=True, symbol=True, ast=True, dependency=True, history=True),
    "R9": RetrievalConfig("R9", "Polyglot contract hybrid", semantic=True, symbol=True, ast=True, dependency=True, contracts=True),
    "R10": RetrievalConfig("R10", "Polyglot hybrid + runtime trace", semantic=True, symbol=True, ast=True, dependency=True, contracts=True, runtime=True),
    "R11": RetrievalConfig("R11", "Static hybrid + documentation", semantic=True, symbol=True, ast=True, dependency=True, documents=True),
    "R12": RetrievalConfig("R12", "Adaptive query router", adaptive=True),
    "R13": RetrievalConfig("R13", "Adaptive query router + reranker", adaptive=True, rerank=True),
}


@dataclass
class Candidate:
    id: str
    kind: str
    name: str
    file: str
    text: str
    code: str
    docstring: str = ""
    is_document: bool = False

    def public(self, score: float, evidence: Sequence[str]) -> Dict[str, Any]:
        return {
            "node_id": self.id,
            "type": self.kind,
            "name": self.name,
            "file": self.file,
            "score": round(float(score), 5),
            "evidence": list(dict.fromkeys(evidence)),
        }


class HybridRetriever:
    """One retrieval implementation with switchable, reproducible configurations."""

    def __init__(
        self,
        builder: Any,
        runtime_edges: Optional[Iterable[Mapping[str, Any]]] = None,
        include_documents: bool = True,
    ) -> None:
        self.builder = builder
        self.graph: nx.MultiDiGraph = builder.graph
        self.candidates: Dict[str, Candidate] = {}
        self.runtime_edges = self._normalise_runtime_edges(runtime_edges or [])
        self._build_candidates(include_documents=include_documents)
        self.candidate_ids = sorted(self.candidates)
        self._fit_indexes()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def retrieve(
        self,
        query: str,
        config: str = "R5",
        top_k: int = 10,
        token_budget: int = 2048,
        graph_depth: int = 2,
    ) -> Dict[str, Any]:
        """Return ranked evidence and token-bounded context for one query."""
        requested = self._config(config)
        effective, intent = self._effective_config(query, requested)
        base_scores, evidence = self._seed_scores(query, effective)
        expanded_scores, expanded_evidence = self._expand_graph(
            base_scores, effective, graph_depth=graph_depth
        )
        for node_id, score in expanded_scores.items():
            if node_id not in base_scores or score > base_scores[node_id]:
                base_scores[node_id] = score
            evidence.setdefault(node_id, []).extend(expanded_evidence.get(node_id, []))

        if effective.tests:
            self._add_test_candidates(query, base_scores, evidence)
        if effective.history:
            self._add_lineage_candidates(base_scores, evidence)
        if effective.runtime:
            self._add_runtime_candidates(base_scores, evidence)

        ranked = self._rank(base_scores, query, effective, evidence)
        packed, bpe_tokens = self._pack_context(ranked, evidence, token_budget)
        return {
            "query": query,
            "requested_config": requested.id,
            "effective_config": effective.id,
            "intent": intent,
            "top_matches": [candidate.public(score, evidence.get(candidate.id, [])) for candidate, score in ranked[:top_k]],
            "selected_node_ids": [candidate.id for candidate, _ in ranked[:top_k]],
            "context": packed,
            "bpe_tokens": bpe_tokens,
            "token_budget": token_budget,
            "candidate_count": len(self.candidates),
        }

    def benchmark(
        self,
        labels: Sequence[Mapping[str, Any]],
        configs: Optional[Sequence[str]] = None,
        top_k: int = 5,
        token_budget: int = 2048,
    ) -> Dict[str, Any]:
        """Evaluate labelled retrieval tasks with identical budgets for each method."""
        selected = list(configs or CONFIGS)
        report: Dict[str, Any] = {
            "task_count": len(labels),
            "top_k": top_k,
            "token_budget": token_budget,
            "methods": {},
        }
        for config_id in selected:
            ranks: List[Optional[int]] = []
            recall_values: List[float] = []
            token_values: List[int] = []
            per_query: List[Dict[str, Any]] = []
            for item in labels:
                result = self.retrieve(str(item["query"]), config_id, top_k=top_k, token_budget=token_budget)
                targets = [str(v) for v in item.get("relevant", item.get("targets", []))]
                ranked_ids = [match["node_id"] for match in result["top_matches"]]
                rank = self._first_relevant_rank(ranked_ids, targets)
                ranks.append(rank)
                recall_values.append(self._context_target_recall(result["context"], targets))
                token_values.append(result["bpe_tokens"])
                per_query.append({
                    "id": item.get("id", item["query"]),
                    "rank": rank,
                    "top_matches": ranked_ids,
                    "effective_config": result["effective_config"],
                })
            valid_ranks = [rank for rank in ranks if rank is not None]
            report["methods"][config_id] = {
                "title": self._config(config_id).title,
                "MRR@%d" % top_k: round(sum(1 / rank for rank in valid_ranks) / max(len(ranks), 1), 4),
                "Hits@1": round(sum(rank == 1 for rank in ranks if rank is not None) / max(len(ranks), 1) * 100, 1),
                "Hits@%d" % top_k: round(len(valid_ranks) / max(len(ranks), 1) * 100, 1),
                "Context_Recall": round(sum(recall_values) / max(len(recall_values), 1) * 100, 1),
                "Mean_BPE_Tokens": round(sum(token_values) / max(len(token_values), 1), 1),
                "queries": per_query,
            }
        return report

    def ingest_lineage(self, max_commits: int = 200) -> int:
        """Attach Git TOUCHES edges for R8.  No-op for workspace-only callers."""
        if hasattr(self.builder, "repo_builders"):
            total = 0
            for repo_builder in self.builder.repo_builders.values():
                total += self._ingest_one_lineage(repo_builder, max_commits)
            return total
        return self._ingest_one_lineage(self.builder, max_commits)

    # ------------------------------------------------------------------
    # Candidate corpus and indexes
    # ------------------------------------------------------------------
    def _build_candidates(self, include_documents: bool) -> None:
        for node_id, data in self.graph.nodes(data=True):
            candidate = self._candidate_from_node(str(node_id), dict(data))
            if candidate:
                self.candidates[candidate.id] = candidate
        if include_documents:
            for path in self._documentation_paths():
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if len(content.strip()) < 10:
                    continue
                rel = str(path)
                document_id = f"doc::{rel.replace(os.sep, '/')}"
                self.candidates[document_id] = Candidate(
                    id=document_id,
                    kind="documentation",
                    name=path.name,
                    file=rel,
                    text=f"{path.name} {_identifier_words(path.name)} {content[:12000]}",
                    code=content[:6000],
                    is_document=True,
                )

    def _candidate_from_node(self, node_id: str, data: Mapping[str, Any]) -> Optional[Candidate]:
        kind = str(data.get("type", "node"))
        name = str(data.get("name", node_id.rsplit(":", 1)[-1]))
        code = str(data.get("code", "") or "")
        docstring = str(data.get("docstring", "") or "")
        file = str(data.get("file", "") or "")
        # Variables, external stubs, and return-expression nodes frequently
        # inherit a whole file as their fallback. Indexing them as independent
        # chunks duplicates context and distorts retrieval. Data-flow still
        # influences expansion through its edges, while source symbols carry
        # the actual packed evidence.
        if kind not in SOURCE_TYPES:
            return None
        if not code and kind == "file":
            code = self._source_for_node(data)
        text = " ".join(part for part in (
            name, _identifier_words(name), file, _identifier_words(file), docstring, code[:2500]
        ) if part)
        if len(text.strip()) < 3:
            return None
        return Candidate(node_id, kind, name, file, text, code[:6000], docstring)

    def _source_for_node(self, data: Mapping[str, Any]) -> str:
        file_name = str(data.get("file", "") or "")
        raw = getattr(self.builder, "raw_file_lines", {}).get(file_name)
        if raw:
            return "".join(raw[:240])
        return ""

    def _documentation_paths(self) -> Iterable[Path]:
        roots: List[Path] = []
        if hasattr(self.builder, "repo_builders"):
            roots = [Path(item.repo_path) for item in self.builder.repo_builders.values()]
        elif getattr(self.builder, "repo_path", None):
            roots = [Path(self.builder.repo_path)]
        seen: Set[Path] = set()
        for root in roots:
            if not root.is_dir():
                continue
            for current, directories, files in os.walk(root):
                directories[:] = [d for d in directories if d not in SKIP_DIRECTORIES]
                for name in files:
                    path = Path(current, name)
                    if path.suffix.lower() in DOC_EXTENSIONS and path not in seen:
                        seen.add(path)
                        yield path

    def _fit_indexes(self) -> None:
        texts = [self.candidates[candidate_id].text for candidate_id in self.candidate_ids]
        self.lexical_vectorizer: Optional[TfidfVectorizer] = None
        self.lexical_matrix = None
        self.semantic_vectorizer: Optional[TfidfVectorizer] = None
        self.semantic_matrix = None
        self.semantic_svd: Optional[TruncatedSVD] = None
        self.bm25 = None
        if not texts:
            return
        self.lexical_vectorizer = TfidfVectorizer(
            tokenizer=_tokens, token_pattern=None, lowercase=True, ngram_range=(1, 2), sublinear_tf=True
        )
        self.lexical_matrix = self.lexical_vectorizer.fit_transform(texts)
        self.semantic_vectorizer = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(3, 5), min_df=1, max_features=12000, sublinear_tf=True
        )
        char_matrix = self.semantic_vectorizer.fit_transform(texts)
        components = min(64, max(0, char_matrix.shape[0] - 1), max(0, char_matrix.shape[1] - 1))
        if components >= 2:
            self.semantic_svd = TruncatedSVD(n_components=components, random_state=17)
            self.semantic_matrix = self.semantic_svd.fit_transform(char_matrix)
        else:
            self.semantic_matrix = char_matrix
        if BM25Okapi:
            self.bm25 = BM25Okapi([_tokens(text) or ["_"] for text in texts])

    # ------------------------------------------------------------------
    # Ranking
    # ------------------------------------------------------------------
    def _seed_scores(self, query: str, config: RetrievalConfig) -> Tuple[Dict[str, float], Dict[str, List[str]]]:
        rankings: List[List[str]] = []
        raw_scores: Dict[str, List[float]] = {}
        evidence: Dict[str, List[str]] = {}
        allowed = self._allowed_ids(config)
        if config.lexical:
            lexical = self._lexical_scores(query, allowed)
            rankings.append(self._rank_ids(lexical))
            for candidate_id, score in lexical.items():
                raw_scores.setdefault(candidate_id, []).append(score)
                if score > 0:
                    evidence.setdefault(candidate_id, []).append("lexical BM25")
        if config.semantic:
            semantic = self._semantic_scores(query, allowed)
            rankings.append(self._rank_ids(semantic))
            for candidate_id, score in semantic.items():
                raw_scores.setdefault(candidate_id, []).append(score)
                if score > 0:
                    evidence.setdefault(candidate_id, []).append("LSA semantic vector")
        if config.symbol:
            symbols = self._symbol_scores(query, allowed)
            rankings.append(self._rank_ids(symbols))
            for candidate_id, score in symbols.items():
                raw_scores.setdefault(candidate_id, []).append(score)
                if score > 0:
                    evidence.setdefault(candidate_id, []).append("symbol / path match")
        if not rankings:
            return {}, {}
        if len(rankings) == 1:
            scores = _normalise({key: values[0] for key, values in raw_scores.items()})
        else:
            scores = self._rrf(rankings)
        return scores, evidence

    def _allowed_ids(self, config: RetrievalConfig) -> Set[str]:
        if config.documents:
            return set(self.candidate_ids)
        return {candidate_id for candidate_id, candidate in self.candidates.items() if not candidate.is_document}

    def _lexical_scores(self, query: str, allowed: Set[str]) -> Dict[str, float]:
        if not self.candidate_ids:
            return {}
        if self.bm25 is not None:
            values = self.bm25.get_scores(_tokens(query) or ["_"])
        elif self.lexical_vectorizer is not None and self.lexical_matrix is not None:
            values = cosine_similarity(self.lexical_vectorizer.transform([query]), self.lexical_matrix).flatten()
        else:
            values = np.zeros(len(self.candidate_ids))
        return {candidate_id: float(values[index]) for index, candidate_id in enumerate(self.candidate_ids) if candidate_id in allowed}

    def _semantic_scores(self, query: str, allowed: Set[str]) -> Dict[str, float]:
        if self.semantic_vectorizer is None or self.semantic_matrix is None:
            return {}
        query_vec = self.semantic_vectorizer.transform([query])
        if self.semantic_svd is not None:
            query_vec = self.semantic_svd.transform(query_vec)
        values = cosine_similarity(query_vec, self.semantic_matrix).flatten()
        return {candidate_id: float(values[index]) for index, candidate_id in enumerate(self.candidate_ids) if candidate_id in allowed}

    def _symbol_scores(self, query: str, allowed: Set[str]) -> Dict[str, float]:
        query_tokens = set(_tokens(query))
        scores: Dict[str, float] = {}
        for candidate_id in allowed:
            candidate = self.candidates[candidate_id]
            name_tokens = set(_tokens(candidate.name))
            path_tokens = set(_tokens(candidate.file))
            overlap = len(query_tokens & name_tokens)
            path_overlap = len(query_tokens & path_tokens)
            score = 2.5 * overlap + 1.25 * path_overlap
            compact_query = "".join(query_tokens)
            if compact_query and compact_query in "".join(name_tokens):
                score += 1.5
            if score:
                scores[candidate_id] = score
        return scores

    @staticmethod
    def _rank_ids(scores: Mapping[str, float]) -> List[str]:
        return [key for key, value in sorted(scores.items(), key=lambda item: (-item[1], item[0])) if value > 0][:100]

    @staticmethod
    def _rrf(rankings: Sequence[Sequence[str]], k: int = 60) -> Dict[str, float]:
        scores: Dict[str, float] = {}
        for ranking in rankings:
            for position, candidate_id in enumerate(ranking, start=1):
                scores[candidate_id] = scores.get(candidate_id, 0.0) + 1.0 / (k + position)
        return scores

    def _rank(
        self,
        scores: Mapping[str, float],
        query: str,
        config: RetrievalConfig,
        evidence: Mapping[str, Sequence[str]],
    ) -> List[Tuple[Candidate, float]]:
        rows = [(self.candidates[candidate_id], score) for candidate_id, score in scores.items() if candidate_id in self.candidates]
        if config.rerank:
            query_terms = set(_tokens(query))
            reranked = []
            for candidate, score in rows:
                lexical_overlap = len(query_terms & set(_tokens(candidate.text[:3000]))) / max(len(query_terms), 1)
                evidence_bonus = min(len(evidence.get(candidate.id, [])), 4) * 0.04
                reranked.append((candidate, score * 0.65 + lexical_overlap * 0.3 + evidence_bonus))
            rows = reranked
        return sorted(rows, key=lambda item: (-item[1], item[0].id))

    # ------------------------------------------------------------------
    # Graph, test, history, and trace augmentation
    # ------------------------------------------------------------------
    def _expand_graph(
        self,
        seed_scores: Mapping[str, float],
        config: RetrievalConfig,
        graph_depth: int,
    ) -> Tuple[Dict[str, float], Dict[str, List[str]]]:
        if not any((config.ast, config.dependency, config.dataflow, config.contracts)):
            return {}, {}
        additions: Dict[str, float] = {}
        evidence: Dict[str, List[str]] = {}
        roots = self._rank_ids(seed_scores)[:12]
        for root in roots:
            if root not in self.graph:
                continue
            queue: List[Tuple[str, int]] = [(root, 0)]
            visited = {root}
            while queue:
                node_id, depth = queue.pop(0)
                if depth >= graph_depth:
                    continue
                for source, target, data in self._both_edges(node_id):
                    neighbor = target if source == node_id else source
                    if neighbor in visited or not self._edge_allowed(data, config):
                        continue
                    visited.add(neighbor)
                    queue.append((neighbor, depth + 1))
                    candidate = self._candidate_from_graph_node(neighbor)
                    if not candidate:
                        continue
                    self.candidates.setdefault(neighbor, candidate)
                    value = float(seed_scores[root]) * (0.68 ** (depth + 1))
                    additions[neighbor] = max(additions.get(neighbor, 0.0), value)
                    relation = str(data.get("relation", data.get("layer", "graph edge")))
                    evidence.setdefault(neighbor, []).append(f"graph:{relation} from {root}")
        return additions, evidence

    def _both_edges(self, node_id: str) -> Iterable[Tuple[str, str, Mapping[str, Any]]]:
        yield from self.graph.out_edges(node_id, data=True)
        yield from self.graph.in_edges(node_id, data=True)

    @staticmethod
    def _edge_allowed(data: Mapping[str, Any], config: RetrievalConfig) -> bool:
        layer = str(data.get("layer", ""))
        relation = str(data.get("relation", ""))
        if config.ast and (layer == "Lsyn" or relation in {"CONTAINS", "DEFINED_IN"}):
            return True
        if config.dependency and (layer == "Ldep" or relation in {"CALLS", "IMPORTS", "EXTENDS", "POLYMORPHIC_CALL"}):
            return True
        if config.dataflow and (layer == "Lflow" or relation in {"USES", "DEFINES", "MUTATES", "RETURNS", "PASSES_ARG"}):
            return True
        if config.contracts and (layer == "Lcontract" or relation in {"CONSUMES", "IMPLEMENTS", "HTTP_CALLS", "DEFINES_RPC"}):
            return True
        return False

    def _candidate_from_graph_node(self, node_id: str) -> Optional[Candidate]:
        if node_id in self.candidates:
            return self.candidates[node_id]
        if node_id not in self.graph:
            return None
        return self._candidate_from_node(node_id, dict(self.graph.nodes[node_id]))

    def _add_test_candidates(self, query: str, scores: Dict[str, float], evidence: Dict[str, List[str]]) -> None:
        query_terms = set(_tokens(query))
        roots = set(self._rank_ids(scores)[:8])
        root_terms = set()
        for root in roots:
            if root in self.candidates:
                root_terms.update(_tokens(self.candidates[root].name))
        for candidate in self.candidates.values():
            is_test = "test" in candidate.file.lower() or candidate.name.lower().startswith("test")
            overlap = len((query_terms | root_terms) & set(_tokens(candidate.text[:1500])))
            if is_test and overlap:
                scores[candidate.id] = max(scores.get(candidate.id, 0.0), 0.28 + overlap * 0.08)
                evidence.setdefault(candidate.id, []).append("test-to-code heuristic")

    def _add_lineage_candidates(self, scores: Dict[str, float], evidence: Dict[str, List[str]]) -> None:
        for candidate_id in self._rank_ids(scores)[:10]:
            if candidate_id not in self.graph:
                continue
            for source, _, data in self.graph.in_edges(candidate_id, data=True):
                if data.get("relation") != "TOUCHES" or source not in self.graph:
                    continue
                commit = self.graph.nodes[source]
                message = str(commit.get("message", ""))
                if not message:
                    continue
                history_id = f"history::{source}"
                self.candidates.setdefault(history_id, Candidate(
                    history_id, "git_commit", str(commit.get("sha", source)), "",
                    f"{message} {candidate_id}", message,
                ))
                scores[history_id] = max(scores.get(history_id, 0.0), scores[candidate_id] * 0.55)
                evidence.setdefault(history_id, []).append(f"Git TOUCHES {candidate_id}")

    def _add_runtime_candidates(self, scores: Dict[str, float], evidence: Dict[str, List[str]]) -> None:
        selected = set(self._rank_ids(scores)[:12])
        for source, target, confidence in self.runtime_edges:
            if source in selected and target in self.graph:
                candidate = self._candidate_from_graph_node(target)
                if candidate:
                    self.candidates.setdefault(target, candidate)
                    scores[target] = max(scores.get(target, 0.0), scores[source] * confidence)
                    evidence.setdefault(target, []).append(f"runtime trace from {source}")
            if target in selected and source in self.graph:
                candidate = self._candidate_from_graph_node(source)
                if candidate:
                    self.candidates.setdefault(source, candidate)
                    scores[source] = max(scores.get(source, 0.0), scores[target] * confidence)
                    evidence.setdefault(source, []).append(f"runtime trace to {target}")

    @staticmethod
    def _normalise_runtime_edges(edges: Iterable[Mapping[str, Any]]) -> List[Tuple[str, str, float]]:
        normalised = []
        for edge in edges:
            source = str(edge.get("source", edge.get("caller", "")))
            target = str(edge.get("target", edge.get("callee", "")))
            if source and target:
                normalised.append((source, target, float(edge.get("confidence", 0.8))))
        return normalised

    @staticmethod
    def _ingest_one_lineage(builder: Any, max_commits: int) -> int:
        try:
            from lineage import LineageLayer
            return LineageLayer(builder).ingest(max_commits=max_commits)
        except (ImportError, OSError):
            return 0

    # ------------------------------------------------------------------
    # Query routing and context packing
    # ------------------------------------------------------------------
    def _effective_config(self, query: str, requested: RetrievalConfig) -> Tuple[RetrievalConfig, str]:
        if not requested.adaptive:
            return requested, "explicit"
        words = set(_tokens(query))
        base_id = "R5"
        intent = "cross-file static"
        if words & {"http", "endpoint", "route", "grpc", "protobuf", "rpc", "service", "api"}:
            base_id, intent = "R9", "cross-service / contract"
        elif words & {"test", "tests", "failing", "failure", "assertion"}:
            base_id, intent = "R7", "test / bug-fix"
        elif words & {"regression", "recent", "changed", "change", "commit", "blame", "history"}:
            base_id, intent = "R8", "temporal / regression"
        elif words & {"trace", "span", "stack", "runtime", "latency"}:
            base_id, intent = "R10", "runtime trace"
        elif words & {"architecture", "design", "overview", "system", "explain"}:
            base_id, intent = "R11", "architecture / documentation"
        elif words & {"return", "returns", "mutation", "mutates", "variable", "dataflow", "flow"}:
            base_id, intent = "R6", "data-flow"
        base = CONFIGS[base_id]
        if requested.rerank:
            return replace(base, id="R13", title="Adaptive query router + reranker", rerank=True), intent
        return base, intent

    def _pack_context(
        self,
        ranked: Sequence[Tuple[Candidate, float]],
        evidence: Mapping[str, Sequence[str]],
        token_budget: int,
    ) -> Tuple[str, int]:
        blocks: List[str] = []
        used = 0
        for candidate, _ in ranked:
            source = candidate.code or candidate.docstring or candidate.text
            if not source:
                continue
            block = (
                f"=== {candidate.kind.upper()} {candidate.name} ===\n"
                f"Source: {candidate.file or candidate.id}\n"
                f"Evidence: {', '.join(dict.fromkeys(evidence.get(candidate.id, []))) or 'retrieval rank'}\n"
                f"{source[:3000]}"
            )
            trial_context = "\n\n".join([*blocks, block])
            tokens = count_tokens(trial_context)
            if tokens > token_budget:
                continue
            blocks.append(block)
            used = tokens
        context = "\n\n".join(blocks)
        return context, count_tokens(context) if context else 0

    @staticmethod
    def _first_relevant_rank(node_ids: Sequence[str], targets: Sequence[str]) -> Optional[int]:
        lowered = [target.lower() for target in targets]
        for index, node_id in enumerate(node_ids, start=1):
            node = node_id.lower()
            if any(target in node for target in lowered):
                return index
        return None

    @staticmethod
    def _context_target_recall(context: str, targets: Sequence[str]) -> float:
        if not targets:
            return 0.0
        lowered = context.lower()
        return sum(target.lower().split(":")[-1] in lowered for target in targets) / len(targets)

    @staticmethod
    def _config(config: str) -> RetrievalConfig:
        try:
            return CONFIGS[config.upper()]
        except KeyError as exc:
            choices = ", ".join(CONFIGS)
            raise ValueError(f"Unknown config '{config}'. Choose one of: {choices}") from exc


def _load_labels(path: str) -> List[Dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("queries", data.get("tasks", []))
    if not isinstance(data, list):
        raise ValueError("Label file must contain a JSON list or a queries/tasks array.")
    return [dict(item) for item in data]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a GRAFT-CKG hybrid retrieval configuration.")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--repo", help="Repository to index")
    target.add_argument("--workspace", help="Workspace YAML/JSON to index")
    parser.add_argument("--query", help="Natural-language query")
    parser.add_argument("--config", default="R5", choices=sorted(CONFIGS), help="Experiment configuration")
    parser.add_argument("--labels", help="JSON labels for a full benchmark run")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--token-budget", type=int, default=2048)
    parser.add_argument("--runtime-trace", help="JSON list of runtime {source,target,confidence} edges")
    parser.add_argument("--ingest-lineage", action="store_true", help="Attach Git history before R8/R12/R13 runs")
    parser.add_argument("--output", help="Optional JSON output path")
    args = parser.parse_args()

    if args.workspace:
        from multi_repo import WorkspaceCKGBuilder
        builder = WorkspaceCKGBuilder(args.workspace)
    else:
        from graft_ckg import CKGBuilder
        builder = CKGBuilder(args.repo)
    builder.build()
    runtime_edges = _load_labels(args.runtime_trace) if args.runtime_trace else []
    retriever = HybridRetriever(builder, runtime_edges=runtime_edges)
    if args.ingest_lineage:
        retriever.ingest_lineage()
    if args.labels:
        result: Dict[str, Any] = retriever.benchmark(_load_labels(args.labels), top_k=args.top_k, token_budget=args.token_budget)
    elif args.query:
        result = retriever.retrieve(args.query, args.config, top_k=args.top_k, token_budget=args.token_budget)
    else:
        parser.error("Provide --query for one retrieval or --labels for a benchmark.")
    rendered = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
