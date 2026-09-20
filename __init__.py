"""
GRAFT-CKG: Generalized Relational Abstraction and Functional Topology
Whole-Repository Code Knowledge Graph and Agent Context Layers.

Topological Layers:
  - Lsyn      (Syntactic): AST containment, definitions, scopes.
  - Ldep      (Dependency): Imports, static & polymorphic calls (Eq. 4).
  - Lflow     (Dataflow): Def-use chains, argument passing, mutations.
  - Lsem      (Semantic): Intent embeddings, docstrings, similarity (Algorithm 1).
  - Lcontract (Contract): Protobuf/gRPC canonical services, IMPLEMENTS & CONSUMES bindings.
  - Llineage  (Lineage): Git commit history & provenance TOUCHES edges.
"""

from graft_ckg import CKGBuilder, HyperEdgeMetadata
from polyglot import TreeSitterExtractor
from multi_repo import WorkspaceCKGBuilder, WorkspaceConfig, RepoConfig
from traversal import SCKGTraversal, count_tokens
from lineage import LineageLayer
from neo4j_export import CypherExporter
from remediation import SCKGSelfHealingEngine, DefectType

__version__ = "1.0.0"
__all__ = [
    "CKGBuilder",
    "HyperEdgeMetadata",
    "TreeSitterExtractor",
    "WorkspaceCKGBuilder",
    "WorkspaceConfig",
    "RepoConfig",
    "SCKGTraversal",
    "count_tokens",
    "LineageLayer",
    "CypherExporter",
    "SCKGSelfHealingEngine",
    "DefectType",
]
