window.VIZ_GLOSSARY = {
  "bfs": {
    "key": "bfs",
    "label": "Breadth-first search",
    "long": "It does not look at the question at all. It finds the answer only if the answer is close enough to the start node that the budget covers every node nearer than it.",
    "short": "Collects everything around the start node, one hop at a time, until the budget is full."
  },
  "bfs_no_choke": {
    "key": "bfs_no_choke",
    "label": "Breadth-first search without the choke-point rule",
    "long": "The same method with the choke-point rule switched off.",
    "short": "The same method with the choke-point rule switched off."
  },
  "budget": {
    "key": "budget",
    "label": "node budget",
    "long": "The maximum number of code nodes a method may return, standing in for how much the AI assistant must read; the start node counts.",
    "short": "The maximum number of code nodes a method may return, standing in for how much the AI assistant must read; the start node counts."
  },
  "community_graphrag": {
    "key": "community_graphrag",
    "label": "Community GraphRAG (text only)",
    "long": "Splits the graph into clusters of tightly connected nodes (Louvain), ranks clusters by how relevant their best nodes are to the question, and returns nodes from the best clusters. Our version has no AI-written cluster summaries.",
    "short": "Splits the graph into clusters of tightly connected nodes (Louvain), ranks clusters by how relevant their best nodes are to the question, and returns nodes from the best clusters. Our version has no AI-written cluster summaries."
  },
  "egpot_full": {
    "key": "egpot_full",
    "label": "EG-POT (full)",
    "long": "At every step it scores each neighboring node on relevance to the question, hop efficiency, contract consistency and entropy gain. It keeps the candidates that no other candidate beats on all four at once (the Pareto front), carries the best 4 paths forward (beam width 4), and stops when the node budget is reached or nothing new is reachable. No lookahead.",
    "short": "Walks outward from the start node, scoring each neighbor on four things and keeping the Pareto-best."
  },
  "egpot_full_mcts": {
    "key": "egpot_full_mcts",
    "label": "EG-POT + MCTS",
    "long": "Before choosing, it runs 16 short simulated walks (3 steps deep) from each candidate and blends what those walks find with the candidate's immediate score, half and half. This can rescue a step that looks weak now but leads somewhere good, at the cost of much more computation. Simulations never add nodes to the answer.",
    "short": "Same as EG-POT, plus a lookahead: it tries short simulated walks before committing to a step."
  },
  "egpot_no_choke_point": {
    "key": "egpot_no_choke_point",
    "label": "No choke-point rule",
    "long": "Normally, when the walk is on an RPC node it does not step \"up\" to the parent service node, because from there it would fan out into all the sibling RPCs. With the rule off, the walk can take that detour and collects many unrelated nodes.",
    "short": "Turns off the rule that stops the walk from going from an RPC back up to its parent service."
  },
  "egpot_no_choke_point_mcts": {
    "key": "egpot_no_choke_point_mcts",
    "label": "No choke-point rule + MCTS",
    "long": "Normally, when the walk is on an RPC node it does not step \"up\" to the parent service node, because from there it would fan out into all the sibling RPCs. With the rule off, the walk can take that detour and collects many unrelated nodes. (with the MCTS lookahead on).",
    "short": "Turns off the rule that stops the walk from going from an RPC back up to its parent service. (with the MCTS lookahead on)."
  },
  "egpot_no_contracts": {
    "key": "egpot_no_contracts",
    "label": "No contracts",
    "long": "The contract score gives 1.0 to steps that cross a gRPC/HTTP/Kafka contract and 0.6 to others. With it off the score is a constant, so the search no longer prefers routes that go through service contracts.",
    "short": "Removes the contract-consistency score."
  },
  "egpot_no_contracts_mcts": {
    "key": "egpot_no_contracts_mcts",
    "label": "No contracts + MCTS",
    "long": "The contract score gives 1.0 to steps that cross a gRPC/HTTP/Kafka contract and 0.6 to others. With it off the score is a constant, so the search no longer prefers routes that go through service contracts. (with the MCTS lookahead on).",
    "short": "Removes the contract-consistency score. (with the MCTS lookahead on)."
  },
  "egpot_no_entropy": {
    "key": "egpot_no_entropy",
    "label": "No entropy",
    "long": "The entropy score rewards steps that bring in a new kind of relationship (for example the first IMPLEMENTS after several CALLS). With it off that score is a constant, so there is no bonus for variety.",
    "short": "Removes the entropy-gain score."
  },
  "egpot_no_entropy_mcts": {
    "key": "egpot_no_entropy_mcts",
    "label": "No entropy + MCTS",
    "long": "The entropy score rewards steps that bring in a new kind of relationship (for example the first IMPLEMENTS after several CALLS). With it off that score is a constant, so there is no bonus for variety. (with the MCTS lookahead on).",
    "short": "Removes the entropy-gain score. (with the MCTS lookahead on)."
  },
  "egpot_no_pareto": {
    "key": "egpot_no_pareto",
    "label": "Equal weighted sum",
    "long": "Instead of keeping the Pareto front, every candidate gets one number (0.25 x relevance + 0.25 x hop + 0.25 x contract + 0.25 x entropy) and the top ones are kept. The weights are not tuned. Simpler and faster than Pareto; it tests whether Pareto selection is actually needed.",
    "short": "Replaces Pareto selection with one combined score: the four scores added with equal weights (0.25 each)."
  },
  "egpot_no_pareto_mcts": {
    "key": "egpot_no_pareto_mcts",
    "label": "Equal weighted sum + MCTS",
    "long": "Instead of keeping the Pareto front, every candidate gets one number (0.25 x relevance + 0.25 x hop + 0.25 x contract + 0.25 x entropy) and the top ones are kept. The weights are not tuned. Simpler and faster than Pareto; it tests whether Pareto selection is actually needed. (with the MCTS lookahead on).",
    "short": "Replaces Pareto selection with one combined score: the four scores added with equal weights (0.25 each). (with the MCTS lookahead on)."
  },
  "explicit": {
    "key": "explicit",
    "label": "explicit",
    "long": "the question names the function (for example \"where is GetSupportedCurrencies implemented for getCurrencies?\")",
    "short": "the question names the function (for example \"where is GetSupportedCurrencies implemented for getCurrencies?\")"
  },
  "gold_recall": {
    "key": "gold_recall",
    "label": "recall",
    "long": "share of answer nodes collected (average).",
    "short": "share of answer nodes collected (average)."
  },
  "greedy_walk": {
    "key": "greedy_walk",
    "label": "Greedy relevance walk",
    "long": "Cheap and fast but easily trapped: one wrong step and it cannot recover, and it often stops after only a few nodes.",
    "short": "From the start, always steps to the single most relevant neighbor; stops at a dead end."
  },
  "greedy_walk_no_choke": {
    "key": "greedy_walk_no_choke",
    "label": "Greedy relevance walk without the choke-point rule",
    "long": "The same method with the choke-point rule switched off.",
    "short": "The same method with the choke-point rule switched off."
  },
  "hit": {
    "key": "hit",
    "label": "hit rate",
    "long": "share of queries where ALL the answer nodes (the contract and the handler) were collected.",
    "short": "share of queries where ALL the answer nodes (the contract and the handler) were collected."
  },
  "indirect": {
    "key": "indirect",
    "label": "indirect",
    "long": "the question describes what the function does without naming it.",
    "short": "the question describes what the function does without naming it."
  },
  "latency_s": {
    "key": "latency_s",
    "label": "latency",
    "long": "seconds measured on the machine that exported the data.",
    "short": "seconds measured on the machine that exported the data."
  },
  "mcts_standard": {
    "key": "mcts_standard",
    "label": "Standard MCTS",
    "long": "Classic Monte Carlo tree search with a single reward (the best relevance reached): 300 iterations, random 3-step rollouts; returns the most-visited nodes.",
    "short": "Classic Monte Carlo tree search with a single reward (the best relevance reached): 300 iterations, random 3-step rollouts; returns the most-visited nodes."
  },
  "mcts_standard_no_choke": {
    "key": "mcts_standard_no_choke",
    "label": "Standard MCTS without the choke-point rule",
    "long": "The same method with the choke-point rule switched off.",
    "short": "The same method with the choke-point rule switched off."
  },
  "nodes_returned": {
    "key": "nodes_returned",
    "label": "nodes returned",
    "long": "how many nodes the method collected (a proxy for how much context the AI assistant would have to read).",
    "short": "how many nodes the method collected (a proxy for how much context the AI assistant would have to read)."
  },
  "nodes_to_hit": {
    "key": "nodes_to_hit",
    "label": "nodes to hit",
    "long": "the position at which the last answer node was found; smaller is better; queries the method missed are excluded.",
    "short": "the position at which the last answer node was found; smaller is better; queries the method missed are excluded."
  },
  "ordered_path_match": {
    "key": "ordered_path_match",
    "label": "ordered path match",
    "long": "whether the answer path appears in the right order in the method's best single path (not meaningful for methods that return a ranking, not a walk).",
    "short": "whether the answer path appears in the right order in the method's best single path (not meaningful for methods that return a ranking, not a walk)."
  },
  "pareto_front": {
    "key": "pareto_front",
    "label": "Pareto front",
    "long": "a candidate is on the front if no other candidate is at least as good on all four scores and strictly better on one. Front 0 is the best group; selection takes front 0 first, then front 1, and so on.",
    "short": "a candidate is on the front if no other candidate is at least as good on all four scores and strictly better on one. Front 0 is the best group; selection takes front 0 first, then front 1, and so on."
  },
  "path_coverage": {
    "key": "path_coverage",
    "label": "path coverage",
    "long": "share of the answer path's nodes (start, contract, handler) that were collected.",
    "short": "share of the answer path's nodes (start, contract, handler) that were collected."
  },
  "ppr": {
    "key": "ppr",
    "label": "Personalized PageRank",
    "long": "Simulates random walks that keep jumping back to the start node (15% chance at each step) and keeps the nodes visited most. It ignores the question text.",
    "short": "Simulates random walks that keep jumping back to the start node (15% chance at each step) and keeps the nodes visited most. It ignores the question text."
  },
  "ppr_no_choke": {
    "key": "ppr_no_choke",
    "label": "Personalized PageRank without the choke-point rule",
    "long": "The same method with the choke-point rule switched off.",
    "short": "The same method with the choke-point rule switched off."
  },
  "precision": {
    "key": "precision",
    "label": "precision",
    "long": "answer nodes found divided by all nodes returned; it is low for every method because only 2 nodes are \"the answer\" while methods return 15 to 60.",
    "short": "answer nodes found divided by all nodes returned; it is low for every method because only 2 nodes are \"the answer\" while methods return 15 to 60."
  },
  "precision_at_hit": {
    "key": "precision_at_hit",
    "label": "precision at hit",
    "long": "The number of answer nodes divided by the number of nodes discovered when the last answer node is found, averaged only over successful queries. Misses are excluded; read the hit count alongside it.",
    "short": "The number of answer nodes divided by the number of nodes discovered when the last answer node is found, averaged only over successful queries. Misses are excluded; read the hit count alongside it."
  },
  "scalar_beam": {
    "key": "scalar_beam",
    "label": "Beam search (one score)",
    "long": "Like EG-POT's beam, but each step is ranked only by text relevance and the best 4 paths are kept by total relevance.",
    "short": "Like EG-POT's beam, but each step is ranked only by text relevance and the best 4 paths are kept by total relevance."
  },
  "scalar_beam_no_choke": {
    "key": "scalar_beam_no_choke",
    "label": "Beam search (one score) without the choke-point rule",
    "long": "The same method with the choke-point rule switched off.",
    "short": "The same method with the choke-point rule switched off."
  },
  "score_contract": {
    "key": "score_contract",
    "label": "Contract consistency",
    "long": "1.0 if the step crosses a service contract (or lands on a contract node), otherwise 0.6.",
    "short": "1.0 if the step crosses a service contract (or lands on a contract node), otherwise 0.6."
  },
  "score_entropy": {
    "key": "score_entropy",
    "label": "Entropy gain",
    "long": "a bonus for introducing a relationship type the path has not used much, so the walk explores different kinds of links. Computed as the gain in relationship-type variety times a novelty factor.",
    "short": "a bonus for introducing a relationship type the path has not used much, so the walk explores different kinds of links. Computed as the gain in relationship-type variety times a novelty factor."
  },
  "score_hop": {
    "key": "score_hop",
    "label": "Hop efficiency",
    "long": "0.8 raised to the number of hops from the start, so nearer nodes score higher (1 hop = 0.8, 2 hops = 0.64).",
    "short": "0.8 raised to the number of hops from the start, so nearer nodes score higher (1 hop = 0.8, 2 hops = 0.64)."
  },
  "score_relevance": {
    "key": "score_relevance",
    "label": "Relevance",
    "long": "how well the node's text matches the question (word-overlap similarity, TF-IDF cosine, after splitting names like GetSupportedCurrencies into separate words). 0 to 1.",
    "short": "how well the node's text matches the question (word-overlap similarity, TF-IDF cosine, after splitting names like GetSupportedCurrencies into separate words). 0 to 1."
  },
  "seed": {
    "key": "seed",
    "label": "seed",
    "long": "the starting value for the random numbers in simulated walks; different seeds give different walks",
    "short": "the starting value for the random numbers in simulated walks; different seeds give different walks"
  },
  "vector_bfs_k2": {
    "key": "vector_bfs_k2",
    "label": "Vector + BFS (2 hops)",
    "long": "Starts from the start node plus the 3 nodes whose text best matches the question, then expands outward hop by hop (up to 2 hops) until the node budget is full. At these budgets every K gives identical results because the budget fills by the second hop.",
    "short": "Starts from the start node plus the 3 nodes whose text best matches the question, then expands outward hop by hop (up to 2 hops) until the node budget is full. At these budgets every K gives identical results because the budget fills by the second hop."
  },
  "vector_bfs_k2_no_choke": {
    "key": "vector_bfs_k2_no_choke",
    "label": "Vector + BFS (2 hops) without the choke-point rule",
    "long": "The same method with the choke-point rule switched off.",
    "short": "The same method with the choke-point rule switched off."
  },
  "vector_bfs_k3": {
    "key": "vector_bfs_k3",
    "label": "Vector + BFS (3 hops)",
    "long": "Starts from the start node plus the 3 nodes whose text best matches the question, then expands outward hop by hop (up to 3 hops) until the node budget is full. At these budgets every K gives identical results because the budget fills by the second hop.",
    "short": "Starts from the start node plus the 3 nodes whose text best matches the question, then expands outward hop by hop (up to 3 hops) until the node budget is full. At these budgets every K gives identical results because the budget fills by the second hop."
  },
  "vector_bfs_k4": {
    "key": "vector_bfs_k4",
    "label": "Vector + BFS (4 hops)",
    "long": "Starts from the start node plus the 3 nodes whose text best matches the question, then expands outward hop by hop (up to 4 hops) until the node budget is full. At these budgets every K gives identical results because the budget fills by the second hop.",
    "short": "Starts from the start node plus the 3 nodes whose text best matches the question, then expands outward hop by hop (up to 4 hops) until the node budget is full. At these budgets every K gives identical results because the budget fills by the second hop."
  },
  "vector_bfs_k5": {
    "key": "vector_bfs_k5",
    "label": "Vector + BFS (5 hops)",
    "long": "Starts from the start node plus the 3 nodes whose text best matches the question, then expands outward hop by hop (up to 5 hops) until the node budget is full. At these budgets every K gives identical results because the budget fills by the second hop.",
    "short": "Starts from the start node plus the 3 nodes whose text best matches the question, then expands outward hop by hop (up to 5 hops) until the node budget is full. At these budgets every K gives identical results because the budget fills by the second hop."
  },
  "vector_topk": {
    "key": "vector_topk",
    "label": "Vector top-K",
    "long": "The simplest baseline (retrieval-augmented generation style). It never follows a link, so it can only find answers whose text resembles the question.",
    "short": "Ignores the graph: ranks every node by text similarity to the question and takes the top N."
  },
  "weighting": {
    "key": "weighting",
    "label": "weighting",
    "long": "a set of four numbers that decide how much each score counts in the weighted sum",
    "short": "a set of four numbers that decide how much each score counts in the weighted sum"
  }
};
