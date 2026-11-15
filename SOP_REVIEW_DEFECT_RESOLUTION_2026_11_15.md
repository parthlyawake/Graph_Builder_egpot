# SOP review defect remediation (2026-11-15)

Source: user-provided external review titled "Seven builder defects found in a review of the remediation harness" (2026-11-13), referencing old builder commit 2d6c55076856bd2cfb69d096e26e4d66ec580925.

This patchset applies to a newer krishna revision. The defects were **individually checked against current code** before modification. Do not treat review line numbers from November 2 as current line numbers.

## Resolution matrix

| # | Status | Implemented / retained behavior |
|---|---|---|
| 1: HTTP path collides across repos | Fixed in source-grounded resolver; legacy fallback made non-assertive | URL hosts from Python/Java source and JS/TS/Go literal clients resolve to exactly one repo using workspace and supported deployment aliases. Relative/path-only requests never assert cross-service HTTP_CALLS; non-strict mode can retain POSSIBLE_HTTP_TARGET candidates. Strict mode omits those candidates. |
| 2: stack-frame wrong repo / absolute paths | Fixed | Complete path-segment suffix scoring plus service namespace preference, then exact function or source line matching. Parseable but unmatched frames do not become arbitrary high-confidence service candidates. |
| 3: nondeterministic, over-budget forward traversal | Fixed | Stable BFS neighbors by canonical ID, firm max_nodes enforcement at discovery, root first, and stable returned nodes. Source code semantics are kept in typed edges. |
| 4: missing absolute JS/TS URLs and HTTP verbs | Partially expanded, with deliberate limitations | JS/TS fetch/axios and Go literal URLs retain host evidence; Java and C# basic verb inference handles PUT/PATCH/DELETE/HEAD/OPTIONS; path templates can contain {id}, <id> or :id. Complex frameworks and runtime-built hosts are not fully resolved. |
| 5: silent missing language/parser coverage | Already partially fixed; improved | Seven-language registry and dependencies were already present. Missing grammars fail fast. A structured skipped_files list now exposes parse failures, partial parses, missing grammar and unsupported sources, and appears in single-repo and workspace verification. |
| 6: dense semantic matrix / noisy blast radius | Sparse construction already present; traversal fixed | Both graph builders already use sparse_semantic_pairs. Provider blast radius now excludes semantic and syntactic containment links by default; explicit TraversalPolicy.include_layers can opt in. Diagnosis results are cached per graph object/size, with explicit cache invalidation for equal-sized content edits. |
| 7: substring heuristics | Fixed in reported paths | Test-prefixed production names such as TestimonialService are no longer excluded solely by their name; service aliases must match exactly (allowing conventional -service suffix); ignore patterns no longer match arbitrary interior substrings; ambiguous bare module filenames are not assigned to first-seen directory. |

## How to reproduce

Install from requirements.txt and run:

    python -m pytest -q tests/test_sop_review_defects.py
    python -m pytest -q tests
    python -m compileall -q contracts/sckg_provider.py contracts/graph_types.py graft_ckg.py polyglot.py multi_repo.py graph_builder_http.py

For a real workspace inspect:

    WorkspaceCKGBuilder("workspace.yaml").verify_graph()["skipped_file_count"]

The graph provider is a static-analysis adapter, not a dynamic tracer. A POSSIBLE_HTTP_TARGET edge must not be fed to a remediation agent as confirmed execution. If the graph is changed without changing node/edge counts, call provider.invalidate_analysis_cache() before repeated root-cause diagnosis.

## Deliberate non-goals and remaining work

- No blanket support is claimed for JS template literals with runtime hosts, framework mount prefixes, Django URL includes, gin/chi/echo muxes, all Python HTTP-client alias forms, or Kubernetes runtime DNS.
- A host alias is accepted only when the source repository can be identified unambiguously; ambiguous host/route combinations are not upgraded to asserted calls.
- The previously published paper's ranking and ablation outputs are tied to its **earlier source revision**. Rerun and pin all experiments after merging this change before claiming final paper results. Graph invariants or small fixture P/R do not establish real-world accuracy.
