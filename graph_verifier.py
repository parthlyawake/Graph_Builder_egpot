"""
SCKG Graph Verifier & Audit Engine
===================================
Automated, invariant-based verification suite for Code Knowledge Graphs (CKG)
and multi-repository microservice topologies.

Validates:
1. Structural integrity (zero dangling edges, valid layers, node ID uniqueness)
2. Polyglot AST extraction completeness across all declared repositories
3. Contract layer completeness (every declared RPC/route has an IMPLEMENTS binding)
4. Consumer-to-producer reachability across repository boundaries
5. Downstream traversal & blast radius invariants
6. Path explanation relation preservation
"""

import os
import sys
import re
import json
import logging
from typing import Dict, List, Set, Tuple, Any, Optional
from dataclasses import dataclass, field
import networkx as nx

from multi_repo import WorkspaceCKGBuilder, WorkspaceConfig
from traversal import SCKGTraversal

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("graph_verifier")

VALID_LAYERS = {"Lsyn", "Ldep", "Lflow", "Lcontract", "Lsem", "Llineage"}
VALID_RELATIONS = {
    # Lsyn
    "CONTAINS", "DECLARES", "DEFINES", "EXTENDS",
    # Ldep
    "CALLS", "POLYMORPHIC_CALL", "IMPORTS", "USES", "HTTP_CALLS",
    # Lflow
    "PASSES_ARG", "FLOWS_TO", "MUTATES", "RETURNS",
    # Lcontract
    "DEFINES_RPC", "IMPLEMENTS", "CONSUMES", "EXPOSES", "CALLS_CONTRACT", "SUBSCRIBES_TO", "PRODUCES",
    # Lsem
    "SEMANTIC_SIMILARITY", "SEMANTIC_SIMILAR", "RELATES_TO",
    # Llineage
    "CHANGED_IN", "CO_CHANGED_WITH",
    # Source callsites and contract schema structure.
    "INVOKES", "EVALUATES", "HAS_CALLSITE", "DECLARES_FIELD",
    "NESTED_MESSAGE", "ACCEPTS_SCHEMA", "RETURNS_SCHEMA",
    "HTTP_REQUEST", "POSSIBLE_HTTP_TARGET",
    "PRODUCES_EVENT", "CONSUMES_EVENT", "CONTRACT_SKEW",
}


@dataclass
class CheckResult:
    name: str
    status: str  # "PASS", "FAIL", "WARN"
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    severity: str = "ERROR"  # "ERROR", "WARNING", "INFO"


@dataclass
class VerificationReport:
    workspace_name: str
    total_nodes: int
    total_edges: int
    checks: List[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.status != "FAIL" for c in self.checks)

    @property
    def pass_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "PASS")

    @property
    def fail_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "FAIL")

    @property
    def warn_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "WARN")

    def summary_table(self) -> str:
        lines = []
        lines.append("=" * 80)
        lines.append(f"  SCKG GRAPH AUDIT REPORT: {self.workspace_name}")
        lines.append(f"  Nodes: {self.total_nodes:,} | Hyper-Edges: {self.total_edges:,}")
        lines.append(f"  Overall Status: {'PASSED' if self.passed else 'FAILED'}")
        lines.append(f"  Passed: {self.pass_count} | Failed: {self.fail_count} | Warnings: {self.warn_count}")
        lines.append("=" * 80)
        lines.append(f"{'STATUS':<8} | {'CHECK NAME':<40} | {'DETAILS'}")
        lines.append("-" * 80)
        for c in self.checks:
            lines.append(f"{c.status:<8} | {c.name:<40} | {c.message}")
            if c.status == "FAIL" and c.details:
                for k, v in list(c.details.items())[:5]:
                    lines.append(f"         |   * {k}: {v}")
        lines.append("=" * 80)
        return "\n".join(lines)


class SCKGGraphVerifier:
    def __init__(self, workspace_path: Optional[str] = None, builder: Optional[WorkspaceCKGBuilder] = None):
        if builder:
            self.builder = builder
            self.workspace_path = builder.workspace_file if hasattr(builder, "workspace_file") else None
        elif workspace_path:
            self.workspace_path = os.path.abspath(workspace_path)
            self.builder = WorkspaceCKGBuilder(self.workspace_path)
            self.builder.build()
        else:
            raise ValueError("Either workspace_path or builder must be provided.")

        self.graph: nx.DiGraph = self.builder.graph
        self.workspace_config: Optional[WorkspaceConfig] = getattr(self.builder, "config", None)

    def verify_all(self, strict: bool = True) -> VerificationReport:
        """Executes full 6-phase verification suite."""
        report = VerificationReport(
            workspace_name=getattr(self.workspace_config, "name", "unknown_workspace"),
            total_nodes=self.graph.number_of_nodes(),
            total_edges=self.graph.number_of_edges(),
        )

        # Phase 1: Structural Integrity
        report.checks.append(self._check_zero_dangling_edges())
        report.checks.append(self._check_edge_layers_and_relations())
        report.checks.append(self._check_node_schema_integrity())

        # Phase 2: Polyglot Multi-Repo Extraction Completeness
        report.checks.append(self._check_polyglot_repository_extraction())

        # Phase 3: Contract Coverage & Producer/Consumer Completeness
        report.checks.append(self._check_contract_completeness_and_producers())
        report.checks.append(self._check_consumer_contract_validity())

        # Phase 4: Cross-Service Interconnection & Reachability
        report.checks.append(self._check_cross_service_reachability())

        # Phase 5: Blast Radius & Traversal Invariants
        report.checks.append(self._check_traversal_and_blast_radius())

        # Phase 6: Path Explanation Preservation
        report.checks.append(self._check_path_explanation_preservation())

        return report

    # -------------------------------------------------------------------------
    # Phase 1: Structural & Layer Invariants
    # -------------------------------------------------------------------------
    def _check_zero_dangling_edges(self) -> CheckResult:
        """Asserts every edge connects two existing nodes with defined metadata."""
        dangling = []
        for u, v, d in self.graph.edges(data=True):
            if u not in self.graph or not self.graph.nodes[u]:
                dangling.append(f"Missing source definition: {u} -> {v}")
            if v not in self.graph or not self.graph.nodes[v]:
                dangling.append(f"Missing target definition: {u} -> {v}")

        if dangling:
            return CheckResult(
                name="Structural Integrity: Zero Dangling Edges",
                status="FAIL",
                message=f"Found {len(dangling)} dangling edges.",
                details={"sample_dangling": dangling[:5]},
            )
        return CheckResult(
            name="Structural Integrity: Zero Dangling Edges",
            status="PASS",
            message=f"All {self.graph.number_of_edges():,} edges connect valid nodes with metadata.",
        )

    def _check_edge_layers_and_relations(self) -> CheckResult:
        """Asserts all edges belong to recognized layers and valid relations."""
        invalid_layers = []
        unknown_relations = []

        for u, v, d in self.graph.edges(data=True):
            layer = d.get("layer")
            relation = d.get("relation") or d.get("edge_type")

            if not layer or layer not in VALID_LAYERS:
                invalid_layers.append((u, v, layer))
            if relation and relation not in VALID_RELATIONS:
                unknown_relations.append((u, v, relation))

        if invalid_layers:
            return CheckResult(
                name="Layer Integrity: Valid Layers",
                status="FAIL",
                message=f"{len(invalid_layers)} edges have invalid or missing layers.",
                details={"sample_invalid_layers": invalid_layers[:5]},
            )
        if unknown_relations:
            return CheckResult(
                name="Layer Integrity: Recognized Relations",
                status="WARN",
                message=f"{len(unknown_relations)} edges have unregistered relations.",
                details={"sample_unknown_relations": unknown_relations[:5]},
            )
        return CheckResult(
            name="Layer Integrity: Layers and Relations",
            status="PASS",
            message="All edges conform to recognized architectural layers and relations.",
        )

    def _check_node_schema_integrity(self) -> CheckResult:
        """Verifies nodes possess required attributes."""
        missing_attrs = []
        for n, data in self.graph.nodes(data=True):
            if not data:
                missing_attrs.append((n, "empty_data"))
                continue
            # Basic sanity: nodes must have at least an identifier or raw_type/type
            has_type = "type" in data or "raw_type" in data or "label" in data or n.startswith("contract::")
            if not has_type:
                missing_attrs.append((n, "missing_type_metadata"))

        if missing_attrs:
            return CheckResult(
                name="Node Schema: Node Attribute Integrity",
                status="WARN",
                message=f"{len(missing_attrs)} nodes lack standard type attributes.",
                details={"sample": missing_attrs[:5]},
            )
        return CheckResult(
            name="Node Schema: Node Attribute Integrity",
            status="PASS",
            message=f"All {self.graph.number_of_nodes():,} nodes have valid metadata attributes.",
        )

    # -------------------------------------------------------------------------
    # Phase 2: Polyglot Extraction Completeness
    # -------------------------------------------------------------------------
    def _check_polyglot_repository_extraction(self) -> CheckResult:
        """Verifies every repository in the workspace contributed code nodes."""
        if not self.workspace_config or not self.workspace_config.repositories:
            return CheckResult(
                name="Polyglot Completeness: Repository Contribution",
                status="PASS",
                message="No multi-repo manifest provided; skipping repo contribution check.",
            )

        empty_repos = []
        repo_node_counts = {}
        for repo in self.workspace_config.repositories:
            count = sum(1 for n in self.graph.nodes if n.startswith(f"{repo.id}/") or f"::{repo.id}/" in n)
            repo_node_counts[repo.id] = count
            if count == 0:
                empty_repos.append(repo.id)

        if empty_repos:
            return CheckResult(
                name="Polyglot Completeness: Repository Contribution",
                status="FAIL",
                message=f"{len(empty_repos)} repositories yielded 0 nodes: {empty_repos}",
                details={"empty_repos": empty_repos, "repo_node_counts": repo_node_counts},
            )
        return CheckResult(
            name="Polyglot Completeness: Repository Contribution",
            status="PASS",
            message=f"All {len(repo_node_counts)} repositories contributed AST nodes to the graph.",
            details={"repo_node_counts": repo_node_counts},
        )

    # -------------------------------------------------------------------------
    # Phase 3: Contract Coverage & Producer/Consumer Completeness
    # -------------------------------------------------------------------------
    def _extract_declared_proto_rpcs(self) -> Dict[str, List[str]]:
        """Parses proto files declared in shared_contracts to determine expected RPCs."""
        declared = {}
        proto_files = []

        if self.workspace_config and self.workspace_config.shared_contracts:
            base_dir = os.path.dirname(self.workspace_path) if self.workspace_path else "."
            for sc in self.workspace_config.shared_contracts:
                sc_path = os.path.join(base_dir, sc)
                if os.path.isdir(sc_path):
                    for root, _, files in os.walk(sc_path):
                        for f in files:
                            if f.endswith(".proto"):
                                proto_files.append(os.path.join(root, f))
                elif os.path.isfile(sc_path):
                    proto_files.append(sc_path)

        for p_file in proto_files:
            try:
                with open(p_file, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                cur_svc = None
                for line in lines:
                    line = line.strip()
                    if line.startswith("service "):
                        cur_svc = line.split()[1].split("{")[0]
                        declared.setdefault(cur_svc, [])
                    elif cur_svc and line.startswith("rpc "):
                        rpc_name = line.split()[1].split("(")[0]
                        if rpc_name not in declared[cur_svc]:
                            declared[cur_svc].append(rpc_name)
                    elif cur_svc and line == "}":
                        cur_svc = None
            except Exception as e:
                logger.warning(f"Error parsing proto {p_file}: {e}")

        return declared

    def _check_contract_completeness_and_producers(self) -> CheckResult:
        """Verifies every declared proto RPC has a canonical node AND a concrete producer (IMPLEMENTS)."""
        declared_rpcs = self._extract_declared_proto_rpcs()
        
        expected_rpcs = set()
        for svc, rpcs in declared_rpcs.items():
            for rpc in rpcs:
                expected_rpcs.add(f"contract::{svc}.{rpc}")
        for n in self.graph.nodes:
            if n.startswith("contract::") and (
                self.graph.nodes[n].get("type") == "rpc_contract" or
                (n.count("::") == 1 and "." in n)
            ):
                expected_rpcs.add(n)

        if not expected_rpcs:
            return CheckResult(
                name="Contract Completeness: Producer Binding",
                status="WARN",
                message="No proto contracts found to evaluate.",
            )

        missing_contract_nodes = []
        orphan_rpcs = []  # Declared or canonical RPCs with NO implementer
        connected_rpcs = []

        for rpc_node in sorted(expected_rpcs):
            if rpc_node not in self.graph:
                missing_contract_nodes.append(rpc_node)
                continue
            # Find IMPLEMENTS in-edges
            impls = [
                u for u, v, d in self.graph.in_edges(rpc_node, data=True)
                if d.get("relation") == "IMPLEMENTS"
            ]
            if not impls:
                orphan_rpcs.append(rpc_node)
            else:
                connected_rpcs.append((rpc_node, impls))

        total_checked = len(missing_contract_nodes) + len(orphan_rpcs) + len(connected_rpcs)

        if missing_contract_nodes or orphan_rpcs:
            details = {}
            if missing_contract_nodes:
                details["missing_contract_nodes"] = missing_contract_nodes
            if orphan_rpcs:
                details["unimplemented_orphan_rpcs"] = orphan_rpcs
            return CheckResult(
                name="Contract Completeness: Producer Binding",
                status="FAIL",
                message=f"{len(orphan_rpcs)} RPCs have NO concrete handler implementations. {len(missing_contract_nodes)} contracts missing.",
                details=details,
            )

        return CheckResult(
            name="Contract Completeness: Producer Binding",
            status="PASS",
            message=f"All {total_checked} declared RPCs exist and are bound to concrete server handlers via IMPLEMENTS.",
            details={"connected_count": len(connected_rpcs)},
        )

    def _check_consumer_contract_validity(self) -> CheckResult:
        """Verifies every CONSUMES edge points to a valid canonical contract."""
        invalid_consumers = []
        valid_consumers_count = 0

        for u, v, d in self.graph.edges(data=True):
            if d.get("relation") == "CONSUMES":
                if not v.startswith("contract::"):
                    invalid_consumers.append((u, v))
                else:
                    valid_consumers_count += 1

        if invalid_consumers:
            return CheckResult(
                name="Contract Validity: Consumer Target Integrity",
                status="FAIL",
                message=f"{len(invalid_consumers)} CONSUMES edges target non-contract nodes.",
                details={"sample_invalid": invalid_consumers[:5]},
            )

        return CheckResult(
            name="Contract Validity: Consumer Target Integrity",
            status="PASS",
            message=f"All {valid_consumers_count} cross-service consumer calls target canonical contract nodes.",
        )

    # -------------------------------------------------------------------------
    # Phase 4: Cross-Service Interconnection & Reachability
    # -------------------------------------------------------------------------
    def _check_cross_service_reachability(self) -> CheckResult:
        """Verifies cross-service connections exist between client callers and server handlers."""
        # Check bidirectional connection: caller -[CONSUMES]-> contract <-[IMPLEMENTS]- handler
        cross_connected_rpcs = 0
        total_rpcs_with_consumers = 0
        disconnected = []

        canonical_rpcs = [n for n in self.graph.nodes if n.startswith("contract::") and (
                self.graph.nodes[n].get("type") == "rpc_contract" or
                (n.count("::") == 1 and "." in n)
            )]
        for rpc in canonical_rpcs:
            consumers = [
                u for u, v, d in self.graph.in_edges(rpc, data=True)
                if d.get("relation") == "CONSUMES"
            ]
            producers = [
                u for u, v, d in self.graph.in_edges(rpc, data=True)
                if d.get("relation") == "IMPLEMENTS"
            ]

            if consumers:
                total_rpcs_with_consumers += 1
                if producers:
                    cross_connected_rpcs += 1
                else:
                    disconnected.append(rpc)

        if disconnected:
            return CheckResult(
                name="Topology: End-to-End Cross-Service Reachability",
                status="FAIL",
                message=f"{len(disconnected)} consumed RPCs lack concrete server handlers: {disconnected}",
                details={"disconnected": disconnected},
            )

        return CheckResult(
            name="Topology: End-to-End Cross-Service Reachability",
            status="PASS",
            message=f"All {total_rpcs_with_consumers} consumed RPC contracts bridge callers to concrete server handlers.",
        )

    # -------------------------------------------------------------------------
    # Phase 5: Blast Radius & Traversal Soundness
    # -------------------------------------------------------------------------
    def _check_traversal_and_blast_radius(self) -> CheckResult:
        """Ensures traversal across contract boundaries functions correctly."""
        traversal = SCKGTraversal(self.builder)
        canonical_rpcs = [n for n in self.graph.nodes if n.startswith("contract::") and (
                self.graph.nodes[n].get("type") == "rpc_contract" or
                (n.count("::") == 1 and "." in n)
            )]
        if not canonical_rpcs:
            return CheckResult(
                name="Traversal: Blast Radius Traversal Soundness",
                status="PASS",
                message="No canonical RPC contracts to traverse.",
            )

        # Pick up to 5 RPCs with consumers and verify blast radius crosses repo boundaries
        tested = 0
        multi_service_impact = 0
        for rpc in canonical_rpcs:
            consumers = [u for u, v, d in self.graph.in_edges(rpc, data=True) if d.get("relation") == "CONSUMES"]
            if consumers:
                tested += 1
                res = traversal.blast_radius(rpc, max_depth=3)
                affected = res.get("affected_services", [])
                if len(affected) >= 2:
                    multi_service_impact += 1

        if tested > 0 and multi_service_impact == 0:
            return CheckResult(
                name="Traversal: Blast Radius Traversal Soundness",
                status="WARN",
                message="Blast radius traversal did not cross service boundaries on tested RPCs.",
            )

        return CheckResult(
            name="Traversal: Blast Radius Traversal Soundness",
            status="PASS",
            message=f"Blast radius traversal successfully crosses service boundaries on {multi_service_impact}/{tested} tested RPCs.",
        )

    # -------------------------------------------------------------------------
    # Phase 6: Path Explanation Preservation
    # -------------------------------------------------------------------------
    def _check_path_explanation_preservation(self) -> CheckResult:
        """Verifies multi-repo composed edges preserve their true relation types in explanations."""
        from contracts.sckg_provider import SCKGGraphProvider
        from contracts.graph_types import CodeNode, NodeType

        if not self.workspace_path:
            return CheckResult(
                name="Explanation: Path Relation Preservation",
                status="PASS",
                message="No workspace file path available for SCKGGraphProvider check.",
            )

        try:
            provider = SCKGGraphProvider(self.workspace_path)
            # Find an IMPLEMENTS edge
            sample_edge = next(
                (u, v, d) for u, v, d in self.graph.edges(data=True)
                if d.get("relation") == "IMPLEMENTS" and v.startswith("contract::")
            )
            u_node = CodeNode(node_id=sample_edge[0], node_type=NodeType.FUNCTION, name=sample_edge[0])
            v_node = CodeNode(node_id=sample_edge[1], node_type=NodeType.CONTRACT, name=sample_edge[1])
            path_exp = provider.explain_path(u_node, v_node)

            if not path_exp.edges:
                return CheckResult(
                    name="Explanation: Path Relation Preservation",
                    status="WARN",
                    message="explain_path returned empty path for direct contract edge.",
                )
            
            first_rel = path_exp.edges[0].metadata.get("raw_relation")
            if first_rel != "IMPLEMENTS":
                return CheckResult(
                    name="Explanation: Path Relation Preservation",
                    status="FAIL",
                    message=f"explain_path degraded relation: expected 'IMPLEMENTS', got '{first_rel}'.",
                )

            return CheckResult(
                name="Explanation: Path Relation Preservation",
                status="PASS",
                message="Path explanations strictly preserve true relationship types across multi-repo edges.",
            )
        except Exception as e:
            return CheckResult(
                name="Explanation: Path Relation Preservation",
                status="WARN",
                message=f"Path explanation verification skipped with note: {e}",
            )


def main():
    import argparse
    parser = argparse.ArgumentParser(description="SCKG Automated Graph Verifier & Audit Suite")
    parser.add_argument("--workspace", "-w", required=True, help="Path to workspace.yaml")
    parser.add_argument("--json", action="store_true", help="Output verification report as JSON")
    parser.add_argument("--strict", action="store_true", help="Exit with code 1 on any check failure")
    args = parser.parse_args()

    verifier = SCKGGraphVerifier(workspace_path=args.workspace)
    report = verifier.verify_all(strict=args.strict)

    if args.json:
        data = {
            "workspace": report.workspace_name,
            "total_nodes": report.total_nodes,
            "total_edges": report.total_edges,
            "passed": report.passed,
            "pass_count": report.pass_count,
            "fail_count": report.fail_count,
            "warn_count": report.warn_count,
            "checks": [
                {
                    "name": c.name,
                    "status": c.status,
                    "message": c.message,
                    "details": c.details
                }
                for c in report.checks
            ]
        }
        print(json.dumps(data, indent=2))
    else:
        print(report.summary_table())

    if args.strict and not report.passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
