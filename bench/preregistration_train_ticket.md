Preregistration - Train-Ticket. Written before any labels, queries or retrieval runs.
Setup: frozen EG-POT and harness code; the whole labeled set (15 links, 30 queries) is run once, with no dev/test split and no tuning. Failures are reported and analysed, not fixed.
Expectations (not claims):
E1. The choke-point ablation gives results identical to the full method, because the rule only applies to rpc_contract nodes and this graph has none (sanity check).
E2. The contract-score ablation changes results less than on Online Boutique, because the first hop of an HTTP link (HTTP_CALLS, layer Ldep) scores 0.6 on contract consistency.
E3. BFS-style baselines (bfs, vector_bfs_k2) do relatively better than on Online Boutique, because the target handler is 1 hop and the endpoint node 2 hops from the start node.
E4. No expectation that EG-POT wins on hits. Fewer nodes needed to hit is the one result that may carry over.
Verdict rules: the same scorecard rules as the Online Boutique Final test, with hit-count thresholds scaled to the larger set: component claims (contracts, choke-point, entropy, Pareto, MCTS) need a difference of at least 4 of 30 queries; the small-budget claim needs at least 6 of 30; the compactness rule is unchanged (<= 60% of the best baseline's nodes-to-hit).
Limitations stated in advance: links were drawn only from those the builder recovers; twin services are excluded; 15 links from one repository.

---
Graph_Builder HEAD: b9f264df08100219aea9b0870060540fa4a1611b
Graph SHA256: 8904e43268d34bd7b8734ec8f93326eb60051a6d2ac71484816ff595cc2a4c55
Date: 2026-11-09
