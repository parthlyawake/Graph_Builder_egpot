"""
SCKGGraphProvider -- Concrete implementation of GraphProvider backed by GRAFT-CKG.

Bridges the evaluation harness / agent orchestrator to the 5-layer Semantic
Code Knowledge Graph (SCKG / GRAFT-CKG) construction and traversal engine.
"""

from __future__ import annotations

import difflib
import os
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import networkx as nx

# Add repository root to path if not already present
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contracts.graph_provider import GraphProvider
from contracts.graph_types import (
    CandidateRootCause,
    CausalPath,
    CodeNode,
    EdgeType,
    InducedSubgraph,
    Language,
    NodeType,
    TelemetryEvent,
    TraversalPolicy,
    TypedEdge,
)
from graft_ckg import CKGBuilder
from multi_repo import WorkspaceCKGBuilder
from remediation import DefectType, SCKGSelfHealingEngine
from traversal import SCKGTraversal


class SCKGGraphProvider(GraphProvider):
    """
    Concrete implementation of GraphProvider for GRAFT-CKG.

    Supports:
      - Single-repo CKG (via CKGBuilder)
      - Multi-repo workspace CKG (via WorkspaceCKGBuilder)
      - Direct pre-built NetworkX graph injection
    """

    def __init__(
        self,
        target_or_builder: Union[str, CKGBuilder, WorkspaceCKGBuilder, nx.MultiDiGraph, nx.DiGraph],
    ):
        """
        Initialize the provider with a repository path, workspace manifest,
        or pre-built CKG builder.
        """
        if isinstance(target_or_builder, str):
            target_path = os.path.abspath(target_or_builder)
            if target_path.endswith((".yaml", ".yml", ".json")) or (
                os.path.isfile(target_path) and "workspace" in os.path.basename(target_path)
            ):
                self.builder = WorkspaceCKGBuilder(target_path)
                self.builder.build()
                self.graph: nx.MultiDiGraph = self.builder.graph
            elif os.path.isdir(target_path):
                # Check if workspace.yaml exists in directory
                ws_file = os.path.join(target_path, "workspace.yaml")
                if os.path.exists(ws_file):
                    self.builder = WorkspaceCKGBuilder(ws_file)
                    self.builder.build()
                    self.graph = self.builder.graph
                else:
                    self.builder = CKGBuilder(target_path)
                    self.builder.build()
                    self.graph = self.builder.graph
            else:
                self.builder = CKGBuilder(target_path)
                self.builder.build()
                self.graph = self.builder.graph
        elif isinstance(target_or_builder, (CKGBuilder, WorkspaceCKGBuilder)):
            self.builder = target_or_builder
            if not hasattr(self.builder, "graph") or len(self.builder.graph.nodes) == 0:
                self.builder.build()
            self.graph = self.builder.graph
        elif isinstance(target_or_builder, (nx.MultiDiGraph, nx.DiGraph)):
            self.graph = target_or_builder
            # Lightweight wrapper mock builder
            class _DummyBuilder:
                def __init__(self, g):
                    self.graph = g
                    self.symbols_by_name = {}
                    self.proto_services = {}
                    self.http_endpoints = {}
                    self.http_calls_to_resolve = []
                    self.contract_skews = []

                def _contract_node_id(self, name):
                    return f"contract::{name}" if f"contract::{name}" in self.graph else None

            self.builder = _DummyBuilder(self.graph)
        else:
            raise TypeError(f"Unsupported target_or_builder type: {type(target_or_builder)}")

        self.traversal = SCKGTraversal(self.builder)
        try:
            self.remediation = SCKGSelfHealingEngine(self.builder)
        except Exception:
            self.remediation = None

        self._version_str = "GRAFT-CKG/1.0.0"

    # -------------------------------------------------------------------------
    # Internal Type Mapping Helpers
    # -------------------------------------------------------------------------

    def _map_node_type(self, raw_type: str, node_id: str) -> NodeType:
        t = str(raw_type).lower()
        if t in ("function", "method", "external_func"):
            return NodeType.FUNCTION
        if t == "class":
            return NodeType.CLASS
        if t == "service":
            return NodeType.SERVICE
        if t in ("topic_contract", "topic") or "topic::" in node_id:
            return NodeType.TOPIC_CONTRACT
        if t in ("http_endpoint", "endpoint") or "endpoint::" in node_id:
            return NodeType.ENDPOINT
        if t == "http_callsite":
            return NodeType.HTTP_CALLSITE
        if t in ("service_contract", "rpc_contract", "contract") or "contract::" in node_id:
            return NodeType.CONTRACT
        if t == "commit":
            return NodeType.COMMIT
        if t == "file":
            return NodeType.FILE
        if t == "module":
            return NodeType.MODULE
        if t == "deployment":
            return NodeType.DEPLOYMENT

        # Fallback heuristic based on node_id format
        if "topic::" in node_id:
            return NodeType.TOPIC_CONTRACT
        if "contract::" in node_id or "http::" in node_id:
            return NodeType.CONTRACT
        if ":" in node_id:
            return NodeType.FUNCTION
        if "." in os.path.basename(node_id):
            return NodeType.FILE
        return NodeType.FUNCTION

    def _map_language(self, lang_str: Optional[str], file_path: Optional[str]) -> Language:
        if lang_str:
            l = lang_str.lower()
            if "python" in l or l == "py":
                return Language.PYTHON
            if "go" in l:
                return Language.GO
            if "java" in l:
                return Language.JAVA
            if "typescript" in l or l == "ts":
                return Language.TYPESCRIPT
            if "javascript" in l or l == "js":
                return Language.JAVASCRIPT
            if "proto" in l:
                return Language.PROTOBUF

        if file_path:
            ext = os.path.splitext(file_path)[1].lower()
            mapping = {
                ".py": Language.PYTHON,
                ".go": Language.GO,
                ".java": Language.JAVA,
                ".ts": Language.TYPESCRIPT,
                ".tsx": Language.TYPESCRIPT,
                ".js": Language.JAVASCRIPT,
                ".jsx": Language.JAVASCRIPT,
                ".proto": Language.PROTOBUF,
            }
            if ext in mapping:
                return mapping[ext]

        return Language.UNKNOWN

    def _map_edge_type(self, rel: str) -> EdgeType:
        r = str(rel).upper()
        if r in ("CALLS", "POLYMORPHIC_CALL"):
            return EdgeType.CALLS
        if r == "IMPLEMENTS":
            return EdgeType.IMPLEMENTS
        if r == "CONSUMES":
            return EdgeType.CONSUMES
        if r == "PRODUCES":
            return EdgeType.PRODUCES
        if r == "PRODUCES_EVENT":
            return EdgeType.PRODUCES_EVENT
        if r == "CONSUMES_EVENT":
            return EdgeType.CONSUMES_EVENT
        if r == "HTTP_CALLS":
            return EdgeType.HTTP_CALLS
        if r == "HTTP_REQUEST":
            return EdgeType.HTTP_REQUEST
        if r == "POSSIBLE_HTTP_TARGET":
            return EdgeType.POSSIBLE_HTTP_TARGET
        if r in ("DEFINES", "DEFINES_RPC"):
            return EdgeType.DEFINES
        if r == "IMPORTS":
            return EdgeType.IMPORTS
        if r in ("MODIFIED_BY", "TOUCHES"):
            return EdgeType.MODIFIED_BY
        if r in ("BREAKS_CONTRACT", "SKEW"):
            return EdgeType.BREAKS_CONTRACT
        # EXTENDS, CONTAINS, PASSES_ARG, FLOWS_TO, MUTATES, RETURNS, USES, DEPENDS_ON
        return EdgeType.DEPENDS_ON

    def _to_code_node(self, node_id: str, data: Optional[Dict[str, Any]] = None) -> CodeNode:
        if data is None:
            data = self.graph.nodes.get(node_id, {})

        raw_type = data.get("type", "function")
        node_type = self._map_node_type(raw_type, node_id)
        name = data.get("name") or node_id.split("::")[-1].split(":")[-1]
        file_path = data.get("file")
        language = self._map_language(data.get("language"), file_path)
        service_name = data.get("repo") or self.traversal._extract_service_name(file_path or "", node_id)

        raw_start = data.get("line_no")
        line_start = int(raw_start) if raw_start is not None and str(raw_start).lstrip("-").isdigit() else None
        raw_end = data.get("line_end")
        line_end = int(raw_end) if raw_end is not None and str(raw_end).lstrip("-").isdigit() else line_start
        source_snippet = data.get("code")

        signature = data.get("signature")
        if not signature:
            if node_type == NodeType.CONTRACT and data.get("request_type"):
                signature = f"rpc {name}({data.get('request_type', '')}) returns ({data.get('response_type', '')})"
            elif data.get("docstring"):
                signature = data.get("docstring").split("\n")[0].strip()

        # Build clean metadata
        metadata = {
            "layer": data.get("layer"),
            "docstring": data.get("docstring"),
            "raw_type": raw_type,
        }
        for k, v in data.items():
            if k not in ("id", "type", "name", "file", "line_no", "line_end", "code", "repo", "language", "signature"):
                metadata[k] = v

        return CodeNode(
            node_id=str(node_id),
            node_type=node_type,
            name=str(name),
            language=language,
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            source_snippet=source_snippet,
            signature=signature,
            service_name=service_name,
            metadata=metadata,
        )

    def _to_typed_edge(self, src: str, tgt: str, data: Dict[str, Any]) -> TypedEdge:
        rel = data.get("relation", "DEPENDS_ON")
        edge_type = self._map_edge_type(rel)
        meta = {
            "layer": data.get("layer"),
            "raw_relation": rel,
        }
        if "metadata" in data and isinstance(data["metadata"], dict):
            meta.update(data["metadata"])
        return TypedEdge(
            source_id=str(src),
            target_id=str(tgt),
            edge_type=edge_type,
            metadata=meta,
        )

    def _matches_file(self, n_file: str, frame_path: str) -> bool:
        if not n_file or not frame_path:
            return False
        f1 = n_file.replace("\\", "/").strip("/").lower()
        f2 = frame_path.replace("\\", "/").strip("/").lower()
        if f1 == f2:
            return True
        if f1.endswith("/" + f2) or f2.endswith("/" + f1):
            return True
        return False

    def _is_test_node(self, nid: str, ndata: Optional[dict] = None) -> bool:
        if ndata is None:
            ndata = self.graph.nodes.get(nid, {})
        if ndata.get("is_test"):
            return True
        file_path = ndata.get("file") or ""
        norm = file_path.replace("\\", "/").lower()
        parts = norm.split("/")
        filename = parts[-1]
        if "tests" in parts or "test" in parts or "__tests__" in parts or "__test__" in parts:
            return True
        if filename.startswith("test_") or filename.endswith("_test.py") or filename.endswith("_test.go"):
            return True
        if filename.endswith(".test.js") or filename.endswith(".test.ts") or filename.endswith(".test.jsx") or filename.endswith(".test.tsx"):
            return True
        if filename.endswith(".spec.js") or filename.endswith(".spec.ts") or filename.endswith(".spec.jsx") or filename.endswith(".spec.tsx"):
            return True
        name = ndata.get("name", "")
        if name.startswith("test_") or name.startswith("Test"):
            return True
        return False

    def _is_excluded_candidate(self, nid: str, ndata: dict, policy: TraversalPolicy) -> bool:
        if self._is_test_node(nid, ndata):
            return True
        raw_type = ndata.get("type", "").lower()
        if raw_type in ("file", "module", "variable", "return", "symbol_ref", "external_func", "parameter"):
            return True
        node_obj = self._to_code_node(nid, ndata)
        if node_obj.node_type in (NodeType.FILE, NodeType.MODULE, NodeType.DEPLOYMENT):
            return True
        if policy.include_node_types and node_obj.node_type not in policy.include_node_types:
            return True
        if policy.exclude_node_types and node_obj.node_type in policy.exclude_node_types:
            return True
        return False

    # -------------------------------------------------------------------------
    # GraphProvider Interface Implementation
    # -------------------------------------------------------------------------

    def resolve_symptom(self, symptom: TelemetryEvent) -> list[CodeNode]:
        """
        Map an unstructured telemetry event to concrete code nodes.
        """
        matched_node_ids: List[str] = []
        seen: Set[str] = set()

        # Step 1: Parse stack trace if present
        if symptom.stack_trace:
            py_matches = re.findall(r'File "([^"]+)", line (\d+)(?:, in (\w+))?', symptom.stack_trace)
            for file_path, line_no, func_name in py_matches:
                line_int = int(line_no)
                frame_candidates = []
                for nid, ndata in self.graph.nodes(data=True):
                    n_file = ndata.get("file", "")
                    if n_file and self._matches_file(n_file, file_path):
                        if func_name:
                            name_matched = (ndata.get("name") == func_name or nid.endswith(":" + func_name) or nid.endswith("." + func_name))
                            if name_matched and ndata.get("type") in ("function", "method") and not self._is_test_node(nid, ndata):
                                frame_candidates.append(nid)
                        else:
                            n_line = int(ndata.get("line_no", 0)) if str(ndata.get("line_no", "")).isdigit() else 0
                            n_line_end = int(ndata.get("line_end", n_line)) if str(ndata.get("line_end", "")).isdigit() else n_line
                            if ndata.get("type") in ("function", "method") and not self._is_test_node(nid, ndata):
                                if n_line <= line_int <= n_line_end:
                                    frame_candidates.append(nid)

                for nid in frame_candidates:
                    if nid not in seen:
                        seen.add(nid)
                        matched_node_ids.append(nid)

            java_matches = re.findall(r'at (?:[\w\.\$]+)\(([\w\.\-]+\.java):(\d+)\)', symptom.stack_trace)
            for file_path, line_no in java_matches:
                line_int = int(line_no)
                for nid, ndata in self.graph.nodes(data=True):
                    n_file = ndata.get("file", "")
                    if n_file and self._matches_file(n_file, file_path) and ndata.get("type") in ("function", "method") and not self._is_test_node(nid, ndata):
                        n_line = int(ndata.get("line_no", 0)) if str(ndata.get("line_no", "")).isdigit() else 0
                        n_line_end = int(ndata.get("line_end", n_line)) if str(ndata.get("line_end", "")).isdigit() else n_line
                        if n_line <= line_int <= n_line_end:
                            if nid not in seen:
                                seen.add(nid)
                                matched_node_ids.append(nid)

            go_matches = re.findall(r'([\w\/\.\-]+(?:\.go|\.js|\.ts|\.py|\.java)):(\d+)', symptom.stack_trace)
            for file_path, line_no in go_matches:
                line_int = int(line_no)
                for nid, ndata in self.graph.nodes(data=True):
                    n_file = ndata.get("file", "")
                    if n_file and self._matches_file(n_file, file_path) and ndata.get("type") in ("function", "method") and not self._is_test_node(nid, ndata):
                        n_line = int(ndata.get("line_no", 0)) if str(ndata.get("line_no", "")).isdigit() else 0
                        n_line_end = int(ndata.get("line_end", n_line)) if str(ndata.get("line_end", "")).isdigit() else n_line
                        if n_line <= line_int <= n_line_end:
                            if nid not in seen:
                                seen.add(nid)
                                matched_node_ids.append(nid)

        # Step 2: Extract keywords from error message & error type ONLY if stack trace produced no matches
        if not matched_node_ids:
            combined_text = f"{symptom.error_type} {symptom.message}"
            tokens = set(re.findall(r'[A-Za-z0-9_]{3,}', combined_text))

            for token in tokens:
                resolved = self.traversal._resolve_node_id(token)
                if resolved and resolved not in seen:
                    seen.add(resolved)
                    matched_node_ids.append(resolved)

                resolved_c = self.traversal._resolve_contract_or_endpoint(token)
                if resolved_c and resolved_c not in seen:
                    seen.add(resolved_c)
                    matched_node_ids.append(resolved_c)

        # Step 3: Service-level filtering / fallback if still empty
        if not matched_node_ids and symptom.service_name:
            svc_nodes = []
            for nid, ndata in self.graph.nodes(data=True):
                svc = ndata.get("repo") or self.traversal._extract_service_name(ndata.get("file", ""), nid)
                if svc.lower() == symptom.service_name.lower():
                    if ndata.get("type") in ("function", "method", "service_contract"):
                        svc_nodes.append(nid)

            ranked = sorted(
                svc_nodes,
                key=lambda n: sum(1 for t in tokens if t.lower() in n.lower()),
                reverse=True,
            )
            for nid in ranked[:10]:
                if nid not in seen:
                    seen.add(nid)
                    matched_node_ids.append(nid)

        return [self._to_code_node(nid) for nid in matched_node_ids]

    def backward_traverse(
        self, node: CodeNode, policy: TraversalPolicy
    ) -> list[CandidateRootCause]:
        """
        From a symptom-linked node, walk backward through the graph
        to find ranked candidate root causes.
        """
        start_id = self.traversal._resolve_node_id(node.node_id) or node.node_id
        if start_id not in self.graph:
            return []

        active_defects = []
        if self.remediation:
            try:
                active_defects = self.remediation.diagnose()
            except Exception:
                active_defects = []

        defect_map: Dict[str, Any] = {}
        for d in active_defects:
            attr = self.remediation.attribute_causal_root(d) if self.remediation else d
            caller = d.get("consumer_caller") or d.get("caller")
            if caller:
                defect_map[caller] = attr
            c_node = d.get("contract_node")
            if c_node:
                defect_map[c_node] = attr

        candidates: List[CandidateRootCause] = []
        visited: Set[str] = {start_id}
        depth_map: Dict[str, int] = {start_id: 0}

        # D1: Add the start/symptom node itself first with confidence 1.0
        start_data = self.graph.nodes.get(start_id, {})
        if not self._is_excluded_candidate(start_id, start_data, policy):
            candidates.append(
                CandidateRootCause(
                    node=self._to_code_node(start_id, start_data),
                    confidence=1.0,
                    evidence=["Symptom location (stack frame)"],
                    rank=1,
                )
            )

        # BFS walk
        queue: List[Tuple[str, int, float, List[str]]] = [(start_id, 0, 1.0, ["Symptom entrypoint"])]

        while queue and len(candidates) < policy.max_nodes:
            curr, depth, curr_conf, path_evidence = queue.pop(0)

            if depth > 0:
                curr_data = self.graph.nodes.get(curr, {})
                if not self._is_excluded_candidate(curr, curr_data, policy):
                    final_conf = curr_conf
                    if curr in defect_map:
                        final_conf = max(final_conf, 0.95)
                        path_evidence.append(f"Implicated in detected defect: {defect_map[curr].get('type')}")

                    candidates.append(
                        CandidateRootCause(
                            node=self._to_code_node(curr, curr_data),
                            confidence=round(min(1.0, max(0.05, final_conf)), 3),
                            evidence=list(path_evidence),
                            rank=len(candidates) + 1,
                        )
                    )

            if depth >= policy.max_depth:
                continue

            # D2: Out-edges: Causal dependencies (callees, used symbols, imported modules, consumed contracts)
            for _, tgt, data in self.graph.out_edges(curr, data=True):
                rel = data.get("relation", "DEPENDS_ON")
                if rel in ("CALLS", "POLYMORPHIC_CALL", "USES", "IMPORTS", "CONSUMES", "IMPLEMENTS", "HTTP_CALLS"):
                    edge_weight = 0.9 if rel in ("CALLS", "POLYMORPHIC_CALL") else 0.85
                    if rel in ("CONSUMES", "IMPLEMENTS"):
                        edge_weight = 0.95
                    new_conf = curr_conf * edge_weight
                    new_evidence = path_evidence + [f"Dependency [{rel}] -> {tgt}"]
                    if tgt not in visited:
                        visited.add(tgt)
                        depth_map[tgt] = depth + 1
                        queue.append((tgt, depth + 1, new_conf, new_evidence))

            # D2: In-edges: Incoming dataflow into curr
            for src, _, data in self.graph.in_edges(curr, data=True):
                rel = data.get("relation", "DEPENDS_ON")
                if rel in ("PASSES_ARG", "FLOWS_TO", "MUTATES", "RETURNS"):
                    edge_weight = 0.8
                    new_conf = curr_conf * edge_weight
                    new_evidence = path_evidence + [f"Dataflow [{rel}] from {src}"]
                    if src not in visited:
                        visited.add(src)
                        depth_map[src] = depth + 1
                        queue.append((src, depth + 1, new_conf, new_evidence))
                elif rel in ("CALLS", "POLYMORPHIC_CALL"):
                    # Callers ("bad argument" hypothesis) - lower confidence than direct dependencies
                    edge_weight = 0.5
                    new_conf = curr_conf * edge_weight
                    new_evidence = path_evidence + [f"Caller [{rel}] from {src}"]
                    if src not in visited:
                        visited.add(src)
                        depth_map[src] = depth + 1
                        queue.append((src, depth + 1, new_conf, new_evidence))

            # D2: Cross-service jump: if curr consumes a contract, explore implementers
            for _, tgt, data in self.graph.out_edges(curr, data=True):
                if data.get("relation") == "CONSUMES":
                    for impl_src, _, impl_data in self.graph.in_edges(tgt, data=True):
                        if impl_data.get("relation") == "IMPLEMENTS" and impl_src not in visited:
                            visited.add(impl_src)
                            depth_map[impl_src] = depth + 1
                            queue.append((
                                impl_src,
                                depth + 1,
                                curr_conf * 0.92,
                                path_evidence + [f"Cross-service: contract {tgt} implemented by {impl_src}"]
                            ))

        # D4: Deterministic ranking: sort by (-confidence, depth, node_id)
        candidates.sort(key=lambda c: (-round(c.confidence, 4), depth_map.get(c.node.node_id, 99), c.node.node_id))
        for i, c in enumerate(candidates):
            c.rank = i + 1

        return candidates[: policy.max_nodes]

    def forward_traverse(
        self, node: CodeNode, policy: TraversalPolicy
    ) -> InducedSubgraph:
        """
        From a root-cause node, walk forward to extract the blast-radius
        subgraph -- all downstream consumers and affected contracts.
        """
        start_id = self.traversal._resolve_node_id(node.node_id) or node.node_id
        if start_id not in self.graph:
            return InducedSubgraph(root_node_id=node.node_id, nodes=[], edges=[])

        visited_nodes: Set[str] = {start_id}
        collected_edges: List[TypedEdge] = []
        queue: List[Tuple[str, int]] = [(start_id, 0)]

        while queue and len(visited_nodes) < policy.max_nodes:
            curr, depth = queue.pop(0)
            if depth >= policy.max_depth:
                continue

            # Forward out-edges (callees, contracts consumed/implemented, dataflow targets)
            for _, tgt, data in self.graph.out_edges(curr, data=True):
                collected_edges.append(self._to_typed_edge(curr, tgt, data))
                if tgt not in visited_nodes:
                    visited_nodes.add(tgt)
                    queue.append((tgt, depth + 1))

            # Callers of curr (functions and tests that call curr) are downstream affected nodes
            for caller_src, _, in_data in self.graph.in_edges(curr, data=True):
                rel = in_data.get("relation")
                if rel in ("CALLS", "POLYMORPHIC_CALL"):
                    collected_edges.append(self._to_typed_edge(caller_src, curr, in_data))
                    if caller_src not in visited_nodes:
                        visited_nodes.add(caller_src)
                        queue.append((caller_src, depth + 1))

            # If curr is a contract or implements one, find downstream consumers (in-edges with CONSUMES)
            curr_data = self.graph.nodes.get(curr, {})
            if "contract" in curr_data.get("type", "") or "contract::" in curr:
                for consumer_src, _, in_data in self.graph.in_edges(curr, data=True):
                    rel = in_data.get("relation")
                    if rel in ("CONSUMES", "HTTP_CALLS"):
                        collected_edges.append(self._to_typed_edge(consumer_src, curr, in_data))
                        if consumer_src not in visited_nodes:
                            visited_nodes.add(consumer_src)
                            queue.append((consumer_src, depth + 1))

        # Filter nodes based on policy
        result_nodes: List[CodeNode] = []
        for nid in visited_nodes:
            c_node = self._to_code_node(nid)
            if policy.include_node_types and c_node.node_type not in policy.include_node_types:
                continue
            if policy.exclude_node_types and c_node.node_type in policy.exclude_node_types:
                continue
            result_nodes.append(c_node)

        node_id_set = {n.node_id for n in result_nodes}
        seen_edges = set()
        filtered_edges: List[TypedEdge] = []
        for e in collected_edges:
            if e.source_id in node_id_set and e.target_id in node_id_set:
                edge_key = (e.source_id, e.target_id, e.edge_type)
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    filtered_edges.append(e)

        return InducedSubgraph(
            root_node_id=start_id,
            nodes=result_nodes,
            edges=filtered_edges,
        )

    def get_node_detail(self, node_id: str) -> CodeNode:
        """Fetch full details for a single node by ID (exact ID only)."""
        if node_id not in self.graph:
            raise KeyError(f"Node '{node_id}' not found in SCKG")
        return self._to_code_node(node_id, self.graph.nodes[node_id])

    def explain_path(
        self, node_a: CodeNode, node_b: CodeNode
    ) -> CausalPath:
        """
        Construct a causal explanation chain from node_a to node_b.
        Uses NetworkX shortest path over directed or undirected graph.
        """
        src = node_a.node_id if node_a.node_id in self.graph else (self.traversal._resolve_node_id(node_a.node_id) or node_a.node_id)
        dst = node_b.node_id if node_b.node_id in self.graph else (self.traversal._resolve_node_id(node_b.node_id) or node_b.node_id)

        if src not in self.graph or dst not in self.graph:
            return CausalPath(nodes=[], edges=[])

        # 1. Try directed path src -> dst
        path_nodes: List[str] = []
        try:
            path_nodes = nx.shortest_path(self.graph, source=src, target=dst)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            pass

        # 2. Try reverse directed path dst -> src
        if not path_nodes:
            try:
                reverse_path = nx.shortest_path(self.graph, source=dst, target=src)
                path_nodes = list(reversed(reverse_path))
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                pass

        # 3. Fallback to undirected path
        if not path_nodes:
            try:
                undirected_g = self.graph.to_undirected(as_view=True)
                path_nodes = nx.shortest_path(undirected_g, source=src, target=dst)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                return CausalPath(nodes=[node_a, node_b], edges=[])

        # Convert path nodes to CodeNodes
        code_nodes = [self._to_code_node(nid) for nid in path_nodes]
        typed_edges: List[TypedEdge] = []

        for i in range(len(path_nodes) - 1):
            u, v = path_nodes[i], path_nodes[i + 1]
            if self.graph.has_edge(u, v):
                edge_dict = self.graph.get_edge_data(u, v)
                if isinstance(edge_dict, dict) and edge_dict:
                    edge_data = next(iter(edge_dict.values()))
                else:
                    edge_data = edge_dict or {}
                typed_edges.append(self._to_typed_edge(u, v, edge_data or {}))
            elif self.graph.has_edge(v, u):
                edge_dict = self.graph.get_edge_data(v, u)
                if isinstance(edge_dict, dict) and edge_dict:
                    edge_data = next(iter(edge_dict.values()))
                else:
                    edge_data = edge_dict or {}
                # Return edge in its real direction (source = actual source node)
                typed_edges.append(self._to_typed_edge(v, u, edge_data or {}))
            else:
                typed_edges.append(TypedEdge(source_id=u, target_id=v, edge_type=EdgeType.DEPENDS_ON))

        return CausalPath(nodes=code_nodes, edges=typed_edges)

    def find_node_by_name(
        self, name: str, file_path: str | None = None
    ) -> list[CodeNode]:
        """
        Fuzzy lookup: find nodes matching a name.
        Used by the OpenHands graph tools when the agent discovers a
        function name in code and wants to query the graph about it.
        """
        matches: List[str] = []
        name_clean = name.strip()
        name_lower = name_clean.lower()

        # 1. Direct symbol registry lookup if builder has it
        if hasattr(self.builder, "symbols_by_name") and name_clean in self.builder.symbols_by_name:
            matches.extend(self.builder.symbols_by_name[name_clean])

        # 2. Search graph nodes
        for nid, data in self.graph.nodes(data=True):
            n_name = data.get("name", "")
            if not n_name and ":" in nid:
                n_name = nid.split(":")[-1]

            # Exact or suffix match
            if n_name == name_clean or nid.endswith(f"::{name_clean}") or nid.endswith(f":{name_clean}"):
                if nid not in matches:
                    matches.append(nid)
            # Case-insensitive match
            elif n_name.lower() == name_lower:
                if nid not in matches:
                    matches.append(nid)

        # 3. If file_path is specified, filter / prioritize
        if file_path:
            norm_target = file_path.replace("\\", "/").lower()
            filtered = [
                m for m in matches
                if self.graph.nodes[m].get("file") and norm_target in self.graph.nodes[m]["file"].replace("\\", "/").lower()
            ]
            if filtered:
                matches = filtered

        # 4. Partial substring fallback if nothing matched
        if not matches:
            for nid, data in self.graph.nodes(data=True):
                n_name = data.get("name", "")
                if name_lower in n_name.lower() or name_lower in nid.lower():
                    matches.append(nid)
                    if len(matches) >= 20:
                        break

        return [self._to_code_node(m) for m in matches]

    def get_contract_between(
        self, service_a: str, service_b: str
    ) -> list[CodeNode]:
        """
        Return all contract nodes (proto, OpenAPI) shared between two services.
        Identifies contracts where one service implements/produces and the other consumes.
        """
        contracts_found: Set[str] = set()
        svc_a_lower = service_a.lower().strip()
        svc_b_lower = service_b.lower().strip()

        def _svc_matches(target: str, candidate: str) -> bool:
            t = target.lower().replace("-", "_")
            c = candidate.lower().replace("-", "_")
            return t == c or t in c or c in t

        # Iterate all contract nodes in graph
        for nid, data in self.graph.nodes(data=True):
            ntype = data.get("type", "")
            is_contract = "contract" in ntype or ntype == "http_endpoint" or "contract::" in nid
            if not is_contract:
                continue

            # Check implementations / producers (in-edges with IMPLEMENTS / PRODUCES)
            producers: Set[str] = set()
            for src, _, edata in self.graph.in_edges(nid, data=True):
                rel = edata.get("relation")
                if rel in ("IMPLEMENTS", "PRODUCES"):
                    src_svc = self.graph.nodes[src].get("repo") or self.traversal._extract_service_name(
                        self.graph.nodes[src].get("file", ""), src
                    )
                    if src_svc:
                        producers.add(src_svc)

            # Check consumers (in-edges with CONSUMES / HTTP_CALLS or out-edges with CONSUMES)
            consumers: Set[str] = set()
            for src, _, edata in self.graph.in_edges(nid, data=True):
                rel = edata.get("relation")
                if rel in ("CONSUMES", "HTTP_CALLS"):
                    src_svc = self.graph.nodes[src].get("repo") or self.traversal._extract_service_name(
                        self.graph.nodes[src].get("file", ""), src
                    )
                    if src_svc:
                        consumers.add(src_svc)

            # Check if (service_a produces and service_b consumes) OR vice-versa
            a_prod = any(_svc_matches(svc_a_lower, p) for p in producers)
            b_prod = any(_svc_matches(svc_b_lower, p) for p in producers)
            a_cons = any(_svc_matches(svc_a_lower, c) for c in consumers)
            b_cons = any(_svc_matches(svc_b_lower, c) for c in consumers)

            if (a_prod and b_cons) or (b_prod and a_cons):
                contracts_found.add(nid)

        # Include parent contract service nodes for any matched RPC contracts
        for nid in list(contracts_found):
            for parent_src, _, edata in self.graph.in_edges(nid, data=True):
                if edata.get("relation") == "DEFINES_RPC":
                    contracts_found.add(parent_src)

        return [self._to_code_node(c) for c in contracts_found]

    def version(self) -> str:
        """Return a version string for reproducibility logging."""
        return self._version_str
