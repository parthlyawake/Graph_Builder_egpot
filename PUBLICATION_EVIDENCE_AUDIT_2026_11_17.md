# GRAFT-CKG publication validation ledger — P1 through P4

**Date:** 2026-11-17 (Asia/Kolkata). **Status:** research evidence increment, **NOT** independently publication-certified.  
**Authoritative code baseline:** `Vikas-Personal-Research-Org/Graph_Builder@a5dfc871ffbb74f7c3a752fe15eaa48e931edaee` (branch `krishna`).  
**Study branch:** `research-publication-evidence-p1-p4-2026-11-17`. Do not conflate this research branch with a result already merged into `krishna`.

## Falsifiability rules

- `source_inspected_pending_independent_human_review` **never** means independently reviewed or human adjudicated. No second human annotator exists in these files. Source markers establish that a phrase is present, **not** that every annotation is unbiased or true.
- 100% accuracy in a small selected closed scope is **not** 100% overall construction accuracy. Do not extrapolate to the rest of a repository or another commit.
- A legitimate Build-stage artifact/telemetry adapter is **not** an authenticated external deployment. Self-signed local CI fixtures demonstrate implementation behavior, **not** real CI provenance.
- All reported metric names must include evaluated object, closed source scope, source revision, protocol and review status. Undefined P/R should remain null.
- Never infer real downstream agent success, prompt redundancy or tool-call reduction from source graph retrieval.
- A Git object existing locally does **not** prove signed origin, CI attestation, build artifact ownership or deployment authorization.

## P1 — Construction accuracy (partially completed, human sign-off open)

Independent *tooling* exists in `bench/verify_graph_accuracy.py` and `bench/paper_metrics.py`. Added a source-reviewed Online Boutique label set `bench/labels/online_boutique_source_review_scopes_v1.json`, pinned at `GoogleCloudPlatform/microservices-demo@38e7348eb289eb5b87c0c6e8cb19ced0449dc389`.

| Restricted annotated scope | Source-inspected nodes | Labeled exact edges | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Online Boutique: 10 selected frontend Go gRPC consumers, 2 shipping Go producers, 2 Python gRPC consumers | 14/14 recovered | 14 | 14 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| DeathStarBench: 4 selected `service -> DEFINES_RPC` Thrift declaration scopes | 8/8 recovered | 4 | 4 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| Sock Shop: one selected Spring AMQP queue-master `CONSUMES_EVENT` scope | 1/1 recovered | 1 | 1 | 0 | 0 | 1.00 | 1.00 | 1.00 |

These are **selected in-source closed relation scopes**, not a multi-service complete graph truth set. Online Boutique has *two* exhaustive function-node files (10 + 1 exact declarations), not 14 exhaustive node scopes. Source evidence existence was checked. The online boutique proof checker initially rejected four invalid markers for Go selector chains split across newlines; they were corrected and the CI re-run passed, rather than silently discarding missing evidence.

**Evidence:** Online Boutique P1-P4 GitHub Actions `Publication Evidence P1-P4` run https://github.com/Vikas-Personal-Research-Org/Graph_Builder/actions/runs/43933564491 and later green successors; Thrift/AMQP and Train-Ticket P2 run https://github.com/Vikas-Personal-Research-Org/Graph_Builder/actions/runs/43934209016.

**Unfinished P1:** Independently label unselected scopes, multiple actual inter-service callsites and hard negatives in all four target systems. Obtain at least **two real human source reviewers**, measure three-category Cohen kappa with `bench/annotation_review.py` (distinct reviewer identifiers and exact universe digest checked; actual human identity and source-completeness **cannot** be cryptographically inferred by this script), adjudicate disagreements, record commits/ground truth and run metrics. The observed 1.00 scores cannot be reported as proposal target achievement at population scale.

## P2 — Real-source contract and communication checks (source samples completed, full protocol accuracy open)

- **Online Boutique:** exact selected gRPC client `CONSUMES` and server `IMPLEMENTS` bindings in pinned Go/Python source; 14/14 source-reviewed triples recovered; additionally check generated stubs and dynamic/ambiguous cases in a larger independent sample.
- **Train-Ticket:** `FudanSELab/train-ticket@313886e99befb94be6cd45f085c98e0019f59829`, exact Java `OrderController` source: three inspected Spring REST declarations were registered under the class route prefix (3/3 source anchors, 3/3 handler nodes, 3/3 route registrations). This is **NOT** 3/3 client-to-server HTTP bindings or a closed-scope precision estimate.
- **DeathStarBench:** Thrift IDL parser reproduces four selected source-declared service `DEFINES_RPC` edges (4/4). **NOT** C++ generated-stub dispatch, RPC implementation or runtime client/server binding.
- **Sock Shop:** one independently pinned `queue-master` Java service's Spring `MessageListenerAdapter`-based `CONSUMES_EVENT` edge found and source-evidenced. **NOT** end-to-end RabbitMQ delivery between all shops; the umbrella deployment repository is not a full service-code checkout.

These projects do not all use the same protocol: Online Boutique gRPC, Train-Ticket Spring REST, DeathStarBench Thrift, Sock Shop HTTP/AMQP. Comparisons must stratify by protocol instead of reporting all as gRPC.

**Unfinished P2:** full service-system scoped consumer/producer reference, genuinely unresolvable cases, generated-stub provenance, Thrift generated dispatch, cross-repo HTTP host discovery and message routing adjudication; some dynamic links should stay marked uncertain.

## P3 — Operational lineage and persistence (implemented locally; actual external attestation/deployment not demonstrated)

- `lineage_bridge.py`: exact **40-character Git SHA-1 commit object** checked via real `git cat-file`, then `EXACT_GIT_OBJECT` bridges `source_revision::<repo>::<sha>` and `commit::<12hex>`; a caller-selected checkout/repo_id remains a trust assumption. No fake service-name joins.
- `provenance_verification.py`: fail-closed **DSSE Ed25519 signature** verification under explicit caller key trust, plus expected source URI, commit, builder and byte-for-byte artifact SHA-256. Unsigned, malformed, altered, wrong builder or artifact fails in tests.
- `annotate_verified_build` upgrades **ONLY** `BUILT_BY` and `PRODUCED_ARTIFACT` build links after successful signature verification; keeps `DEPLOYED_AS` and `OBSERVED_DURING` as `reported_unverified`. This avoids the false claim that a signed build verifies deployment or telemetry.
- `sqlite_graph_store.py`: immutable SQLite snapshot revisions, atomic parent/CAS conflicts, sha256 tamper detection, exact JSON node/edge/graph attrs reload, restart and historical snapshots.
- `tests/test_publication_operational_chain.py`: **ephemeral test** source repository and Git commit, temporary signing key + artifact bytes, synthetic deployment and telemetry, end-to-end graph bridge to durable restart. Explicitly rejects build records whose recorded completion timestamp contradicts the signed `finishedOn` field. This is NOT a real benchmark service's production provenance.

**Unfinished P3:** verifiable signed CI provenance + real deployment records + OTLP exports from actual four systems tied to their identifiers, independently evaluated precision and temporal coverage, robust multi-process/concurrent query load and full graph migration testing. Do not write “production lineage verified” or “SLSA L3 achieved.”

## P4 — Comparisons and incremental performance (exploratory measured, external baselines open)

Pinned 27 Online Boutique source-inspected localization questions, k=5, B=2,048 cl100k_base tokens, fixed candidates:
- BM25 R0 MRR@5 **0.341**
- LSA R1 **0.6382716049382715**
- Static graph hybrid R5 **0.5135802469135803**
- Paired R1-R5 MRR difference **+0.12469135802469135**; within-dataset paired bootstrap 10,000 resamples, seed 20261117, 95% percentile interval **[-0.0574074074, +0.3000000000]**. Interval includes 0; 27 curated queries are not independent review or a random sample. No reliable general ranking gain inferred.
- R3/R9 ≈0.514 (same script), post-construction Lsyn/Ldep/Lflow/Lsem/Lcontract masks are **NOT** construction-stage parser ablations, and not external graph-builder comparisons.
- `bench/paper_performance.py` initially tested node IDs and typed multiedge counts only. The new `full_graph_signature`, `semantic_graph_signature` and `diagnose_graph_attribute_drift` distinguish **keyed-edge-identity**, **full graph metadata and semantic attributes ignoring only ephemeral edge keys**, and **structural triples**.
- **Newly detected and fixed source-provenance defect:** deferred gRPC and HTTP `CONSUMES`/`IMPLEMENTS` and related HTTP edges previously borrowed mutable `current_file_ctx`. The same checkout-service edge had `id_ctx=src/shippingservice/main.go` on an incremental rebuild and `id_ctx=src/shoppingassistantservice/shoppingassistantservice.py` on a fresh build, neither being its own source. Both were incorrect. Contract/HTTP binding construction now derives `id_ctx` from the true source symbol or explicit callsite file. `tests/test_publication_contract_provenance.py` guards this.
- On one pinned real Online Boutique single-file Go `append_comment` edit across three CI repetitions **after correction**: structural equivalence **3/3**, full **semantic attribute equivalence ignoring insertion-counter edge IDs 3/3**, and byte/key-identity equivalence **0/3** (internal `eNNN` edge IDs differ). Median incremental **0.722715137 s**, fresh **7.961545377 s**, ratio **11.016159714**. This is a measured same-semantic-content speedup on this **specific** edit, not universal O(delta) scaling or a byte-identical storage claim.
- Passing CI on corrected provenance code `0b981cbd2c001e9fcfdec86b3a3fef9b18b17419`: https://github.com/Vikas-Personal-Research-Org/Graph_Builder/actions/runs/43937160806 — **342 tests passed, 3 skipped**.

**Unfinished P4:** Stable internal keyed-edge identity is **not** established; broader deletion/schema/transactional/multi-repo update cases and full performance confidence intervals are outstanding. Execute external published baselines on matching tasks where compatible (RepoGraph, CodexGraph, LocAgent) or limit numerical comparison to named in-project R0/R1/R3/R5/R9 methods. Do not transfer non-comparable scores.

## Explicit correction ledger: hallucinated, ungrounded or overstated prior findings

| Earlier content/claim | Verdict and correction |
|---|---|
| `Paper1.pdf` “MRR@5 0.894”, “Recall@10 95.2%”, “14.8% token redundancy” | No matching independently reproducible evaluation; **retract**. Revised paper's 0.638 vs 0.514 on 27 unreviewed tasks is accurate scope, but not population inference. |
| `Paper1.pdf` “46% fewer agent tool calls”, “60% lower agent task latency” | Simulated procedure or unsupported; **retract**. No genuine deployed agent evaluation established here. |
| `Paper1.pdf` “96.8% dependency/link precision”, “polymorphic > 90%” | Not demonstrated against complete independent real-source scopes; **do not claim**. |
| Earlier four-system graph counts as “precision/recall achieved” | Node/edge counts are construction and compatibility only, not correctness. |
| Old Sock Shop umbrella repo 4 parsed files as “full Sock Shop” | Incorrect. Eight separate pinned source service repos audited later. The AMQP sample here is one queue-master service, not all system communications. |
| Green parser/CI checks as “all languages and all source accurate” | False. DataHub TS/TSX and DeathStarBench C++ have known partial syntax cases, see `REAL_REPOSITORY_COMPATIBILITY_AUDIT.md`. |
| `bench/results/multi_system_eval.json` heuristic rankings as directly comparable with corrected 27-query study | Incompatible candidate sets, protocols, labels and scope; **do not mix or publish as same benchmark**. |
| Reported `ckg_consistency=VERIFIED` in `remediation.py` despite no actual patch graph rebuild | An earlier identified **Objective 3** validation-status issue; **not valid evidence for Objective 1 graph correctness**. |
| Claim operational SLSA v1 JSON parser itself authenticates production build | False. Parser verifies structure only. DSSE local key test verifies controlled fixture and caller trust only. |
| Claim Git SHA object presence proves deployment or telemetry origin | False. Explicitly keep unverified deployment/OTLP edges. |
| Structural incremental equals fresh (3/3) implies equal node provenance, metadata and edge keys | **False** before correction: bad `id_ctx` in deferred contract/HTTP edges. **Fixed** in the tested case: semantic node/edge metadata now 3/3. Internal counter-generated edge keys remain nonstable (0/3), so do not claim byte-for-byte equality. |
| Perfect selected labels imply P1 fully completed | False: tiny selected source-inspected scopes and no independent human adjudication; expansion to unbiased scope required. |
| Train-Ticket 3 route declarations establish cross-service HTTP binding 100% | False: only exact handler route registrations 3/3, no caller-to-target graph accuracy. |

## Paper-ready elements versus mandatory external evidence

**Can write now, labeled exploratory:** architecture / definitions; exact scope and versions of selected four-system probes; 14/14 boutique, 4/4 Thrift, 1/1 AMQP closed selected scopes with source evidence and pending human review; Train-Ticket 3 route registrations; 27-query R0/R1/R5 comparison and paired bootstrap; SQLite restart and synthetic signed fixture; documented limitations.

**Cannot honestly write as completed:** independently adjudicated cross-system precision/recall, proposal-wide 0.90/0.85/0.80 targets, signed *real* CI → artifact → deployed service → observed OTLP records, general full-graph incremental equivalence, published external method SOTA, agent success, reliable graph ranking superiority.

**Required external inputs:** two or more independent subject-matter annotators on complete source scopes, access to actual signed build provenance and deployment identity records plus corresponding OTLP captures from benchmark services, and comparable external baseline reproductions where research scope demands them.

Raw CI outputs are retained as GitHub Actions artifacts (30 days by workflow setting), NOT copied into checked-in performance tables without an explicit pinned run reference. Never silently promote fixtures or assumptions into facts.
