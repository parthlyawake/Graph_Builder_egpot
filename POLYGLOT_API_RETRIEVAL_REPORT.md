# Polyglot API Retrieval Report

**Scope:** Six labelled TypeScript/Axios/fetch-to-Python route-handler queries
from `benchmarks/polyglot_api`, evaluated at `top_k=5` and a 2,048 BPE-token
context budget.

This measures retrieval of the correct backend handler. It is distinct from
the existing API-edge benchmark, which measures construction of `HTTP_CALLS`
edges.

## Results

| Configuration | MRR@5 | Hits@1 | Hits@5 | Mean BPE context |
|---|---:|---:|---:|---:|
| R0 — BM25 lexical | 0.889 | 83.3% | 100.0% | 544.0 |
| R1 — LSA semantic | 0.556 | 16.7% | 100.0% | 577.0 |
| R2 — RRF hybrid | 0.806 | 66.7% | 100.0% | 628.5 |
| R3 — AST hybrid | 0.889 | 83.3% | 100.0% | 927.8 |
| R4 — dependency hybrid | 0.806 | 66.7% | 100.0% | 703.5 |
| R5 — static hybrid | 0.889 | 83.3% | 100.0% | 1,017.7 |
| R9 — contract/polyglot hybrid | 0.889 | 83.3% | 100.0% | 1,017.7 |
| R12 — adaptive router | 0.889 | 83.3% | 100.0% | 1,017.7 |
| R13 — adaptive + reranker | 0.639 | 50.0% | 83.3% | 1,017.7 |

## Interpretation

R9 retrieves every labelled Python handler in the top five and ties the best
MRR on this fixture. It does **not** yet outperform BM25/R3/R5: the fixture
contains literal endpoint, method, and handler terms that make lexical
retrieval unusually strong. This is a correct negative result, not evidence
to claim that the contract layer improves handler retrieval generally.

The underlying graph-construction result remains 6/6 labelled `HTTP_CALLS`
edges with 2/2 negative cases unresolved. A larger pinned-repository benchmark
with route prefixes, routers, aliases, and indirect naming is needed to test
whether R9 creates a real retrieval advantage.

## Reproduce

```powershell
python bench/run_hybrid_retrieval.py `
  --repo benchmarks/polyglot_api `
  --labels bench/labels/polyglot_api_retrieval.json `
  --output bench/results/polyglot_api_retrieval.json
```
