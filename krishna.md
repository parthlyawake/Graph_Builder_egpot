# Krishna: graph-builder review guide

This branch is a handoff for reviewing the graph construction changes. Start with source-to-graph correctness: whether a recovered cross-service edge has the right caller, producer, HTTP verb/route or RPC, and source evidence. Retrieval scores are not evidence that a graph edge is correct.

The code snapshot before this guide is `9fa4398`. The branch also contains EG-POT, evaluation records and the offline site; the focused graph changes below can be reviewed independently through their commits.

## 1. Start with these two commits

| Commit | Change | Main review question |
| --- | --- | --- |
| `92bcaf6` | Producer binding after workspace composition; JS bound handlers; C# and Java gRPC registrations | Does each `IMPLEMENTS` edge correspond to a real registration and the correct concrete handler? |
| `9a89265` (`builder-http-22a`) | Source/config-based HTTP service-to-service resolution and opt-in production-file filtering | Does a unique host + verb + route identify exactly one producer, with no guessed binding? |

```powershell
git show --stat 92bcaf6
git show 92bcaf6 -- graft_ckg.py multi_repo.py polyglot.py
git show --stat 9a89265
git show 9a89265 -- graft_ckg.py multi_repo.py polyglot.py
```

For a combined builder diff, excluding the traversal/site changes:

```powershell
git diff 92bcaf6^ 9a89265 -- graft_ckg.py multi_repo.py polyglot.py tests/test_contract_binding_fixes.py tests/test_contract_binding_csharp_java.py tests/test_workspace_http_resolution.py
```

## 2. Read the construction pipeline in this order

1. [multi_repo.py](multi_repo.py): `WorkspaceConfig`, `WorkspaceCKGBuilder.build`, `_compose_workspace`, and `update_files`. Check namespacing, shared-contract availability, composition order and incremental recomposition.
2. [graft_ckg.py](graft_ckg.py): `CKGBuilder.build`, `update_files`, registration bookkeeping and `_bind_contract_producers`. Check that registrations skipped before shared protos exist are rebound later, without duplicate or stale edges.
3. [polyglot.py](polyglot.py): `TreeSitterExtractor`, language-specific call extraction and registration recognition. Check what is actually parsed rather than assuming all framework patterns are supported.
4. Back in [multi_repo.py](multi_repo.py), inspect `_resolve_cross_repo_http_calls`, `_http_path_matches`, `_http_deployment_context`, `_java_http_requests` and `_python_http_requests`.

Use the raw NetworkX `MultiDiGraph` for this review. Distinguish edge incidences from unique node pairs: parallel/reverse relations can connect the same two nodes.

## 3. Producer binding checklist

- Shared proto contracts must exist before binding; unknown services must not create invented contracts.
- Go registrations and Python servicer registrations must bind after workspace composition, not only in the service-local build.
- JS class-qualified handlers such as `ClassName.method.bind(this)` must resolve to the correct local class and method, without accepting unrelated receivers.
- C#: `MapGrpcService<T>()` must resolve the registered class and generated service base; RPC methods require the appropriate overriding PascalCase method.
- Java: `.addService(new X(...))` must resolve the registered class, including nested/qualified classes; the generated service base determines the service, and RPC names map to lowerCamelCase methods.
- Run producer binding twice: edge identities and counts should not change.
- Updating/removing a registration or shared proto must produce the same relevant graph as a full rebuild and must not retain stale bindings.

Tests: [test_contract_binding_fixes.py](tests/test_contract_binding_fixes.py) and [test_contract_binding_csharp_java.py](tests/test_contract_binding_csharp_java.py).

## 4. HTTP resolution checklist

- Java: literals, literal-plus-parameter URLs, service-URL helpers, RestTemplate, WebClient and HttpClient patterns.
- Python: requests/urllib/httpx URLs; environment values recovered from Kubernetes/compose configuration; supported imported helpers followed one level.
- Resolve the host to exactly one workspace service. Check aliases, ports and ambiguous/unknown hosts.
- Match the HTTP verb and the combined class/method route. Route parameters may match variable segments; a wrong path or verb must not bind.
- Reject overloaded/ambiguous producer definitions and unknown configuration rather than selecting a plausible destination.
- Inspect `match_kind`, `source_evidence`, `http_method` and `http_url` on recovered edges, and open the real source at the recorded line.
- The recovered direct edge is `caller --HTTP_CALLS (Ldep)--> handler`. The handler points to its `http_endpoint` with `IMPLEMENTS`; the graph may also contain `endpoint --PRODUCES--> handler`. Do not assume HTTP follows the same edge layout as gRPC.
- `exclude_nonproduction` defaults to `False`; the frozen Train-Ticket build explicitly enables it. Check that tests/generated/vendor filtering remains opt-in for existing callers.

Tests: [test_workspace_http_resolution.py](tests/test_workspace_http_resolution.py), including wrong verb/path/host, ambiguous hosts/endpoints, unknown env values, helper resolution and incremental/full equivalence.

## 5. Reproduce the focused tests

Use Python >=3.10 and an isolated environment. Java and C# parsers are optional extras; skipping their tests is not a successful validation of those languages.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install tree-sitter-java tree-sitter-c-sharp
python -B -m pytest -p no:cacheprovider tests/test_contract_binding_fixes.py tests/test_contract_binding_csharp_java.py tests/test_workspace_http_resolution.py
```

Then broaden to the existing construction/contract regressions:

```powershell
python -B -m pytest -p no:cacheprovider tests/test_graph_audit_fixes.py tests/test_contract_layer.py tests/test_interface_http_contracts.py tests/test_multi_repo.py tests/test_polyglot_integration.py tests/test_polyglot_spring_events.py tests/test_polyglot_api_bench.py
```

These commands are review instructions, not a claim that tests were rerun when this documentation was added. Record your Python/parser versions, passed/failed/skipped counts, and any traceback.

## 6. Check the frozen graph evidence

| Artifact | What to inspect |
| --- | --- |
| [Online Boutique graph](bench/results/online_boutique_graph_fresh.graphml) | Real polyglot producer bindings; verify caller, RPC contract and implementation against source. |
| [Online Boutique labels](bench/labels/online_boutique_egpot_queries.json) | Fifteen previously source-checked links and their source locations; use as graph evidence, not for retrieval tuning. |
| `bench/results/train_ticket_graph.graphml` (local artifact) | Direct HTTP caller-to-handler links and handler-to-endpoint structure; this file is ignored by Git and is not included in this branch. |
| [Train build settings](bench/results/train_ticket_graph.build_config.json) | Effective workspace, service roots and exclusions; local source paths need adjustment on your machine. |
| [Train provenance](bench/results/train_ticket_graph.provenance.json) | Source commit, builder identity, parser versions, graph hash and construction counts. |

The Train graph itself is approximately 81.7 MB and is local-only. For direct inspection, obtain that exact artifact separately or rebuild from the source commit and settings in the tracked provenance/config; adjust the absolute source paths for your machine. The Online Boutique fresh graph is tracked and available on this branch.

The frozen Train graph records **24,990 nodes, 123,738 edges, 123 unique HTTP_CALLS pairs, 263 http_endpoint nodes and one topic_contract node**. Its SHA256 is:

```text
8904e43268d34bd7b8734ec8f93326eb60051a6d2ac71484816ff595cc2a4c55
```

Load saved graphs with `nx.read_graphml(path, force_multigraph=True)`. Metadata may change Python types on reload; inspect both relation/layer and the individual metadata fields.

For a new build, use `WorkspaceConfig` / `WorkspaceCKGBuilder` and save to a new scratch path. Keep the committed frozen graphs, labels, preregistration and locked result JSONs unchanged. Do not invoke `--mode test-final`, `--mode run-locked` or second-look flags as part of this graph review.

## 7. Known limitations worth checking

- **Missing internal Java call chains:** the frozen Train graph has no controller-to-concrete-function `CALLS` edges. Controller delegation commonly remains an `external_func`, even when the source contains a service call. Correct HTTP bindings do not imply a complete intra-service call graph.
- **Java searchable source:** Java handler `code` fields are generally empty in the frozen Train graph. Real method bodies exist in source but are not necessarily carried into node text. Distinguish missing graph text from missing source.
- **Static configuration only:** an unknown/ambiguous URL, dynamic configuration, reflection or runtime dispatch may remain unresolved. A missing edge is not proof of no dependency.
- **Source coordinates:** Java method positions can point to an annotation rather than the declaration line; Online Boutique `getAds` records the `@Override` line (93), while its declaration is line 94.
- **Producer registration versus active runtime implementation:** EmailService and DummyEmailService may both have source registrations; Online Boutique's runtime `start()` chooses the dummy implementation. Check runtime selection separately from static binding.
- **Repeated relationships:** `IMPLEMENTS` and reverse `PRODUCES` can give two traversal incidences to one endpoint. Report unique targets separately from edge counts.
- **Documentation drift:** the broad README/viewer guide predates some HTTP changes. Use the implementation, focused tests and provenance to establish actual behavior; do not inherit old performance/coverage claims without reproducing them.

The recent exploratory source/task sheets live outside Git under `C:\dev\triage_out`; they are not part of this branch or the locked record. Everything required to start the code review is listed above.

## 8. Optional visual inspection

- [TEAMMATE_GRAPH_GUIDE.md](TEAMMATE_GRAPH_GUIDE.md) explains the local repository viewer.
- Open [viz/index.html](viz/index.html) for the offline benchmark site. The graph tab is rendered by [viz/js/graph_view.js](viz/js/graph_view.js); this is a view of exported data, not a fresh parser run.
- The source-to-graph audit entry point is [bench/audit_graph_builder.py](bench/audit_graph_builder.py). It builds one repository without retrieval and requires explicit `--repo` and `--output` paths. Workspace HTTP binding should be reviewed through the workspace builder instead.

## What to send back

For each issue, provide the source repository/commit, minimal source snippet, expected edge, actual nodes/edges and metadata, full-build versus incremental behavior, and a suggested regression fixture. Please separate confirmed incorrect edges, missing supported bindings and unsupported framework patterns. The review is about graph correctness and coverage; traversal outcomes are a separate question.
