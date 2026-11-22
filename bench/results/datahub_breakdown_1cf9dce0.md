# DataHub post-hoc breakdown

**Exploratory.** All numbers in this report are exploratory. Counts use the main seed-0 rows from [the locked result](datahub_final_1cf9dce0.json). Gold roles come from the frozen labels. Handler depth and two-hop neighborhood size come from the [saved topology audit](datahub_edge_audit_v3.json). Neighborhood counts include the start. Terciles rank links by size and then link ID, divide them as evenly as possible with extra links in the earlier groups, and keep the paired wordings together.

## a. Query wording (exploratory)

### Explicit (exploratory)

| Method | Budget 10 | Budget 20 | Budget 40 |
|---|---:|---:|---:|
| `egpot_full_w4` | 23/26 | 23/26 | 23/26 |
| `egpot_full_w12` | 10/26 | 26/26 | 26/26 |
| `egpot_no_contracts_w4` | 14/26 | 16/26 | 16/26 |
| `ppr` | 0/26 | 3/26 | 11/26 |
| `scalar_beam` | 15/26 | 15/26 | 15/26 |
| `mcts_standard` | 1/26 | 6/26 | 17/26 |
| `vector_topk` | 2/26 | 4/26 | 7/26 |
| `bfs` | 0/26 | 3/26 | 12/26 |

### Indirect (exploratory)

| Method | Budget 10 | Budget 20 | Budget 40 |
|---|---:|---:|---:|
| `egpot_full_w4` | 18/26 | 19/26 | 19/26 |
| `egpot_full_w12` | 3/26 | 22/26 | 22/26 |
| `egpot_no_contracts_w4` | 7/26 | 7/26 | 7/26 |
| `ppr` | 0/26 | 3/26 | 11/26 |
| `scalar_beam` | 6/26 | 6/26 | 6/26 |
| `mcts_standard` | 1/26 | 4/26 | 14/26 |
| `vector_topk` | 0/26 | 0/26 | 0/26 |
| `bfs` | 0/26 | 3/26 | 12/26 |

Width 4 leads width 12 at budget 10 in both wording groups. Width 12 leads at budgets 20 and 40 in both. Turning off contract consistency costs more hits for indirect wording at budget 40.

## b. Gold handler depth (exploratory)

### Depth 1 (exploratory)

| Method | Budget 10 | Budget 20 | Budget 40 |
|---|---:|---:|---:|
| `egpot_full_w4` | 4/4 | 4/4 | 4/4 |
| `egpot_full_w12` | 4/4 | 4/4 | 4/4 |
| `egpot_no_contracts_w4` | 2/4 | 2/4 | 2/4 |
| `ppr` | 0/4 | 0/4 | 4/4 |
| `scalar_beam` | 2/4 | 2/4 | 2/4 |
| `mcts_standard` | 1/4 | 4/4 | 4/4 |
| `vector_topk` | 0/4 | 1/4 | 1/4 |
| `bfs` | 0/4 | 2/4 | 4/4 |

### Depth 2 (exploratory)

| Method | Budget 10 | Budget 20 | Budget 40 |
|---|---:|---:|---:|
| `egpot_full_w4` | 37/48 | 38/48 | 38/48 |
| `egpot_full_w12` | 9/48 | 44/48 | 44/48 |
| `egpot_no_contracts_w4` | 19/48 | 21/48 | 21/48 |
| `ppr` | 0/48 | 6/48 | 18/48 |
| `scalar_beam` | 19/48 | 19/48 | 19/48 |
| `mcts_standard` | 1/48 | 6/48 | 27/48 |
| `vector_topk` | 2/48 | 3/48 | 6/48 |
| `bfs` | 0/48 | 4/48 | 20/48 |

The two depth-1 links, DH18 and DH24, yield four queries. Both widths hit all four at every budget, and several baselines also do so at budget 40. The depth-2 group accounts for the width-4 lead at budget 10 and the width-12 lead at budgets 20 and 40.

## c. Start-node neighborhood size (exploratory)

### Small tercile (56 to 1,326 nodes) (exploratory)

| Method | Budget 10 | Budget 20 | Budget 40 |
|---|---:|---:|---:|
| `egpot_full_w4` | 15/18 | 15/18 | 15/18 |
| `egpot_full_w12` | 6/18 | 17/18 | 17/18 |
| `egpot_no_contracts_w4` | 6/18 | 6/18 | 6/18 |
| `ppr` | 0/18 | 4/18 | 10/18 |
| `scalar_beam` | 7/18 | 7/18 | 7/18 |
| `mcts_standard` | 0/18 | 5/18 | 12/18 |
| `vector_topk` | 1/18 | 2/18 | 2/18 |
| `bfs` | 0/18 | 6/18 | 10/18 |

### Middle tercile (1,438 to 1,697 nodes) (exploratory)

| Method | Budget 10 | Budget 20 | Budget 40 |
|---|---:|---:|---:|
| `egpot_full_w4` | 13/18 | 14/18 | 14/18 |
| `egpot_full_w12` | 0/18 | 18/18 | 18/18 |
| `egpot_no_contracts_w4` | 6/18 | 8/18 | 8/18 |
| `ppr` | 0/18 | 2/18 | 4/18 |
| `scalar_beam` | 5/18 | 5/18 | 5/18 |
| `mcts_standard` | 0/18 | 2/18 | 12/18 |
| `vector_topk` | 0/18 | 0/18 | 2/18 |
| `bfs` | 0/18 | 0/18 | 12/18 |

### Large tercile (1,873 to 3,544 nodes) (exploratory)

| Method | Budget 10 | Budget 20 | Budget 40 |
|---|---:|---:|---:|
| `egpot_full_w4` | 13/16 | 13/16 | 13/16 |
| `egpot_full_w12` | 7/16 | 13/16 | 13/16 |
| `egpot_no_contracts_w4` | 9/16 | 9/16 | 9/16 |
| `ppr` | 0/16 | 0/16 | 8/16 |
| `scalar_beam` | 9/16 | 9/16 | 9/16 |
| `mcts_standard` | 2/16 | 3/16 | 7/16 |
| `vector_topk` | 1/16 | 2/16 | 3/16 |
| `bfs` | 0/16 | 0/16 | 2/16 |

Width 4 leads width 12 at budget 10 in all three terciles. Width 12 pulls ahead at budgets 20 and 40 in the small and middle terciles and ties width 4 in the largest.

## d. Module pair (exploratory)

### React → GraphQL (exploratory)

| Method | Budget 10 | Budget 20 | Budget 40 |
|---|---:|---:|---:|
| `egpot_full_w4` | 17/28 | 18/28 | 18/28 |
| `egpot_full_w12` | 0/28 | 24/28 | 24/28 |
| `egpot_no_contracts_w4` | 9/28 | 11/28 | 11/28 |
| `ppr` | 0/28 | 4/28 | 6/28 |
| `scalar_beam` | 8/28 | 8/28 | 8/28 |
| `mcts_standard` | 0/28 | 2/28 | 14/28 |
| `vector_topk` | 0/28 | 1/28 | 3/28 |
| `bfs` | 0/28 | 4/28 | 18/28 |

### Python → OpenAPI (exploratory)

| Method | Budget 10 | Budget 20 | Budget 40 |
|---|---:|---:|---:|
| `egpot_full_w4` | 10/10 | 10/10 | 10/10 |
| `egpot_full_w12` | 7/10 | 10/10 | 10/10 |
| `egpot_no_contracts_w4` | 6/10 | 6/10 | 6/10 |
| `ppr` | 0/10 | 0/10 | 8/10 |
| `scalar_beam` | 7/10 | 7/10 | 7/10 |
| `mcts_standard` | 2/10 | 4/10 | 10/10 |
| `vector_topk` | 1/10 | 1/10 | 1/10 |
| `bfs` | 0/10 | 0/10 | 4/10 |

### Python → Rest.li (exploratory)

| Method | Budget 10 | Budget 20 | Budget 40 |
|---|---:|---:|---:|
| `egpot_full_w4` | 14/14 | 14/14 | 14/14 |
| `egpot_full_w12` | 6/14 | 14/14 | 14/14 |
| `egpot_no_contracts_w4` | 6/14 | 6/14 | 6/14 |
| `ppr` | 0/14 | 2/14 | 8/14 |
| `scalar_beam` | 6/14 | 6/14 | 6/14 |
| `mcts_standard` | 0/14 | 4/14 | 7/14 |
| `vector_topk` | 1/14 | 2/14 | 3/14 |
| `bfs` | 0/14 | 2/14 | 2/14 |

Width 4 leads width 12 at budget 10 in every module pair. At budgets 20 and 40 the width-12 gain comes from React to GraphQL. Both widths hit every Python to OpenAPI and Python to Rest.li query at those budgets. Standard MCTS ties both widths on OpenAPI at budget 40.

## e. Contract and handler recall (exploratory)

Each column counts exact recoveries of the indicated gold node, over the same queries.

| Method | Budget | Contract found | Handler found |
|---|---:|---:|---:|
| `egpot_full_w4` | 10 | 51/52 (98.1%) | 41/52 (78.8%) |
| `egpot_full_w4` | 20 | 51/52 (98.1%) | 42/52 (80.8%) |
| `egpot_full_w4` | 40 | 51/52 (98.1%) | 42/52 (80.8%) |
| `egpot_full_w12` | 10 | 52/52 (100.0%) | 13/52 (25.0%) |
| `egpot_full_w12` | 20 | 52/52 (100.0%) | 48/52 (92.3%) |
| `egpot_full_w12` | 40 | 52/52 (100.0%) | 48/52 (92.3%) |

Contracts are nearly always found at both widths. Handler recall follows the full-hit pattern. Width 4 leads at budget 10, and width 12 leads at budgets 20 and 40.
