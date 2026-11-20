# DataHub off-cohort timing pilot

Three start functions were drawn using `random.Random(0)`, one per listed namespace, from sorted function IDs with multigraph degree 5–60 after excluding every labeled start, contract, and handler. Each start received one synthetic prompt. Calls used the whole graph and policy D. Every returned result was discarded.

| Probe | Start | Synthetic prompt |
| --- | --- | --- |
| probe-1 | `web/app/entityV2/shared/utils/selectorUtils.ts:isEntityResolutionRequired` | render descriptive catalog information |
| probe-2 | `ingestion/datahub/ingestion/source/sqlalchemy_profiler/base_adapter.py:PlatformAdapter.get_column_value_frequencies` | convert a source record for ingestion |
| probe-3 | `graphql/com/linkedin/datahub/graphql/types/query/QueryType.java:QueryType.getKeyProvider` | prepare the request execution context |

Graph load 27.00 s. TF-IDF setup 9.50 s. The columns below show means over the three probes at each budget, and the full observed retrieval range. Constructor time is shown separately. Weight means are per vector and weight setup is summed over 54 constructors.

| Method | @10 sec | @20 sec | @40 sec | Range sec | Setup sec | Declared plan hours | All six repeats hours |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 54-vector study | 0.423 | 0.427 | — | 0.230–0.642 | 32.51 | 0.663 | 3.977 |
| community_graphrag | 0.594 | 0.618 | 0.603 | 0.555–0.709 | 122.46 | 0.026 | 0.157 |
| egpot_full_mcts_w4 | 18.856 | 30.502 | 37.197 | 4.293–51.086 | 0.51 | 7.501 | 7.501 |
| egpot_full_w12 | 0.357 | 2.983 | 3.398 | 0.327–8.539 | 0.47 | 0.097 | 0.584 |
| egpot_full_w4 | 0.389 | 0.450 | 0.902 | 0.332–1.893 | 0.53 | 0.025 | 0.151 |
| equal | 0.407 | 0.434 | — | 0.397–0.486 | 0.43 | 0.012 | 0.073 |
| mcts_standard | 0.598 | 0.621 | 0.575 | 0.527–0.687 | 0.00 | 0.155 | 0.155 |
| ppr | 3.970 | 4.931 | 4.286 | 3.414–5.798 | 9.31 | 0.190 | 1.143 |

Measured methods project to **8.67 serial retrieval hours** on the declared plan, or **13.74 hours** if all were repeated six times. Weights use their two declared budgets. These totals exclude common setup, worker startup, checkpoint overhead, and unmeasured variants and side runs. The full draft job matrix would contain 14,196 unique calls and 15,184 reporting rows. A coarse full-plan scenario is **31.89 serial retrieval hours**. It uses blended width-4 MCTS as the proxy for untimed lookahead variants, same-width plain EG-POT for other EG-POT ablations, and standard MCTS for untimed baselines except choke-off PPR, which uses PPR. This is a planning scenario and omits initialization and I/O. Width-12 lookahead is still an important unknown.

Blended EG-POT MCTS is impractical for a short single-worker run. Its measured projection alone is over seven hours, and the tiebreak and no-Pareto MCTS variants remain untimed. The weight study is roughly 40 serial minutes. PPR costs several seconds per call. Community GraphRAG has the greatest measured constructor cost. The small, degree-limited sample cannot bound worst-case calls.
