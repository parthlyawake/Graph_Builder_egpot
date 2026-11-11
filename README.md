# SCKG Graph Builder

A polyglot, multi-repository Source Code Knowledge Graph (SCKG) construction engine for distributed software systems. SCKG Graph Builder parses source code across multiple programming languages and Git repositories simultaneously, producing a single unified directed graph that captures syntactic structure, dependency relationships, dataflow chains, semantic similarity, and cross-service API contracts.

Run the [local graph viewer](TEAMMATE_GRAPH_GUIDE.md) on your repository, read the [contract graph guide](CONTRACTS.md), or review the [hybrid retrieval experiments](HYBRID_RETRIEVAL_EXPERIMENTS.md).

For graph construction checks on eight polyglot systems, read the [baseline audit](GRAPH_BUILDER_POLYGLOT_AUDIT.md) and [fix validation](GRAPH_BUILDER_FIX_VALIDATION.md).

For the latest file-retrieval comparison across those checkouts, open the [interactive dashboard](polyglot_retrieval_dashboard.html) or read the [benchmark report](POLYGLOT_REPO_RETRIEVAL_REPORT.md). The dashboard is a self-contained HTML file and works on localhost or directly in a browser.

---

## Overview

Modern distributed software systems are composed of multiple microservices, each written in potentially different programming languages and communicating over network APIs (gRPC, REST) and asynchronous message queues (Kafka). Standard static analysis tools and code knowledge graph systems fail at this boundary: they lose track of execution paths the moment code crosses a network call or event channel from one service to another.

SCKG Graph Builder solves this by constructing a unified five-layer Code Knowledge Graph (CKG) that spans an entire multi-repository workspace. It explicitly models cross-service gRPC/Protobuf contracts, Spring REST endpoints, and event topics as first-class graph edges, enabling LLM agents and developer tools to trace execution paths across language and service boundaries with bounded token context and zero choke-point bottlenecks.

---

## Key Capabilities

- **Multi-Repository Composition:** Constructs a unified graph across multiple Git repositories in a single build pass.
- **Polyglot Parsing:** Native AST and tree-sitter support across six programming languages (Go, Python, JavaScript, TypeScript, Java, C#) plus Protobuf schemas.
- **Contract Layer ($L_{\text{contract}}$):** Models gRPC, Spring REST (`@RestController`, `@GetMapping`, `@PostMapping`), and message queues (`@KafkaListener`, event publishing) via typed `CONSUMES`, `IMPLEMENTS`, `PRODUCES_EVENT`, and `CONSUMES_EVENT` edges.
- **Incremental Streaming Build:** Sub-second incremental updates via SHA-256 hash checking and file-scoped contract invalidation, rebuilding only affected AST and contract subtrees upon file changes.
- **Choke-Point-Free Traversal:** Optimizes blast-radius and context grafting traversals by bypassing backward traversal into parent service hubs, preventing star-graph fanout and choke points.
- **Schema Drift Detection:** Detects API contract version skew between vendored Protobuf schemas across service boundaries.
- **Deterministic Subtree Grafting:** Token-bounded context extraction for LLM agent prompts with minimal token redundancy.
- **Standardized Graph Provider Interface:** Exposes an interface (`GraphProvider` / `SCKGGraphProvider`) for symptom resolution, backward root-cause analysis, and blast-radius tracing.
- **Export & Storage:** Exports directly to NetworkX, JSON, GraphML, CSV, and Neo4j formats.

---

## Architecture

The system is organized into modular components:

### graft_ckg.py — Single-Repository CKG Builder

The foundational graph construction engine for a single repository. Parses Python source files using Python's native `ast` module and coordinates polyglot tree-sitter extractors for other languages.
- Computes four core topological layers: $L_{\text{syn}}$, $L_{\text{dep}}$, $L_{\text{flow}}$, $L_{\text{sem}}$.
- Attaches 4-dimensional HyperEdge Metadata vectors to every edge: `m = [d_scope, f_call, c_type, id_ctx]`.
- Implements `update_files(changed_files)` for file-scoped incremental streaming builds: invalidates changed nodes, cleans associated contract and dependency edges, re-parses modified files, and rebinds cross-file edges.
- Tracks Protobuf contract nodes on a per-file basis (`proto_nodes_by_file`) to ensure schema modifications cleanly invalidate and regenerate RPC and message contracts without leaving stale orphan nodes.

### polyglot.py — Multi-Language Adapter

Adapts non-Python source files into the unified node and edge vocabulary using `tree-sitter`:
- **Go, JavaScript, TypeScript, C#:** Parses function declarations, imports, calls, variables, class structures, and docstrings.
- **Java:** Parses package declarations, cross-file imports, class hierarchies (`EXTENDS`), method invocations (`CALLS`), and object instantiations.
- **Spring REST & Messaging:** Extracts Spring Boot annotations (`@RestController`, `@RequestMapping`, `@GetMapping`, `@PostMapping`, etc.) into `endpoint` contract nodes, and `@KafkaListener` / `kafkaTemplate.send(...)` into `topic_contract` nodes.

### multi_repo.py — Workspace Orchestration Engine

Reads a `workspace.yaml` configuration, instantiates a CKG builder for each repository, and fuses all resulting graphs into one unified workspace graph:
- Enforces strict node namespacing using the format `<repo_id>/<rel_path>:<qualname>`, guaranteeing zero node-ID collisions across repositories.
- Parses `.proto` files to extract service and RPC definitions.
- Computes SHA-256 hashes of schemas to detect `CONTRACT_SKEW` defects across repositories.
- Binds cross-repository `CONSUMES`, `IMPLEMENTS`, `HTTP_CALLS`, and event edges.
- Computes the workspace-level semantic layer ($L_{\text{sem}}$) across all repositories.
- Implements `rebuild_incremental(changed_files_by_repo)` for workspace-wide streaming updates.

For high-precision cross-service HTTP graphs, set `strict_http_source_evidence: true` in `workspace.yaml` (or `WorkspaceConfig`). The default is `false` for backwards compatibility. Strict mode preserves HTTP edges supported by a resolved source URL, HTTP verb, and unique destination service/handler, but suppresses legacy path-only guesses. It can reduce recall for JS/TS/Go requests whose hosts are not yet resolved. Python `urllib` import aliases are supported, and ambiguous Java overload caller nodes are never treated as confirmed HTTP call sources.

### traversal.py — Graph-Guided Traversal & Grafting

Provides deterministic, typed graph traversal primitives across all five layers:
- `compute_blast_radius`: Multi-hop transitive dependency impact analysis (upstream and downstream).
- `deterministic_subtree_graft`: Bounded-token context subgraph extraction for LLM prompts.
- `downstream_consumers`: Identifies all cross-service consumers dependent on a specific RPC, endpoint, or topic.
- `contract_of`: Maps implementation functions back to their governing contract specification.
- **Choke-Point Elimination:** Prevents backward traversal across `DEFINES_RPC` edges into parent `service_contract` nodes, eliminating star-graph combinatorial fanout during impact analysis.

### contracts/ (sckg_provider.py) — Graph Provider Interface

Defines the service layer interface `GraphProvider` and `SCKGGraphProvider` implementation:
- `find_node_by_name`: Exact and partial symbol lookup.
- `get_node_detail`: Complete node attribute and adjacency inspection.
- `resolve_symptom`: Maps stack trace frames and error logs directly to graph nodes.
- `backward_traverse`: Traverses dependencies backward to identify candidate root causes.
- `forward_traverse`: Traverses forward to compute blast radius and affected services.
- `explain_path`: Generates human-readable causal path explanations between nodes.
- `get_contract_between`: Retrieves shared contracts governing two interacting services.

---

## The Five-Layer Graph Topology

Each edge in the graph belongs to one of five topological layers:

| Layer | Name | Description | Primary Edge Types |
|---|---|---|---|
| $L_{\text{syn}}$ | Syntactic | AST containment and namespace hierarchy | `DEFINES`, `CONTAINS`, `EXTENDS` |
| $L_{\text{dep}}$ | Dependency | Cross-file imports, call graph, and class inheritance | `CALLS`, `IMPORTS`, `USES` |
| $L_{\text{flow}}$ | Dataflow | Variable definition-use chains, arguments, and returns | `DEFINES`, `PASSES_ARG`, `RETURNS`, `FLOWS_TO`, `MUTATES` |
| $L_{\text{sem}}$ | Semantic | TF-IDF docstring similarity across symbols | `SEMANTIC_SIMILAR` |
| $L_{\text{contract}}$ | Contract | Cross-service gRPC, REST, and messaging event bindings | `IMPLEMENTS`, `CONSUMES`, `PRODUCES`, `HTTP_CALLS`, `PRODUCES_EVENT`, `CONSUMES_EVENT` |

The contract layer ($L_{\text{contract}}$) is the critical differentiator. Ablation experiments demonstrate that removing this layer causes a 43.1 percentage point drop in cross-service context recall (77.1% down to 34.0%), confirming it recovers nearly half of all cross-service context.

---

## Incremental Streaming Build

To support large, fast-evolving multi-repository codebases, SCKG provides fine-grained incremental updates:

1. **Change Ingestion:** Modified or added files are detected via Git status or file watcher notifications.
2. **File-Scoped Subtree Invalidation:**
   - Source code nodes belonging to the file are identified and excised along with their incident edges.
   - For Protobuf files, tracked service definitions, RPC contracts, and schema SHA-256 hashes are selectively cleared using `proto_nodes_by_file`.
3. **Partial Re-Parsing & Grafting:**
   - Only modified files are re-parsed by the appropriate AST or tree-sitter extractor.
   - Internal edges ($L_{\text{syn}}$, $L_{\text{dep}}$, $L_{\text{flow}}$) for the modified file are re-established.
   - Cross-file call sites and contract bindings are re-resolved against the existing global index without rebuilding untouched services.
4. **Sub-Second Throughput:** On codebases with up to 150K LOC, incremental rebuilds take between 20ms and 240ms (up to 33.7x faster than a full build).

---

## Installation

**Requirements:** Python >= 3.10

```bash
# Clone the repository
git clone https://github.com/SNK0-0/SCKG_Build.git
cd SCKG_Build

# Install core dependencies
pip install -r requirements.txt

# Or install as an editable package with all optional language adapters
pip install -e ".[all]"
```

**Core dependencies:**
- `networkx >= 3.0` — graph data structure and algorithms
- `scikit-learn >= 1.2.0` — TF-IDF vectorization for semantic layer
- `tree-sitter >= 0.25, < 0.26` — multi-language parsing
- `tree-sitter-go`, `tree-sitter-javascript`, `tree-sitter-typescript` — language grammars
- `rank_bm25 >= 0.2` — BM25 lexical retrieval baseline
- `tiktoken >= 0.5` — BPE token counting for redundancy metrics
- `pyvis >= 0.3.2` — interactive graph visualization

**Optional language adapters:**
```bash
pip install tree-sitter-java      # Java support
pip install tree-sitter-c-sharp   # C# support
```

---

## Quick Start

### Building a Single Repository

```python
from graft_ckg import CKGBuilder

builder = CKGBuilder("/path/to/your/repository")
builder.build()

graph = builder.graph
print(f"Nodes: {graph.number_of_nodes()}")
print(f"Edges: {graph.number_of_edges()}")
```

### Performing Incremental Updates

```python
# Modify a source file or schema file
# ...
changed_files = ["/path/to/your/repository/service.proto"]
builder.update_files(changed_files)

# Graph is updated incrementally without a full rebuild
print(f"Updated Nodes: {builder.graph.number_of_nodes()}")
```

### Building a Multi-Repository Workspace

Create a `workspace.yaml` file in your workspace root:

```yaml
workspace_name: "my_microservices"
version: "1.0.0"
repositories:
  - name: "frontend"
    path: "src/frontend"
  - name: "backend"
    path: "src/backend"
  - name: "payment_service"
    path: "src/payment"
```

Then build and query the workspace:

```python
import yaml
from multi_repo import WorkspaceCKGBuilder

with open("workspace.yaml") as f:
    config = yaml.safe_load(f)

builder = WorkspaceCKGBuilder(config)
builder.build()

graph = builder.workspace_graph
print(f"Total Workspace Nodes: {graph.number_of_nodes()}")
print(f"Total Workspace Edges: {graph.number_of_edges()}")
```

### Using the Graph Provider Interface

```python
from sckg_provider import SCKGGraphProvider
from contracts.graph_types import TelemetryEvent, TraversalPolicy

provider = SCKGGraphProvider("workspace.yaml")

# 1. Resolve runtime error symptom
event = TelemetryEvent(
    event_id="evt-1",
    timestamp=1700000000.0,
    service_name="order_service",
    error_message="RPC failed to PaymentService: timeout",
)
symptoms = provider.resolve_symptom(event)

# 2. Backward traversal for root cause discovery
root_causes = provider.backward_traverse(symptoms[0].id, policy=TraversalPolicy(max_depth=3))
for cause in root_causes:
    print(f"Candidate: {cause.node_id} (Score: {cause.confidence_score})")

# 3. Forward traversal for blast radius
blast_radius = provider.forward_traverse(symptoms[0].id, policy=TraversalPolicy(max_depth=2))
print(f"Affected Nodes: {len(blast_radius.nodes)}")
```

---

## Project Structure

```
SCKG_Build/
|
|-- graft_ckg.py              # Core single-repo CKG builder (CKGBuilder class)
|-- multi_repo.py             # Multi-repo workspace orchestrator (WorkspaceCKGBuilder class)
|-- polyglot.py               # Multi-language parser adapter (TreeSitterExtractor class)
|-- traversal.py              # BFS/DFS context grafting & blast radius engine
|-- lineage.py                # Git commit lineage integration (TOUCHES edges)
|-- remediation.py            # Contract skew detection and remediation suggestions
|-- neo4j_export.py           # Export to Neo4j graph database
|-- serve_ckg.py              # HTTP API server for graph queries
|-- visualize.py              # Static graph visualization utilities
|-- inspect_contracts.py      # Contract layer inspection and validation
|-- example_integration.py    # End-to-end build and traversal verification script
|-- sckg_provider.py          # Root re-export for Graph Provider interface
|
|-- contracts/                # Standardized Graph Provider contract package
|   |-- __init__.py           # Package exports
|   |-- graph_types.py        # Domain models, enums (NodeType, EdgeType), dataclasses
|   |-- graph_provider.py     # Abstract GraphProvider interface definition
|   `-- sckg_provider.py      # Concrete SCKGGraphProvider implementation
|
|-- bench/                    # Benchmark suite
|   |-- run_multi_system_eval.py      # Table I: construction scalability
|   |-- run_multi_repo_benchmark.py   # Table II/III: retrieval and contracts
|   |-- bench_agent_toolcall.py       # Table V: agent tool-call efficiency
|   |-- bench_incremental.py          # Table IV: incremental build speedup
|   |-- run_single_repo_comparison.py # Single-repo comparison
|   |-- verify_all_numbers.py         # Cross-validates all benchmark JSON outputs
|   |-- trace_oracle.py               # Ground-truth query oracle for evaluations
|   |-- inject_contract_fault.py      # Fault injection for contract skew tests
|   `-- results/                      # JSON results from benchmark runs
|
|-- tests/                    # Unit and integration test suite (67 tests)
|   |-- test_contract_layer.py
|   |-- test_dependency_resolution.py
|   |-- test_multi_repo.py
|   |-- test_polyglot_integration.py
|   |-- test_polyglot_spring_events.py
|   |-- test_proto_choke_point_fixes.py
|   |-- test_graph_provider.py
|   |-- test_traversal.py
|   |-- test_lineage.py
|   |-- test_remediation.py
|   `-- test_neo4j_export.py
|
|-- examples/                 # Example workspace configurations
|   |-- polyglot_system/      # Go + Python + TypeScript example
|   |-- multi_repo_system/    # Multi-service example with Protobuf contracts
|   `-- mixed_service/        # Mixed language example
|
|-- requirements.txt          # Python dependencies
|-- pyproject.toml            # Package build configuration
`-- README.md                 # This file
```

---

## Benchmark Results

All numbers below are sourced directly from `bench/results/*.json` and verified by `bench/verify_all_numbers.py`.

### Table I — Construction Scalability

| System | Languages | Services | LOC | Nodes | Edges | s/kLOC | Contract Edges | Skews |
|---|---|---|---|---|---|---|---|---|
| Google Online Boutique | Go, Python, Node.js, Proto | 10 | 5,001 | 1,794 | 5,155 | 0.040 | 30 | 0 |
| Jaeger Distributed Tracing | Go, Python, Proto | 5 modules | 159,851 | 50,861 | 184,957 | 0.039 | 0 | 0 |
| gRPC-Gateway | Go, Proto | 3 | 148,844 | 46,277 | 363,713 | 0.102 | 0 | 1 |
| Podinfo Microservice | Go, Proto | 4 | 6,238 | 1,994 | 6,648 | 0.136 | 9 | 0 |

PyCG reports approximately 0.38 s/kLOC on Python-only single-repo codebases. SCKG Graph Builder achieves 0.039 to 0.136 s/kLOC on polyglot multi-repo systems — 2.8x to 9.5x faster — while handling multiple languages simultaneously.

### Table II — Retrieval and Context Quality

Evaluated on a 12-query polyglot benchmark over Google Online Boutique:

| Baseline | MRR@5 | Hits@1 (%) | Recall@10 (%) | Token Redundancy (%) |
|---|---|---|---|---|
| SCKG Graph Builder (full) | 0.561 | 41.7 | 77.1 | 103.2 |
| BM25 Lexical | 0.617 | 50.0 | 46.5 | 100.0 |
| Flat File Chunking | 1.000 | 100.0 | 72.2 | 251.0 |
| Naive AST/CPG | 0.561 | 41.7 | 29.2 | 46.4 |

### Table II-b — Layer Ablation Study

| Configuration | Recall@10 (%) | Delta Recall |
|---|---|---|
| Full model | 77.1 | — |
| Without $L_{\text{flow}}$ | 77.1 | 0.0% |
| Without $L_{\text{dep}}$ | 75.0 | -2.1% |
| Without $L_{\text{sem}}$ | 77.1 | 0.0% |
| Without $L_{\text{contract}}$ | 34.0 | -43.1% |

### Table III — Contract Layer Precision, Recall and F1

Evaluated against ground truth on Google Online Boutique:

| Binding Type | Ground Truth | Resolved | Precision | Recall | F1 |
|---|---|---|---|---|---|
| CONSUMES (gRPC) | 21 | 21 | 1.000 | 1.000 | 1.000 |
| IMPLEMENTS (gRPC) | 9 | 9 | 1.000 | 1.000 | 1.000 |
| HTTP_CALLS | 1 | 1 | 1.000 | 1.000 | 1.000 |

### Table IV — Incremental Build Speedup

| System | LOC | Full Build (ms) | Incremental (ms) | Speedup |
|---|---|---|---|---|
| Online Boutique | 5,001 | 3.1 | 2.7 | 1.1x |
| Podinfo | 6,238 | 44.7 | 18.3 | 2.4x |
| Jaeger | 159,851 | 4,424 | 242 | 18.3x |
| gRPC-Gateway | 148,844 | 2,054 | 61 | 33.7x |

### Table V — Agent Tool-Call Efficiency

| Metric | SCKG Graph Builder | Raw File Reader | Delta |
|---|---|---|---|
| Mean Tool Calls per Task | 1.8 | 3.3 | -45.5% |
| Mean Context Tokens per Task | 190 | 252 | -24.6% |
| Mean Latency (ms) | 11.9 | 1.1 | +11ms |

---

## Running the Tests

The test suite contains 67 tests covering contract resolution, dependency resolution, multi-repo composition, polyglot extraction, incremental updates, choke-point avoidance, and Graph Provider operations:

```bash
# Run the full test suite
python -m pytest tests/ -v

# Run incremental and choke-point verification tests
python -m pytest tests/test_proto_choke_point_fixes.py -v

# Run Spring REST and event contract tests
python -m pytest tests/test_polyglot_spring_events.py -v

# Run Graph Provider integration tests
python -m pytest tests/test_graph_provider.py -v
```

---

## Comparison with Related Work

| System | Multi-Repo | Polyglot | API Contracts | Incremental | Primary Metric |
|---|---|---|---|---|---|
| SCKG Graph Builder | Yes | 6 languages | Yes (gRPC, REST, Events) | Yes (up to 33.7x) | Recall@10=77.1%, Contract F1=1.000 |
| RepoGraph (ICLR 2025) | No | Python only | No | No | SWE-bench +6.6% delta resolve |
| LocAgent (ACL 2025) | No | Python only | No | No | Acc@1=85%+, 86% cost reduction |
| CodexGraph (2024) | No | Python only | No | No | Pass@1=86.2% |
| PyCG (ICSE 2021) | No | Python only | No | No | F1=0.822 on call graphs |
| Agentless (2024) | No | Python only | No | No | 27.3% SWE-bench resolve |

---

## License

MIT License. See LICENSE file for details.
