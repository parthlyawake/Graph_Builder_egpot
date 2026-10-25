# Graph builder fixes: follow-up validation

**Date:** 2026-10-25

**Baseline:** [polyglot graph audit](GRAPH_BUILDER_POLYGLOT_AUDIT.md) on builder revision `3ce1ba2`

**Scope:** graph construction only. Retrieval and runtime behavior were not evaluated.

## What changed

1. **One HTTP contract per route.** Spring routes now feed the same `http::METHOD:/path` contract builder used by other languages. The canonical node keeps `IMPLEMENTS` (handler to route) and `PRODUCES` (route to handler) edges. The older `contract::HTTP.METHOD./path` duplicate is no longer created.
2. **Safer call resolution.** An unknown qualified receiver no longer binds to a same-named repository method. The Robot Shop `System.getenv` call now points to an external symbol rather than back to `Controller.getenv`.
3. **Go struct-field type resolution.** For a typed field such as `Controller.api *CatalogAPI`, `c.api.Reindex()` now reaches `CatalogAPI.Reindex` when the type is unambiguous. It does not select another `Reindex` implementation by name alone.
4. **Interface and closure edges.** Java/C# interface methods receive `DECLARES` edges. Invoking a Go function literal no longer creates an external node whose name is its entire source body.
5. **Dynamic-host HTTP evidence.** A Python `session.post(base + "/path")` or Go `http.NewRequest("POST", base+"/path", ...)` creates an `http_callsite` with the visible method and path. If an indexed route has the same method and path, a `POSSIBLE_HTTP_TARGET` edge marks it as a candidate. This is deliberately separate from confirmed `HTTP_CALLS` because the host remains unresolved.

The GraphProvider contract now exposes distinct `HTTP_CALLSITE`, `HTTP_REQUEST`, and `POSSIBLE_HTTP_TARGET` types. The local viewer colors callsites as contract-layer nodes.

## Measured checks on the same pinned repositories

All eight graph builds completed without parser warnings. Repeating the same seeded source sample gave **24/24 matching function nodes and 24/24 containment edges**. The full test suite passed **87 tests**. The compact machine-readable comparison is [fix_verification.json](bench/results/graph_builder_audit/fix_verification.json).

| Real-repo check | Before | After |
| --- | ---: | ---: |
| Duplicate HTTP route names, AWS Retail Store | 44 | **0** |
| Duplicate HTTP route names, Robot Shop | 9 | **0** |
| Duplicate HTTP route names, Train-Ticket | 262 | **0** |
| Robot Shop `Controller.getenv → Controller.getenv` false `CALLS` | Present | **Absent**; `external::System.getenv` present |
| AWS Retail `Controller.ReindexProducts → CatalogAPI.Reindex` | Missing | **Present** |
| Online Boutique `ICartStore → Ping` `DECLARES` | Missing | **Present** |
| Product catalog `main → external::func() {…}` pseudo-call | Present | **Absent** |
| Astronomy Shop `checkout.shipOrder` dynamic-host path | Not represented as HTTP evidence | **`POST /ship-order` callsite** |
| DeathStarBench `upload_movie_info` dynamic-host path | Not represented as HTTP evidence | **`POST /wrk2-api/movie-info/write` callsite** |

The final builds have 17 dynamic-host HTTP callsites in Astronomy Shop and 7 in the extracted DeathStarBench source. They are evidence nodes, not 24 confirmed service links. The test fixture also verifies that an exact method/path match creates `POSSIBLE_HTTP_TARGET` while leaving `HTTP_CALLS` absent.

## Remaining limits

- A dynamic host is not proven to point at a local service. The new possible-target relation must not be treated as a confirmed affected-service link.
- C++ and Thrift in DeathStarBench, plus additional Astronomy Shop languages, remain outside the six supported programming languages and `.proto` parser. This work does not claim a complete graph of those systems.
- The Sock Shop repository in the source list is an umbrella deployment repository. Its separate service repositories still need a service-level audit.
- The original audit used a seeded sample, so these checks do not establish exhaustive edge precision or recall. No retrieval benchmark scores were produced here.

## Reproduce

Build the same pinned repository trees using [audit_graph_builder.py](bench/audit_graph_builder.py), then run the sample script from the [baseline audit](GRAPH_BUILDER_POLYGLOT_AUDIT.md). With locally generated pre-fix and fixed graph snapshots:

```powershell
python bench/verify_graph_audit_fixes.py --before "C:\path\to\results_main" --after "C:\path\to\results_final" --output "C:\path\to\fix_verification.json"
```

The validator checks all eight builds, the 24 sampled declarations, route duplication, and the concrete source relationships above. Only its compact JSON result is committed; graph pickles and upstream clones remain local.
