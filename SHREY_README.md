# Shrey's GRAFT-CKG work

This branch records my work on retrieving useful code context across repositories and programming languages. It builds on the shared GRAFT-CKG engine already present on `main`. The existing graph builder, multi-repository support, traversal, lineage, and benchmark infrastructure are collaborative foundations. This branch adds a controlled hybrid retrieval experiment layer and a labelled TypeScript-to-Python API evaluation.

## Research question

When an engineering question spans several files or services, which combination of text search, semantic search, and code relationships retrieves the best evidence within a fixed context budget?

The pipeline indexes code symbols, retrieves likely starting points, follows selected graph relationships, and packs source evidence for an LLM. The graph links can be inspected. Retrieval quality still has to be measured: a valid graph edge alone does not prove a better search result.

## Changes on this branch

| Area | What I added |
|---|---|
| Hybrid retrieval | [`hybrid_retrieval.py`](hybrid_retrieval.py) provides a common result format and 14 switchable configurations, R0–R13. They cover BM25, low-rank semantic vectors (LSA), rank fusion, AST scope, dependencies, dataflow, tests, Git lineage, API contracts, runtime trace input, documentation, query routing, and deterministic reranking. |
| Fair context assembly | Source evidence is packed within the same BPE-token budget for every configuration; results record why each item was selected. |
| Reproducible evaluation | [`bench/run_hybrid_retrieval.py`](bench/run_hybrid_retrieval.py) runs labelled queries with a shared corpus, top-K, budget, and output schema. Inputs and JSON results are in `bench/labels/` and `bench/results/`. |
| Polyglot API evaluation | `benchmarks/polyglot_api/` supplies six labelled TypeScript-to-Python HTTP links and two negative cases. [`eval_polyglot_api_bench.py`](eval_polyglot_api_bench.py) evaluates graph-edge construction; separate retrieval labels evaluate whether the correct Python handler is found. |
| Tests and explanation | `tests/test_hybrid_retrieval.py` and `tests/test_polyglot_api_bench.py` cover the shared interface, budget, routing, and API links. [`hybrid-retrieval-lab.html`](hybrid-retrieval-lab.html) is a local standup dashboard. |

R1 uses deterministic LSA over character n-grams, not a neural code embedding model. R13 uses a deterministic heuristic rather than a trained reranker. R8 and R10 need Git history and trace edges respectively to contribute their extra signals.

## Results so far

| Evaluation | Result | What it supports |
|---|---|---|
| API graph construction, six positive and two negative labelled cases | 6/6 expected HTTP links recovered; 2/2 negative cases left unlinked | Static literal TypeScript request to Python route linking works on this curated fixture. |
| Three-query Python/Go/TypeScript workspace retrieval | R1 leads at **0.750 MRR@5** | On this small workspace, semantic retrieval ranks the labelled answers best. |
| Six-query TypeScript-to-Python handler retrieval | R0, R3, R5, R9, and R12 tie at **0.889 MRR@5**; R9 has **100% Hits@5** | Contract-aware R9 retrieves all handlers, but has no demonstrated gain over simpler methods on literal-route questions. |
| Project regression suite | **60 tests passing** after installing the declared Go parser dependency | The branch's tests and existing project tests run together in the local environment. |

These are smoke tests with three or six retrieval questions. They establish that the experiment pipeline executes and reveal useful failure cases. They do not identify a general winner or support a paper-level accuracy claim. The six-link API graph result measures edge construction, not issue resolution.

## Run it locally

From the repository root, install the declared dependencies and run:

```powershell
python -m pip install -r requirements.txt
python -m pytest tests/ -q

python bench/run_hybrid_retrieval.py `
  --workspace examples/multi_repo_system/workspace.yaml `
  --labels bench/labels/hybrid_multi_repo_smoke.json `
  --output bench/results/hybrid_multi_repo_smoke.json

python bench/run_hybrid_retrieval.py `
  --repo benchmarks/polyglot_api `
  --labels bench/labels/polyglot_api_retrieval.json `
  --output bench/results/polyglot_api_retrieval.json
```

Open `hybrid-retrieval-lab.html` in a browser for the standup view. The experiment definitions are in [`HYBRID_RETRIEVAL_EXPERIMENTS.md`](HYBRID_RETRIEVAL_EXPERIMENTS.md). The API results and limitations are in [`POLYGLOT_API_BENCHMARK_REPORT.md`](POLYGLOT_API_BENCHMARK_REPORT.md) and [`POLYGLOT_API_RETRIEVAL_REPORT.md`](POLYGLOT_API_RETRIEVAL_REPORT.md).

## Next research steps

1. Build a larger set of version-pinned repositories and independently reviewed questions, especially questions that require cross-service relationships.
2. Compare R0, R1, R3, R5, R9, and R12 with the same candidate corpus, top-K, and token budgets. Report MRR, recall, context quality, latency, and index cost by query type.
3. Test neural code embeddings as a separately named backend, and evaluate whether graph expansion helps beyond strong lexical and semantic baselines.
4. Only after retrieval improves, evaluate downstream completion or issue-resolution tasks with a fixed model and prompt.
