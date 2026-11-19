# Preregistration draft for DeathStarBench

- Preregistration date: `<fill at freeze>`
- Final benchmark commit: `<fill at freeze>`
- DeathStarBench source commit: `6ecb09706140f8730b5385c08f1386c654c3c526`
- Graph builder: `egpot-bench-builder-v1` at `94aae7b8aef08ac2beddcbc7fc37a7e2b2cc69ce`
- EG-POT: `egpot-tiebreak-v1` at `f3d3163eec15c3e814302fb8269cd3fbca6430a1`
- Source label draft SHA-256: `2824117d02311d45b8b700c8aa7c93c7c1db20e1b2b04d2cb9e52118803e3945`

## Data and coverage

The scored set contains 23 source-labelled links and 46 queries. Each link has one explicit and one indirect query. Report Social Network (14 links, 28 queries), Media Microservices (9 links, 18 queries), and the pooled set. Run each dataset as one whole set. Report any builder coverage failures separately and exclude them from all methods' denominators. All 23 inputs recovered the exact source-labelled contract path at preparation.

| Dataset | Nodes | Edges | GraphML SHA-256 | Query JSON SHA-256 |
| --- | ---: | ---: | --- | --- |
| `dsb_social` | 663 | 2,138 | `7a9a9b9941edd62ae8ca78c556ca5361e3a22fd583c2ce61b26833dcb8d00ae9` | `d3727d1070243fd0e8d67a5c15cedd89c2dbb73c8296c4ca0f494429b17c9b15` |
| `dsb_media` | 576 | 2,174 | `96868d204874b6c2bbbba6c3b0399b45b74857f61e472b0ef19ef7ea23efb671` | `7d5dbd5ae2118bca598ae2b5dc35ee86fc53a8861de69ffedea7aa426247a134` |

Each workspace has one namespace per C++ service root and a separate namespace that admits only its Thrift IDL file. The sidecars record the roots, builder settings, and dependency versions. The builds used `exclude_nonproduction=True`, the Protobuf source-parser fallback, and the in-memory audit guard. Both independent builds yielded identical GraphML bytes for each app.

The following links are excluded from scoring:

- Social Network's `WriteHomeTimelineService` worker (`OnReceivedWorker`) to `SocialGraphService.GetFollowers`. The worker is disabled in the default build and Compose configuration.
- Media's `PageService.ReadPage` to `MovieInfoService.ReadMovieInfo`, `MovieReviewService.ReadMovieReviews`, `CastInfoService.ReadCastInfo`, and `PlotService.ReadPlot`.
- Media's `MovieReviewHandler.ReadMovieReviews` and `UserReviewHandler.ReadUserReviews` to `ReviewStorageService.ReadReviews`. The excluded Media links have test-backed entry paths only.

## Frozen evaluation

Use `LEGACY` with contract-match scoring withheld for `ACCEPTS_SCHEMA`, `RETURNS_SCHEMA`, `INVOKES`, and `POSSIBLE_HTTP_TARGET`. This is equivalent to four `--no-contract-match-relation` options in the comparison CLI. Traversal excludes no additional relations, and the legacy entropy denominator and RPC choke point remain in effect. The locked runner applies this policy to every method.

The primary method is `egpot_full`. Secondary methods are `egpot_no_pareto`, `egpot_full_mcts` with blend weight 0.5, and the pre-declared `egpot_full_tiebreak`. The locked harness's standard baselines are `vector_topk`, `bfs`, `greedy_walk`, `vector_bfs_k2`, `ppr`, `scalar_beam`, `community_graphrag`, and `mcts_standard`.

Run budgets 20 and 40. Report the number and fraction of queries with every gold node returned, and mean per-query gold recall. For `egpot_full_mcts`, `egpot_full_tiebreak`, and `mcts_standard`, run seeds 0 through 5. Use seed 0 for the primary results and comparisons. Report each stochastic method's median, minimum, and maximum across all six seeds for both metrics.

## Paired comparisons

At each budget and for each reported set, compare `egpot_full` with every baseline using paired differences in full-hit rate and mean gold recall. Resample start-node clusters with replacement, keeping every query for a sampled start and every paired method result together. Use 10,000 resamples, bootstrap seed 0, and percentile 95% intervals. For the pooled report, identify clusters by dataset and start node and resample within each app. Compute query-weighted metrics in the original and resampled sets.

Also report the comparison against the strongest observed baseline for the metric, budget, and reported set, breaking ties by method name. This is a conservative reference for the observed difference. For its bootstrap interval, recompute the strongest baseline in each resample so the comparison does not treat the data-selected baseline as fixed in advance.

## Run procedure and limits

Use `bench.egpot_multi_eval --mode run-locked` once for each dataset, `dsb_social` and `dsb_media`. The tracked preregistration, clean Git tree, and frozen input hashes are required. Keep both locked records if a documented harness bug requires an acknowledged rerun and report both runs. Freeze policy, weights, and labels when committing the preregistration. No DeathStarBench retrieval was run during preparation.

Labels are pending human review. Evidence comes from static C++ source and Thrift IDL, with no verification of live execution or deployment health. The DeathStarBench LICENSE states Apache-2.0 and its README states GPLv2. Do not redistribute the label and graph files.
