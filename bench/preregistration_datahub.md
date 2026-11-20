# DataHub preregistration draft

Status: DRAFT

Draft date `2026-11-20`. Freeze date, final benchmark commit, and analysis-script path and commit are fill-at-freeze fields. This draft authorizes no retrieval on the labeled cohort.

## Data and coverage

Use DataHub source `c2a82c97f0faf73c266d6525aead90557615147f`, builder `egpot-bench-builder-v2` at `fb55db870727cbba3fa32208aa1db9213b83b5a0`, and engine `egpot-tiebreak-v1` at `f3d3163eec15c3e814302fb8269cd3fbca6430a1`. The graph has 314,219 nodes and 1,032,920 edges. The v2 coverage sidecar records the guarded production workspace and build revision.

| Input | SHA-256 |
|---|---|
| `bench/results/datahub_graph_v2.graphml` | `71067cb3598e40b2be00c3a4f8b3f3557f03172a3dcd9b9a462cba59894dd162` |
| `bench/labels/datahub_egpot_queries.json` | `69e72fde97c6d7c32fc1809f74b45d960af11ac1566da57059a783af25bde6e0` |

The whole set comprises 26 links and 52 queries, one explicit and one indirect per link. There is no dev split. Report the pooled cohort and descriptive results for React → GraphQL (14 links), Python → OpenAPI (5), and Python → Rest.li (7). Labels and lookalikes were verified through second-model checks and pinned source citations, without human review. Exact IDs came from cited file, line and qualified declaration name. Report builder-coverage failures separately and exclude them from the denominators of every method. Excluded links receive no evaluation or score.

The builder was modified after the 26 links were identified, with those links in view. The four rules apply across the production workspace. Their repo-wide additions and independent source audit are documented in `datahub_edge_audit.md`. The labeled cohort was unseen by retrieval during preparation. Confirmatory inference is conditional on the eventual frozen cohort and graph. The audit found false OpenAPI edges outside the labeled links. Resolve that issue and review the resulting graph and input hashes before freezing this draft.

## Evaluation plan

Use policy D for every method. This is `LEGACY` with contract-match credit withheld for `ACCEPTS_SCHEMA`, `RETURNS_SCHEMA`, `INVOKES`, and `POSSIBLE_HTTP_TARGET`. Keep legacy traversal eligibility, entropy denominator, and the RPC choke point, with the specified choke-off exceptions.

- Main budgets are 10, 20 and 40, including the start. Run `egpot_full`, `egpot_no_pareto`, and `egpot_full_tiebreak` with `_w4` and `_w12` method IDs. Run `egpot_full_mcts_w4` and `egpot_no_pareto_mcts_w4` with blend weight 0.5, and `egpot_no_entropy_w4`, `egpot_no_contracts_w4`, and `egpot_no_choke_point_w4`.
- Baselines are `vector_topk`, `bfs`, `greedy_walk`, `vector_bfs_k2` through `vector_bfs_k5`, `ppr`, `scalar_beam`, `community_graphrag`, and `mcts_standard`. At budgets 20 and 40 run choke-off variants of BFS, VectorBFS k2, PPR, scalar beam, standard MCTS, and greedy walk.
- Use seed 0 for primary comparisons. Run seeds 0–5 for the tiebreak and blended MCTS variants and standard MCTS at all main budgets, and for choke-off standard MCTS at its two budgets. Report minimum, median and maximum by seed. Deterministic methods run once per budget. The matched controls for lookahead comparisons are the no-lookahead methods with the same width and Pareto setting.
- At budgets 10 and 20 run the 54-vector scalar weight study at width 4 without lookahead. Use 50 `RandomState(0)` Dirichlet(1,1,1,1) vectors rounded to four decimals and renormalized, plus four 0.7/0.1 emphasis vectors. Report equal weights separately. Use `egpot_full_w4` as the Pareto reference. Report the distribution and counts below, equal to, and above that reference. Select no weight for later use.

## Outcomes and inference

A full hit requires both exact gold IDs. Report full hits as counts and rates, gold recall, precision, path coverage, ordered path match, nodes returned, nodes-to-hit, precision-at-hit, and latency. Accepted alternatives receive no credit. Report hits-only compactness and the paired subset that both methods hit, with its size. Lookalike failure analysis is descriptive.

The four confirmatory contrasts use pooled full-hit-rate differences at seed 0. In each contrast the predicted direction is positive.

| ID | Budget | First method minus comparator |
|---|---:|---|
| C1 | 10 | `egpot_full_w4` minus the strongest baseline |
| C2 | 40 | `egpot_full_w12` minus the strongest baseline |
| C3 | 10 | `egpot_full_w4` minus `egpot_full_w12` |
| C4 | 40 | `egpot_full_w4` minus `egpot_no_contracts_w4` |

Use 10,000 paired cluster bootstrap resamples over start nodes with NumPy `RandomState(0)`. Keep all queries and paired method outcomes for a sampled start together. Compute query-weighted rates. In C1 and C2, re-select the strongest baseline in every resample by highest full-hit rate, then lowest mean nodes-to-hit, then name. Undefined nodes-to-hit sorts last. Apply Bonferroni-adjusted percentile intervals at `1 − 0.05/4` with `0.05/8` in each tail. An interval above zero supports the specified direction, one below zero indicates the first method was significantly worse, and one including zero leaves the claim unsupported. Label every other analysis exploratory and use unadjusted 95% intervals where reported.

## Predictions made before the run

PPR will lose ground because 40 nodes cover a tiny share of this graph. Width-4 EG-POT will retain its tight-budget advantage. Width 12 will cost hits at budget 10. Contract consistency will matter at budget 40. Report failed predictions as plainly as successful ones.

## Freeze and deviations

Use the DataHub-only locked runner. It must verify a clean Git state, a tracked frozen preregistration and its tag, the input hashes, and the pinned engine and builder code. Any label change after freeze invalidates the locked run. A run on changed labels is a separate new analysis.

The whole cohort has no dev/test split. This draft uses two widths and four adjusted comparisons and retires the earlier scorecard thresholds. The builder changes and lack of human label review are disclosed above. Three off-cohort synthetic probes were used for timing only, with returned results discarded.
