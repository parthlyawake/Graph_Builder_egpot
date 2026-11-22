# DeathStarBench width-12 preregistration (post-hoc exploratory)

Frozen November 20, 2026. This is a post-hoc exploratory follow-up. We chose width 12 using the pre-stated rule on Online Boutique and Train-Ticket DEV at `9e696e9df7907e2ea654c039140f1a0007e6ef7e`, after seeing the locked DeathStarBench run. These DeathStarBench results cannot independently confirm the width choice. The locked width-4 analysis and C1–C7 remain primary.

## Inputs and design

Use the same 46 scored queries (28 Social Network, 18 Media Microservices) and the same GraphML and labels as the [original DeathStarBench preregistration](preregistration_dsb.md). Use the committed, independently rebuilt and hash-verified snapshots. There is no need for a new graph build. Policy D is the original `LEGACY` policy with contract-match scoring withheld for `ACCEPTS_SCHEMA`, `RETURNS_SCHEMA`, `INVOKES`, and `POSSIBLE_HTTP_TARGET`. The RPC choke point is on.

| Dataset | GraphML SHA-256 | Labels SHA-256 | Original width-4 record SHA-256 |
| --- | --- | --- | --- |
| Social Network | `7a9a9b9941edd62ae8ca78c556ca5361e3a22fd583c2ce61b26833dcb8d00ae9` | `d3727d1070243fd0e8d67a5c15cedd89c2dbb73c8296c4ca0f494429b17c9b15` | `f6d4d0bda72161da2d3ff27d80738e70819650d1396530f6ab22d17cfc21ca50` |
| Media Microservices | `96868d204874b6c2bbbba6c3b0399b45b74857f61e472b0ef19ef7ea23efb671` | `7d5dbd5ae2118bca598ae2b5dc35ee86fc53a8861de69ffedea7aa426247a134` | `518da8e6b92296e3e67634f0b04d650b0735182aa2a7b4edf8f74363ae9b375c` |

The engine must match both `egpot-tiebreak-v1` and `egpot-dsb-locked-v1`. The builder scope and pin are the same as the original freeze at `egpot-bench-builder-v1`. Require a clean Git state, a tracked plan matching `egpot-dsb-w12-prereg-v1`, a verified original width-4 record and input hashes, and explicit width 12 in every new method's effective configuration, run header, and result row. Run once per app to separate width-12 files.

At budgets 10, 20 and 40, run seed 0 for `egpot_full_w12`, `egpot_no_pareto_w12`, and `egpot_full_tiebreak_w12`. The stochastic tiebreak variant follows the locked seed study at budgets 20 and 40 with seeds 0–5. Inherit all other settings from the original method specifications. Use the saved width-4 records for all comparisons, including PPR and other baselines. The blended `egpot_full_mcts` stays at its locked width 4 because DEV showed that blending demotes terminal Train-Ticket endpoints.

## Predictions made before the run

- **A.** At budget 40, the pooled `egpot_full_w12` full-hit count exceeds 37/46, narrowing the gap to PPR.
- **B.** At budget 10, the pooled `egpot_full_w12` full-hit count is below 36/46, reducing its lead over PPR.
- **C.** At budget 40, pooled `egpot_full_w12` mean nodes returned exceeds 24.8 and mean precision is below 0.081, moving both toward the PPR profile.

Report a failed prediction as plainly as one that holds. Judge both parts of C separately and require both for the combined prediction.

## Post-hoc exploratory reporting

Label every table and interval post-hoc exploratory. Report per-app and pooled results at seed 0, including full hits (count and rate), gold recall, precision, path coverage, ordered-path match, nodes returned, hits-only nodes-to-hit, hits-only precision-at-hit, and retrieval latency. For tiebreak, report per-seed metrics and median, minimum and maximum at the seed-study budgets. Describe results by gold depth 1 versus 2 using the maximum raw undirected GraphML distance from the start to either gold ID, as in `bench/analyze_dsb_distance.py`. Report misses with the IDs of any returned lookalikes using the ordered returned-node records. This is descriptive only.

For each width-12 method, budget and scope, report hit-rate and mean-recall differences against its width-4 counterpart and against PPR. Use paired, unadjusted 95% percentile intervals from 10,000 start-node cluster resamples with NumPy `RandomState(0)`. For the pooled result resample within each app, keeping all queries in a start-node cluster together and using query-weighted metrics. Make no confirmatory claims or multiplicity adjustment.

## Labels and deviations from earlier benchmarks

Any label change after freeze invalidates this run. A rerun using changed labels constitutes a separate analysis. Exact gold IDs determine credit. Accepted alternatives receive no credit. Excluded links stay outside scoring and evaluation. Each app is evaluated as a whole set without a DEV/test split. The old scorecard thresholds remain retired. Gateway and Lua roots were omitted by design before evaluation. The original locked run introduced the bootstrap and confirmatory family. This follow-up reuses the bootstrap for exploratory intervals only.
