# Graph-generation depth completion — implementation and reproducibility

**Branch:** krishna  
**Date:** 2026-11-15  
**Purpose:** Implement and test the five previously identified feature-depth areas without changing the fundamental five-layer architecture.

## 1. Implemented engineering work

| Workstream | Implementation | Source / test |
| --- | --- | --- |
| Polymorphic call resolution | Java/C# overloaded declarations remain distinct. Source callsites retain argument expressions, literal types, arity and source locations. Static method candidates are filtered by explicit class/receiver scope, arity and literal-compatible types; only a single unambiguous candidate receives an exact CALLS edge. Ambiguous candidates retain POLYMORPHIC_CALL and normalized confidence. Unknown receiver types do not become exact by name alone. | static_dispatch.py, polyglot.py, graft_ckg.py; tests/test_depth_completion.py |
| Interprocedural dataflow | Python AST callsite argument -> callee formal variable; callee return node -> caller assignment/return destination. Java/C# declarations expose parameter names/types and callsite arguments. Actual callsite identity and dependency-edge provenance are required before linking; complex/unknown expressions are represented explicitly, never guessed as named source variables. | interprocedural_flow.py, graft_ckg.py, polyglot.py |
| Contract parsing / typing | Official protoc descriptor compilation for Protobuf 2/3, imports, map fields, oneof members, nested messages and streaming RPCs (conservative parser fallback with provenance); message field nodes, typed RPC request/response schema edges. OpenAPI 2/3 request/response schemas, parameter inheritance, local JSON Pointer $ref expansion with cycle and depth guards, typed schema nodes. GraphQL AST with SDL extensions, explicit root types, document operations, unambiguous source-evidenced Java DataFetcher registrations. | proto_compiler.py, proto_field_graph.py, openapi_schema.py, contract_schema_graph.py, graphql_ast_support.py, graphql_links.py, graphql_java_bindings.py |
| Token-exact grafting | Graph neighbor candidates are rendered deterministically, root first. Final context is packed and checked with actual tiktoken cl100k_base encoding including headers and separators, with explicit truncation and omitted-node tracking. No whitespace approximation is used for final budget enforcement. | token_grafting.py, traversal.py |
| Compiler and LSP integration | Automatic reading of local SCIP JSON index exports and explicit definition JSON indexes; option to query a locally installed JSON-RPC language server with Content-Length framing, initialize/didOpen/definition/shutdown messages, exact declaration-file/line matching, ambiguity guard and timeout. An explicit environment opt-in is required before starting any repository-declared executable. | compiler_resolution.py, lsp_augmenter.py, graft_ckg.py |

New schema and callsite node/edge types are exposed via contracts/graph_types.py and contracts/sckg_provider.py. The graph verifier distinguishes rpc_contract from Protobuf field and schema nodes.

## 2. Verification contract

GitHub Actions workflow: .github/workflows/graph-builder-integration.yml

Every push to krishna runs:

1. Installation, Python compilation of all graph-building modules.
2. Three independent full invocations of the repository test suite (pytest -q tests).
3. A pinned real DataHub source-subtree graph-build smoke test, repeated three times.
4. The DataHub test modifies a copied source file, builds an incrementally updated graph, builds a separate fresh graph and compares the **exact node ID set and typed edge multiplicities**.
5. The real-repository test publishes a machine-readable JSON artifact.

The DataHub smoke test covers datahub-actions/src (88 parsed Python files). It **does not** verify all language adapters on the full DataHub monorepo or prove edge accuracy against a manually annotated gold standard.

In the earlier green run at commit 8422f8d2, **181 passed, 3 skipped in each of three test runs**, and **three DataHub incremental-equivalence trials passed**. Additional security tests may increase the final test count; use the most recent green workflow run for exact final counts.

## 3. Reproduction

From a clean checkout of krishna:

    python -m pip install -r requirements.txt
    python -m pytest -q tests

Repeat the test command three times. For the pinned real-repository check:

    git clone https://github.com/datahub-project/datahub.git
    cd datahub
    git checkout 051fb78fe6a6395043d272218b035cb00fe27321
    cd ..
    python bench/smoke_datahub_graph.py --repo datahub/datahub-actions/src --repetitions 3

No upstream files are modified: the benchmark constructs its own temporary copy.

### Compiler index and local LSP usage

Create a **trusted** .sckg_lsp.json in the target source checkout:

    {
      "scip_indexes": ["index.scip.json"],
      "definition_indexes": ["definitions.json"],
      "servers": {"python": ["pylsp"]},
      "timeout_seconds": 5
    }

The SCIP input is a JSON representation of a SCIP compiler index, not a raw binary .scip file. Definitions are matched by source file and exact declaration line. Ambiguous matches remain unresolved.

Read-only index ingestion works without further flags. To explicitly allow executing locally installed language-server commands specified by the trusted manifest:

    export SCKG_ALLOW_LSP_SUBPROCESS=1

In PowerShell:

    $env:SCKG_ALLOW_LSP_SUBPROCESS = "1"

Never enable this option for untrusted repository manifests.

### Strict token limit

    from traversal import SCKGTraversal
    graft = SCKGTraversal(builder).deterministic_subtree_graft(
        "your_symbol", max_tokens=2048)
    assert graft["bpe_tokens"] <= 2048

## 4. Soundness boundaries (NOT claims of full semantic completeness)

- **Polymorphism:** runtime reflection, arbitrary dynamic dispatch, custom metaprogramming and unresolved receiver types cannot always be identified statically. Ambiguity must remain explicit.
- **Dataflow:** source-grounded explicit argument/return relationships are implemented. The engine is not a compiler-level SSA, path-sensitive taint engine, alias/heap analysis, symbolic executor, or dynamic-trace collector. Opaque expressions are represented as expressions rather than fabricated source-variable identities.
- **Contracts:** Protobuf compiler descriptors are complete for compilable schemas, but unresolved import paths use a flagged source-parser fallback. OpenAPI remote $ref URLs are intentionally not fetched; arbitrary runtime service discovery and dynamic gateway rewrites cannot be inferred without evidence. Complex GraphQL runtime wiring beyond literal registered DataFetchers is unresolved.
- **Grafting:** the exact budget is for the cl100k_base tokenizer, not for every LLM/tokenizer family. It covers rendered context, not provider-specific conversation framing or tool-call overhead.
- **LSP/SCIP:** a compiler index or locally installed server is needed. Source symbols without compiler definitions are never assigned an exact resolution by external name matching. Local language server commands only run with explicit operator opt-in.
- **Performance:** multi-repository updates reuse per-repository parse results but recompose workspace relationships and semantic indexes; sparse semantic neighbors are bounded candidates, not exhaustive nearest neighbors.

**Release criterion:** Green full suite three times, three successful pinned DataHub equivalence trials, and all new source-grounded workstream tests passing. None of these constitutes formal proof of whole-program soundness or completeness.


## 5. Follow-up correctness enhancements (final code revision `27f5e3bf`)

After the initial five-workstream implementation, an additional source-grounded
regression pass identified and fixed these cases:

1. **Keyword/default parameter mapping:** Python callsite evidence now retains
   explicit keyword arguments, starred/unpacked arguments, required parameters,
   positional-only parameters and source argument expressions. The
   interprocedural graph maps each explicit keyword to its actual formal
   parameter, handles omitted defaulted parameters, and rejects ambiguous
   `*args`/`**kwargs` mappings. Nodes for complex argument expressions
   receive links from referenced local variables. Test:
   `tests/test_depth_additional.py`.
2. **Expression-level return/assignment flow:** Python locally referenced
   variables in arithmetic/container expressions now connect to assigned
   destination variables and return nodes. These are syntactic **may-flow**
   dependencies, not a path-sensitive SSA or heap alias guarantee.
3. **Compiler/LSP ambiguity:** Conflicting imported definitions for the same
   source occurrence or unqualified symbol no longer receive an exact match.
   Same-basename files in different directories are not conflated when
   source paths are qualified. A basename fallback remains available only
   when the caller supplied a bare filename.

These enhancements preserve the existing graph schema and callsite APIs;
`FLOWS_TO`, `CALLS`, `POLYMORPHIC_CALL`, and confidence semantics remain
consistent with the earlier implementation.

### Final triple test and real-repository gate

**Source commit:** `27f5e3bf240c6a8af8a07a302cb207f4ecee7dbf`  
**Workflow:** https://github.com/SNK0-0/SCKG_Build/actions/runs/43639044867

- Full suite pass 1: **190 passed, 3 skipped**.
- Full suite pass 2: **190 passed, 3 skipped**.
- Full suite pass 3: **190 passed, 3 skipped**.
- GitHub Actions: **success**. No failing test in those three runs.
- Real DataHub `datahub-actions/src` check: **3/3 matching** exact node IDs
  and typed-edge multiplicities after a controlled temporary source edit.
- DataHub post-edit graph in each trial: **3,604 nodes**, **9,756 edges**,
  **88 source files**. This is a pinned source subset, not all DataHub.

Measured CI times (seconds, not benchmark-standardized):

| Trial | Initial full | Incremental edit | Fresh post-edit |
| --- | ---: | ---: | ---: |
| 1 | 0.407937 | 0.173326 | 0.487623 |
| 2 | 0.459109 | 0.179324 | 0.529827 |
| 3 | 0.591281 | 0.183711 | 0.423803 |

The resulting graph-equivalence check proves equal **typed graph structures**
for the tested changes; it does not prove that all edges represent runtime truth.
Three skipped tests and limitations in §4 still apply.

### Additional regression scenarios

The expanded tests require:

- Correct binding of reordered keyword calls and expression reads
  (`f(y=v+1, x=3)`), including exact return-to-assignment flow.
- Correct handling of omitted defaulted parameters.
- No invented exact links for unpacked `**kwargs`.
- Variable-to-variable assignment and expression-to-return flow.
- Incremental versus fresh typed-graph equality after modifying the expressions.
- Collision-safe LSP index imports with conflicting same-name targets and
  same-basename files in different directories.

**Release scope:** The five requested depth workstreams are represented in the
code and their documented regression paths passed triple CI and real-source
equivalence tests. Full static semantic completeness for dynamic behavior,
arbitrary languages and runtime APIs is neither theoretically guaranteed nor
claimed.
