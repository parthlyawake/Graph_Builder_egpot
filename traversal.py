"""
SCKG Graph-Guided Traversal Engine.

Provides deterministic, typed graph traversal primitives across the 4 CKG layers
(Lsyn, Ldep, Lflow, Lsem) and the Contract Layer (Lcontract):
  1. blast_radius: Multi-hop transitive dependency impact analysis (upstream/downstream).
  2. downstream_consumers: Cross-service consumer identification for contracts/endpoints.
  3. contract_of: Reverse resolution from implementation/call site to governing contract.
  4. deterministic_subtree_graft: Token-bounded context subgraph extraction for LLM generation.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

# Ensure parent directory is in path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from graft_ckg import CKGBuilder


def count_tokens(text: str, model: str = "cl100k_base") -> int:
    """
    Count BPE tokens in `text` using tiktoken (OpenAI cl100k_base encoding).
    Falls back to word-count * 1.3 heuristic if tiktoken is not installed.

    Used for accurate token-redundancy metric in paper Table II (§VII-A).
    The cl100k_base encoding matches GPT-4 / GPT-3.5-turbo tokenisation.
    """
    try:
        import tiktoken
        enc = tiktoken.get_encoding(model)
        return len(enc.encode(text))
    except Exception:
        return max(1, int(len(text.split()) * 1.3))


class SCKGTraversal:
    """Graph traversal and context grafting engine over a built CKG."""

    def __init__(self, builder_or_path):
        if isinstance(builder_or_path, nx.MultiDiGraph):
            # Exported graphs can be traversed without running the builder
            # or re-cloning the original source repositories.
            from types import SimpleNamespace
            self.builder = SimpleNamespace(graph=builder_or_path,
                                           proto_services={},
                                           http_endpoints={})
            self.graph = builder_or_path
            return
        if isinstance(builder_or_path, str) and builder_or_path.endswith(".graph.json"):
            from graph_io import load_graph_json
            from types import SimpleNamespace
            graph = load_graph_json(builder_or_path)
            self.builder = SimpleNamespace(graph=graph, proto_services={},
                                           http_endpoints={})
            self.graph = graph
            return
        if isinstance(builder_or_path, str):
            if builder_or_path.endswith((".yaml", ".yml", ".json")) or (os.path.isfile(builder_or_path) and "workspace" in builder_or_path):
                from multi_repo import WorkspaceCKGBuilder
                self.builder = WorkspaceCKGBuilder(builder_or_path)
                self.builder.build()
            else:
                self.builder = CKGBuilder(builder_or_path)
                self.builder.build()
        else:
            self.builder = builder_or_path
        self.graph: nx.MultiDiGraph = self.builder.graph

    # -------------------------------------------------------------------------
    # 1. BLAST RADIUS
    # -------------------------------------------------------------------------
    def blast_radius(
        self,
        symbol_or_node: str,
        max_depth: int = 2,
        direction: str = "both",
        layers: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Computes the structural and operational blast radius of a symbol.

        Traverses typed links (CALLS, CONSUMES, IMPLEMENTS, MUTATES, FLOWS_TO, HTTP_CALLS)
        up to `max_depth` hops.

        Args:
            symbol_or_node: Symbol name or exact CKG node ID.
            max_depth: Traversal depth limit (default: 2).
            direction: 'downstream' (callees/dependents), 'upstream' (callers/consumers),
                       or 'both' (bidirectional closure).
            layers: Optional subset of layers to restrict traversal to
                    ('Lsyn', 'Ldep', 'Lflow', 'Lsem', 'Lcontract').

        Returns:
            Dict containing impacted nodes, edges, affected files, affected services,
            and an overall impact severity score.
        """
        root = self._resolve_node_id(symbol_or_node)
        if not root:
            return {"error": f"Symbol or node '{symbol_or_node}' not found in CKG."}

        layer_filter = set(layers) if layers else None
        visited_nodes: Set[str] = {root}
        traversed_edges: List[Dict[str, Any]] = []
        affected_files: Set[str] = set()
        affected_services: Set[str] = set()

        root_data = self.graph.nodes.get(root, {})
        if root_data.get("file"):
            affected_files.add(root_data["file"])
            svc = self._extract_service_name(root_data["file"])
            if svc:
                affected_services.add(svc)

        # BFS Queue: (node_id, current_depth)
        queue: List[Tuple[str, int]] = [(root, 0)]

        while queue:
            curr, depth = queue.pop(0)
            if depth >= max_depth:
                continue

            candidate_edges = []
            if direction in ("downstream", "both"):
                for _, tgt, data in self.graph.out_edges(curr, data=True):
                    candidate_edges.append((curr, tgt, data, "downstream"))
            if direction in ("upstream", "both"):
                for src, _, data in self.graph.in_edges(curr, data=True):
                    candidate_edges.append((src, curr, data, "upstream"))

            for src, tgt, data, dir_tag in candidate_edges:
                edge_layer = data.get("layer")
                rel = data.get("relation", "LINK")

                if layer_filter and edge_layer not in layer_filter:
                    continue

                other_node = tgt if dir_tag == "downstream" else src

                # Choke-point optimization: do not traverse backwards across DEFINES_RPC from an RPC
                # into the parent service_contract, which would cause combinatorial fanout into all sibling RPCs.
                if rel == "DEFINES_RPC" and dir_tag == "upstream" and self.graph.nodes.get(curr, {}).get("type") == "rpc_contract":
                    continue

                traversed_edges.append({
                    "source": src,
                    "target": tgt,
                    "relation": rel,
                    "layer": edge_layer,
                    "direction": dir_tag,
                    "depth": depth + 1,
                })

                other_data = self.graph.nodes.get(other_node, {})
                if other_data.get("file"):
                    affected_files.add(other_data["file"])
                    svc = self._extract_service_name(other_data["file"])
                    if svc:
                        affected_services.add(svc)
                elif str(other_node).startswith("contract::"):
                    affected_services.add(str(other_node).split("::", 1)[-1].split(".")[0])

                if other_node not in visited_nodes:
                    visited_nodes.add(other_node)
                    queue.append((other_node, depth + 1))

        # Classify nodes by layer/type
        node_summaries = []
        for nid in sorted(visited_nodes):
            ndata = self.graph.nodes.get(nid, {})
            node_summaries.append({
                "id": nid,
                "type": ndata.get("type", "unknown"),
                "name": ndata.get("name", nid),
                "file": ndata.get("file"),
                "line": ndata.get("line_no"),
                "service": self._extract_service_name(ndata.get("file", "")),
            })

        cross_service_count = len(affected_services)
        impact_score = round(
            len(visited_nodes) * 1.0 + len(affected_files) * 2.0 + cross_service_count * 5.0, 2
        )

        return {
            "root": root,
            "root_type": root_data.get("type"),
            "max_depth": max_depth,
            "direction": direction,
            "impact_score": impact_score,
            "total_impacted_nodes": len(visited_nodes),
            "total_traversed_edges": len(traversed_edges),
            "affected_files": sorted(list(affected_files)),
            "affected_services": sorted(list(affected_services)),
            "impacted_nodes": node_summaries,
            "edges": traversed_edges,
        }

    def event_delivery_paths(self, producer_or_node: str, max_paths: int = 100):
        """Trace only proven producer -> [exchange route] -> queue -> consumer paths.

        No message delivery link is inferred solely from matching topic names.
        Conditional broker configuration and unknown bindings stay excluded.
        """
        source = self._resolve_node_id(producer_or_node)
        if not source:
            return {"error": f"Producer '{producer_or_node}' not found."}
        paths = []
        for _, first, produced in self.graph.out_edges(source, data=True):
            if produced.get("relation") != "PRODUCES_EVENT":
                continue
            queue_paths = []
            if first.startswith("queue::amqp::") or first.startswith("topic::kafka::"):
                queue_paths.append((first, None))
            if first.startswith("topic::amqp::"):
                for _, queue, routed in self.graph.out_edges(first, data=True):
                    if routed.get("relation") == "ROUTES_TO":
                        queue_paths.append((queue, routed))
            for queue, routed in queue_paths:
                consumers = sorted({
                    consumer for consumer, _, edge in
                    self.graph.in_edges(queue, data=True)
                    if edge.get("relation") == "CONSUMES_EVENT"
                })
                schemas = sorted({
                    schema for _, schema, edge in self.graph.out_edges(first, data=True)
                    if edge.get("relation") == "PAYLOAD_SCHEMA"
                })
                for consumer in consumers:
                    paths.append({
                        "producer": source, "published_contract": first,
                        "queue_or_topic": queue, "consumer": consumer,
                        "payload_schemas": schemas,
                        "routing_evidence": routed.get("source_evidence") if routed else None,
                        "routing_kind": routed.get("binding_kind") if routed else "direct",
                        "confirmed": True,
                    })
        return {"producer": source, "path_count": min(len(paths), max_paths),
                "truncated": len(paths) > max_paths,
                "paths": paths[:max_paths]}

    # -------------------------------------------------------------------------
    # 2. DOWNSTREAM CONSUMERS
    # -------------------------------------------------------------------------
    def downstream_consumers(self, service_or_contract: str) -> Dict[str, Any]:
        """
        Finds all downstream consumers of a given contract service or RPC.

        Supports:
          - Protobuf gRPC contracts: 'ShippingService', 'ShippingService.GetQuote'
          - HTTP Endpoints: 'POST /api/checkout'
          - Source functions / stubs
        """
        node_id = self._resolve_contract_or_endpoint(service_or_contract)
        if not node_id:
            return {"error": f"Contract or endpoint '{service_or_contract}' not found."}

        target_nodes = {node_id}
        node_type = self.graph.nodes[node_id].get("type")

        # If it's a service contract, include all child RPC contracts
        if node_type == "service_contract":
            svc_name = node_id.split("::", 1)[-1]
            if svc_name in self.builder.proto_services:
                target_nodes |= set(self.builder.proto_services[svc_name]["rpcs"].values())

        consumers: List[Dict[str, Any]] = []
        seen_consumers: Set[str] = set()

        for target in target_nodes:
            for src, _, data in self.graph.in_edges(target, data=True):
                rel = data.get("relation")
                if rel in ("CONSUMES", "HTTP_CALLS"):
                    if src not in seen_consumers:
                        seen_consumers.add(src)
                        sdata = self.graph.nodes.get(src, {})
                        consumers.append({
                            "consumer_node": src,
                            "caller_name": sdata.get("name", src),
                            "file": sdata.get("file"),
                            "line": sdata.get("line_no"),
                            "service": self._extract_service_name(sdata.get("file", "")),
                            "target_contract": target,
                            "relation": rel,
                            "code_snippet": sdata.get("code", "")[:200] if sdata.get("code") else "",
                        })

        return {
            "query": service_or_contract,
            "resolved_contract_node": node_id,
            "consumer_count": len(consumers),
            "consumers": consumers,
        }

    # -------------------------------------------------------------------------
    # 3. CONTRACT OF
    # -------------------------------------------------------------------------
    def contract_of(self, function_or_symbol: str) -> Dict[str, Any]:
        """
        Reverse resolution: Finds contracts associated with a code symbol.

        Identifies:
          - Contracts implemented by this symbol (IMPLEMENTS)
          - Contracts consumed by this symbol (CONSUMES, HTTP_CALLS)
          - Structural schema definitions
        """
        node_id = self._resolve_node_id(function_or_symbol)
        if not node_id:
            return {"error": f"Symbol '{function_or_symbol}' not found in CKG."}

        implemented_contracts: List[Dict[str, Any]] = []
        consumed_contracts: List[Dict[str, Any]] = []

        # Out-edges: What does this function implement or consume?
        for _, tgt, data in self.graph.out_edges(node_id, data=True):
            rel = data.get("relation")
            if rel == "IMPLEMENTS":
                tdata = self.graph.nodes.get(tgt, {})
                implemented_contracts.append({
                    "contract_node": tgt,
                    "type": tdata.get("type"),
                    "request_type": tdata.get("request_type"),
                    "response_type": tdata.get("response_type"),
                    "file": tdata.get("file"),
                })
            elif rel in ("CONSUMES", "HTTP_CALLS"):
                tdata = self.graph.nodes.get(tgt, {})
                consumed_contracts.append({
                    "contract_node": tgt,
                    "type": tdata.get("type"),
                    "relation": rel,
                    "file": tdata.get("file"),
                })

        # In-edges: Does any contract point to this node?
        for src, _, data in self.graph.in_edges(node_id, data=True):
            rel = data.get("relation")
            if rel == "IMPLEMENTS":
                implemented_contracts.append({
                    "contract_node": src,
                    "relation": "IMPLEMENTED_BY",
                })

        return {
            "symbol": function_or_symbol,
            "node_id": node_id,
            "implements": implemented_contracts,
            "consumes": consumed_contracts,
            "is_contract_bound": len(implemented_contracts) > 0 or len(consumed_contracts) > 0,
        }

    # -------------------------------------------------------------------------
    # 4. DETERMINISTIC SUBTREE GRAFT
    # -------------------------------------------------------------------------
    def deterministic_subtree_graft(
        self,
        symbol_or_node: str,
        max_tokens: int = 2048,
        layers: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Synthesizes a minimal, bounded execution context subgraph for LLM generation.

        Traverses:
          - Target definition & docstrings
          - Base classes & interfaces (EXTENDS)
          - 1-hop callees and polymorphic dispatch targets (CALLS, POLYMORPHIC_CALL)
          - Bound contract definitions (Lcontract)
          - Key dataflow dependencies (MUTATES, RETURNS)

        Ensures strict token budget compliance without prompt bloat or hallucination.
        """
        root = self._resolve_node_id(symbol_or_node)
        if not root:
            return {"error": f"Symbol '{symbol_or_node}' not found."}

        allowed_layers = set(layers) if layers else {"Lsyn", "Ldep", "Lflow", "Lsem", "Lcontract"}
        selected_nodes: Set[str] = {root}
        selected_edges: List[Dict[str, Any]] = []

        # Multi-hop deterministic traversal (depth 2 as per Fig 2 in paper)
        queue = [(root, 0)]
        visited_in_queue = {root}

        while queue:
            curr, depth = queue.pop(0)
            if depth >= 2:
                continue

            # 1. Outgoing dependencies (callees, contracts, mutations, semantic links)
            for _, tgt, data in self.graph.out_edges(curr, data=True):
                l = data.get("layer")
                rel = data.get("relation")
                if l in allowed_layers and rel in (
                    "CALLS", "POLYMORPHIC_CALL", "CONSUMES", "IMPLEMENTS",
                    "EXTENDS", "MUTATES", "RETURNS", "HTTP_CALLS", "SEMANTIC_SIMILAR",
                    "DEFINES_RPC", "PRODUCES_EVENT", "CONSUMES_EVENT",
                    "ROUTES_TO", "PAYLOAD_SCHEMA"
                ):
                    selected_nodes.add(tgt)
                    selected_edges.append({
                        "source": curr,
                        "target": tgt,
                        "relation": rel,
                        "layer": l,
                        "confidence": data.get("metadata", {}).get("c_type", 1.0)
                        if isinstance(data.get("metadata"), dict)
                        else 1.0,
                    })
                    if tgt not in visited_in_queue:
                        visited_in_queue.add(tgt)
                        queue.append((tgt, depth + 1))

            # 2. Incoming contract bindings, consumers, or containment
            for src, _, data in self.graph.in_edges(curr, data=True):
                l = data.get("layer")
                rel = data.get("relation")

                # Choke-point optimization: if curr is an rpc_contract, do NOT step backwards
                # across DEFINES_RPC into the parent service_contract, which would pull in all sibling RPCs.
                if rel == "DEFINES_RPC" and self.graph.nodes.get(curr, {}).get("type") == "rpc_contract":
                    continue

                if l in allowed_layers and rel in (
                    "IMPLEMENTS", "CONSUMES", "CONTAINS", "DEFINES_RPC",
                    "SEMANTIC_SIMILAR", "CALLS", "CONSUMES_EVENT",
                    "PRODUCES_EVENT", "ROUTES_TO", "PAYLOAD_SCHEMA"
                ):
                    selected_nodes.add(src)
                    selected_edges.append({
                        "source": src,
                        "target": curr,
                        "relation": rel,
                        "layer": l,
                    })
                    if src not in visited_in_queue:
                        visited_in_queue.add(src)
                        queue.append((src, depth + 1))

        # Exact token budget and stable candidate ordering. Unlike the old
        # whitespace approximation, the final encoded prompt cannot exceed
        # the caller's BPE budget, including the root snippet.
        from token_grafting import pack_context
        return pack_context(self.graph, root, selected_nodes, selected_edges, max_tokens)

    # -------------------------------------------------------------------------
    # INTERNAL HELPERS
    # -------------------------------------------------------------------------
    def _resolve_node_id(self, name: str) -> Optional[str]:
        """Resolves a symbol name, node ID, or contract name to canonical node ID."""
        if name in self.graph:
            return name
        # Check contract prefixes
        if not name.startswith("contract::") and f"contract::{name}" in self.graph:
            return f"contract::{name}"
        # Check by symbol registry
        if name in self.builder.symbols_by_name:
            candidates = self.builder.symbols_by_name[name]
            if candidates:
                return candidates[0]
        # Partial match on node IDs
        for node in self.graph.nodes:
            if node.endswith(f"::{name}") or node.endswith(f".{name}") or f":{name}" in node:
                return node
        return None

    def _resolve_contract_or_endpoint(self, name: str) -> Optional[str]:
        """Resolves contract service/rpc or HTTP endpoint string."""
        if hasattr(self.builder, "_contract_node_id"):
            resolved = self.builder._contract_node_id(name)
            if resolved:
                return resolved
        candidate = name if name.startswith("contract::") else f"contract::{name}"
        if candidate in self.graph:
            return candidate
        # Check HTTP endpoints
        if name in self.graph and self.graph.nodes[name].get("type") == "http_endpoint":
            return name
        for node, data in self.graph.nodes(data=True):
            if data.get("type") == "http_endpoint":
                if name.lower() in node.lower():
                    return node
        return None

    def _extract_service_name(self, file_path: str, node_id: str = "") -> str:
        """Derives microservice name from node metadata or directory path structure."""
        if node_id and self.graph.has_node(node_id):
            repo = self.graph.nodes[node_id].get("repo")
            if repo:
                return repo
        if not file_path:
            return ""
        norm = file_path.replace("\\", "/")
        parts = norm.split("/")
        for i, p in enumerate(parts):
            if p in ("services", "src", "apps", "microservices") and i + 1 < len(parts):
                return parts[i + 1]
        # Fallback to top-level folder
        return parts[0] if parts else ""

    def _format_node_fallback(self, node_id: str) -> str:
        ndata = self.graph.nodes.get(node_id, {})
        return f"# Symbol: {ndata.get('name', node_id)} (type: {ndata.get('type', 'symbol')})"


# -----------------------------------------------------------------------------
# CLI INTERFACE
# -----------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="SCKG Traversal & Context Subtree Grafting Engine"
    )
    parser.add_argument("--repo", help="Path to repository")
    parser.add_argument("--workspace", help="Path to workspace.yaml or workspace.json manifest")
    parser.add_argument("--blast-radius", dest="blast_radius", help="Symbol or node for blast radius calculation")
    parser.add_argument("--depth", type=int, default=2, help="Max depth for blast radius traversal")
    parser.add_argument("--direction", choices=["downstream", "upstream", "both"], default="both", help="Traversal direction")
    parser.add_argument("--consumers", help="Contract service/RPC to find downstream consumers for")
    parser.add_argument("--contract-of", dest="contract_of", help="Find contract associated with symbol")
    parser.add_argument("--graft", help="Extract deterministic subtree grafted context for LLM prompt")
    parser.add_argument("--max-tokens", type=int, default=2048, help="Max token budget for grafted context")
    parser.add_argument("--json", action="store_true", help="Print output as JSON")
    args = parser.parse_args()

    target = args.workspace or args.repo
    if not target:
        parser.error("Either --repo or --workspace must be provided.")

    traversal = SCKGTraversal(target)

    if args.blast_radius:
        res = traversal.blast_radius(args.blast_radius, max_depth=args.depth, direction=args.direction)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print("\n" + "=" * 70)
            print(f"SCKG BLAST RADIUS: '{args.blast_radius}' (depth={args.depth}, direction={args.direction})")
            print("=" * 70)
            print(f"Impact Score:            {res.get('impact_score')}")
            print(f"Total Impacted Nodes:    {res.get('total_impacted_nodes')}")
            print(f"Total Traversed Edges:   {res.get('total_traversed_edges')}")
            print(f"Affected Microservices:  {', '.join(res.get('affected_services', [])) or 'None'}")
            print(f"Affected Files:          {len(res.get('affected_files', []))}")
            for f in res.get("affected_files", []):
                print(f"  * {f}")
            print("\nKey Impacted Entities:")
            for node in res.get("impacted_nodes", [])[:10]:
                print(f"  - [{node.get('type')}] {node.get('id')} ({node.get('file')})")

    elif args.consumers:
        res = traversal.downstream_consumers(args.consumers)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print("\n" + "=" * 70)
            print(f"SCKG DOWNSTREAM CONSUMERS FOR: '{args.consumers}'")
            print("=" * 70)
            print(f"Resolved Contract Node: {res.get('resolved_contract_node')}")
            print(f"Consumer Call-Sites:    {res.get('consumer_count')}")
            for c in res.get("consumers", []):
                print(f"  * [{c.get('service') or 'local'}] {c.get('caller_name')} ({c.get('file')}:{c.get('line')})")

    elif args.contract_of:
        res = traversal.contract_of(args.contract_of)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print("\n" + "=" * 70)
            print(f"SCKG CONTRACT-OF MAPPING FOR: '{args.contract_of}'")
            print("=" * 70)
            print(f"Node ID:          {res.get('node_id')}")
            print(f"Contract-Bound:   {res.get('is_contract_bound')}")
            if res.get("implements"):
                print("Implements:")
                for imp in res["implements"]:
                    print(f"  - {imp.get('contract_node')} ({imp.get('type', '')})")
            if res.get("consumes"):
                print("Consumes:")
                for con in res["consumes"]:
                    print(f"  - {con.get('contract_node')} (via {con.get('relation')})")

    elif args.graft:
        res = traversal.deterministic_subtree_graft(args.graft, max_tokens=args.max_tokens)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print("\n" + "=" * 70)
            print(f"DETERMINISTIC SUBTREE GRAFT: '{args.graft}' (Budget: {args.max_tokens} tokens)")
            print("=" * 70)
            print(f"Subtree Size:    {res.get('node_count')} nodes, {res.get('edge_count')} edges")
            print(f"Approx Tokens:   {res.get('approx_tokens')}")
            print("\n=== GENERATED CONTEXT FOR LLM PROMPT ===")
            print(res.get("grafted_context"))


if __name__ == "__main__":
    main()
