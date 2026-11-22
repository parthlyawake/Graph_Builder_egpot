# Suite 2 exploratory summary

All outcomes come from the frozen Suite 2 analyzer on the 12,882 locked records. The tables use seed 0 unless marked. Best seeded method is selected per repository and link type by the seed-0 hit total over all six budget/wording cells, with ties broken by method name. Seed ranges are the observed minimum and maximum over seeds 0–5. Both no-Pareto widths are included.

## Methods

| Code | Frozen method |
| --- | --- |
| W4 | egpot_full_w4 |
| W12 | egpot_full_w12 |
| BFS | bfs |
| PPR | ppr |
| Vec | vector_topk |
| Scalar | scalar_beam |
| MCTS | mcts_standard |
| NP4 | egpot_no_pareto_w4 |
| NP12 | egpot_no_pareto_w12 |

## Best seeded methods

| Repository | Type | Best method | Seed 0 total | Seeds 0–5 total range |
| --- | --- | --- | --- | --- |
| DataHub | blast_radius | mcts_standard | 57 | 55–57 |
| DSB Social | lookalike | egpot_full_tiebreak_w4 | 9 | 9–12 |
| DSB Media | lookalike | egpot_full_mcts_w4 | 18 | 14–18 |
| DSB Social | chain | egpot_full_tiebreak_w12 | 6 | 6–6 |
| DSB Media | chain | egpot_full_tiebreak_w4 | 17 | 12–18 |

## Hits — DataHub blast radius (out of 10 per cell)

| Method | 10 E | 10 I | 20 E | 20 I | 40 E | 40 I |
| --- | --- | --- | --- | --- | --- | --- |
| W4 | 0 | 0 | 1 | 0 | 1 | 0 |
| W12 | 8 | 8 | 10 | 8 | 10 | 8 |
| BFS | 7 | 7 | 10 | 10 | 10 | 10 |
| PPR | 8 | 8 | 10 | 10 | 10 | 10 |
| Vec | 0 | 0 | 0 | 0 | 0 | 0 |
| Scalar | 0 | 0 | 0 | 0 | 1 | 0 |
| MCTS | 9 | 8 | 10 | 10 | 10 | 10 |
| NP4 | 0 | 0 | 0 | 0 | 0 | 0 |
| NP12 | 8 | 8 | 10 | 8 | 10 | 8 |
| Best mcts_standard | 9 [8–9] | 8 [7–8] | 10 [10–10] | 10 [10–10] | 10 [10–10] | 10 [10–10] |

## Hits — DSB Social lookalike (out of 2 per cell)

| Method | 20 E | 20 I | 40 E | 40 I | 80 E | 80 I |
| --- | --- | --- | --- | --- | --- | --- |
| W4 | 2 | 0 | 2 | 0 | 2 | 0 |
| W12 | 1 | 0 | 1 | 1 | 2 | 1 |
| BFS | 0 | 0 | 1 | 1 | 2 | 2 |
| PPR | 0 | 0 | 0 | 0 | 1 | 1 |
| Vec | 2 | 0 | 2 | 1 | 2 | 2 |
| Scalar | 2 | 0 | 2 | 0 | 2 | 0 |
| MCTS | 0 | 0 | 1 | 1 | 1 | 1 |
| NP4 | 2 | 1 | 2 | 1 | 2 | 1 |
| NP12 | 1 | 1 | 2 | 1 | 2 | 1 |
| Best egpot_full_tiebreak_w4 | 2 [2–2] | 1 [1–2] | 2 [2–2] | 1 [1–2] | 2 [2–2] | 1 [1–2] |

## Hits — DSB Media lookalike (out of 3 per cell)

| Method | 20 E | 20 I | 40 E | 40 I | 80 E | 80 I |
| --- | --- | --- | --- | --- | --- | --- |
| W4 | 3 | 3 | 3 | 3 | 3 | 3 |
| W12 | 2 | 1 | 3 | 2 | 3 | 2 |
| BFS | 0 | 0 | 0 | 0 | 3 | 3 |
| PPR | 2 | 2 | 3 | 3 | 3 | 3 |
| Vec | 3 | 0 | 3 | 1 | 3 | 3 |
| Scalar | 3 | 0 | 3 | 0 | 3 | 0 |
| MCTS | 0 | 0 | 1 | 1 | 2 | 3 |
| NP4 | 3 | 3 | 3 | 3 | 3 | 3 |
| NP12 | 2 | 2 | 3 | 3 | 3 | 3 |
| Best egpot_full_mcts_w4 | 3 [3–3] | 3 [1–3] | 3 [3–3] | 3 [1–3] | 3 [3–3] | 3 [3–3] |

## Hits — DSB Social chain (out of 1 per cell)

| Method | 20 E | 20 I | 40 E | 40 I | 80 E | 80 I |
| --- | --- | --- | --- | --- | --- | --- |
| W4 | 1 | 0 | 1 | 0 | 1 | 0 |
| W12 | 1 | 1 | 1 | 1 | 1 | 1 |
| BFS | 0 | 0 | 0 | 0 | 1 | 1 |
| PPR | 0 | 0 | 1 | 1 | 1 | 1 |
| Vec | 1 | 0 | 1 | 0 | 1 | 0 |
| Scalar | 0 | 0 | 0 | 0 | 0 | 0 |
| MCTS | 0 | 0 | 0 | 0 | 1 | 1 |
| NP4 | 1 | 0 | 1 | 0 | 1 | 0 |
| NP12 | 1 | 1 | 1 | 1 | 1 | 1 |
| Best egpot_full_tiebreak_w12 | 1 [1–1] | 1 [1–1] | 1 [1–1] | 1 [1–1] | 1 [1–1] | 1 [1–1] |

## Hits — DSB Media chain (out of 3 per cell)

| Method | 20 E | 20 I | 40 E | 40 I | 80 E | 80 I |
| --- | --- | --- | --- | --- | --- | --- |
| W4 | 2 | 1 | 3 | 1 | 3 | 2 |
| W12 | 3 | 1 | 3 | 3 | 3 | 3 |
| BFS | 0 | 0 | 0 | 0 | 2 | 2 |
| PPR | 1 | 1 | 2 | 2 | 3 | 3 |
| Vec | 2 | 0 | 3 | 1 | 3 | 3 |
| Scalar | 2 | 0 | 2 | 0 | 2 | 0 |
| MCTS | 0 | 0 | 0 | 0 | 2 | 3 |
| NP4 | 2 | 3 | 2 | 3 | 2 | 3 |
| NP12 | 3 | 2 | 3 | 2 | 3 | 2 |
| Best egpot_full_tiebreak_w4 | 3 [2–3] | 2 [2–3] | 3 [2–3] | 3 [2–3] | 3 [2–3] | 3 [2–3] |

Blast radius cells show mean recall / contracts at or above 0.8 / mean precision. The mean is over the ten contracts for each wording.

## Blast radius detail

| Method | 10 E | 10 I | 20 E | 20 I | 40 E | 40 I |
| --- | --- | --- | --- | --- | --- | --- |
| W4 | 0.2500 / 0 / 0.1300 | 0.3775 / 0 / 0.1900 | 0.3600 / 1 / 0.1017 | 0.3775 / 0 / 0.1117 | 0.3800 / 1 / 0.0678 | 0.3775 / 0 / 0.0797 |
| W12 | 0.9000 / 8 / 0.4700 | 0.8958 / 8 / 0.4700 | 0.9875 / 10 / 0.2717 | 0.9417 / 8 / 0.2500 | 0.9875 / 10 / 0.1803 | 0.9417 / 8 / 0.1253 |
| BFS | 0.8050 / 7 / 0.4200 | 0.8050 / 7 / 0.4200 | 1.0000 / 10 / 0.2700 | 1.0000 / 10 / 0.2700 | 1.0000 / 10 / 0.1350 | 1.0000 / 10 / 0.1350 |
| PPR | 0.9000 / 8 / 0.4700 | 0.9000 / 8 / 0.4700 | 1.0000 / 10 / 0.2700 | 1.0000 / 10 / 0.2700 | 1.0000 / 10 / 0.1350 | 1.0000 / 10 / 0.1350 |
| Vec | 0.0200 / 0 / 0.0100 | 0.0000 / 0 / 0.0000 | 0.0775 / 0 / 0.0200 | 0.0000 / 0 / 0.0000 | 0.0975 / 0 / 0.0125 | 0.0000 / 0 / 0.0000 |
| Scalar | 0.2167 / 0 / 0.1200 | 0.3158 / 0 / 0.1700 | 0.2292 / 0 / 0.0661 | 0.3158 / 0 / 0.1235 | 0.2892 / 1 / 0.0511 | 0.3158 / 0 / 0.1092 |
| MCTS | 0.9292 / 9 / 0.4900 | 0.8508 / 8 / 0.4400 | 1.0000 / 10 / 0.2700 | 1.0000 / 10 / 0.2700 | 1.0000 / 10 / 0.1350 | 1.0000 / 10 / 0.1350 |
| NP4 | 0.3658 / 0 / 0.2000 | 0.4175 / 0 / 0.2200 | 0.3992 / 0 / 0.1180 | 0.4175 / 0 / 0.1350 | 0.3992 / 0 / 0.0950 | 0.4175 / 0 / 0.1036 |
| NP12 | 0.9167 / 8 / 0.4800 | 0.8958 / 8 / 0.4700 | 0.9875 / 10 / 0.2769 | 0.9417 / 8 / 0.2607 | 0.9875 / 10 / 0.2154 | 0.9417 / 8 / 0.1482 |

## Blast-radius ceilings

| Link | Representable / source consumers |
| --- | --- |
| C01 | 5/5 |
| C02 | 5/5 |
| C03 | 5/5 |
| C04 | 6/6 |
| C05 | 6/6 |
| C06 | 4/9 |
| C07 | 5/8 |
| C08 | 8/9 |
| C09 | 6/6 |
| C10 | 4/4 |

Lookalike cells show clean / confused / both / neither. Chain cells show both / partial / neither. Each column uses one wording. DSB apps remain separate in the hit tables above.

## Lookalike outcomes — DSB

| Method | 20 E | 20 I | 40 E | 40 I | 80 E | 80 I |
| --- | --- | --- | --- | --- | --- | --- |
| W4 | 1/0/4/0 | 1/0/2/2 | 0/0/5/0 | 1/0/2/2 | 0/0/5/0 | 1/0/2/2 |
| W12 | 2/0/1/2 | 0/0/1/4 | 2/0/2/1 | 0/0/3/2 | 2/0/3/0 | 0/0/3/2 |
| BFS | 0/0/0/5 | 0/0/0/5 | 0/0/1/4 | 0/0/1/4 | 0/0/5/0 | 0/0/5/0 |
| PPR | 1/0/1/3 | 1/0/1/3 | 1/0/2/2 | 1/0/2/2 | 1/0/3/1 | 1/0/3/1 |
| Vec | 1/0/4/0 | 0/0/0/5 | 1/0/4/0 | 1/1/1/2 | 0/0/5/0 | 1/0/4/0 |
| Scalar | 3/0/2/0 | 0/2/0/3 | 2/0/3/0 | 0/2/0/3 | 2/0/3/0 | 0/2/0/3 |
| MCTS | 0/0/0/5 | 0/0/0/5 | 1/0/1/3 | 1/0/1/3 | 0/0/3/2 | 1/1/3/0 |
| NP4 | 1/0/4/0 | 0/0/4/1 | 1/0/4/0 | 0/0/4/1 | 1/0/4/0 | 0/0/4/1 |
| NP12 | 1/0/2/2 | 1/0/2/2 | 3/0/2/0 | 1/0/3/1 | 1/0/4/0 | 1/0/3/1 |
| egpot_full_tiebreak_w4 | 1/0/4/0 | 2/1/1/1 | 0/0/5/0 | 1/1/3/0 | 0/0/5/0 | 1/1/3/0 |
| egpot_full_mcts_w4 | 1/0/4/0 | 1/0/2/2 | 0/0/5/0 | 1/0/2/2 | 0/0/5/0 | 1/0/3/1 |

## Chain outcomes — DSB

| Method | 20 E | 20 I | 40 E | 40 I | 80 E | 80 I |
| --- | --- | --- | --- | --- | --- | --- |
| W4 | 3/1/0 | 1/3/0 | 4/0/0 | 1/3/0 | 4/0/0 | 2/2/0 |
| W12 | 4/0/0 | 2/1/1 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 |
| BFS | 0/2/2 | 0/2/2 | 0/2/2 | 0/2/2 | 3/1/0 | 3/1/0 |
| PPR | 1/3/0 | 1/3/0 | 3/1/0 | 3/1/0 | 4/0/0 | 4/0/0 |
| Vec | 3/1/0 | 0/2/2 | 4/0/0 | 1/3/0 | 4/0/0 | 3/1/0 |
| Scalar | 2/2/0 | 0/3/1 | 2/2/0 | 0/3/1 | 2/2/0 | 0/3/1 |
| MCTS | 0/2/2 | 0/2/2 | 0/3/1 | 0/2/2 | 3/1/0 | 4/0/0 |
| NP4 | 3/1/0 | 3/1/0 | 3/1/0 | 3/1/0 | 3/1/0 | 3/1/0 |
| NP12 | 4/0/0 | 3/1/0 | 4/0/0 | 3/1/0 | 4/0/0 | 3/1/0 |
| egpot_full_tiebreak_w12 | 4/0/0 | 2/2/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 |
| egpot_full_tiebreak_w4 | 4/0/0 | 2/2/0 | 4/0/0 | 3/1/0 | 4/0/0 | 3/1/0 |

Per-link cells list the three budgets in the table heading. Each budget shows explicit/indirect. Identical wordings share one entry. A leading + is a hit and − is a miss. Letters identify returned gold nodes in the gold-ID key. The dash means no gold node returned. Best uses seed 0.

## Per-link outcomes — DataHub blast radius (10/20/40)

| Link | W4 | W12 | BFS | PPR | Vec | Scalar | MCTS | NP4 | NP12 | Best |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C01 | −D/−AB · −D/−AB · −D/−AB | +ABCDE · +ABCDE · +ABCDE | +ABCDE · +ABCDE · +ABCDE | +ABCDE · +ABCDE · +ABCDE | −– · −D/−– · −D/−– | −D/−A · −D/−A · +BCDE/−A | +ABCDE · +ABCDE · +ABCDE | −D/−AB · −D/−AB · −D/−AB | +ABCDE · +ABCDE · +ABCDE | +ABCDE · +ABCDE · +ABCDE |
| C02 | −D/−E · −D/−E · −DE/−E | +ABCDE · +ABCDE · +ABCDE | +ABCDE · +ABCDE · +ABCDE | +ABCDE · +ABCDE · +ABCDE | −– · −– · −D/−– | −D/−E · −D/−E · −D/−E | +ABCDE · +ABCDE · +ABCDE | −D/−AE · −D/−AE · −D/−AE | +ABCDE · +ABCDE · +ABCDE | +ABCDE · +ABCDE · +ABCDE |
| C03 | −A/−E · −AE/−E · −AE/−E | +ABCDE · +ABCDE · +ABCDE | +ABCDE · +ABCDE · +ABCDE | +ABCDE · +ABCDE · +ABCDE | −– · −– · −– | −A/−E · −A/−E · −A/−E | +ABCDE · +ABCDE · +ABCDE | −AE · −AE · −AE | +ABCDE · +ABCDE · +ABCDE | +ABCDE · +ABCDE · +ABCDE |
| C04 | −F/−ABCE · −F/−ABCE · −F/−ABCE | +ABCDEF · +ABCDEF · +ABCDEF | +ABCDE · +ABCDEF · +ABCDEF | +ABCDEF · +ABCDEF · +ABCDEF | −– · −– · −– | −F/−ABCE · −F/−ABCE · −F/−ABCE | +ABCDEF · +ABCDEF · +ABCDEF | −F/−ABCE · −F/−ABCE · −F/−ABCE | +ABCDEF · +ABCDEF · +ABCDEF | +ABCDEF · +ABCDEF · +ABCDEF |
| C05 | −B/−A · −B/−A · −B/−A | +ABCDE/+ABCDEF · +ABCDEF · +ABCDEF | +ABCDE · +ABCDEF · +ABCDEF | +ABCDEF · +ABCDEF · +ABCDEF | −– · −– · −– | −– · −– · −– | +ABCEF · +ABCDEF · +ABCDEF | −BE/−A · −BE/−A · −BE/−A | +ABCDEF · +ABCDEF · +ABCDEF | +ABCEF · +ABCDEF · +ABCDEF |
| C06 | −CD/−ABD · −CD/−ABD · −CD/−ABD | +ABCD · +ABCD · +ABCD | +ABCD · +ABCD · +ABCD | +ABCD · +ABCD · +ABCD | −– · −D/−– · −D/−– | −CD/−ABD · −CD/−ABD · −CD/−ABD | +ABCD · +ABCD · +ABCD | −CD/−ABD · −CD/−ABD · −CD/−ABD | +ABCD · +ABCD · +ABCD | +ABCD · +ABCD · +ABCD |
| C07 | −CD/−ACD · +ABCD/−ACD · +ABCD/−ACD | +ABCDE · +ABCDE · +ABCDE | +ABCD · +ABCDE · +ABCDE | +ABCDE · +ABCDE · +ABCDE | −C/−– · −C/−– · −C/−– | −CD/−ACD · −CD/−ACD · −CD/−ACD | +ABCDE/+ACDE · +ABCDE · +ABCDE | −CD/−ACD · −CD/−ACD · −CD/−ACD | +ABCDE · +ABCDE · +ABCDE | +ABCDE/+ACDE · +ABCDE · +ABCDE |
| C08 | −GH/−C · −GH/−C · −GH/−C | −DFGH/−ABCDE · +ABDEFGH/−ABCDEF · +ABDEFGH/−ABCDEF | −ABCD · +ABCDEFGH · +ABCDEFGH | −ABCE · +ABCDEFGH · +ABCDEFGH | −– · −H/−– · −H/−– | −DFGH/−C · −DEFGH/−C · −DEFGH/−C | −ABFGH/−CEH · +ABCDEFGH · +ABCDEFGH | −DEFGH/−C · −DEFGH/−C · −DEFGH/−C | −DFGH/−ABCDE · +ABDEFGH/−ABCDEF · +ABDEFGH/−ABCDEF | −ABFGH/−CEH · +ABCDEFGH · +ABCDEFGH |
| C09 | −E · −BCDE/−E · −BCDE/−E | −BCDE/−AE · +ABCDEF/−ABCE · +ABCDEF/−ABCE | −AB · +ABCDEF · +ABCDEF | −BEF · +ABCDEF · +ABCDEF | −– · −– · −– | −–/−E · −–/−E · −–/−E | +ABDEF/−CDE · +ABCDEF · +ABCDEF | −CE/−E · −BCDE/−E · −BCDE/−E | −BCDE/−AE · +ABCDEF/−ABCE · +ABCDEF/−ABCE | +ABDEF/−CDE · +ABCDEF · +ABCDEF |
| C10 | −A/−AB · −A/−AB · −A/−AB | +ABCD · +ABCD · +ABCD | −ABC · +ABCD · +ABCD | +ABCD · +ABCD · +ABCD | −– · −– · −– | −–/−B · −–/−B · −–/−B | +ABCD · +ABCD · +ABCD | −AB · −AB · −AB | +ABCD · +ABCD · +ABCD | +ABCD · +ABCD · +ABCD |

## Per-link outcomes — DSB Social lookalike (20/40/80)

| Link | W4 | W12 | BFS | PPR | Vec | Scalar | MCTS | NP4 | NP12 | Best |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DSB-B05 | +A/−– · +A/−– · +A/−– | +A/−– · +A · +A | −– · +A · +A | −– · −– · +A | +A/−– · +A · +A | +A/−– · +A/−– · +A/−– | −– · +A · +A | +A · +A · +A | +A · +A · +A | +A · +A · +A |
| DSB-B07 | +A/−– · +A/−– · +A/−– | −– · −– · +A/−– | −– · −– · +A | −– · −– · −– | +A/−– · +A/−– · +A | +A/−– · +A/−– · +A/−– | −– · −– · −– | +A/−– · +A/−– · +A/−– | −– · +A/−– · +A/−– | +A/−– · +A/−– · +A/−– |

## Per-link outcomes — DSB Media lookalike (20/40/80)

| Link | W4 | W12 | BFS | PPR | Vec | Scalar | MCTS | NP4 | NP12 | Best |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DSB-B01 | +A · +A · +A | +A · +A · +A | −– · −– · +A | +A · +A · +A | +A/−– · +A/−– · +A | +A/−– · +A/−– · +A/−– | −– · −– · +A | +A · +A · +A | +A · +A · +A | +A · +A · +A |
| DSB-B02 | +A · +A · +A | −– · +A · +A | −– · −– · +A | −– · +A · +A | +A/−– · +A · +A | +A/−– · +A/−– · +A/−– | −– · −–/+A · −–/+A | +A · +A · +A | −– · +A · +A | +A · +A · +A |
| DSB-B03 | +A · +A · +A | +A/−– · +A/−– · +A/−– | −– · −– · +A | +A · +A · +A | +A/−– · +A/−– · +A | +A/−– · +A/−– · +A/−– | −– · +A/−– · +A | +A · +A · +A | +A · +A · +A | +A · +A · +A |

## Per-link outcomes — DSB Social chain (20/40/80)

| Link | W4 | W12 | BFS | PPR | Vec | Scalar | MCTS | NP4 | NP12 | Best |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DSB-A05 | +AB/−A · +AB/−A · +AB/−A | +AB · +AB · +AB | −A · −A · +AB | −A · +AB · +AB | +AB/−– · +AB/−B · +AB/−B | −A · −A · −A | −A · −A · +AB | +AB/−A · +AB/−A · +AB/−A | +AB · +AB · +AB | +AB · +AB · +AB |

## Per-link outcomes — DSB Media chain (20/40/80)

| Link | W4 | W12 | BFS | PPR | Vec | Scalar | MCTS | NP4 | NP12 | Best |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DSB-A06 | +AB/−B · +AB/−B · +AB | +AB/−– · +AB · +AB | −– · −– · +AB | +AB · +AB · +AB | +AB/−B · +AB/−B · +AB | +AB/−– · +AB/−– · +AB/−– | −– · −A/−– · +AB | +AB · +AB · +AB | +AB · +AB · +AB | +AB · +AB · +AB |
| DSB-A07 | +AB · +AB · +AB | +AB · +AB · +AB | −– · −– · +AB | −A · +AB · +AB | +AB/−– · +AB/−B · +AB | −A/−B · −A/−B · −A/−B | −– · −– · +AB | −A/+AB · −A/+AB · −A/+AB | +AB · +AB · +AB | +AB/−A · +AB · +AB |
| DSB-A08 | −B · +AB/−B · +AB/−B | +AB/−A · +AB · +AB | −A · −A · −A | −A · −A · +AB | −B · +AB · +AB | +AB/−A · +AB/−A · +AB/−A | −A · −A · −A/+AB | +AB · +AB · +AB | +AB/−A · +AB/−A · +AB/−A | +AB · +AB · +AB |

## Gold-ID key

| Link | Letter → gold node ID |
| --- | --- |
| C01 | A → `web/app/glossaryV2/BusinessGlossaryPage.tsx:BusinessGlossaryPage`<br>B → `web/app/glossaryV2/GlossaryBrowser/GlossaryBrowser.tsx:GlossaryBrowserInner`<br>C → `web/app/glossaryV2/GlossarySidebar.tsx:GlossarySidebarInner`<br>D → `web/app/homeV3/modules/hierarchyViewModule/components/glossary/hooks/useRootGlossaryNodes.ts:useRootGlossaryNodes`<br>E → `web/app/sharedV2/tags/useGlossaryTreeEntities.ts:useGlossaryTreeEntities` |
| C02 | A → `web/app/glossaryV2/BusinessGlossaryPage.tsx:BusinessGlossaryPage`<br>B → `web/app/glossaryV2/GlossaryBrowser/GlossaryBrowser.tsx:GlossaryBrowserInner`<br>C → `web/app/glossaryV2/GlossarySidebar.tsx:GlossarySidebarInner`<br>D → `web/app/homeV3/modules/hierarchyViewModule/components/glossary/hooks/useRootGlossaryTerms.ts:useRootGlossaryTerms`<br>E → `web/app/sharedV2/tags/useGlossaryTreeEntities.ts:useGlossaryTreeEntities` |
| C03 | A → `web/app/entityV2/view/ViewsList.tsx:ViewsList`<br>B → `web/app/entityV2/view/select/ViewSelectContext.tsx:ViewSelectContextProvider`<br>C → `web/app/homeV2/introduce/IntroduceYourselfMainContent.tsx:IntroduceYourselfMainContent`<br>D → `web/app/identity/serviceAccount/ServiceAccountList.hooks.tsx:useServiceAccountViewOptions`<br>E → `web/app/search/view/select/ViewSelect.tsx:ViewSelect` |
| C04 | A → `web/app/homeV2/action/announcement/useGetUnseenAnnouncements.tsx:useGetUnseenAnnouncements`<br>B → `web/app/homeV2/content/tabs/announcements/useGetAnnouncements.tsx:useGetAnnouncements`<br>C → `web/app/homeV2/content/tabs/useGetVisibleTabs.tsx:useGetAnnouncementsExists`<br>D → `web/app/homeV2/reference/sections/pinned/useGetPinnedLinks.tsx:useGetPinnedLinks`<br>E → `web/app/homeV3/announcements/useGetAnnouncementsForUser.ts:useGetAnnouncementsForUser`<br>F → `web/app/settingsV2/posts/PostsList.tsx:PostList` |
| C05 | A → `web/app/homeV2/introduce/IntroduceYourselfMainContent.tsx:IntroduceYourselfMainContent`<br>B → `web/app/homeV2/useHomeRecommendations.ts:useHomeRecommendations`<br>C → `web/app/search/SearchBar.tsx:SearchBar`<br>D → `web/app/searchV2/SearchBar.tsx:SearchBar`<br>E → `web/app/searchV2/searchBarV2/hooks/useRecentlySearchedQueries.ts:useRecentlySearchedQueries`<br>F → `web/app/searchV2/searchBarV2/hooks/useRecentlyViewedEntities.ts:useRecentlyViewedEntities` |
| C06 | A → `web/app/document/hooks/useDocumentGroupDocuments.ts:useDocumentGroupDocuments`<br>B → `web/app/document/hooks/useDocumentGroupRoots.ts:useDocumentGroupRoots`<br>C → `web/app/document/hooks/useDocumentSidebarSearch.ts:useDocumentSidebarSearch`<br>D → `web/app/document/hooks/useSearchDocuments.ts:useSearchDocuments` |
| C07 | A → `web/app/entityV2/dataProduct/AssetsSections.tsx:AssetsSection`<br>B → `web/app/entityV2/dataProduct/OutputPortsSection.tsx:OutputPortsSection`<br>C → `web/app/entityV2/dataProduct/generateUseListDataProductAssets.ts:generateUseListDataProductAssets`<br>D → `web/app/entityV2/summary/modules/assets/useGetDataProductAssets.ts:useGetDataProductAssets`<br>E → `web/app/entityV2/summary/modules/outputPorts/useGetOutputPorts.ts:useGetOutputPorts` |
| C08 | A → `web/app/businessAttribute/utils/useDescriptionRenderer.tsx:useDescriptionRenderer`<br>B → `web/app/entityV2/mlFeatureTable/profile/features/TableOfMlFeatures.tsx:TableOfMlFeatures`<br>C → `web/app/entityV2/shared/EntityDropdown/EditGlossaryEntityModal.tsx:EditGlossaryEntityModal.onSave`<br>D → `web/app/entityV2/shared/tabs/Dataset/Schema/components/SchemaFieldDrawer/FieldDescription.tsx:FieldDescription`<br>E → `web/app/entityV2/shared/tabs/Dataset/Schema/utils/useDescriptionRenderer.tsx:useDescriptionRenderer`<br>F → `web/app/entityV2/shared/tabs/Documentation/components/DescriptionEditor.tsx:DescriptionEditor.updateDescription`<br>G → `web/app/entityV2/summary/documentation/useDescriptionUtils.ts:useDescriptionUtils.updateDescription`<br>H → `web/app/sharedV2/TagStyleEntity.tsx:TagStyleEntity.updateDescriptionValue` |
| C09 | A → `web/app/entityV2/shared/components/styled/search/action/DataProductsDropdown.tsx:DataProductsDropdown.batchUnsetDataProducts`<br>B → `web/app/entityV2/shared/containers/profile/sidebar/DataProduct/DataProductSection.tsx:DataProductSection.removeDataProduct`<br>C → `web/app/entityV2/shared/containers/profile/sidebar/DataProduct/SetDataProductModal.tsx:SetDataProductModal.onOk`<br>D → `web/app/entityV2/shared/entity/EntityActions.tsx:EntityActions.batchSetDataProduct`<br>E → `web/app/entityV2/summary/modules/assets/AddAssetsModal.tsx:AddAssetsModal.batchSetDataProduct`<br>F → `web/app/previewV2/utils.ts:useRemoveDataProductAssets.handleDataProduct` |
| C10 | A → `web/app/entityV2/shared/EntityDropdown/UpdateDeprecationModal.tsx:UpdateDeprecationModal.handleSubmit`<br>B → `web/app/entityV2/shared/EntityDropdown/useUndeprecateResource.ts:useUndeprecateResource`<br>C → `web/app/entityV2/shared/components/styled/search/action/DeprecationDropdown.tsx:DeprecationDropdown.batchUndeprecate`<br>D → `web/app/tags/TagsTableColumns.tsx:handleUndeprecate` |
| DSB-A05 | A → `Text/TextHandler.h:social_network.ComposeText`<br>B → `UrlShorten/UrlShortenHandler.h:social_network.ComposeUrls` |
| DSB-A06 | A → `MovieReview/MovieReviewHandler.h:media_service.ReadMovieReviews`<br>B → `ReviewStorage/ReviewStorageHandler.h:media_service.ReadReviews` |
| DSB-A07 | A → `Rating/RatingHandler.h:media_service.UploadRating`<br>B → `ComposeReview/ComposeReviewHandler.h:media_service.UploadRating` |
| DSB-A08 | A → `ComposeReview/ComposeReviewHandler.h:media_service._ComposeAndUpload`<br>B → `ReviewStorage/ReviewStorageHandler.h:media_service.StoreReview` |
| DSB-B01 | A → `Rating/RatingHandler.h:media_service.UploadRating` |
| DSB-B02 | A → `MovieId/MovieIdHandler.h:media_service.UploadMovieId` |
| DSB-B03 | A → `MovieReview/MovieReviewHandler.h:media_service.ReadMovieReviews` |
| DSB-B05 | A → `ComposePost/ComposePostHandler.h:social_network._UploadUserTimelineHelper` |
| DSB-B07 | A → `SocialGraph/SocialGraphHandler.h:social_network.FollowWithUsername` |

## Preregistered predictions

| Prediction | Verdict | Counts in budget order, explicit / indirect |
| --- | --- | --- |
| P1 BFS reaches blast-radius ceiling at 20 and 40 | Held | 20: 10/10 and 10/10. 40: 10/10 and 10/10. |
| P2 BFS is never clean on lookalikes | Held | 20: 0/5 and 0/5. 40: 0/5 and 0/5. 80: 0/5 and 0/5. |
| P3 BFS scores 0 on DSB-A08 at every budget | Held | 20: 0/1 and 0/1. 40: 0/1 and 0/1. 80: 0/1 and 0/1. |
