# SCKG Graph Builder

A polyglot, multi-repository Source Code Knowledge Graph (SCKG) construction engine for distributed software systems. SCKG Graph Builder parses source code across multiple programming languages and Git repositories simultaneously, producing a single unified directed graph that captures syntactic structure, dependency relationships, dataflow chains, semantic similarity, and cross-service API contracts.

Run the [local graph viewer](TEAMMATE_GRAPH_GUIDE.md) on your repository, read the [contract graph guide](CONTRACTS.md), or review the [hybrid retrieval experiments](HYBRID_RETRIEVAL_EXPERIMENTS.md).

For graph construction checks on eight polyglot systems, read the [baseline audit](GRAPH_BUILDER_POLYGLOT_AUDIT.md) and [fix validation](GRAPH_BUILDER_FIX_VALIDATION.md).

---

## Overview

Modern distributed software systems are composed of multiple microservices, each written in potentially different programming languages and communicating over network APIs (gRPC, REST) and asynchronous message queues (Kafka). Source-only dependency analysis often lacks reliable evidence for the code-to-network boundary; dynamically resolved targets require configuration or runtime corroboration.

SCKG Graph Builder solves this by constructing a unified five-layer Code Knowledge Graph (CKG) that spans an entire multi-repository workspace. It explicitly models cross-service gRPC/Protobuf contracts, Spring REST endpoints, and event topics as first-class graph edges, supporting source-evidenced dependency exploration and token-bounded context. Unresolved host identity, runtime dispatch, event routing and schema version skew remain explicit limitations.

---

## Key Capabilities

- **Multi-Repository Composition:** Constructs a unified graph across multiple Git repositories in a single build pass.
- **Polyglot Parsing:** Native Python AST and Tree-sitter adapters cover core Go, JavaScript/TypeScript, Java, C# and additional language grammars. Feature completeness varies; see [real-source coverage](REAL_REPOSITORY_COMPATIBILITY_AUDIT.md).
- **Contract Layer ($L_{\text{contract}}$):** Models gRPC, Spring REST (`@RestController`, `@GetMapping`, `@PostMapping`), and message queues (`@KafkaListener`, event publishing) via typed `CONSUMES`, `IMPLEMENTS`, `PRODUCES_EVENT`, and `CONSUMES_EVENT` edges.
- **Incremental Maintenance:** File-level updates preserve source registries and re-resolve derived edges. Large workspace/schema changes can trigger a full rebuild; latency and exact graph equivalence must be checked per edit and scope.
- **Bounded Traversal Policies:** Limits selected service-hub expansion during blast-radius/context extraction; no global choke-point or asymptotic-complexity guarantee is claimed.
- **Schema Drift Detection:** Detects API contract version skew between vendored Protobuf schemas across service boundaries.
- **Deterministic Subtree Grafting:** Exact cl100k_base token-budget enforcement for rendered context. Semantic prompt redundancy has **not** been independently quantified.
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
- Uses repository-specific node namespacing (`<repo_id>/<rel_path>:<qualname>`) to reduce cross-repository ID collisions; unresolved symbol identities remain possible.
- Parses `.proto` files to extract service and RPC definitions.
- Computes SHA-256 hashes of schemas to detect `CONTRACT_SKEW` defects across repositories.
- Binds cross-repository `CONSUMES`, `IMPLEMENTS`, `HTTP_CALLS`, and event edges.
- Computes the workspace-level semantic layer ($L_{\text{sem}}$) across all repositories.
- Implements `rebuild_incremental(changed_files_by_repo)` for workspace-wide streaming updates.

For conservative, source-evidenced cross-service HTTP graphs, set `strict_http_source_evidence: true` in `workspace.yaml` (or `WorkspaceConfig`). The default is `false` for backwards compatibility. Strict mode preserves HTTP edges supported by a resolved source URL, HTTP verb, and unique destination service/handler, but suppresses legacy path-only guesses. It can reduce recall for JS/TS/Go requests whose hosts are not yet resolved. Python `urllib` import aliases are supported, and ambiguous Java overload caller nodes are never treated as confirmed HTTP call sources.

### traversal.py — Graph-Guided Traversal & Grafting

Provides deterministic, typed graph traversal primitives across all five layers:
- `compute_blast_radius`: Multi-hop transitive dependency impact analysis (upstream and downstream).
- `deterministic_subtree_graft`: Bounded-token context subgraph extraction for LLM prompts.
- `downstream_consumers`: Identifies all cross-service consumers dependent on a specific RPC, endpoint, or topic.
- `contract_of`: Maps implementation functions back to their governing contract specification.
- **Fanout Control:** Prevents selected backward traversals through `DEFINES_RPC` service hubs to limit pathological expansion; no general complexity or zero-choke-point guarantee is implied.

### contracts/ (sckg_provider.py) — Graph Provider Interface

Defines the service layer interface `GraphProvider` and `SCKGGraphProvider` implementation:
- `find_node_by_name`: Exact and partial symbol lookup.
- `get_node_detail`: Inspects recorded node attributes and adjacency; unrepresented dynamic/runtime behavior is outside its scope.
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

The contract layer represents explicitly evidenced service relationships. In the revised **27-query, source-inspected** study, disabling contract edges after construction reduced exact-target graph-graft inclusion from **0.815 to 0.741**, while dependency-edge removal reduced it from **0.815 to 0.444**. These are selected context-inclusion ablations, **not** independent full-system contract accuracy or downstream agent improvements.

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
4. **Measured Incremental Cost:** Report source revision, change type, multi-run latency and semantic graph equivalence. In the pinned 2026-11-17 Go source edit, the observed medians were 0.723s incremental versus 7.962s fresh (~11.0×); no uniform sub-second or universal speedup guarantee exists.

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

## Evaluation evidence and publication status (corrected 2026-11-17)

**Do not cite the retired benchmark tables or agent-efficiency proxies formerly in this README.** They mixed historical runs, heterogeneous candidate sets, small source samples, simulated tool-call procedures and unadjudicated labels. Keep `bench/results/` JSON as historical diagnostics, **not** publication-certified accuracy.

### Source-inspected exact-ID retrieval, Online Boutique

Source: `GoogleCloudPlatform/microservices-demo@38e7348eb289eb5b87c0c6e8cb19ced0449dc389`; 27 source-inspected symbol-localization questions, no independent human sign-off, k=5 and 2,048 cl100k_base tokens.

| Retriever | MRR@5 | Hits@1 | Hits@5 |
|---|---:|---:|---:|
| BM25 R0 | 0.341 | 18.5% | 59.3% |
| LSA R1 | **0.638** | 48.1% | 92.6% |
| Syntax hybrid R3 | 0.514 | 37.0% | 74.1% |
| Static graph hybrid R5 | 0.514 | 37.0% | 74.1% |
| Contract hybrid R9 | 0.514 | 37.0% | 74.1% |

LSA **outperformed** the tested graph hybrids on this task set. In the separate P1–P4 research branch, paired LSA-minus-R5 MRR was +0.125, with a 10,000-sample within-cohort bootstrap 95% interval [−0.057, 0.300], including zero. No general or statistically reliable graph-ranking advantage is claimed.

The revised paper reports **post-construction** graft inclusion of annotated exact node IDs: full 0.815, without dependencies 0.444, without contracts 0.741. These are not real agent task resolution scores or parser-stage ablations.

### Source-graph correctness and operational integration

- Baseline `krishna` CI `a5dfc871ffbb74f7c3a752fe15eaa48e931edaee`: 323 passed, 3 skipped in each of three test runs, plus green real-repository compatibility jobs. Test success is **not** graph precision.
- Controlled 6-positive/2-negative HTTP and 21-triple relation fixtures verify designed scopes; their perfect scores are not unbiased real-source precision.
- [P1–P4 research study](https://github.com/Vikas-Personal-Research-Org/Graph_Builder/tree/research-publication-evidence-p1-p4-2026-11-17): Online Boutique 14/14 selected gRPC consumer/producer edges; DeathStarBench Thrift four selected declaration edges; Sock Shop queue-master one AMQP consumer; Train-Ticket three Spring REST route registrations. The first three sets have closed-scoped P/R/F1 **only in their listed selections**, without independent human adjudication.
- Source-to-Git object bridge, optional locally trusted DSSE signed build assertions, SQLite snapshot history/restart and synthetic deployment/telemetry integration exist in the research branch. This does **not** certify real production CI/CD, real deployment identity or OTLP telemetry provenance.
- The pinned Go incremental edit after correcting stale gRPC/HTTP edge provenance gave **3/3 semantic graph attribute equivalence** (internal counter edge keys excluded) and medians 0.723s incremental versus 7.962s fresh, approximately 11.0× for this one edit. Exact internal edge-key agreement remains 0/3; no universal speedup claim.

See [PAPER_EVALUATION_STATUS.md](PAPER_EVALUATION_STATUS.md), [PUBLICATION_EVIDENCE_AUDIT_2026_11_17.md](PUBLICATION_EVIDENCE_AUDIT_2026_11_17.md) and [source coverage limitations](REAL_REPOSITORY_COMPATIBILITY_AUDIT.md) before presenting any numeric result.

**Still missing for full PhD Objective 1 scientific sign-off:** independently reviewed exhaustive graph scopes, authenticated real deployment/OTLP evidence on representative systems, broader incremental and scaling trials, and equivalent external construction-method baselines. No claim of 0.90 symbolic P/R, 0.85/0.80 contract P/R, or 0.80 operational-lineage precision has been established.

---

## Running the Tests

The evolving test suite covers contract resolution, dependency resolution, multi-repo composition, polyglot extraction, incremental updates, traversal and Graph Provider operations. Use the current GitHub Actions run for exact totals:

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

## Comparison with related work — task-aligned, not borrowed scores

| Published work | Verified venue | Main evaluation task | Comparable interpretation |
|---|---|---|---|
| [RepoGraph](https://proceedings.iclr.cc/paper_files/paper/2025/hash/4a4a3c197deac042461c677219efd36c-Abstract-Conference.html) | ICLR 2025 | Repository graph navigation for software-engineering agents and CrossCodeEval | Structural graph idea; its SWE-bench resolve rate is not our construction edge precision |
| [CodexGraph](https://aclanthology.org/2025.naacl-long.7/) | NAACL 2025 | Code graph database querying with LLMs | Graph interfaces and navigation; different benchmark and tasks |
| [LocAgent](https://aclanthology.org/2025.acl-long.426/) | ACL 2025 | Graph-guided code localization | Different question population/targets; published scores are not our MRR baseline |
| [CodePlan](https://www.microsoft.com/en-us/research/publication/codeplan-repository-level-coding-using-llms-and-planning-2/) | FSE 2024 | Repository-wide edit planning and incremental impact | Relevant method idea, not direct four-service graph-accuracy score |

External implementations have **not** been rerun under the same pinned source, candidate-ID set and scoring protocol here. Do not place their published scores in a numerical performance comparison without such an experiment. The [literature comparability audit](LITERATURE_COMPARABILITY_AUDIT_2026_11_17.md) records verified reference metadata.

---

## License

MIT License. See LICENSE file for details.
