# Train-Ticket locked result summary

Read-only aggregation of stored JSON fields. No retriever, scorer, metric-from-traversal calculation or evaluation was run.

## 1. Integrity and stored provenance

```json
{
  "commit": "0545478c5a33d4ce9206d243accee009c2aa066a",
  "graph_sha256": "8904e43268d34bd7b8734ec8f93326eb60051a6d2ac71484816ff595cc2a4c55",
  "labels_sha256": "21a2ed8b5658d665f00c6dc0078eaba14811ffed7402f99934513701aab5686e",
  "preregistration_sha256": "002790a89a8b15e296d70f0a5d8f891d43b1cdc543b702f5ca571b9b8b56d15d",
  "versions": {
    "networkx": "3.5",
    "numpy": "2.3.2",
    "python": "3.13.6",
    "scikit-learn": "1.7.1"
  },
  "worker_count": 4,
  "utc_timestamp": "2026-11-09T10:39:12.121598+00:00",
  "result_file_sha256": "d109e96d72fe4009afa8f7fb915b3807759b365e72587f92c16768c732f45c66"
}
```

| Check | Result |
|---|---|
| stored graph SHA matches graph provenance | PASS |
| stored label SHA matches label provenance | PASS |
| label provenance refers to same graph | PASS |
| verified graph hash agrees | PASS |
| verified label hash agrees | PASS |
| current labels hash agrees | PASS |
| current preregistration hash agrees | PASS |
| stored deterministic rows digest agrees | PASS |

## 2. Main methods and ablations

**Bold** marks every tied best value in each column, before display rounding. Hits/recall/precision-at-hit: higher is better; nodes/nodes-to-hit: lower is better. Low node counts do not imply high coverage. Nodes-to-hit and precision-at-hit use hits only; — means no hits.

### Budget 10

| Method | Hits | Recall | Mean nodes | Mean nodes-to-hit (hit count) | Mean precision-at-hit |
|---|---|---|---|---|---|
| bfs | 0/30 | 0.1667 | 10.0000 | — (0 hits) | — |
| community_graphrag | 5/30 | 0.3500 | 10.0000 | 3.8000 (5 hits) | 0.5467 |
| egpot_full | **25/30** | **0.8333** | 9.6000 | 5.1600 (25 hits) | 0.3947 |
| egpot_full_mcts | 0/30 | 0.4667 | 10.0000 | — (0 hits) | — |
| egpot_no_choke_point | **25/30** | **0.8333** | 9.6000 | 5.1600 (25 hits) | 0.3947 |
| egpot_no_contracts | 14/30 | 0.6500 | 9.7000 | 6.1429 (14 hits) | 0.3337 |
| egpot_no_entropy | **25/30** | **0.8333** | 9.6000 | 5.1600 (25 hits) | 0.3947 |
| egpot_no_pareto | **25/30** | **0.8333** | 9.6000 | 5.2000 (25 hits) | 0.3928 |
| egpot_no_pareto_mcts | 0/30 | 0.3833 | 10.0000 | — (0 hits) | — |
| greedy_walk | 7/30 | 0.4833 | **5.4000** | **3.0000** (7 hits) | **0.6667** |
| mcts_standard | 0/30 | 0.4167 | 10.0000 | — (0 hits) | — |
| ppr | 0/30 | 0.2000 | 10.0000 | — (0 hits) | — |
| scalar_beam | 13/30 | 0.6333 | 9.7667 | 6.0000 (13 hits) | 0.3401 |
| vector_bfs_k2 | 0/30 | 0.2833 | 10.0000 | — (0 hits) | — |
| vector_topk | 4/30 | 0.3167 | 10.0000 | 6.0000 (4 hits) | 0.3556 |

### Budget 20

| Method | Hits | Recall | Mean nodes | Mean nodes-to-hit (hit count) | Mean precision-at-hit |
|---|---|---|---|---|---|
| bfs | 0/30 | 0.3667 | 20.0000 | — (0 hits) | — |
| community_graphrag | 9/30 | 0.4333 | 20.0000 | 7.5556 (9 hits) | 0.3774 |
| egpot_full | **25/30** | **0.8333** | 16.0667 | 5.1600 (25 hits) | 0.3947 |
| egpot_full_mcts | 0/30 | 0.4667 | 20.0000 | — (0 hits) | — |
| egpot_no_choke_point | **25/30** | **0.8333** | 16.0667 | 5.1600 (25 hits) | 0.3947 |
| egpot_no_contracts | 14/30 | 0.6500 | 17.4667 | 6.1429 (14 hits) | 0.3337 |
| egpot_no_entropy | **25/30** | **0.8333** | 15.1333 | 5.1600 (25 hits) | 0.3947 |
| egpot_no_pareto | **25/30** | **0.8333** | 14.6333 | 5.2000 (25 hits) | 0.3928 |
| egpot_no_pareto_mcts | 0/30 | 0.3833 | 20.0000 | — (0 hits) | — |
| greedy_walk | 7/30 | 0.4833 | **5.6000** | **3.0000** (7 hits) | **0.6667** |
| mcts_standard | 6/30 | 0.5833 | 20.0000 | 19.1667 (6 hits) | 0.1046 |
| ppr | 0/30 | 0.4333 | 20.0000 | — (0 hits) | — |
| scalar_beam | 13/30 | 0.6333 | 16.7667 | 6.0000 (13 hits) | 0.3401 |
| vector_bfs_k2 | 2/30 | 0.4167 | 20.0000 | 17.5000 (2 hits) | 0.1167 |
| vector_topk | 7/30 | 0.4500 | 20.0000 | 9.0000 (7 hits) | 0.2712 |

### Budget 40

| Method | Hits | Recall | Mean nodes | Mean nodes-to-hit (hit count) | Mean precision-at-hit |
|---|---|---|---|---|---|
| bfs | 0/30 | 0.4333 | 40.0000 | — (0 hits) | — |
| community_graphrag | 11/30 | 0.4833 | 40.0000 | 11.1818 (11 hits) | 0.3224 |
| egpot_full | **25/30** | **0.8333** | 17.4333 | 5.1600 (25 hits) | 0.3947 |
| egpot_full_mcts | 2/30 | 0.5167 | 40.0000 | 26.5000 (2 hits) | 0.0777 |
| egpot_no_choke_point | **25/30** | **0.8333** | 17.4333 | 5.1600 (25 hits) | 0.3947 |
| egpot_no_contracts | 14/30 | 0.6500 | 20.4333 | 6.1429 (14 hits) | 0.3337 |
| egpot_no_entropy | **25/30** | **0.8333** | 16.2667 | 5.1600 (25 hits) | 0.3947 |
| egpot_no_pareto | **25/30** | **0.8333** | 15.5667 | 5.2000 (25 hits) | 0.3928 |
| egpot_no_pareto_mcts | 0/30 | 0.4000 | 39.0000 | — (0 hits) | — |
| greedy_walk | 7/30 | 0.4833 | **5.6000** | **3.0000** (7 hits) | **0.6667** |
| mcts_standard | 16/30 | 0.7667 | 40.0000 | 22.1250 (16 hits) | 0.0918 |
| ppr | 10/30 | 0.6667 | 40.0000 | 27.8000 (10 hits) | 0.0732 |
| scalar_beam | 13/30 | 0.6333 | 20.2667 | 6.0000 (13 hits) | 0.3401 |
| vector_bfs_k2 | 7/30 | 0.5667 | 40.0000 | 23.1429 (7 hits) | 0.0917 |
| vector_topk | 9/30 | 0.5167 | 40.0000 | 12.5556 (9 hits) | 0.2287 |

## 3. Hits by query type and lookalike group

### Explicit (n=15)

| Method | 10 | 20 | 40 |
|---|---|---|---|
| bfs | 0/15 | 0/15 | 0/15 |
| community_graphrag | 5/15 | 7/15 | 8/15 |
| egpot_full | **15/15** | **15/15** | **15/15** |
| egpot_full_mcts | 0/15 | 0/15 | 1/15 |
| egpot_no_choke_point | **15/15** | **15/15** | **15/15** |
| egpot_no_contracts | 8/15 | 8/15 | 8/15 |
| egpot_no_entropy | **15/15** | **15/15** | **15/15** |
| egpot_no_pareto | **15/15** | **15/15** | **15/15** |
| egpot_no_pareto_mcts | 0/15 | 0/15 | 0/15 |
| greedy_walk | 4/15 | 4/15 | 4/15 |
| mcts_standard | 0/15 | 2/15 | 9/15 |
| ppr | 0/15 | 0/15 | 5/15 |
| scalar_beam | 7/15 | 7/15 | 7/15 |
| vector_bfs_k2 | 0/15 | 2/15 | 6/15 |
| vector_topk | 4/15 | 6/15 | 6/15 |

### Indirect (n=15)

| Method | 10 | 20 | 40 |
|---|---|---|---|
| bfs | 0/15 | 0/15 | 0/15 |
| community_graphrag | 0/15 | 2/15 | 3/15 |
| egpot_full | **10/15** | **10/15** | **10/15** |
| egpot_full_mcts | 0/15 | 0/15 | 1/15 |
| egpot_no_choke_point | **10/15** | **10/15** | **10/15** |
| egpot_no_contracts | 6/15 | 6/15 | 6/15 |
| egpot_no_entropy | **10/15** | **10/15** | **10/15** |
| egpot_no_pareto | **10/15** | **10/15** | **10/15** |
| egpot_no_pareto_mcts | 0/15 | 0/15 | 0/15 |
| greedy_walk | 3/15 | 3/15 | 3/15 |
| mcts_standard | 0/15 | 4/15 | 7/15 |
| ppr | 0/15 | 0/15 | 5/15 |
| scalar_beam | 6/15 | 6/15 | 6/15 |
| vector_bfs_k2 | 0/15 | 0/15 | 1/15 |
| vector_topk | 0/15 | 1/15 | 3/15 |

### Lookalike links 4,5,6 (n=6)

| Method | 10 | 20 | 40 |
|---|---|---|---|
| bfs | 0/6 | 0/6 | 0/6 |
| community_graphrag | 0/6 | 1/6 | 2/6 |
| egpot_full | **4/6** | **4/6** | **4/6** |
| egpot_full_mcts | 0/6 | 0/6 | 0/6 |
| egpot_no_choke_point | **4/6** | **4/6** | **4/6** |
| egpot_no_contracts | 2/6 | 2/6 | 2/6 |
| egpot_no_entropy | **4/6** | **4/6** | **4/6** |
| egpot_no_pareto | **4/6** | **4/6** | **4/6** |
| egpot_no_pareto_mcts | 0/6 | 0/6 | 0/6 |
| greedy_walk | 2/6 | 2/6 | 2/6 |
| mcts_standard | 0/6 | 0/6 | 2/6 |
| ppr | 0/6 | 0/6 | 0/6 |
| scalar_beam | 2/6 | 2/6 | 2/6 |
| vector_bfs_k2 | 0/6 | 0/6 | 1/6 |
| vector_topk | 0/6 | 1/6 | 2/6 |

### Other 12 links (n=24)

| Method | 10 | 20 | 40 |
|---|---|---|---|
| bfs | 0/24 | 0/24 | 0/24 |
| community_graphrag | 5/24 | 8/24 | 9/24 |
| egpot_full | **21/24** | **21/24** | **21/24** |
| egpot_full_mcts | 0/24 | 0/24 | 2/24 |
| egpot_no_choke_point | **21/24** | **21/24** | **21/24** |
| egpot_no_contracts | 12/24 | 12/24 | 12/24 |
| egpot_no_entropy | **21/24** | **21/24** | **21/24** |
| egpot_no_pareto | **21/24** | **21/24** | **21/24** |
| egpot_no_pareto_mcts | 0/24 | 0/24 | 0/24 |
| greedy_walk | 5/24 | 5/24 | 5/24 |
| mcts_standard | 0/24 | 6/24 | 14/24 |
| ppr | 0/24 | 0/24 | 10/24 |
| scalar_beam | 11/24 | 11/24 | 11/24 |
| vector_bfs_k2 | 0/24 | 2/24 | 6/24 |
| vector_topk | 4/24 | 6/24 | 7/24 |

## 4. Preregistered expectations

### E1: identical stored records

Compared all stored non-latency fields except method name for 30 queries x 3 budgets = 90 pairs. Differences: 0.
Full visited sets/discovery order were not saved, so identity of those unrecorded outputs cannot be independently confirmed.

### E2: contract-score effect at budget 20

| Dataset | Full hits | No-contracts hits | Difference | Difference in hit-rate points |
|---|---|---|---|---|
| Train | 25/30 | 14/30 | 11 | 36.6667 |
| Online Boutique TEST | 14/14 | 9/14 | 5 | 35.7143 |

The smaller contract-score effect expected for Train is not observed: its effect is larger in raw hits and slightly larger in hit-rate points.

### E3: BFS-style baselines versus full

| Dataset | Budget | EG-POT full | BFS | Vector BFS k2 |
|---|---|---|---|---|
| Train | 10 | 25/30 | 0/30 | 0/30 |
| Online Boutique TEST | 10 | 14/14 | 0/14 | 5/14 |
| Train | 20 | 25/30 | 0/30 | 2/30 |
| Online Boutique TEST | 20 | 14/14 | 10/14 | 8/14 |
| Train | 40 | 25/30 | 0/30 | 7/30 |
| Online Boutique TEST | 40 | 14/14 | 12/14 | 12/14 |

BFS-style baseline hit rates do not improve on Train: BFS remains at zero; vector-BFS is lower than Online Boutique at every budget.

### E4: compactness at budget 40

| Item | Stored-number result |
|---|---|
| Full nodes-to-hit | 5.1600 (25/30 hits) |
| Qualifying baseline requirement | >=27/30 hits |
| Best qualifying baseline | None |
| Ratio full/baseline | — |
| Highest-hit baseline (not a substitute) | mcts_standard: 16/30 hits |

No qualifying baseline exists; a compactness ratio cannot be calculated under the registered rule.

## 5. Mechanical scorecard

Definitions and the eight-baseline pool are taken from viz/js/final_test_logic.js. Train has one whole set, not two splits: the registered 4-hit/6-hit thresholds apply once to that set. No artificial dev/test split is created. None of the observed component deltas is in the underspecified small-positive 1..3 range, so split-specific Inconclusive wording does not affect these verdicts.

| Claim | Numbers | Verdict | Rule |
|---|---|---|---|
| Contract score helps | 25 - 14 = +11 | Supported | Budget 20, no MCTS: full minus ablation must be >=4/30 hits. |
| Choke-point rule helps | 25 - 25 = +0 | Not supported | Budget 20, no MCTS: full minus ablation must be >=4/30 hits. |
| Entropy helps | 25 - 25 = +0 | Not supported | Budget 20, no MCTS: full minus ablation must be >=4/30 hits. |
| Pareto beats equal weights | 25 - 25 = +0 | Not supported | Budget 20, no MCTS: full minus ablation must be >=4/30 hits. |
| MCTS helps | 0 - 25 = -25 | Not supported | Budget 20: MCTS minus full must be >=4 hits; nonpositive effect is Not supported. |
| Compactness | Full 5.1600; qualifying baseline: none | Not supported | Budget 40: among eight baselines reaching >=90% hits, take lowest mean nodes-to-hit; full must use <=60% of it. No qualifying baseline means no support. |
| Small-budget advantage | 25 - 13 (scalar_beam) = +12 | Supported | Budget 10: full minus the highest-hit of the eight baselines must be >=6/30 hits; baseline ties break by nodes-to-hit then name. |

## 6. Seeds and weights

### MCTS seeds

| Method | Budget | Hits at seeds 0,1,2,3,4 | Min /30 | Max /30 |
|---|---|---|---|---|
| egpot_full_mcts | 20 | 0, 0, 0, 0, 1 | 0 | 1 |
| egpot_full_mcts | 40 | 2, 0, 0, 3, 2 | 0 | 3 |
| egpot_no_pareto_mcts | 20 | 0, 0, 0, 0, 0 | 0 | 0 |
| egpot_no_pareto_mcts | 40 | 0, 0, 0, 1, 0 | 0 | 1 |
| mcts_standard | 20 | 6, 5, 7, 5, 7 | 5 | 7 |
| mcts_standard | 40 | 16, 16, 15, 15, 16 | 15 | 16 |

### Weight distribution

Equal weights are a separate control, excluded from the 54 alternative vectors; no best vector is selected.

| Budget | Pareto hits /30 | Worse | Tied | Better |
|---|---|---|---|---|
| 10 | 25 | 19 | 35 | 0 |
| 20 | 25 | 19 | 35 | 0 |

## 7. Per-link hits at budget 20

E = explicit hit; I = indirect hit; - = miss. For example EI, E-, -I, --.

| Method | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bfs | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- |
| community_graphrag | E- | E- | E- | -- | -- | E- | E- | -- | E- | -- | -- | E- | -I | -I | -- |
| egpot_full | EI | EI | E- | E- | E- | EI | E- | EI | EI | EI | E- | EI | EI | EI | EI |
| egpot_full_mcts | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- |
| egpot_no_choke_point | EI | EI | E- | E- | E- | EI | E- | EI | EI | EI | E- | EI | EI | EI | EI |
| egpot_no_contracts | EI | EI | E- | -- | -- | EI | E- | -- | EI | -- | -- | E- | EI | -I | -- |
| egpot_no_entropy | EI | EI | E- | E- | E- | EI | E- | EI | EI | EI | E- | EI | EI | EI | EI |
| egpot_no_pareto | EI | EI | E- | E- | E- | EI | E- | EI | EI | EI | E- | EI | EI | EI | EI |
| egpot_no_pareto_mcts | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- |
| greedy_walk | E- | -I | E- | -- | -- | EI | E- | -- | -- | -- | -- | -- | -- | -I | -- |
| mcts_standard | -- | -I | -- | -- | -- | -- | -- | -- | EI | -- | -- | -- | -- | EI | -I |
| ppr | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- |
| scalar_beam | EI | -I | E- | -- | -- | EI | E- | -- | EI | -- | -- | E- | EI | -I | -- |
| vector_bfs_k2 | E- | -- | -- | -- | -- | -- | -- | -- | E- | -- | -- | -- | -- | -- | -- |
| vector_topk | E- | E- | E- | -- | -- | E- | E- | -- | -- | -- | -- | E- | -- | -I | -- |

## 8. Misses at budget 20

Missing gold IDs = hash-verified label gold_nodes minus the JSON's stored gold_found. First five returned IDs cannot be determined: the JSON saves no visited/discovery/ordered path list. gold_found is only a sorted gold subset, not retrieval order. No nodes are reconstructed or substituted.

Best baseline by hits: scalar_beam (13/30); ties use lowest nodes-to-hit then method name.

### egpot_full: 5 misses

| Query ID | Missing gold node IDs | First five returned IDs |
|---|---|---|
| tt03_indirect | `http::ts-route-plan-service/POST:/api/v1/routeplanservice/routePlan/quickestRoute`; `ts-route-plan-service/src/main/java/plan/controller/RoutePlanController.java:RoutePlanController.getQuickestRoutes` | Not recorded |
| tt04_indirect | `http::ts-basic-service/POST:/api/v1/basicservice/basic/travel`; `ts-basic-service/src/main/java/fdse/microservice/controller/BasicController.java:BasicController.queryForTravel` | Not recorded |
| tt05_indirect | `http::ts-station-food-service/POST:/api/v1/stationfoodservice/stationfoodstores`; `ts-station-food-service/src/main/java/food/controller/StationFoodController.java:StationFoodController.getFoodStoresByStationNames` | Not recorded |
| tt07_indirect | `http::ts-route-plan-service/POST:/api/v1/routeplanservice/routePlan/cheapestRoute`; `ts-route-plan-service/src/main/java/plan/controller/RoutePlanController.java:RoutePlanController.getCheapestRoutes` | Not recorded |
| tt11_indirect | `http::ts-consign-service/POST:/api/v1/consignservice/consigns`; `ts-consign-service/src/main/java/consign/controller/ConsignController.java:ConsignController.insertConsign` | Not recorded |

### egpot_no_pareto: 5 misses

| Query ID | Missing gold node IDs | First five returned IDs |
|---|---|---|
| tt03_indirect | `http::ts-route-plan-service/POST:/api/v1/routeplanservice/routePlan/quickestRoute`; `ts-route-plan-service/src/main/java/plan/controller/RoutePlanController.java:RoutePlanController.getQuickestRoutes` | Not recorded |
| tt04_indirect | `http::ts-basic-service/POST:/api/v1/basicservice/basic/travel`; `ts-basic-service/src/main/java/fdse/microservice/controller/BasicController.java:BasicController.queryForTravel` | Not recorded |
| tt05_indirect | `http::ts-station-food-service/POST:/api/v1/stationfoodservice/stationfoodstores`; `ts-station-food-service/src/main/java/food/controller/StationFoodController.java:StationFoodController.getFoodStoresByStationNames` | Not recorded |
| tt07_indirect | `http::ts-route-plan-service/POST:/api/v1/routeplanservice/routePlan/cheapestRoute`; `ts-route-plan-service/src/main/java/plan/controller/RoutePlanController.java:RoutePlanController.getCheapestRoutes` | Not recorded |
| tt11_indirect | `http::ts-consign-service/POST:/api/v1/consignservice/consigns`; `ts-consign-service/src/main/java/consign/controller/ConsignController.java:ConsignController.insertConsign` | Not recorded |

### mcts_standard: 24 misses

| Query ID | Missing gold node IDs | First five returned IDs |
|---|---|---|
| tt01_explicit | `http::ts-route-service/GET:/api/v1/routeservice/routes/{routeId}` | Not recorded |
| tt01_indirect | `http::ts-route-service/GET:/api/v1/routeservice/routes/{routeId}` | Not recorded |
| tt02_explicit | `http::ts-station-service/DELETE:/api/v1/stationservice/stations/{stationsId}` | Not recorded |
| tt03_explicit | `http::ts-route-plan-service/POST:/api/v1/routeplanservice/routePlan/quickestRoute` | Not recorded |
| tt03_indirect | `http::ts-route-plan-service/POST:/api/v1/routeplanservice/routePlan/quickestRoute` | Not recorded |
| tt04_explicit | `http::ts-basic-service/POST:/api/v1/basicservice/basic/travel` | Not recorded |
| tt04_indirect | `http::ts-basic-service/POST:/api/v1/basicservice/basic/travel` | Not recorded |
| tt05_explicit | `http::ts-station-food-service/POST:/api/v1/stationfoodservice/stationfoodstores` | Not recorded |
| tt05_indirect | `http::ts-station-food-service/POST:/api/v1/stationfoodservice/stationfoodstores` | Not recorded |
| tt06_explicit | `http::ts-user-service/GET:/api/v1/userservice/users/id/{userId}` | Not recorded |
| tt06_indirect | `http::ts-user-service/GET:/api/v1/userservice/users/id/{userId}` | Not recorded |
| tt07_explicit | `http::ts-route-plan-service/POST:/api/v1/routeplanservice/routePlan/cheapestRoute` | Not recorded |
| tt07_indirect | `http::ts-route-plan-service/POST:/api/v1/routeplanservice/routePlan/cheapestRoute` | Not recorded |
| tt08_explicit | `http::ts-station-service/POST:/api/v1/stationservice/stations/idlist` | Not recorded |
| tt08_indirect | `http::ts-station-service/POST:/api/v1/stationservice/stations/idlist` | Not recorded |
| tt10_explicit | `http::ts-route-service/POST:/api/v1/routeservice/routes` | Not recorded |
| tt10_indirect | `http::ts-route-service/POST:/api/v1/routeservice/routes` | Not recorded |
| tt11_explicit | `http::ts-consign-service/POST:/api/v1/consignservice/consigns` | Not recorded |
| tt11_indirect | `http::ts-consign-service/POST:/api/v1/consignservice/consigns` | Not recorded |
| tt12_explicit | `http::ts-verification-code-service/GET:/api/v1/verifycode/verify/{verifyCode}` | Not recorded |
| tt12_indirect | `http::ts-verification-code-service/GET:/api/v1/verifycode/verify/{verifyCode}` | Not recorded |
| tt13_explicit | `http::ts-station-food-service/GET:/api/v1/stationfoodservice/stationfoodstores/bystoreid/{stationFoodStoreId}`; `ts-station-food-service/src/main/java/food/controller/StationFoodController.java:StationFoodController.getFoodListByStationFoodStoreId` | Not recorded |
| tt13_indirect | `http::ts-station-food-service/GET:/api/v1/stationfoodservice/stationfoodstores/bystoreid/{stationFoodStoreId}` | Not recorded |
| tt15_explicit | `http::ts-food-service/POST:/api/v1/foodservice/orders` | Not recorded |

### scalar_beam: 17 misses

| Query ID | Missing gold node IDs | First five returned IDs |
|---|---|---|
| tt02_explicit | `http::ts-station-service/DELETE:/api/v1/stationservice/stations/{stationsId}` | Not recorded |
| tt03_indirect | `http::ts-route-plan-service/POST:/api/v1/routeplanservice/routePlan/quickestRoute`; `ts-route-plan-service/src/main/java/plan/controller/RoutePlanController.java:RoutePlanController.getQuickestRoutes` | Not recorded |
| tt04_explicit | `http::ts-basic-service/POST:/api/v1/basicservice/basic/travel` | Not recorded |
| tt04_indirect | `http::ts-basic-service/POST:/api/v1/basicservice/basic/travel`; `ts-basic-service/src/main/java/fdse/microservice/controller/BasicController.java:BasicController.queryForTravel` | Not recorded |
| tt05_explicit | `http::ts-station-food-service/POST:/api/v1/stationfoodservice/stationfoodstores` | Not recorded |
| tt05_indirect | `http::ts-station-food-service/POST:/api/v1/stationfoodservice/stationfoodstores`; `ts-station-food-service/src/main/java/food/controller/StationFoodController.java:StationFoodController.getFoodStoresByStationNames` | Not recorded |
| tt07_indirect | `http::ts-route-plan-service/POST:/api/v1/routeplanservice/routePlan/cheapestRoute`; `ts-route-plan-service/src/main/java/plan/controller/RoutePlanController.java:RoutePlanController.getCheapestRoutes` | Not recorded |
| tt08_explicit | `http::ts-station-service/POST:/api/v1/stationservice/stations/idlist` | Not recorded |
| tt08_indirect | `http::ts-station-service/POST:/api/v1/stationservice/stations/idlist` | Not recorded |
| tt10_explicit | `http::ts-route-service/POST:/api/v1/routeservice/routes` | Not recorded |
| tt10_indirect | `http::ts-route-service/POST:/api/v1/routeservice/routes` | Not recorded |
| tt11_explicit | `http::ts-consign-service/POST:/api/v1/consignservice/consigns` | Not recorded |
| tt11_indirect | `http::ts-consign-service/POST:/api/v1/consignservice/consigns`; `ts-consign-service/src/main/java/consign/controller/ConsignController.java:ConsignController.insertConsign` | Not recorded |
| tt12_indirect | `http::ts-verification-code-service/GET:/api/v1/verifycode/verify/{verifyCode}` | Not recorded |
| tt14_explicit | `http::ts-assurance-service/GET:/api/v1/assuranceservice/assurances/{typeIndex}/{orderId}` | Not recorded |
| tt15_explicit | `http::ts-food-service/POST:/api/v1/foodservice/orders` | Not recorded |
| tt15_indirect | `http::ts-food-service/POST:/api/v1/foodservice/orders` | Not recorded |

## Limits

- Full returned-node order and full visited sets are absent. First-five nodes and full-set identity for E1 cannot be independently established.
- No baseline reaches the registered >=90% hit threshold at budget 40, so E4's ratio is unavailable.
- The original site scorecard describes two splits; the preregistration replaces them with one 30-query set. Observed deltas avoid the unregistered small-positive inconclusive boundary.
- Nodes-to-hit averages cover each method's successful queries, which may be different subsets.
- All numeric tables aggregate stored fields only. Label strings are used solely to name missing gold nodes after hash verification.
