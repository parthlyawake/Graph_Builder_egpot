# Source-grounded graph verification

This verification pipeline supplements graph_verifier.py, which tests graph
invariants but cannot establish full extraction accuracy.

## Five phases

1. Independently label code declarations and exact triples against pinned
   source files. Use a source path and a distinctive code excerpt as evidence.
   The supplied Online Boutique seed has 21 consumer labels from the existing
   audit; it is **not** independently re-audited, has no producer handler IDs,
   and must not be described as ground-truth precision.
2. Run bench/verify_graph_accuracy.py to compare exact node IDs and exact
   (source, relation, target) triples. Report recall for sampled labels.
   Precision/F1 are computed ONLY for explicitly complete closed_scopes.
3. Capture actual runtime calls using instrumentation and export exact
   observed_edges triples. For Python call traces, see bench/trace_oracle.py.
   For gRPC/HTTP, provide span-derived source/target IDs after mapping traces
   to actual code locations. Runtime coverage is a positive-only oracle.
4. Inject a controlled source edit on a temporary repository copy and compare
   the incremental graph with a fresh full rebuild. Require expected delta
   node/edge assertions for meaningful fault-injection validation.
5. Repeat with separately audited labels per repository, language, and
   relation type; report unlabelled scope and unsupported language coverage.

## Run on Online Boutique

Clone a PINNED upstream revision and install project dependencies first.
The starter labels use single-repository node IDs and should be evaluated
against a single-repo graph (no workspace prefix). Missing paths are failures.

    python bench/verify_graph_accuracy.py \
      --repo /path/to/microservices-demo \
      --labels bench/labels/online_boutique_accuracy_seed.json \
      --output bench/results/online_boutique_accuracy_report.json \
      --fail-on-missing

After reviewing the source, create a new label file with exact fully qualified
producer handler IDs, independent source evidence, and closed scopes. Example:

    {
      "status": "independently_reviewed",
      "nodes": [{"id": "src/service.py:handle",
                 "evidence": {"file": "src/service.py", "contains": "def handle("}}],
      "edges": [{"source": "src/service.py:handle",
                 "relation": "IMPLEMENTS",
                 "target": "contract::Service.Call",
                 "language": "python",
                 "evidence": {"file": "src/service.py", "contains": "def handle("}}],
      "negatives": [],
      "closed_scopes": [{"relation": "IMPLEMENTS",
                         "sources": ["src/service.py:handle"],
                         "language": "python"}]
    }

Every closed scope asserts that ALL outgoing edges of that relation from its
specified source IDs have been labelled. Do NOT mark a partially annotated
scope closed. The evaluator otherwise leaves precision explicitly null.

    python bench/verify_graph_accuracy.py \
      --repo /path/to/repo \
      --labels /path/to/independent_labels.json \
      --source-root /path/to/repo \
      --trace /path/to/observed_traces.json \
      --mutation /path/to/mutation.json \
      --output /path/to/report.json \
      --fail-on-missing

Runtime trace schema:

    {"observed_edges": [
      {"source": "src/client.py:request", "relation": "CONSUMES",
       "target": "contract::Service.Call"}]}

Mutation schema (real code edit is applied only to a temporary copy):

    {"file": "src/service.py",
     "old": "def old_handler(",
     "new": "def new_handler(",
     "expected_added_nodes": ["src/service.py:new_handler"],
     "expected_removed_nodes": ["src/service.py:old_handler"]}

Mutation results compare exact node IDs, selected metadata and edge
multiplicities. This is a structural equivalence check, not a proof that both
graphs represent every runtime behavior. For contract skew, select a
checked-in fixture with a uniquely matched proto edit.

Use python -m unittest discover -s tests -p test_verify_graph_accuracy.py

## Reporting discipline

- A passing sampled-label check is not full graph accuracy.
- Absence of observed runtime edges is not proof of a false static edge.
- Source snippets must be reviewed independently; marker matching only
  verifies that cited evidence still exists, not that the relationship is true.
- Prefixes must match exact graph IDs; no substring or fuzzy matching.
- Never invent source-level producer IDs to make producer precision 100%.
- Pin upstream repository revisions, dependencies, seed, labels, and hardware
  when publishing benchmark results.

For node precision/F1, add closed_node_scopes entries with a node type and
an exhaustive list of file paths, e.g. {"type":"function","files":["src/service.py"],
"language":"python"}. Each matching node label must include its type and file.
This is a promise that every in-scope declaration has been annotated.
