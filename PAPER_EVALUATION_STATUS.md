# GRAFT-CKG Paper Evaluation — Revised, Measured, Versioned

**Status:** exploratory reproducible research results; **not publication certified** pending independent human adjudication of labels.

## Exact source and experiment provenance

- Implementation branch: `research-evaluation-2026-11-15`, based on `krishna` commit `55ffb70fc0f7f75b8e5fc9620fa721f27ee6f2c2`.
- Validation workflow on evaluation branch: [run 43642747947](https://github.com/SNK0-0/SCKG_Build/actions/runs/43642747947) (successful).
- Online Boutique source: `GoogleCloudPlatform/microservices-demo@38e7348eb289eb5b87c0c6e8cb19ced0449dc389`.
- DataHub source: `datahub-project/datahub@051fb78fe6a6395043d272218b035cb00fe27321`, only `datahub-actions/src`.
- Retrieval tasks: `bench/labels/online_boutique_27_source_tasks.json`, exact canonical node IDs, 27 source-inspected tasks, human sign-off pending.
- Closed-scope fixture labels: `bench/labels/polyglot_api_closed_scopes.json` and `bench/labels/paper_relations_closed_scopes.json`.

## Confirmed CI evidence, not broad generalization

- 197 tests passed, 3 skipped in each of three independent regression runs.
- Controlled DataHub source-subtree incremental/full typed graph equivalence passed 3/3.
- Closed-scope TypeScript/Python HTTP fixture: 6 TP, 0 FP, 0 FN; two negative callsites unresolved; eight function nodes verified.
- Expanded controlled multi-language fixture: 21 exact triples, 21 TP, 0 FP, 0 FN, ten closed source/relation scopes covering CALLS, POLYMORPHIC_CALL, PASSES_ARG, FLOWS_TO, CONSUMES, IMPLEMENTS, HTTP_CALLS. These labels are directly source-inspected and still require independent human adjudication. They do **not** prove general accuracy.

## Measured exploratory retrieval, Online Boutique, n=27, k=5, B=2048

| Method | MRR@5 | Hits@1 | Hits@5 |
|---|---:|---:|---:|
| R0 BM25 | 0.341 | 18.5% | 59.3% |
| R1 LSA | 0.638 | 48.1% | 92.6% |
| R3 syntax hybrid | 0.514 | 37.0% | 74.1% |
| R5 static hybrid | 0.514 | 37.0% | 74.1% |
| R9 contract hybrid | 0.514 | 37.0% | 74.1% |

**Important:** LSA outperformed the hybrid variants on this labelled set. Neither an SOTA nor universal graph ranking benefit is claimed.

## Layer masks: R5 separate ranking and grafting effects

Baseline R5 graft exact-node context recall: **0.815**.

| Disabled layer | Ranking MRR@5 | Graft-only exact-node recall | Ranking+grafting recall |
|---|---:|---:|---:|
| Lsyn | 0.514 | 0.815 | 0.815 |
| Ldep | 0.514 | 0.444 | 0.444 |
| Lflow | 0.514 | 0.815 | 0.815 |
| Lsem (LSA disabled too) | 0.254 | 0.815 | 0.481 |
| Lcontract | 0.514 | 0.741 | 0.741 |

These are **post-construction feature masks**. They do not measure parser-level construction ablations or end-to-end coding-agent success.

## Performance protocol

Run `python bench/paper_performance.py --manifest bench/manifests/paper_ci_pinned.json --repetitions 3 --output bench/results/paper_performance_ci.json` on pinned source checkouts, after adapting manifest paths. Reports raw times, p50, p95, Python/OS/CPU, Python allocation tracing peaks, revision IDs and exact typed graph equivalence.

The CI timing results depend on runner load and are available as raw job artifacts; do not transfer an unqualified speedup number across environments. The updater may recompose workspace-level relationships, so no unconditional O(delta) time bound is claimed.

## Accurate metrics and related scripts

- `bench/paper_metrics.py`: independent exact-ID MRR/Hits/Recall, closed-scope P/R/F1, UTF-8 byte-aligned BPE evidence-token accounting, p50/p95.
- `bench/run_paper_study.py`: fixed corpus/budget retrieval R0/R1/R3/R5/R9 and ranking/grafting/combined feature masks.
- `bench/run_paper_accuracy.py`: source evidence and exact triple checks under explicitly closed scopes.
- `bench/paper_performance.py`: pinned isolated edit trials and fresh-build equivalence.
- `bench/run_multi_repo_benchmark.py`: compatibility entrypoint redirecting to the corrected exact-label study. Legacy heuristic results MUST NOT be cited.

The six-query annotated token fixture intentionally labels short source evidence excerpts, **not all semantically useful context**. Its very high outside-annotation token rate is not a defensible estimate of semantic prompt redundancy.

## Removed/unestablished claims

1. Draft-paper numbers such as MRR=0.894, 14.8% redundancy, 46% agent tool-call and 60% latency improvements were placeholders or incomparable proxy findings and are not evidence in the revised paper.
2. The old `bench/bench_agent_toolcall.py` is a simulated retrieval/file-read procedure, **not** a genuine agent experiment.
3. Broad extraction precision/recall across all seven relations on real repositories remains unverified without independently annotated complete scopes.
4. Report cross-system SWE-bench/RepoBench/GraphCodeBERT numbers only for the same benchmark protocol; no separate published method is claimed to be reproduced here.

## Publication gate

Require at least a second independent annotator (and disagreement adjudication) for the realistic 27-query set, and independently audited closed source scopes across several real polyglot repositories. Publish exact query/edge labels, negatives, source revisions, token budgets, raw outputs and confidence intervals. Until then this is a **reproducible exploratory study**, not a fully validated comparative paper.
