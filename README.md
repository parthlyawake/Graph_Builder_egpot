# GRAFT-CKG: Generalized Relational Abstraction and Functional Topology for Code Knowledge Graphs

> A multi-repository, polyglot Code Knowledge Graph (CKG) engine for LLM agent context generation in distributed microservice systems.

[![Tests](https://img.shields.io/badge/tests-53%20passed-brightgreen)](#testing)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](#installation)
[![Languages](https://img.shields.io/badge/languages-Python%20%7C%20Go%20%7C%20JS%2FTS%20%7C%20Protobuf-orange)](#supported-languages)

---

## Overview

GRAFT-CKG builds a **six-layer hyper-relational knowledge graph** from source code across multiple repositories and programming languages. Unlike existing single-repository code graph systems (RepoGraph, CodexGraph, LocAgent), GRAFT-CKG:

- **Spans multiple repositories** in a single unified workspace graph with zero node-ID collisions
- **Models gRPC/Protobuf service contracts** as first-class graph nodes (L_contract)
- **Resolves cross-service dependencies** — which Go service *implements* a proto RPC, which Python service *consumes* it
- **Detects contract drift** when vendored .proto copies diverge between services
- **Builds incrementally** — a changed file updates the graph in O(Δ) time, not O(N)
- **Integrates git lineage** — commit history becomes TOUCHES edges in the graph

### Architecture

`
Source Code (Go, Python, JS/TS, Protobuf)
                │
                ▼
┌───────────────────────────────────────────────────────────┐
│  L_syn      │ CONTAINS · IMPORTS · EXTENDS                │
│  L_dep      │ CALLS · POLYMORPHIC_CALL (Eq.4 softmax)     │
│  L_flow     │ PASSES_ARG · DEFINES · USES · MUTATES       │
│  L_sem      │ SEMANTIC_SIMILAR (TF-IDF + BM25)            │
│  L_contract │ IMPLEMENTS · CONSUMES · HTTP_CALLS          │  ← novel
│  L_lineage  │ TOUCHES (git commit provenance)             │  ← novel
└───────────────────────────────────────────────────────────┘
                │
                ▼
   Unified Multi-Repo Workspace Graph
   → RAG Query  → Blast-Radius  → Subtree Graft  → Neo4j Export
`

---

## Installation

`ash
git clone <repo>
cd SCKG_Build-v2

pip install -r requirements.txt
`

**requirements.txt** installs:
- 
etworkx, scikit-learn, 
ank_bm25 — graph + retrieval
- 	ree-sitter, 	ree-sitter-go, 	ree-sitter-javascript, 	ree-sitter-typescript — parsers
- 	iktoken — accurate BPE token counting for paper metrics
- pytest — test runner

Optional (not auto-installed):
`ash
pip install tree-sitter-java    # Java support (AdService, Spring Boot)
pip install tree-sitter-c-sharp # C# support (CartService)
`

---

## Quick Start

### 1. Build a single-repository CKG

`python
from graft_ckg import CKGBuilder

builder = CKGBuilder("path/to/your/repo")
builder.build()

# Query: find all nodes related to "payment processing"
result = builder.rag_query("payment processing", top_k=5)
for hit in result["top_matches"]:
    print(hit["node_id"], hit["score"])
`

### 2. Build a multi-repository workspace CKG

Create a workspace.yaml:
`yaml
name: 'my_workspace'
repositories:
  - id: 'frontend'
    path: './services/frontend'
  - id: 'backend'
    path: './services/backend'
  - id: 'payments'
    path: './services/payments'
shared_contracts:
  - './protos'
ignore_patterns:
  - '*.pb.go'
  - 'vendor/*'
`

`python
from multi_repo import WorkspaceCKGBuilder

wb = WorkspaceCKGBuilder("workspace.yaml")
wb.build()

print(f"Nodes: {wb.graph.number_of_nodes()}")
print(f"Edges: {wb.graph.number_of_edges()}")
print(f"Contracts: {len(wb.canonical_contracts)}")
print(f"Skews: {len(wb.contract_skews)}")
`

### 3. Traverse the graph

`python
from traversal import SCKGTraversal

trav = SCKGTraversal(wb)

# What breaks if ShippingService.GetQuote changes?
result = trav.blast_radius("contract::ShippingService.GetQuote", max_depth=3)
print(f"Affected: {result['total_impacted_nodes']} nodes across {len(result['affected_services'])} services")

# Who consumes CartService?
consumers = trav.downstream_consumers("CartService")
for c in consumers["consumers"]:
    print(c["consumer_node"], "->", c["target_contract"])

# Token-bounded LLM context for a symbol
ctx = trav.deterministic_subtree_graft("checkoutservice/main.go:placeOrder", max_tokens=1500)
print(f"BPE tokens: {ctx['bpe_tokens']}")  # accurate tiktoken count
print(ctx["grafted_context"])
`

### 4. Git lineage

`python
from lineage import LineageLayer

layer = LineageLayer(wb.repo_builders["checkoutservice"])
layer.ingest(max_commits=100)

# Who changed placeOrder?
for commit in layer.who_changed("placeOrder"):
    print(f"[{commit['sha']}] {commit['date']} — {commit['message']}")

# Temporal coupling: do these files change together?
weight = layer.co_change_weight("main.go", "server.go")
print(f"Co-change weight: {weight:.2f}")
`

### 5. Export to Neo4j

`python
from neo4j_export import CypherExporter

exporter = CypherExporter(wb.graph)
exporter.export("output.cypher")
# Run: cypher-shell -u neo4j -p password < output.cypher
`

Or from CLI:
`ash
python neo4j_export.py workspace.yaml output.cypher
`

---

## Supported Languages

| Language | Parser | Status |
|---|---|---|
| Python | st (stdlib) | Full |
| JavaScript / JSX | 	ree-sitter-javascript | Full |
| TypeScript / TSX | 	ree-sitter-typescript | Full |
| Go | 	ree-sitter-go | Full |
| Protobuf / gRPC | Custom regex + AST | Full |
| Java | 	ree-sitter-java | Supported |
| C# | 	ree-sitter-c-sharp | Supported |

---

## Module Reference

| Module | Class / Function | Purpose |
|---|---|---|
| graft_ckg.py | CKGBuilder | Core 4-layer graph builder for a single repo |
| polyglot.py | TreeSitterExtractor | JS/TS/Go/Java/C# tree-sitter adapter |
| multi_repo.py | WorkspaceCKGBuilder | Multi-repo workspace composition |
| 	raversal.py | SCKGTraversal, count_tokens | Graph traversal, context grafting, token counting |
| 
emediation.py | SCKGRemediation | Contract skew detection and self-healing |
| lineage.py | LineageLayer | Git commit provenance layer |
| 
eo4j_export.py | CypherExporter | Cypher batch export for Neo4j |
| isualize.py | CLI | GraphML → GEXF / HTML export |
| serve_ckg.py | CLI | localhost:8080 D3 graph workbench |

---

## Benchmarks (Measured on 4 Real Open-Source Systems)

### Construction Scalability

| System | Languages | LOC | Nodes | Edges | Build (s) | Speedup (incr.) |
|---|---|---|---|---|---|---|
| Google Online Boutique | Go+Py+JS+Proto | 5k | 1,794 | 5,157 | 0.71 | 1.0x |
| Podinfo gRPC service | Go+Proto | 6k | 1,994 | 6,654 | 0.92 | 1.9x |
| Jaeger Tracing Platform | Go+Py+Proto | 50k | 16,826 | 61,606 | 5.20 | **6.6x** |
| gRPC-Gateway Ecosystem | Go+Proto | 148k | 46,277 | 703,385 | 18.64 | **9.9x** |

> **Zero node-ID collisions** across all systems. **1 real CONTRACT_SKEW found** automatically in gRPC-Gateway.

### Contract Layer Accuracy (Online Boutique, labelled ground truth)

| Binding Type | GT | Detected | P | R | F1 |
|---|---|---|---|---|---|
| CONSUMES (gRPC) | 21 | 21 | 1.000 | 1.000 | 1.000 |
| IMPLEMENTS (gRPC) | 9 | 9 | 1.000 | 1.000 | 1.000 |
| HTTP_CALLS | 1 | 1 | 1.000 | 1.000 | 1.000 |

---

## Testing

`ash
python -m pytest tests/ -v
# Expected: 53 passed
`

Test coverage:
- 	est_contract_layer.py — gRPC contract parsing and binding
- 	est_dependency_resolution.py — import/call resolution across Python/TS/Go
- 	est_gap_fixes.py — polymorphic dispatch, incremental update, cross-service isolation
- 	est_lineage.py — git lineage layer APIs
- 	est_multi_repo.py — workspace composition, cross-repo traversal
- 	est_neo4j_export.py — Cypher export validity
- 	est_polyglot_integration.py — JSDoc/GoDoc, HTTP bindings
- 	est_remediation.py — contract skew detection and 5-stage healing
- 	est_traversal.py — blast radius, subtree grafting, consumer queries

---

## Demo (5 minutes)

`ash
# Live demo on Google Online Boutique (10 services, 5k LOC)
python demo_online_boutique.py

# Run full multi-system benchmark (4 real repos)
python bench/run_multi_system_eval.py

# Interactive graph workbench
python serve_ckg.py path/to/repo --port 8080
`

---

## Prior Work Comparison

| System | Venue | Multi-Repo | Polyglot | gRPC/Proto | Incremental |
|---|---|---|---|---|---|
| RepoGraph | ICLR 2025 | No | Partial | No | No |
| LocAgent | ACL 2025 | No | No | No | No |
| CodexGraph | arXiv 2024 | No | Partial | No | No |
| GraphCodeBERT | ICLR 2021 | No | Yes (6 langs) | No | No |
| **GRAFT-CKG** | This work | **Yes** | **Yes** | **Yes** | **Yes** |

---

## Paper

*GRAFT-CKG: Generalized Relational Abstraction and Functional Topology for Whole-Repository Code Knowledge Graphs and Agent Context Layers*

