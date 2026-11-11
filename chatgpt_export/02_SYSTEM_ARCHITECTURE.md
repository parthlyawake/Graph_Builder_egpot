# GRAFT-CKG System Architecture & Topological Planes

GRAFT-CKG represents multi-repository, polyglot software architectures as a directed, attributed hyper-relational multigraph:
$$G = (\mathcal{V}, \mathcal{E}, \mathcal{L}, \Phi, \Psi, \mathcal{M})$$

## The 5 Topological Planes (\mathcal{L})

1. **Syntactic Hierarchy Plane (Lsyn)**:
   - Captures grammatical containment and lexical organization.
   - Nodes: `file`, `module`, `class`, `function`, `parameter`, `variable`.
   - Edges: `CONTAINS`, `DECLARES`, `DEFINES`, `EXTENDS`.
   - Derived directly via language-specific Tree-Sitter concrete syntax trees (CSTs).

2. **Dependency & Call Graph Plane (Ldep)**:
   - Captures static and polymorphic invocations, imports, and references.
   - Edges: `CALLS`, `POLYMORPHIC_CALL`, `IMPORTS`, `USES`, `HTTP_CALLS`.
   - Polymorphic calls maintain confidence $c_{\text{type}} \in [0, 1]$ adhering strictly to Theorem 2 (Partition of Unity: $\sum c_{\text{type}} = 1.0$).
   - Enhanced via Language Server Protocol (LSP) augmentation (`lsp_augmenter.py`) to resolve ambiguous dynamic call sites.

3. **Dataflow & Def-Use Plane (Lflow)**:
   - Captures value propagation, parameter passing, mutations, and return values.
   - Intra-service edges: `PASSES_ARG`, `FLOWS_TO`, `MUTATES`, `RETURNS`.
   - **Inter-service Dataflow (P4 Enhancement)**: Seamlessly connects caller arguments across repository boundaries to remote server handler parameters via contract RPC nodes in $L_{\text{contract}}$, making distributed RPC traces completely deterministic.

4. **Latent Semantic Plane (Lsem)**:
   - Dense vector embeddings linking semantically analogous code blocks and natural language documentation (GoDoc, JSDoc, Python docstrings).
   - Edges: `SEMANTIC_SIMILARITY`, `RELATES_TO`.
   - Bridges fuzzy natural language user queries to precise programmatic symbol anchors.

5. **Cross-Service Contract Plane (Lcontract)**:
   - Canonical interface representations decoupling consumers from concrete producer implementations.
   - Supports:
     - Protobuf 3 gRPC Services and RPCs (`proto_parser.py`)
     - OpenAPI 3.x / Swagger REST endpoints (`openapi_graphql_parser.py`)
     - GraphQL SDL queries and mutations (`openapi_graphql_parser.py`)
   - Edges: `DEFINES_RPC`, `IMPLEMENTS`, `CONSUMES`, `EXPOSES`, `CALLS_CONTRACT`.
   - Invariant: Zero schema skew across microservices; 100% recall of cross-service interfaces.
