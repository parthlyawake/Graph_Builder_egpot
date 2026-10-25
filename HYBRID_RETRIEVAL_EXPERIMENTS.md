# Hybrid Retrieval Experiment Protocol

`hybrid_retrieval.py` implements every R0–R13 variant using one candidate
corpus, fixed token budget, common labels, and a shared output schema. This is
important: an apparent gain is not meaningful if a method receives more source
files, a larger token budget, or a different repository revision.

## Implemented configurations

| ID | Method | Implementation status |
|---|---|---|
| R0 | BM25 lexical | Implemented |
| R1 | Low-rank semantic (LSA) vectors | Implemented |
| R2 | BM25 + LSA reciprocal-rank fusion | Implemented |
| R3 | R2 + AST scope expansion | Implemented |
| R4 | R2 + dependency graph expansion | Implemented |
| R5 | R3 + R4 static hybrid | Implemented |
| R6 | R5 + dataflow expansion | Implemented |
| R7 | R5 + test-aware heuristic | Implemented |
| R8 | R5 + Git `TOUCHES` lineage | Implemented; use `--ingest-lineage` |
| R9 | R5 + HTTP/gRPC/Protobuf contracts | Implemented |
| R10 | R9 + runtime trace links | Implemented; supply JSON trace edges |
| R11 | R5 + Markdown/text architecture documents | Implemented |
| R12 | Query-adaptive routing among R5–R11 | Implemented |
| R13 | R12 + deterministic evidence reranking | Implemented |

## Reproduce the smoke benchmark

```powershell
python bench/run_hybrid_retrieval.py `
  --repo examples/hybrid_retrieval_system `
  --labels bench/labels/hybrid_retrieval_demo.json `
  --output bench/results/hybrid_retrieval_demo.json
```

The fixture is a smoke test, not a paper result. For a publication benchmark,
pin each repository commit and run the same labels, embedding backend, top-K,
and context budget for every configuration.

## Run a real workspace

```powershell
python bench/run_hybrid_retrieval.py `
  --workspace examples/multi_repo_system/workspace.yaml `
  --labels path/to/labelled_queries.json `
  --token-budget 4096 `
  --ingest-lineage `
  --output bench/results/hybrid_workspace.json
```

Runtime edges for R10 use a JSON list of `{ "source", "target", "confidence" }`
objects. The existing `bench/trace_oracle.py` is the starting point for
collecting them. R1 currently uses reproducible LSA vectors; a neural code
embedding adapter should be evaluated as a separately named backend, never
substituted into historical R1 scores.
