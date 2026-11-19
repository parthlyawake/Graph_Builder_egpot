# DeathStarBench PPR audit

The audit reads locked records, labels and GraphML. It does not run a retriever.

| Check | Status | Social | Media | Pooled |
| --- | --- | ---: | ---: | ---: |
| Main-row coverage | PASS | 1/1 | 1/1 | 2/2 app(s) complete |
| 1a. Within node budget | PASS | 84/84 | 54/54 | 138/138 rows |
| 1b. Start included in returned count | PASS | 84/84 | 54/54 | 138/138 rows |
| 2. No duplicate node IDs | PASS | 84/84 | 54/54 | 138/138 rows |
| 3a. Every returned ID exists in GraphML | PASS | 84/84 | 54/54 | 138/138 rows |
| 3b. Returned ID occurrences found in GraphML | PASS | 1960/1960 | 1260/1260 | 3220/3220 IDs |
| 4a. Both gold nodes returned at budget 40, seed 0 | PASS | 28/28 | 18/18 | 46/46 queries |
| 4b. Recorded hit matches independent recomputation | PASS | 28/28 | 18/18 | 46/46 queries |
| 7. Distance and rank rows at budget 40, seed 0 | PASS | 28/28 | 18/18 | 46/46 queries |

Main seeds by app: `dsb_social` [0], `dsb_media` [0].
Budget-40 hit-flag mismatches: [].
Budget-40 queries missing at least one gold ID: [].

## 5. PASS — PPR input and personalization

`bench/egpot_eval.py:640–648` passes only query text, start node and budget to the retriever. `PersonalizedPageRank.retrieve` (lines 259–268) ignores query text and uses the graph and start for ranking. The budget caps the output and includes the start. PPR receives no gold, contract or handler label IDs, link ID, or query type. The evaluator scores against gold after retrieval (lines 660–664).

`PersonalizedPageRank.scores` at `bench/egpot_eval.py:254`:

```python
personalization = {n: float(n == start_node) for n in self.move_graph}
self._scores[start_node] = nx.pagerank(self.move_graph, alpha=0.85,
    personalization=personalization, tol=1e-10, max_iter=500, weight="weight")
```

## 6. PASS — Shared choke-point rule

Normal PPR builds its move graph from the shared `GraphView.neighbors` (`bench/egpot_eval.py:73–80,230–250`). The OFF variant rebuilds from the same graph and policy with the rule disabled (`bench/egpot_eval.py:462–491`). The shared rule blocks only incoming `DEFINES_RPC` moves from `rpc_contract` nodes (`eg_pot.py:171–189`).

| App | Suppressed moves (actual / expected) | Unexpected changes |
| --- | ---: | ---: |
| dsb_social | 27/27 | 0 |
| dsb_media | 29/29 | 0 |

| App | Budget | ON hits | OFF hits | Same hit flag | Same returned order |
| --- | ---: | ---: | ---: | ---: | ---: |
| dsb_social | 20 | 26/28 | 26/28 | 28/28 | 2/28 |
| dsb_social | 40 | 28/28 | 28/28 | 28/28 | 0/28 |
| dsb_media | 20 | 16/18 | 16/18 | 18/18 | 0/18 |
| dsb_media | 40 | 18/18 | 18/18 | 18/18 | 0/18 |

The shared rule changes the available moves here. Identical hits are an observed result of these records, not a guarantee of the rule.

## 7. Budget-40 query distances and gold positions

Counts are cumulative shortest-path distances on the raw undirected GraphML and include the start at distance zero. Gold positions are one-based in the saved discovery order.

| App | Query | Returned | Distance ≤1 | Distance ≤2 | Distance ≤3 | Contract rank | Handler rank |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| dsb_social | sn01_explicit | 40 | 14 | 39 | 40 | 2 | 11 |
| dsb_social | sn01_indirect | 40 | 14 | 39 | 40 | 2 | 11 |
| dsb_social | sn02_explicit | 40 | 15 | 40 | 40 | 3 | 2 |
| dsb_social | sn02_indirect | 40 | 15 | 40 | 40 | 3 | 2 |
| dsb_social | sn03_explicit | 40 | 15 | 40 | 40 | 2 | 3 |
| dsb_social | sn03_indirect | 40 | 15 | 40 | 40 | 2 | 3 |
| dsb_social | sn04_explicit | 40 | 15 | 40 | 40 | 2 | 3 |
| dsb_social | sn04_indirect | 40 | 15 | 40 | 40 | 2 | 3 |
| dsb_social | sn05_explicit | 40 | 14 | 40 | 40 | 2 | 3 |
| dsb_social | sn05_indirect | 40 | 14 | 40 | 40 | 2 | 3 |
| dsb_social | sn06_explicit | 40 | 15 | 40 | 40 | 2 | 10 |
| dsb_social | sn06_indirect | 40 | 15 | 40 | 40 | 2 | 10 |
| dsb_social | sn07_explicit | 40 | 16 | 40 | 40 | 3 | 2 |
| dsb_social | sn07_indirect | 40 | 16 | 40 | 40 | 3 | 2 |
| dsb_social | sn08_explicit | 40 | 23 | 40 | 40 | 3 | 8 |
| dsb_social | sn08_indirect | 40 | 23 | 40 | 40 | 3 | 8 |
| dsb_social | sn09_explicit | 40 | 23 | 40 | 40 | 3 | 5 |
| dsb_social | sn09_indirect | 40 | 23 | 40 | 40 | 3 | 5 |
| dsb_social | sn10_explicit | 40 | 33 | 40 | 40 | 3 | 6 |
| dsb_social | sn10_indirect | 40 | 33 | 40 | 40 | 3 | 6 |
| dsb_social | sn11_explicit | 40 | 33 | 40 | 40 | 5 | 8 |
| dsb_social | sn11_indirect | 40 | 33 | 40 | 40 | 5 | 8 |
| dsb_social | sn12_explicit | 40 | 21 | 40 | 40 | 3 | 13 |
| dsb_social | sn12_indirect | 40 | 21 | 40 | 40 | 3 | 13 |
| dsb_social | sn13_explicit | 40 | 20 | 40 | 40 | 8 | 3 |
| dsb_social | sn13_indirect | 40 | 20 | 40 | 40 | 8 | 3 |
| dsb_social | sn14_explicit | 40 | 21 | 40 | 40 | 7 | 24 |
| dsb_social | sn14_indirect | 40 | 21 | 40 | 40 | 7 | 24 |
| dsb_media | mm01_explicit | 40 | 17 | 40 | 40 | 13 | 22 |
| dsb_media | mm01_indirect | 40 | 17 | 40 | 40 | 13 | 22 |
| dsb_media | mm02_explicit | 40 | 17 | 40 | 40 | 12 | 20 |
| dsb_media | mm02_indirect | 40 | 17 | 40 | 40 | 12 | 20 |
| dsb_media | mm03_explicit | 40 | 17 | 40 | 40 | 11 | 14 |
| dsb_media | mm03_indirect | 40 | 17 | 40 | 40 | 11 | 14 |
| dsb_media | mm04_explicit | 40 | 16 | 40 | 40 | 9 | 4 |
| dsb_media | mm04_indirect | 40 | 16 | 40 | 40 | 9 | 4 |
| dsb_media | mm05_explicit | 40 | 16 | 40 | 40 | 12 | 13 |
| dsb_media | mm05_indirect | 40 | 16 | 40 | 40 | 12 | 13 |
| dsb_media | mm06_explicit | 40 | 19 | 40 | 40 | 2 | 4 |
| dsb_media | mm06_indirect | 40 | 19 | 40 | 40 | 2 | 4 |
| dsb_media | mm07_explicit | 40 | 15 | 40 | 40 | 2 | 4 |
| dsb_media | mm07_indirect | 40 | 15 | 40 | 40 | 2 | 4 |
| dsb_media | mm08_explicit | 40 | 19 | 40 | 40 | 5 | 4 |
| dsb_media | mm08_indirect | 40 | 19 | 40 | 40 | 5 | 4 |
| dsb_media | mm09_explicit | 40 | 15 | 40 | 40 | 7 | 11 |
| dsb_media | mm09_indirect | 40 | 15 | 40 | 40 | 7 | 11 |
