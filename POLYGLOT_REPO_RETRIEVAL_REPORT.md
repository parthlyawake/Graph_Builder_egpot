# File retrieval comparison on the polyglot repository list

- **Run:** 2026-10-25
- **Builder revision:** `1eadc47c15f9294a632ea0205bff18a395847415`
- **Evidence:** [`bench/results/polyglot_repo_file_retrieval.json`](bench/results/polyglot_repo_file_retrieval.json)
- **Interactive dashboard:** [`polyglot_retrieval_dashboard.html`](polyglot_retrieval_dashboard.html)
- **Runnable benchmark:** [`bench/run_polyglot_repo_file_retrieval.py`](bench/run_polyglot_repo_file_retrieval.py)
- **Queries and manually checked labels:** [`bench/labels/polyglot_repo_file_retrieval.json`](bench/labels/polyglot_repo_file_retrieval.json)

## Answer

For the current goal—returning an **array of possibly affected source files**—**R3 (BM25 + LSA + symbol/path matching + AST scope)** is the provisional choice. It had the highest File Recall@10 at **90.5%**, but missed two Train-Ticket files. R5, R6, R8, R9, R10, and R12 matched that coverage without improving it. **R1 (LSA alone)** had the best first-relevant-file rank, with **0.593 MRR@10** and **47.6% Hits@1**, but lower total file recall at 88.1%. There is no single winner on both measures.

This is a small, curated localization exercise. It is useful for choosing the next experiments; it does not establish a statistically reliable winner or a paper-ready retrieval claim.

## Test design

- Used the eight repositories from the [polyglot list](https://github.com/Vikas-Personal-Research-Org/polygot-repo-list) and the final corrected graph snapshots from the [graph-builder audit](GRAPH_BUILDER_FIX_VALIDATION.md). Source revisions and graph paths are recorded per repository in the JSON result. The source checkouts are pinned snapshots without `.git` directories.
- Searched **each listed application separately**. These are unrelated products; mixing them into one workspace would add irrelevant competition. This measures performance across the list, not cross-repository navigation inside a single product.
- Wrote three natural-language, issue-like queries per application. I checked the relevant source files directly, including two queries with two relevant files. All expected files were confirmed to exist and to have retrieval candidates in their graphs before scoring.
- Queried all 14 implemented configurations, R0–R13, with identical query text and a 2,048-token context budget. The declared `rank_bm25` dependency was installed for this run; the runner now refuses to run with the TF-IDF fallback. Evaluated the first **10 distinct files**, rather than counting multiple function nodes in one file as separate results. The runner retrieves up to 250 candidate nodes to form that file list.
- Reported **File Recall@10** (fraction of all labelled files present), **Hits@1** (first file relevant), and **MRR@10** (reciprocal rank of the first relevant file). Each of the seven application corpora has three tasks, so averaging 21 tasks gives equal weight to each application.
- Sock Shop's listed umbrella repository contains deployment and dashboard code, not its service implementations. Two dashboard tasks were run as a smoke test and excluded from the primary comparison.

## Results on 21 application tasks

| Method | What it adds | File Recall@10 | Hits@1 | MRR@10 |
| --- | --- | ---: | ---: | ---: |
| R0 | BM25 lexical baseline | 81.0% | **47.6%** | 0.578 |
| R1 | LSA semantic vectors | 88.1% | **47.6%** | **0.593** |
| R2 | BM25 + LSA fusion | 85.7% | 38.1% | 0.497 |
| **R3** | **R2 + symbol/path + AST scope** | **90.5%** | 38.1% | 0.534 |
| R4 | R2 + dependency edges | 85.7% | 38.1% | 0.496 |
| R5 | R3 + dependency edges | **90.5%** | 38.1% | 0.533 |
| R6 | R5 + data flow | **90.5%** | 38.1% | 0.533 |
| R7 | R5 + test-file heuristic | 42.9% | 9.5% | 0.142 |
| R8 | R5 + Git lineage | **90.5%** | 38.1% | 0.533 |
| R9 | R5 + API/gRPC contracts | **90.5%** | 38.1% | 0.533 |
| R10 | R9 + runtime trace | **90.5%** | 38.1% | 0.533 |
| R11 | R5 + documentation | 85.7% | 38.1% | 0.528 |
| R12 | Adaptive router | **90.5%** | 38.1% | 0.533 |
| R13 | R12 + reranker | 85.7% | 38.1% | 0.532 |

## What the rankings show

- R3 recovered the Redis checkout repository file in AWS Retail at **rank 2**, which R1 and R2 missed. It missed Train-Ticket's station-food CORS file and dashboard date script. Plain BM25 found the date script at **rank 6**. These cases show that the methods have different strengths even where their aggregate scores are close.
- R1 ranked a first relevant file better overall, but found only one of the two labelled files for the retail catalog reindex task. For affected-file arrays, this is why File Recall@10 matters alongside MRR.
- Adding dependency, data-flow, and contract expansion to R3 did **not** raise file recall on these tasks. This result does not mean those graph edges lack value: this label set has few true cross-service root-cause chains, and it mainly asks for source-file localization.
- R7's test heuristic pushed broad test files ahead of implementation files even for queries that did not ask for tests. This is a concrete ranking defect to fix before treating R7 as a competitive test-aware method.
- R13's deterministic reranker lost a top-10 hit on the retail reindex task and a DeathStarBench timeline task compared with R3. Its current overlap bonus can favor similarly named but wrong modules.
- Sock Shop's two dashboard smoke tasks returned the sole dashboard file at rank 1 for most configurations. That says nothing about retrieval across its service repositories.

## Limits and next evaluation

1. **Small, curated labels:** The 21 application tasks were created from inspected source examples in the graph audit. They are not held-out real bug reports. Expand to independently written issues and several relevant files per issue before making a paper claim.
2. **Feature coverage:** The source snapshots have no Git histories, so R8 gained no lineage evidence. No runtime traces were supplied, so R10's extra signal was untested. R8 and R10 must be rerun with those inputs before assessing those features.
3. **Language coverage:** DeathStarBench's main C++/Thrift services and OpenTelemetry's Rust shipping service are outside the current parser coverage. The selected tasks there target supported source. Report these as coverage limits, not retrieval successes.
4. **Sock Shop:** Clone its component service repositories into a multi-repo workspace to test service-level retrieval. The listed umbrella checkout cannot provide those labels.
5. **File ranking:** The current retriever ranks graph nodes; this runner collapses them into distinct files after ranking. A production affected-file API should score and deduplicate files directly, and report evidence paths and uncertainty.

## Reproduce

From the `official-sckg` directory, with the pinned source trees and audit graph snapshots in `../graph_validation_repos`:

```powershell
python -m pip install -e .
python bench/run_polyglot_repo_file_retrieval.py
```

The runner validates every label against the source tree and graph candidates, then writes all per-query file lists and scores to `bench/results/polyglot_repo_file_retrieval.json`.
