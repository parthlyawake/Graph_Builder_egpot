# Suite 2 exploratory preregistration

Status: EXPLORATORY. No confirmatory contrasts and no hypothesis tests.

Why this scope: a source-only audit before any retrieval found that the
builders could not represent most harder links. 0/12 DataHub chains had all
hops in v3; DataHub lookalike twins lay beyond 80 nodes from the primary shared neighbor
or any exclusive caller in 11/12 cases, and from any recorded shared neighbor
or exclusive caller in 7/12 cases; plain BFS reaches 80% of DataHub blast-radius consumers
within 9-15 nodes. Train-Ticket lookalikes (1/6 within 80), Train-Ticket and
Boutique chains and blast radius, and Boutique overall (DEV overlap) are
excluded. This audit is itself reported as a limitation.

Links: 19, from the manifest at commit 30a82fe3: 10 DataHub blast radius,
5 DSB lookalikes, 4 DSB chains. Starts for lookalikes and chains were chosen
from graph structure after inspection, before any method ran. They were not
chosen by method outcomes. Links A06/B03 and A07/B01 share nodes.

Methods: the roster and configurations frozen at tag egpot-datahub-locked-v1.
No tuning, no new methods. Stochastic variants use the same seed handling as
that run and are reported per seed.

Queries: two per link (explicit, indirect), fixed in bench/suite2_queries.json.
Budgets include the start node.

Outcomes:
- Blast radius: recall of the representable gold set; hit = recall >= 0.8.
  Precision reported descriptively only (it is capped by budget/gold size).
  Report the recall ceiling per contract (C06 4/9, C07 5/8, C08 8/9).
- Lookalike: C retrieved; D retrieved; clean = C retrieved and L not;
  confused = L retrieved and C not.
- Chain: hit = both B and C retrieved; partial credit reported separately.

Reporting: a per-link table; hit counts per method, budget, wording and repo.
DataHub and DSB are never pooled. No inferential statistics.

Predictions (written before running):
 P1 plain BFS reaches the blast-radius ceiling at budgets 20 and 40.
 P2 plain BFS is never "clean" on lookalikes, because the decoy sits within 80
    nodes of the start in all 5 pairs.
 P3 plain BFS scores 0 on DSB-A08 at every budget (it needs 129 nodes).

Disclosure: any harness change after the tag is logged as a deviation.
