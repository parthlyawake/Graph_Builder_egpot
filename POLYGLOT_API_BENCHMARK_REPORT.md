# Polyglot API-Bench v1 report

**Run date:** 2026-09-13  
**Baseline:** upstream commit `1c566173e06d7e9a43cdfb247d15ba4c2acceda3`  
**Current implementation:** the working tree containing the Tree-sitter polyglot
adapter, JavaScript/TypeScript flow extraction, and static HTTP-link resolver.

## Purpose

This benchmark measures the feature introduced in this project: recovery of
static links from TypeScript frontend requests to Python backend route handlers.
It is intentionally separate from SWE-bench Lite. SWE-bench Lite is Python-only
and evaluates issue resolution, so it cannot measure TypeScript parsing or
frontend-to-backend endpoint linkage.

## Benchmark design

The checked-in fixture at `benchmarks/polyglot_api` contains four source files
(89 lines):

- Flask-style handlers using `@app.get`, `@app.post`, and `@app.route`;
- FastAPI-style handlers using `@router.get` and `@router.delete`;
- TypeScript callers using `fetch()` with default and explicit methods;
- TypeScript callers using Axios `get()` and `delete()`.

It has six labelled positive edges and two labelled negative cases:

| Case class | Count | Expected outcome |
|---|---:|---|
| Literal method + path matching a Python handler | 6 | One `HTTP_CALLS` graph edge |
| Dynamic template-literal URL | 1 | No edge |
| Literal URL with a mismatching method | 1 | No edge |

An edge is correct only when both its frontend function and Python handler match
the label. Metrics are standard edge-level precision, recall, and F1. This
prevents a route with the right path but wrong HTTP method from being counted as
correct.

## Before/after results

| Measure | Upstream baseline | Current implementation |
|---|---:|---:|
| Parsed source files | 2 Python | 2 Python + 2 TypeScript |
| Graph nodes | 26 | 52 |
| Graph edges | 32 | 67 |
| Labelled positive links recovered | 0 / 6 | 6 / 6 |
| False positives | 0 | 0 |
| Precision | 0.0%* | 100.0% |
| Recall | 0.0% | 100.0% |
| F1 | 0.0% | 100.0% |
| Negative cases kept unresolved | 2 / 2 | 2 / 2 |
| One-pass build time | 0.0050 s | 0.0083 s |

\*The baseline emitted no API-link edges, so conventional precision is
undefined; the evaluator reports `0.0%` consistently rather than treating an
empty output as perfect precision.

## Interpretation

The result is a direct capability change, not an agent or issue-resolution
claim. The upstream baseline scanned only Python and had no representation for
frontend HTTP calls. The current implementation parses the TypeScript callers,
indexes literal Python route decorators, and connects only exact static
method/path matches. The small additional build time is measured on this
89-line fixture and should not be extrapolated to large repositories.

## Reproduce

```powershell
# From the project root
git worktree add --detach ..\sckg-upstream-baseline 1c566173e06d7e9a43cdfb247d15ba4c2acceda3
python eval_polyglot_api_bench.py --baseline-root ..\sckg-upstream-baseline
python -m unittest discover -s tests -v
git worktree remove ..\sckg-upstream-baseline
```

The run produced 10/10 passing project tests, including the benchmark
regression test.

## Limits and next benchmark

This is a deterministic curated benchmark, not a claim of real-world API-link
accuracy. It covers only literal URLs and direct route decorators. It does not
cover route prefixes, application factories, router composition, dynamic URLs,
proxies, gateways, runtime registration, authentication middleware, or
JavaScript alias/property flow.

The appropriate next stage is **Polyglot API-Bench v2**: 20–30 version-pinned,
manually labelled open-source repositories with TypeScript frontend and Python
backend code. That will provide real-repository precision, recall, F1, p50/p95
latency, and failure-category analysis. SWE-bench Lite should remain a separate
Python-regression and downstream-agent benchmark, not evidence for this
polyglot feature.
