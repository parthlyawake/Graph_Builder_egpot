# DeathStarBench distance analysis (post-hoc exploratory)

This analysis uses saved hits and returned IDs. Graph distances are descriptive and were never inputs to a retriever or a label. This is outside C1–C7.

## Gold depth and degree distributions (post-hoc exploratory)

Each cell shows value × query count. Gold depth is the larger raw undirected distance. Multigraph degree counts parallel edges; unique undirected neighbors are in the JSON.

| Scope | Type | Depth | Start degree | Contract degree |
| --- | --- | --- | --- | --- |
| dsb_social | all | 1×8, 2×20 | 15×4, 16×8, 17×2, 24×2, 29×2, 42×4, 47×2, 55×2, 61×2 | 9×8, 10×10, 11×6, 12×4 |
| dsb_social | explicit | 1×4, 2×10 | 15×2, 16×4, 17×1, 24×1, 29×1, 42×2, 47×1, 55×1, 61×1 | 9×4, 10×5, 11×3, 12×2 |
| dsb_social | indirect | 1×4, 2×10 | 15×2, 16×4, 17×1, 24×1, 29×1, 42×2, 47×1, 55×1, 61×1 | 9×4, 10×5, 11×3, 12×2 |
| dsb_media | all | 1×8, 2×10 | 20×2, 30×2, 32×2, 45×2, 53×6, 56×4 | 9×4, 10×6, 12×8 |
| dsb_media | explicit | 1×4, 2×5 | 20×1, 30×1, 32×1, 45×1, 53×3, 56×2 | 9×2, 10×3, 12×4 |
| dsb_media | indirect | 1×4, 2×5 | 20×1, 30×1, 32×1, 45×1, 53×3, 56×2 | 9×2, 10×3, 12×4 |
| pooled | all | 1×16, 2×30 | 15×4, 16×8, 17×2, 20×2, 24×2, 29×2, 30×2, 32×2, 42×4, 45×2, 47×2, 53×6, 55×2, 56×4, 61×2 | 9×12, 10×16, 11×6, 12×12 |
| pooled | explicit | 1×8, 2×15 | 15×2, 16×4, 17×1, 20×1, 24×1, 29×1, 30×1, 32×1, 42×2, 45×1, 47×1, 53×3, 55×1, 56×2, 61×1 | 9×6, 10×8, 11×3, 12×6 |
| pooled | indirect | 1×8, 2×15 | 15×2, 16×4, 17×1, 20×1, 24×1, 29×1, 30×1, 32×1, 42×2, 45×1, 47×1, 53×3, 55×1, 56×2, 61×1 | 9×6, 10×8, 11×3, 12×6 |

## Hits by gold depth (post-hoc exploratory)

Cells show seed 0 hits / queries, with the median hit count / queries in parentheses where seeds 0–5 were recorded.

| Scope | Depth | Budget | egpot_full | egpot_no_pareto | egpot_full_mcts | ppr | bfs | vector_topk | mcts_standard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dsb_social | 1 | 10 | 7/8 | 8/8 | 7/8 | 8/8 | 8/8 | 4/8 | 5/8 |
| dsb_social | 1 | 20 | 7/8 | 8/8 | 7/8 (7/8) | 8/8 | 8/8 | 4/8 | 8/8 (8/8) |
| dsb_social | 1 | 40 | 7/8 | 8/8 | 7/8 (7/8) | 8/8 | 8/8 | 6/8 | 8/8 (8/8) |
| dsb_social | 2 | 10 | 13/20 | 16/20 | 12/20 | 14/20 | 0/20 | 2/20 | 1/20 |
| dsb_social | 2 | 20 | 13/20 | 16/20 | 13/20 (13/20) | 18/20 | 0/20 | 5/20 | 8/20 (8/20) |
| dsb_social | 2 | 40 | 14/20 | 16/20 | 16/20 (16/20) | 20/20 | 8/20 | 11/20 | 15/20 (15/20) |
| dsb_media | 1 | 10 | 8/8 | 8/8 | 6/8 | 8/8 | 8/8 | 2/8 | 4/8 |
| dsb_media | 1 | 20 | 8/8 | 8/8 | 6/8 (6/8) | 8/8 | 8/8 | 4/8 | 8/8 (8/8) |
| dsb_media | 1 | 40 | 8/8 | 8/8 | 6/8 (6/8) | 8/8 | 8/8 | 5/8 | 8/8 (8/8) |
| dsb_media | 2 | 10 | 8/10 | 8/10 | 5/10 | 0/10 | 0/10 | 2/10 | 0/10 |
| dsb_media | 2 | 20 | 8/10 | 8/10 | 6/10 (7.5/10) | 8/10 | 0/10 | 4/10 | 0/10 (0/10) |
| dsb_media | 2 | 40 | 8/10 | 8/10 | 8/10 (8.5/10) | 10/10 | 0/10 | 8/10 | 0/10 (0/10) |
| pooled | 1 | 10 | 15/16 | 16/16 | 13/16 | 16/16 | 16/16 | 6/16 | 9/16 |
| pooled | 1 | 20 | 15/16 | 16/16 | 13/16 (13/16) | 16/16 | 16/16 | 8/16 | 16/16 (16/16) |
| pooled | 1 | 40 | 15/16 | 16/16 | 13/16 (13/16) | 16/16 | 16/16 | 11/16 | 16/16 (16/16) |
| pooled | 2 | 10 | 21/30 | 24/30 | 17/30 | 14/30 | 0/30 | 4/30 | 1/30 |
| pooled | 2 | 20 | 21/30 | 24/30 | 19/30 (20/30) | 26/30 | 0/30 | 9/30 | 8/30 (8/30) |
| pooled | 2 | 40 | 22/30 | 24/30 | 24/30 (24.5/30) | 30/30 | 8/30 | 19/30 | 15/30 (15/30) |

## Paired hit-rate differences by depth (post-hoc exploratory)

EG-POT full minus PPR at seed 0. Only buckets with at least eight queries get an unadjusted 95% cluster bootstrap interval. Other buckets have counts only above.

| Scope | Depth | Budget | Queries | Difference | 95% interval |
| --- | --- | --- | --- | --- | --- |
| dsb_social | 1 | 10 | 8 | -0.1250 | [-0.3750, +0.0000] |
| dsb_social | 1 | 20 | 8 | -0.1250 | [-0.3750, +0.0000] |
| dsb_social | 1 | 40 | 8 | -0.1250 | [-0.3750, +0.0000] |
| dsb_social | 2 | 10 | 20 | -0.0500 | [-0.4615, +0.4444] |
| dsb_social | 2 | 20 | 20 | -0.2500 | [-0.5833, +0.1667] |
| dsb_social | 2 | 40 | 20 | -0.3000 | [-0.5000, -0.1000] |
| dsb_media | 1 | 10 | 8 | +0.0000 | [+0.0000, +0.0000] |
| dsb_media | 1 | 20 | 8 | +0.0000 | [+0.0000, +0.0000] |
| dsb_media | 1 | 40 | 8 | +0.0000 | [+0.0000, +0.0000] |
| dsb_media | 2 | 10 | 10 | +0.8000 | [+0.5000, +1.0000] |
| dsb_media | 2 | 20 | 10 | +0.0000 | [-0.5000, +0.1667] |
| dsb_media | 2 | 40 | 10 | -0.2000 | [-0.5000, +0.0000] |
| pooled | 1 | 10 | 16 | -0.0625 | [-0.1875, +0.0000] |
| pooled | 1 | 20 | 16 | -0.0625 | [-0.1875, +0.0000] |
| pooled | 1 | 40 | 16 | -0.0625 | [-0.1875, +0.0000] |
| pooled | 2 | 10 | 30 | +0.2333 | [-0.1429, +0.5714] |
| pooled | 2 | 20 | 30 | -0.1667 | [-0.4615, +0.1071] |
| pooled | 2 | 40 | 30 | -0.2667 | [-0.4287, -0.1154] |

## EG-POT full misses at budget 40 (post-hoc exploratory)

One row per missing gold ID. The closest returned node uses raw undirected distance, with ties resolved by earliest one-based discovery rank. An eligible start neighbor was considered in round one and pruned if it is missing. A node with no eligible move from any returned node was beyond the returned frontier. Other cases are undetermined because the locked records contain no beam trace. These checks use the locked GraphView policy and the frozen root expansion and selection ledger (`eg_pot.py:397–410,556–647`).

| App | Query | Type | Depth | Start degree | Contract degree | Missing gold | Nearest ID | Rank | Hops | Frontier or pruned |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dsb_social | sn04_indirect | indirect | 1 | 16 | 10 | handler | `ComposePost/ComposePostHandler.h:social_network._ComposeUniqueIdHelper` | 1 | 1 | pruned at root |
| dsb_social | sn08_explicit | explicit | 2 | 47 | 11 | contract | `HomeTimeline/HomeTimelineHandler.h:social_network.WriteHomeTimeline` | 1 | 1 | pruned at root |
| dsb_social | sn08_explicit | explicit | 2 | 47 | 11 | handler | `external::LOG` | 21 | 1 | undetermined (beam trace unavailable) |
| dsb_social | sn08_indirect | indirect | 2 | 47 | 11 | contract | `HomeTimeline/HomeTimelineHandler.h:social_network.WriteHomeTimeline` | 1 | 1 | pruned at root |
| dsb_social | sn08_indirect | indirect | 2 | 47 | 11 | handler | `HomeTimeline/HomeTimelineHandler.h:social_network.WriteHomeTimeline` | 1 | 2 | beyond returned frontier |
| dsb_social | sn09_explicit | explicit | 2 | 29 | 11 | contract | `HomeTimeline/HomeTimelineHandler.h:social_network.ReadHomeTimeline` | 1 | 1 | pruned at root |
| dsb_social | sn09_explicit | explicit | 2 | 29 | 11 | handler | `HomeTimeline/HomeTimelineHandler.h:social_network.ReadHomeTimeline` | 1 | 2 | beyond returned frontier |
| dsb_social | sn10_explicit | explicit | 2 | 42 | 10 | contract | `Text/TextHandler.h:social_network.ComposeText` | 1 | 1 | pruned at root |
| dsb_social | sn10_explicit | explicit | 2 | 42 | 10 | handler | `Text/TextHandler.h:social_network.ComposeText` | 1 | 2 | beyond returned frontier |
| dsb_social | sn11_indirect | indirect | 2 | 42 | 10 | contract | `Text/TextHandler.h:social_network.ComposeText` | 1 | 1 | pruned at root |
| dsb_social | sn11_indirect | indirect | 2 | 42 | 10 | handler | `Text/TextHandler.h:social_network.ComposeText` | 1 | 2 | beyond returned frontier |
| dsb_social | sn12_explicit | explicit | 2 | 24 | 12 | handler | `contract::thrift::social_network.UserService.GetUserId` | 7 | 1 | undetermined (beam trace unavailable) |
| dsb_media | mm02_indirect | indirect | 2 | 53 | 9 | contract | `ComposeReview/ComposeReviewHandler.h:media_service._ComposeAndUpload` | 1 | 1 | pruned at root |
| dsb_media | mm02_indirect | indirect | 2 | 53 | 9 | handler | `external::num_reviews.get` | 7 | 1 | undetermined (beam trace unavailable) |
| dsb_media | mm05_indirect | indirect | 2 | 56 | 12 | contract | `MovieId/MovieIdHandler.h:media_service.UploadMovieId` | 1 | 1 | pruned at root |
| dsb_media | mm05_indirect | indirect | 2 | 56 | 12 | handler | `MovieId/MovieIdHandler.h:media_service.UploadMovieId` | 1 | 2 | beyond returned frontier |

## PPR mean gold ranks by depth (post-hoc exploratory)

Means use only found IDs. Each cell shows mean rank (found / queries).

| Scope | Depth | Budget | Contract rank | Handler rank |
| --- | --- | --- | --- | --- |
| dsb_social | 1 | 10 | 2.50 (8/8) | 2.50 (8/8) |
| dsb_social | 1 | 20 | 2.50 (8/8) | 2.50 (8/8) |
| dsb_social | 1 | 40 | 2.50 (8/8) | 2.50 (8/8) |
| dsb_social | 2 | 10 | 3.80 (20/20) | 6.14 (14/20) |
| dsb_social | 2 | 20 | 3.80 (20/20) | 7.44 (18/20) |
| dsb_social | 2 | 40 | 3.80 (20/20) | 9.10 (20/20) |
| dsb_media | 1 | 10 | 4.50 (8/8) | 4.00 (8/8) |
| dsb_media | 1 | 20 | 4.50 (8/8) | 4.00 (8/8) |
| dsb_media | 1 | 40 | 4.50 (8/8) | 4.00 (8/8) |
| dsb_media | 2 | 10 | 7.00 (2/10) | — (0/10) |
| dsb_media | 2 | 20 | 11.00 (10/10) | 14.50 (8/10) |
| dsb_media | 2 | 40 | 11.00 (10/10) | 16.00 (10/10) |
| pooled | 1 | 10 | 3.50 (16/16) | 3.25 (16/16) |
| pooled | 1 | 20 | 3.50 (16/16) | 3.25 (16/16) |
| pooled | 1 | 40 | 3.50 (16/16) | 3.25 (16/16) |
| pooled | 2 | 10 | 4.09 (22/30) | 6.14 (14/30) |
| pooled | 2 | 20 | 6.20 (30/30) | 9.62 (26/30) |
| pooled | 2 | 40 | 6.20 (30/30) | 11.40 (30/30) |

## Two-hop neighborhoods and budget coverage (post-hoc exploratory)

Counts include the start at distance zero.

| App | Nodes | Unique starts | Mean within 2 per start | Mean within 2 per query | Budget 40 / graph |
| --- | --- | --- | --- | --- | --- |
| dsb_social | 663 | 13 | 97.23 | 97.36 | 6.03% |
| dsb_media | 576 | 6 | 96.67 | 104.67 | 6.94% |

## Per-query distances and PPR ranks (post-hoc exploratory)

Pairs are contract / handler. Full-graph forward paths follow raw arrows. The labelled structure points from start to contract and from handler to contract. Its forward-only handler distance is therefore missing; following the labelled walk reverses the IMPLEMENTS hop. A dash in a rank pair means PPR did not return that gold ID.

| App | Query | Type | Undirected | Full graph forward | Gold structure forward | Gold structure walk | Depth | Start degree | Contract degree | PPR rank @10 | PPR rank @20 | PPR rank @40 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dsb_social | sn01_explicit | explicit | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 15 | 9 | 2 / — | 2 / 11 | 2 / 11 |
| dsb_social | sn01_indirect | indirect | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 15 | 9 | 2 / — | 2 / 11 | 2 / 11 |
| dsb_social | sn02_explicit | explicit | 1 / 1 | 1 / 1 | 1 / — | 1 / 2 | 1 | 16 | 10 | 3 / 2 | 3 / 2 | 3 / 2 |
| dsb_social | sn02_indirect | indirect | 1 / 1 | 1 / 1 | 1 / — | 1 / 2 | 1 | 16 | 10 | 3 / 2 | 3 / 2 | 3 / 2 |
| dsb_social | sn03_explicit | explicit | 1 / 1 | 1 / 1 | 1 / — | 1 / 2 | 1 | 16 | 9 | 2 / 3 | 2 / 3 | 2 / 3 |
| dsb_social | sn03_indirect | indirect | 1 / 1 | 1 / 1 | 1 / — | 1 / 2 | 1 | 16 | 9 | 2 / 3 | 2 / 3 | 2 / 3 |
| dsb_social | sn04_explicit | explicit | 1 / 1 | 1 / 1 | 1 / — | 1 / 2 | 1 | 16 | 10 | 2 / 3 | 2 / 3 | 2 / 3 |
| dsb_social | sn04_indirect | indirect | 1 / 1 | 1 / 1 | 1 / — | 1 / 2 | 1 | 16 | 10 | 2 / 3 | 2 / 3 | 2 / 3 |
| dsb_social | sn05_explicit | explicit | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 15 | 9 | 2 / 3 | 2 / 3 | 2 / 3 |
| dsb_social | sn05_indirect | indirect | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 15 | 9 | 2 / 3 | 2 / 3 | 2 / 3 |
| dsb_social | sn06_explicit | explicit | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 16 | 10 | 2 / 10 | 2 / 10 | 2 / 10 |
| dsb_social | sn06_indirect | indirect | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 16 | 10 | 2 / 10 | 2 / 10 | 2 / 10 |
| dsb_social | sn07_explicit | explicit | 1 / 1 | 1 / 1 | 1 / — | 1 / 2 | 1 | 17 | 9 | 3 / 2 | 3 / 2 | 3 / 2 |
| dsb_social | sn07_indirect | indirect | 1 / 1 | 1 / 1 | 1 / — | 1 / 2 | 1 | 17 | 9 | 3 / 2 | 3 / 2 | 3 / 2 |
| dsb_social | sn08_explicit | explicit | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 47 | 11 | 3 / 8 | 3 / 8 | 3 / 8 |
| dsb_social | sn08_indirect | indirect | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 47 | 11 | 3 / 8 | 3 / 8 | 3 / 8 |
| dsb_social | sn09_explicit | explicit | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 29 | 11 | 3 / 5 | 3 / 5 | 3 / 5 |
| dsb_social | sn09_indirect | indirect | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 29 | 11 | 3 / 5 | 3 / 5 | 3 / 5 |
| dsb_social | sn10_explicit | explicit | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 42 | 10 | 3 / 6 | 3 / 6 | 3 / 6 |
| dsb_social | sn10_indirect | indirect | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 42 | 10 | 3 / 6 | 3 / 6 | 3 / 6 |
| dsb_social | sn11_explicit | explicit | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 42 | 10 | 5 / 8 | 5 / 8 | 5 / 8 |
| dsb_social | sn11_indirect | indirect | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 42 | 10 | 5 / 8 | 5 / 8 | 5 / 8 |
| dsb_social | sn12_explicit | explicit | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 24 | 12 | 3 / — | 3 / 13 | 3 / 13 |
| dsb_social | sn12_indirect | indirect | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 24 | 12 | 3 / — | 3 / 13 | 3 / 13 |
| dsb_social | sn13_explicit | explicit | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 61 | 11 | 8 / 3 | 8 / 3 | 8 / 3 |
| dsb_social | sn13_indirect | indirect | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 61 | 11 | 8 / 3 | 8 / 3 | 8 / 3 |
| dsb_social | sn14_explicit | explicit | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 55 | 12 | 7 / — | 7 / — | 7 / 24 |
| dsb_social | sn14_indirect | indirect | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 55 | 12 | 7 / — | 7 / — | 7 / 24 |
| dsb_media | mm01_explicit | explicit | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 53 | 9 | — / — | 13 / — | 13 / 22 |
| dsb_media | mm01_indirect | indirect | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 53 | 9 | — / — | 13 / — | 13 / 22 |
| dsb_media | mm02_explicit | explicit | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 53 | 9 | — / — | 12 / 20 | 12 / 20 |
| dsb_media | mm02_indirect | indirect | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 53 | 9 | — / — | 12 / 20 | 12 / 20 |
| dsb_media | mm03_explicit | explicit | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 53 | 10 | — / — | 11 / 14 | 11 / 14 |
| dsb_media | mm03_indirect | indirect | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 53 | 10 | — / — | 11 / 14 | 11 / 14 |
| dsb_media | mm04_explicit | explicit | 1 / 1 | 1 / 2 | 1 / — | 1 / 2 | 1 | 56 | 10 | 9 / 4 | 9 / 4 | 9 / 4 |
| dsb_media | mm04_indirect | indirect | 1 / 1 | 1 / 2 | 1 / — | 1 / 2 | 1 | 56 | 10 | 9 / 4 | 9 / 4 | 9 / 4 |
| dsb_media | mm05_explicit | explicit | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 56 | 12 | — / — | 12 / 13 | 12 / 13 |
| dsb_media | mm05_indirect | indirect | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 56 | 12 | — / — | 12 / 13 | 12 / 13 |
| dsb_media | mm06_explicit | explicit | 1 / 1 | 1 / 2 | 1 / — | 1 / 2 | 1 | 30 | 12 | 2 / 4 | 2 / 4 | 2 / 4 |
| dsb_media | mm06_indirect | indirect | 1 / 1 | 1 / 2 | 1 / — | 1 / 2 | 1 | 30 | 12 | 2 / 4 | 2 / 4 | 2 / 4 |
| dsb_media | mm07_explicit | explicit | 1 / 1 | 1 / 2 | 1 / — | 1 / 2 | 1 | 20 | 12 | 2 / 4 | 2 / 4 | 2 / 4 |
| dsb_media | mm07_indirect | indirect | 1 / 1 | 1 / 2 | 1 / — | 1 / 2 | 1 | 20 | 12 | 2 / 4 | 2 / 4 | 2 / 4 |
| dsb_media | mm08_explicit | explicit | 1 / 1 | 1 / 2 | 1 / — | 1 / 2 | 1 | 32 | 10 | 5 / 4 | 5 / 4 | 5 / 4 |
| dsb_media | mm08_indirect | indirect | 1 / 1 | 1 / 2 | 1 / — | 1 / 2 | 1 | 32 | 10 | 5 / 4 | 5 / 4 | 5 / 4 |
| dsb_media | mm09_explicit | explicit | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 45 | 12 | 7 / — | 7 / 11 | 7 / 11 |
| dsb_media | mm09_indirect | indirect | 1 / 2 | 1 / 2 | 1 / — | 1 / 2 | 2 | 45 | 12 | 7 / — | 7 / 11 | 7 / 11 |
