"""
Graph-layer data contracts.

Defines the core types that flow through the GraphProvider interface:
CodeNode, TypedEdge, InducedSubgraph, CandidateRootCause, CausalPath,
TelemetryEvent, and TraversalPolicy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class NodeType(str, Enum):
    """Types of nodes in the Semantic Code Knowledge Graph."""
    FUNCTION = "function"
    CLASS = "class"
    SERVICE = "service"
    CONTRACT = "contract"       # e.g., a Protobuf message / OpenAPI endpoint
    TOPIC_CONTRACT = "topic_contract"  # e.g., Kafka / RabbitMQ message topic
    ENDPOINT = "endpoint"       # e.g., REST / HTTP route endpoint
    HTTP_CALLSITE = "http_callsite"  # request with an unresolved host
    COMMIT = "commit"
    FILE = "file"
    MODULE = "module"
    DEPLOYMENT = "deployment"


class EdgeType(str, Enum):
    """Types of edges (relationships) in the SCKG."""
    CALLS = "calls"
    IMPLEMENTS = "implements"
    DEPENDS_ON = "depends_on"
    BREAKS_CONTRACT = "breaks_contract"
    DEFINES = "defines"
    IMPORTS = "imports"
    PRODUCES = "produces"        # service produces a gRPC/REST endpoint
    CONSUMES = "consumes"        # service consumes an endpoint
    PRODUCES_EVENT = "produces_event"  # service publishes to a topic
    CONSUMES_EVENT = "consumes_event"  # service listens to a topic
    HTTP_CALLS = "http_calls"    # service calls a REST endpoint
    HTTP_REQUEST = "http_request"  # function makes an unresolved-host request
    POSSIBLE_HTTP_TARGET = "possible_http_target"  # path match without host proof
    MODIFIED_BY = "modified_by"  # code node was changed by a commit


class Language(str, Enum):
    """Supported programming languages."""
    PYTHON = "python"
    GO = "go"
    JAVA = "java"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    PROTOBUF = "protobuf"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Core graph types
# ---------------------------------------------------------------------------

@dataclass
class CodeNode:
    """A single node in the Semantic Code Knowledge Graph."""

    node_id: str
    node_type: NodeType
    name: str
    language: Language = Language.UNKNOWN
    file_path: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    source_snippet: Optional[str] = None
    signature: Optional[str] = None       # e.g., function signature only
    service_name: Optional[str] = None    # which microservice this belongs to
    metadata: dict[str, Any] = field(default_factory=dict)

    def short_label(self) -> str:
        """Human-readable short label for logging/display."""
        svc = f"[{self.service_name}] " if self.service_name else ""
        return f"{svc}{self.node_type.value}:{self.name}"


@dataclass
class TypedEdge:
    """A typed, directed edge between two CodeNodes."""

    source_id: str
    target_id: str
    edge_type: EdgeType
    metadata: dict[str, Any] = field(default_factory=dict)

    def short_label(self) -> str:
        return f"{self.source_id} --[{self.edge_type.value}]--> {self.target_id}"


@dataclass
class TelemetryEvent:
    """
    A runtime anomaly that triggers remediation.

    In a real system this comes from logs, metrics, or traces.
    For the prototype we hand-author these.
    """

    event_id: str = ""
    service_name: str = ""
    error_type: str = ""                  # e.g., "HTTP_500", "gRPC_UNIMPLEMENTED"
    message: str = ""                     # raw error message / log line
    timestamp: Optional[str] = None
    stack_trace: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TraversalPolicy:
    """Controls how far / how aggressively the graph is traversed."""

    max_depth: int = 4
    max_nodes: int = 50
    entropy_threshold: float = 0.7        # for EG-POT; ignored by simpler traversals
    include_node_types: Optional[list[NodeType]] = None
    exclude_node_types: Optional[list[NodeType]] = None


# ---------------------------------------------------------------------------
# Composite types
# ---------------------------------------------------------------------------

@dataclass
class CandidateRootCause:
    """A ranked candidate root-cause node with confidence and evidence."""

    node: CodeNode
    confidence: float                     # 0.0 – 1.0
    evidence: list[str] = field(default_factory=list)  # human-readable evidence trail
    rank: int = 0


@dataclass
class CausalPath:
    """An ordered chain of nodes + edges explaining 'A caused B caused C'."""

    nodes: list[CodeNode] = field(default_factory=list)
    edges: list[TypedEdge] = field(default_factory=list)

    def to_narrative(self) -> str:
        """Render the causal path as a human-readable narrative."""
        if not self.nodes:
            return "No causal path available."

        parts: list[str] = []
        for i, node in enumerate(self.nodes):
            parts.append(f"  Step {i + 1}: {node.short_label()}")
            if i < len(self.edges):
                parts.append(f"    ──[{self.edges[i].edge_type.value}]──▶")
        return "\n".join(parts)


@dataclass
class InducedSubgraph:
    """
    The blast-radius context object.

    Contains the set of nodes and edges reachable from a root-cause node
    via forward traversal.  This is the primary data structure passed to
    the LLM for patch generation.
    """

    root_node_id: str
    nodes: list[CodeNode] = field(default_factory=list)
    edges: list[TypedEdge] = field(default_factory=list)

    # ---- Computed helpers --------------------------------------------------

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    @property
    def services_affected(self) -> set[str]:
        return {n.service_name for n in self.nodes if n.service_name}

    def _node_map(self) -> dict[str, CodeNode]:
        return {n.node_id: n for n in self.nodes}

    # ---- Serialization for LLM prompts ------------------------------------

    def to_prompt_context(self, strategy: str = "full_source") -> str:
        """
        Serialize the subgraph into an LLM-friendly text block.

        Strategies:
          - "full_source"     : include full source snippets
          - "signatures_only" : include only function signatures
          - "narrative"       : natural-language summary
        """
        serializers = {
            "full_source": self._serialize_full,
            "signatures_only": self._serialize_signatures,
            "narrative": self._serialize_narrative,
        }
        serializer = serializers.get(strategy, self._serialize_full)
        return serializer()

    def estimated_tokens(self) -> int:
        """Rough token estimate (1 token ≈ 4 chars)."""
        full = self._serialize_full()
        return len(full) // 4

    # ---- Private serializers -----------------------------------------------

    def _serialize_full(self) -> str:
        node_map = self._node_map()
        sections: list[str] = []
        sections.append(
            f"=== Blast Radius Subgraph ({self.node_count} nodes, "
            f"{self.edge_count} edges, services: "
            f"{', '.join(self.services_affected)}) ==="
        )

        # Group nodes by service
        by_service: dict[str, list[CodeNode]] = {}
        for n in self.nodes:
            svc = n.service_name or "unknown"
            by_service.setdefault(svc, []).append(n)

        for svc, nodes in by_service.items():
            sections.append(f"\n--- Service: {svc} ---")
            for n in nodes:
                sections.append(
                    f"\n[{n.node_type.value}] {n.name}"
                    f"  (file: {n.file_path or 'N/A'}, "
                    f"lines: {n.line_start}-{n.line_end})"
                )
                if n.source_snippet:
                    sections.append(f"```{n.language.value}")
                    sections.append(n.source_snippet)
                    sections.append("```")

        sections.append("\n--- Relationships ---")
        for e in self.edges:
            src = node_map.get(e.source_id)
            tgt = node_map.get(e.target_id)
            src_label = src.short_label() if src else e.source_id
            tgt_label = tgt.short_label() if tgt else e.target_id
            sections.append(f"  {src_label} --[{e.edge_type.value}]--> {tgt_label}")

        return "\n".join(sections)

    def _serialize_signatures(self) -> str:
        sections: list[str] = []
        sections.append(
            f"=== Blast Radius (signatures only, {self.node_count} nodes) ==="
        )
        for n in self.nodes:
            sig = n.signature or n.name
            sections.append(f"  [{n.service_name or '?'}] {n.node_type.value}: {sig}")

        sections.append("\n--- Key Relationships ---")
        for e in self.edges:
            sections.append(f"  {e.source_id} --[{e.edge_type.value}]--> {e.target_id}")
        return "\n".join(sections)

    def _serialize_narrative(self) -> str:
        parts: list[str] = [
            f"The change at the root cause affects {self.node_count} code elements "
            f"across {len(self.services_affected)} service(s): "
            f"{', '.join(self.services_affected)}.",
            "",
            "Affected components:",
        ]
        for n in self.nodes:
            parts.append(
                f"  - {n.short_label()} in {n.file_path or 'unknown file'}"
            )
        return "\n".join(parts)
