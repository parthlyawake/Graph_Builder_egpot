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

### Workspace reconciliation

The committed graph workspaces use the same 12 Social and 13 Media `src/*Service` roots and service namespaces as recon. They omit the additional gateway roots. The following figures are sequential changes from the reproduced recon build. Removing a root also removes shared external nodes that are no longer referenced and can change semantic edges.

| Change | Social Δ nodes / edges | Media Δ nodes / edges |
| --- | ---: | ---: |
| Earlier recon | 979 / 3,232 | 653 / 2,351 |
| Use the full-body Thrift binder | 0 / +9 | 0 / +27 |
| Omit Social's `media-frontend` root (two Lua scripts) | −26 / −42 | 0 / 0 |
| Omit `nginx-web-server/lua-scripts/api` | −68 / −433 | 0 / 0 |
| Omit `nginx-web-server/lua-scripts/wrk2-api` | −80 / −223 | −65 / −193 |
| Omit the rest of the `nginx-web-server` root | −142 / −405 | −12 / −11 |
| Replace the recon IDL filter and namespace and remove the broad ignore globs | 0 / 0 | 0 / 0 |
| Committed layout | 663 / 2,138 | 576 / 2,174 |

The binder added three Social and nine Media edges of each type `CONSUMES`, `FLOWS_TO`, and `PASSES_ARG`. The first two gateway Lua removals accounted for nine and six Social Lua files and zero and six Media Lua files, respectively. The remainder included seven JavaScript files under Social's `pages/javascript` and Media's `lua-scripts/test.lua`.

Recon pointed an `idl` root at each app directory and applied broad subdirectory ignore globs to the workspace. The committed build uses `socialNetwork-idl` with only `social_network.thrift` and `mediaMicroservices-idl` with only `media_service.thrift`, applying the sidecars' `only_files` during discovery. The namespace change renames one file node per app. Switching to the exact IDL scope and dropping the broad globs each changed neither node nor edge counts. Both layouts use `exclude_nonproduction=True`. Guarded rebuilds from the committed sidecars reproduced both GraphML hashes above.

The following links are excluded from scoring:

- Social Network's `WriteHomeTimelineService` worker (`OnReceivedWorker`) to `SocialGraphService.GetFollowers`. The worker is disabled in the default build and Compose configuration.
- Media's `PageService.ReadPage` to `MovieInfoService.ReadMovieInfo`, `MovieReviewService.ReadMovieReviews`, `CastInfoService.ReadCastInfo`, and `PlotService.ReadPlot`.
- Media's `MovieReviewHandler.ReadMovieReviews` and `UserReviewHandler.ReadUserReviews` to `ReviewStorageService.ReadReviews`. The excluded Media links have test-backed entry paths only.

## Frozen evaluation

Use `LEGACY` with contract-match scoring withheld for `ACCEPTS_SCHEMA`, `RETURNS_SCHEMA`, `INVOKES`, and `POSSIBLE_HTTP_TARGET`. This is equivalent to four `--no-contract-match-relation` options in the comparison CLI. Traversal excludes no additional relations, and the legacy entropy denominator and RPC choke point remain in effect. The locked runner applies this policy to every method.

The primary method is `egpot_full`. The main table uses budgets **10, 20, and 40** with all 15 original locked methods and the pre-declared tiebreak method:

- EG-POT methods are `egpot_full`, `egpot_full_mcts` (blend 0.5), `egpot_full_tiebreak`, `egpot_no_pareto`, `egpot_no_pareto_mcts`, `egpot_no_entropy`, `egpot_no_contracts`, and `egpot_no_choke_point`.
- Baselines are `vector_topk`, `bfs`, `greedy_walk`, `vector_bfs_k2`, `ppr`, `scalar_beam`, `community_graphrag`, and `mcts_standard`.

Retain the original baseline choke-off side runs at budgets **20 and 40** for `bfs_no_choke`, `vector_bfs_k2_no_choke`, `ppr_no_choke`, `scalar_beam_no_choke`, `mcts_standard_no_choke`, and `greedy_walk_no_choke`. The EG-POT choke-off result comes from the main table.

Use seed **0** for the main and choke comparisons. At the original seed-study budgets **20 and 40**, run seeds **0–5** for every stochastic method, including `egpot_full_mcts`, `egpot_full_tiebreak`, `egpot_no_pareto_mcts`, `mcts_standard`, and `mcts_standard_no_choke`. For each metric report median, minimum and maximum, with the number of seeds that define each hits-only metric.

At budgets **10 and 20**, preserve the 54-vector weight study without lookahead. Use 50 `RandomState(0)` Dirichlet(1,1,1,1) draws rounded to four decimals then renormalized, plus the four vectors with 0.7 on one objective and 0.1 on each other objective. Report equal weights separately. Reuse the full Pareto run as the reference and report the distribution and counts above, equal to and below it.

## Metrics

The primary metric is **full-hit count at budget 40**, reported per app and pooled. A full hit requires every exact gold node. Accepted alternatives receive no credit, as in the original harness.

Report all harness metrics as secondary outcomes across the measured budgets, with full hits outside the primary endpoint, gold recall, precision, path coverage, ordered path match, nodes returned, nodes-to-hit, precision-at-hit, and retrieval latency. Give full hits as both count and rate. For compactness report each method's original hits-only mean nodes-to-hit and the paired comparison on the subset both methods hit, with the paired subset size. Report a missing value when that subset is empty.

## Paired comparisons

At each budget and for each reported set, compare `egpot_full` with every baseline using paired differences in full-hit rate and mean gold recall. Resample start-node clusters with replacement, keeping every query for a sampled start and every paired method result together. Use 10,000 resamples, bootstrap seed 0, and percentile 95% intervals. For the pooled report, identify clusters by dataset and start node and resample within each app. Compute query-weighted metrics in the original and resampled sets. For a component claim, compare full minus the corresponding ablation. For an MCTS claim, compare the pre-declared lookahead method minus its corresponding no-lookahead control. Support a claim only when its paired interval excludes zero in the claimed direction. The old scorecard thresholds, including +4/30 and +6/30, are not used.

Also report the comparison against the strongest observed baseline for the metric, budget, and reported set, breaking ties by method name. This is a conservative reference for the observed difference. For its bootstrap interval, recompute the strongest baseline in each resample so the comparison does not treat the data-selected baseline as fixed in advance.

## Run procedure and limits

Use `bench.egpot_multi_eval --mode run-locked` once for each dataset, `dsb_social` and `dsb_media`. The tracked preregistration, clean Git tree, and frozen input hashes are required. Keep both locked records if a documented harness bug requires an acknowledged rerun and report both runs. Freeze policy, weights, and labels when committing the preregistration. No DeathStarBench retrieval was run during preparation.

Labels are pending human review. Evidence comes from static C++ source and Thrift IDL, with no verification of live execution or deployment health. The DeathStarBench LICENSE states Apache-2.0 and its README states GPLv2. Do not redistribute the label and graph files.
