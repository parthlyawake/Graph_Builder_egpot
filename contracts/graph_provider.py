"""
GraphProvider -- abstract interface for the SCKG + traversal layer.

This is the pluggable boundary between the orchestrator and the graph.
The orchestrator never knows how the graph is built or how traversal
works internally -- it only talks through this contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from contracts.graph_types import (
    CandidateRootCause,
    CausalPath,
    CodeNode,
    InducedSubgraph,
    TelemetryEvent,
    TraversalPolicy,
)


class GraphProvider(ABC):
    """
    Abstract interface for the Semantic Code Knowledge Graph.

    Implementations:
      - MockGraphProvider   (hand-authored, for testing)
      - NullGraphProvider   (no-graph baseline, for ablation)
      - SCKGProvider        (real Neo4j / NetworkX, future)
    """

    @abstractmethod
    def resolve_symptom(self, symptom: TelemetryEvent) -> list[CodeNode]:
        """
        Map an unstructured telemetry event to concrete code nodes.

        This is a fuzzy NLP / embedding step -- separate from the
        deterministic graph traversal in backward_traverse.
        """
        ...

    @abstractmethod
    def backward_traverse(
        self, node: CodeNode, policy: TraversalPolicy
    ) -> list[CandidateRootCause]:
        """
        From a symptom-linked node, walk backward through the graph
        to find ranked candidate root causes.

        Returns: list of CandidateRootCause, ordered by confidence descending.
        """
        ...

    @abstractmethod
    def forward_traverse(
        self, node: CodeNode, policy: TraversalPolicy
    ) -> InducedSubgraph:
        """
        From a root-cause node, walk forward to extract the blast-radius
        subgraph -- all downstream consumers and affected contracts.
        """
        ...

    @abstractmethod
    def get_node_detail(self, node_id: str) -> CodeNode:
        """Fetch full details for a single node by ID."""
        ...

    @abstractmethod
    def explain_path(
        self, node_a: CodeNode, node_b: CodeNode
    ) -> CausalPath:
        """
        Construct a causal explanation chain from node_a to node_b.

        Used in the EXPLAIN phase to generate human-readable rationale.
        """
        ...

    @abstractmethod
    def find_node_by_name(
        self, name: str, file_path: str | None = None
    ) -> list[CodeNode]:
        """
        Fuzzy lookup: find nodes matching a name.

        Used by the OpenHands graph tools when the agent discovers a
        function name in code and wants to query the graph about it.
        The agent has strings like 'post_order_recommendations', not node IDs.

        Parameters
        ----------
        name:
            Function/class/contract name to search for.
        file_path:
            Optional file path to narrow the search.

        Returns: list of matching CodeNodes (may be empty).
        """
        ...

    @abstractmethod
    def get_contract_between(
        self, service_a: str, service_b: str
    ) -> list[CodeNode]:
        """
        Return all contract nodes (proto, OpenAPI) shared between two services.

        Used by the OpenHands contract tool when the agent asks:
        'What's the API contract between checkout-service and frontend-service?'
        """
        ...

    @abstractmethod
    def version(self) -> str:
        """Return a version string for reproducibility logging."""
        ...
