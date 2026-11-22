# Boutique and Train-Ticket test splits (second look, exploratory)

Frozen November 20, 2026. Both cohorts were scored before this protocol. The underlying source, exact label IDs and earlier scores are historical inputs. Every comparison in this run is exploratory.

| Dataset | Prior record | Raw SHA-256 | Earlier governing protocol |
| --- | --- | --- | --- |
| Online Boutique | `test_final_41d61e11.json` | `125ceb6af5f11955d0161d83eed806c2d5f2f200976c83071cdfd17bd47934db` | The frozen `test-final` protocol at commit `41d61e11`, implemented in `bench/egpot_eval.py` and recorded in the run's configurations. No standalone Boutique preregistration is tracked at that commit. |
| Train-Ticket | `train_ticket_final_0545478c.json` | `9a893d884f3af3f38459772f6bc8b8dc41b25fcb933e6336c7ecf61804811373` | [Train-Ticket preregistration](preregistration_train_ticket.md), which covered the whole labelled set using the frozen original harness. |

The original runs used the earlier engine and legacy edge policy. The current port adds policy D (LEGACY with contract matching withheld for `ACCEPTS_SCHEMA`, `RETURNS_SCHEMA`, `INVOKES`, and `POSSIBLE_HTTP_TARGET`), the width option, immediate-score tiebreak lookahead, and the shared-tip origin bookkeeping fix. The current builder includes expanded language and verified edge extraction, optional nonproduction filtering for Train-Ticket, and the binder-only C++ full-body fix. To the best of the available records, retrieval tuning and selection decisions used DEV only, including the width sweep and the evaluation of tiebreak. Source coverage checks informed builder work, and the DeathStarBench width-4 miss diagnosis motivated the DEV width sweep after that locked run had been seen. This provenance does not make either test cohort unseen.

## Inputs, split and freeze

For both datasets the DEV links are 1, 4, 5, 9, 11, 13, 14, 15. The test links are **2, 3, 6, 7, 8, 10, 12**, comprising 14 queries per dataset, one explicit and one indirect per link. This uses the existing SHA-256 alternating-link split. Use the pinned workspace configurations from `egpot_dev_baseline_rows_4ebe87f9.json` (raw SHA-256 `c613d19b4bf102940d259296222e822136bc07750fb762fd72cd3ee639b3cf7d`). Rebuild under the read-only audit guard, use the Protobuf source fallback, and round-trip GraphML in memory.

| Dataset | Source revision | In-memory GraphML SHA-256 | Query JSON SHA-256 |
| --- | --- | --- | --- |
| Online Boutique | `c7cb6d5bfd6ea3aed768634ebbcb98cb7a523712` | `aa74317e400f720ac9c07e4d0c1222c75fa3b4bc2e4479e4f657955e373d4354` | `1735221b3e35760d9dff5c5f40854946860c1c7dfe0ccdd1843a73d819f1ae63` |
| Train-Ticket | `313886e99befb94be6cd45f085c98e0019f59829` | `4de367091ff69c40042549686560acbe76272c230e72e94a2759d45c1b9baf1e` | `21a2ed8b5658d665f00c6dc0078eaba14811ffed7402f99934513701aab5686e` |

Require a clean Git state, a tracked plan pinned to `egpot-test-prereg-v1`, verified graph and label hashes, engine and builder blobs matching `egpot-tiebreak-v1` and `egpot-bench-builder-v1`, and an explicit second-look acknowledgement. Reserve one attempt per app before retrieval. The ordinary held-out policy guard stays in place. No prior test rows may be decoded until both new records are committed. Historical comparisons must be separate and descriptive, with no trend interpretation.

Report graph coverage exclusions separately. Exclude a query from every method if any exact start, gold or gold-path node is absent, or if its labelled directed gold path is absent. Record failed IDs or hops and reasons. Accepted alternatives receive no credit. Any label change after freeze invalidates the run. A run with changed labels is a separate analysis.

## Configurations

Policy D applies to every method, with the RPC choke point on except in the explicit ablations. The start counts toward budgets 10, 20 and 40. Run seed 0 for the main table. The methods are:

- `egpot_full_w4`, `egpot_full_w12`, `egpot_no_pareto_w4`, `egpot_no_pareto_w12`, `egpot_full_tiebreak_w4`, `egpot_full_tiebreak_w12`.
- `egpot_full_mcts_w4` with blend 0.5, plus `egpot_no_entropy_w4`, `egpot_no_contracts_w4`, and `egpot_no_choke_point_w4`.
- `vector_topk`, `bfs`, `greedy_walk`, `vector_bfs_k2` through `vector_bfs_k5`, `ppr`, `scalar_beam`, `community_graphrag` and `mcts_standard`.
- Existing choke-off baseline variants for BFS, vector BFS k2, PPR, scalar beam, standard MCTS and greedy walk at budgets 20 and 40. The EG-POT choke ablation is already in the main table.

Report seeds 0–5 at budgets 10, 20 and 40 for both tiebreak widths, blended EG-POT width 4 and standard MCTS. Report seeds 0–5 at budgets 20 and 40 for choke-off standard MCTS. Seed 0 remains the primary descriptive seed.

## Primary comparisons (second look, exploratory)

For each app, first report the budget-40 seed-0 full-hit rate of `egpot_full_w4` minus the strongest of the listed main baselines. Select the strongest baseline within each resample by full-hit count, then lower hits-only mean nodes-to-hit, then method name. Provide the observed strongest baseline and paired interval. Each cohort is small, so report wide or zero-crossing intervals plainly. There is no multiplicity adjustment and no formal claim in this run.

## Predictions made before this run; the cohorts were seen before

- **A.** Train-Ticket `egpot_full_w4` exceeds the strongest baseline at budget 40 and seed 0. DEV was 12/16 versus 4–6/16 for the reference baselines.
- **B.** Boutique PPR matches or exceeds `egpot_full_w4` at budget 40 and seed 0. DEV was 16/16 versus 15/16.
- **C.** For plain `egpot_full`, width 12 gains full hits over width 4 at budget 40 and loses full hits at budget 10, as suggested by DEV and the DeathStarBench exploratory follow-up. Judge both parts in each app and show pooled counts descriptively.
- **D.** Train-Ticket blended `egpot_full_mcts_w4` returns zero gold HTTP endpoint contracts at budget 40 and seed 0. Show the count for every seed.

Report failures of predictions just as plainly as successes.

## Reporting and deviations

Report full hits (count and rate), recall, precision, path coverage, ordered path match, nodes returned, hits-only nodes-to-hit, hits-only precision-at-hit, and retrieval latency. Use 10,000 paired start-node cluster bootstrap resamples with NumPy RandomState(0), unadjusted percentile 95% intervals. Compare each EG-POT method against each main baseline and the strongest baseline at each budget for hit rate and mean recall. Include paired width 12 versus width 4, tiebreak versus plain at equal width, component removal versus full width 4, blend versus plain width 4, and choke-off versus on. Re-select the strongest baseline using the compared metric with the same tie rule. Report the other strongest baseline besides PPR per budget by the observed hit count, then the same tie rule.

Use raw undirected maximum distance to gold IDs for depth buckets, as in `bench/analyze_dsb_distance.py`. Report seed spread (median, min and max) and descriptive misses with any returned lookalike IDs. Use the same hits-only definition for nodes-to-hit. Historical test numbers are a separate table restricted to the covered query IDs that can be matched.

The original Boutique run used a split and the original Train-Ticket run scored its whole set. This run uses a test-only slice of both earlier cohorts. Old scorecard thresholds stay retired. The cluster bootstrap follows the DeathStarBench work. The original DeathStarBench width-4 records and claims remain primary for that benchmark. This follow-up uses no new labels or graph roots.
