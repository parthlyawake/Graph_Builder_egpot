# P1–P4 expanded empirical evidence — 2026-11-17

**Research status:** Repeatable source/CI experiments, **NOT independent-human adjudication or submission certification**. This file reports raw outcomes from pinned code and GitHub Actions rather than extrapolated population estimates.

## Environment, pins, executable evidence

- Code under evaluation: research branch `research-p1-p4-expanded-reproducibility-2026-11-17`, subsequently destined for `krishna`.
- Online Boutique: `GoogleCloudPlatform/microservices-demo@38e7348eb289eb5b87c0c6e8cb19ced0449dc389`.
- Train-Ticket: `FudanSELab/train-ticket@313886e99befb94be6cd45f085c98e0019f59829`.
- DeathStarBench: `delimitrou/DeathStarBench@6ecb09706140f8730b5385c08f1386c654c3c526`.
- Sock Shop queue-master: `microservices-demo/queue-master@7dc33721c765e5af415c9d244d84637ff2d510cd`.
- Raw P1/P2/P4 run: [workflow 43946011210](https://github.com/Vikas-Personal-Research-Org/Graph_Builder/actions/runs/43946011210) and its `expanded-p1-p4-raw` artifact (contains per-trial JSON, source scope checks, the retrieval study, and **blank** reviewer templates).
- Real P3 CI runtime experiment: [workflow 43946802680](https://github.com/Vikas-Personal-Research-Org/Graph_Builder/actions/runs/43946802680), `real-benchmark-email-otel` artifact.
- Workflow definition: `.github/workflows/research-expanded-p1-p4.yml`; Python 3.11, GitHub-hosted Linux.

All source pins are checked against `git rev-parse HEAD` before evaluation.

## P1: complete-file declaration recovery (automatic source oracle only)

The independent lexical census reads **all declarations in one pinned source file**, without selecting graph successes. It compares exact source IDs, edge types, routes and targets, capturing false positives and false negatives inside those file/relationship scopes.

| Source scope | Unit | Expected | Graph recovered | TP | FP | FN |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Online Boutique `protos/demo.proto` | Protobuf service `DEFINES_RPC` | 15 | 15 | 15 | 0 | 0 |
| DeathStarBench `socialNetwork/social_network.thrift` | Thrift service `DEFINES_RPC` | 27 | 27 | 27 | 0 | 0 |
| Train-Ticket `OrderController.java` | Spring route declaration registration | 16 | 16 | 16 | 0 | 0 |
| **Aggregate of these unlike declaration units** | **not one population accuracy estimate** | **58** | **58** | **58** | **0** | **0** |

Within each explicitly circumscribed automatic declaration scope, observed P/R/F1 are 1.0; **these are not independently adjudicated population metrics**. The Protobuf and Thrift rows are contract declarations, not implementation or consumer link proof. The Spring row is route registration, not end-to-end HTTP connection.

**Review preparation:** `bench/review_packet_source_contracts.py` builds entirely graph-blind candidate universes for the above full contract files: **135 possible source-service×RPC triples** in nine Online Boutique services (15 declared RPCs), and **297 possible triples** in 11 DeathStarBench services (27 declared RPCs), **432 candidate judgments total**. The CI artifact has `reviewer_A_BLANK.json`, `reviewer_B_BLANK.json`, frozen candidate-universe hashes, and manifest instructions. **No human judgments were generated or implied.** Two independent blinded human reviewers and an adjudicator must sign off before reporting a gold accuracy table; broad Lsyn/Ldep/Lflow/Lsem and all four systems still need review.

## P2: cross-service protocol validation, bounded to actual evidence

- **Online Boutique gRPC:** the earlier pinned source-reviewed selected study recovers 14/14 independently *source-inspected* exact consumer/producer triples; external human review is pending. A real Go source mutation `GetCart` → invalid `GetCartTypo` removes the original `CONSUMES` binding in fresh and incremental constructions without inventing a replacement (dedicated fault result).
- **Train-Ticket HTTP:** 16/16 route **declarations** in the complete Java controller file are registered. This does **not** validate actual remote callers or resolve computed hosts.
- **DeathStarBench Thrift:** 27/27 RPC **declarations** recovered; C++ generated dispatch, caller and server implementation links unmeasured.
- **Sock Shop AMQP:** a selected `queue-master` Spring consumer binding remains source-inspected and CI-checked. A producer-to-queue-to-consumer delivery path across independently deployed services has not been demonstrated.

Protocol accuracy cannot be pooled as though these objects were interchangeable. Unknown target endpoints must remain unresolved. No separate valid P2 producer-to-consumer F1 exists for all four systems.

## P3: actual source-pinned benchmark execution, real OTLP, but unsigned runtime link

The CI experiment `bench/real_benchmark_email_otlp.py` executes the **original** pinned Online Boutique `src/emailservice/email_server.py` in its supported dummy-server mode; it does not replace the benchmark server implementation. It compiles the pinned Protobuf schema, invokes five real `SendOrderConfirmation` gRPC methods, and runs a local OTLP TraceService collector.

| Measurement | Result |
| --- | --- |
| Successful gRPC responses | **5 / 5** |
| OTLP server spans with matching RPC name | **5** |
| Trace resource `service.version` matches pinned source SHA | **Yes** |
| Reported `source.git.commit` matches pinned source SHA | **Yes** |
| Original EmailService Python source SHA-256 | `942ad730bdc04007c84b7cda038b58b68498f344d8233a0384a40991ccd574f4` |
| Deployment setting | Ephemeral CI process, not production rollout |
| Authenticated external artifact → deployment attestation | **No** |

The GitHub-native OIDC `actions/attest-build-provenance@v3` attempt successfully compiled a real Protobuf code-generation artifact, then GitHub rejected attestation publication: **private organization plan does not support the attestations API**. The workflow preserves an `UNVERIFIED` trust-gate record and does not upgrade unsigned build, deployment or OTLP facts to authenticated status.

**Interpretation:** real benchmark runtime traces exist, but the resource/commit identity is **self-reported environment metadata**; it does not authenticate the actual deployed binary/image or a real external release chain. SLSA attainment or production incident-to-source attribution is **not** established.

## P4: real-source mutation matrix and exploratory retrieval

Six source mutation types × three independent temporary-checkout trials each = **18 / 18 structural and semantic-attribute equivalence passes** against fresh builds, disregarding only ephemeral `eNNN` edge insertion keys (not metadata). Mutations were performed on real pinned files and never committed to upstream benchmarks.

| System / mutation | Equivalent / trials | Median incremental (s) | Median fresh (s) | Fresh÷incremental |
| --- | ---: | ---: | ---: | ---: |
| Online Boutique invalid gRPC method | 3/3 | 0.0988 | 0.2816 | 2.85× |
| Online Boutique Protobuf RPC rename | 3/3 | 0.3416 | 0.2789 | 0.82× |
| Online Boutique Go source deletion | 3/3 | 0.0976 | 0.3384 | 3.47× |
| Online Boutique Go function addition | 3/3 | 0.1053 | 0.3317 | 3.15× |
| Train-Ticket Spring route rename | 3/3 | 0.0120 | 0.0160 | 1.34× |
| DeathStarBench Thrift RPC rename | 3/3 | 0.0060 | 0.0059 | 0.97× |

**Important:** a schema edit may retain an old RPC identity sourced elsewhere; the correct equivalence condition is that the incremental state matches the fresh state, not that a name disappears globally. Two edits above are **slower** to update than to rebuild; no universal speedup or O(∆) complexity theorem follows. These 18 observations are tiny workload-specific measurements, not independent statistical units or process-RSS measurements.

The fixed 27-query Online Boutique exact-node localization study reproduces:

- **BM25 R0:** MRR@5 = **0.34074**; **LSA R1:** **0.63827**; **R3/R5/R9 graph hybrids:** **0.51358**.
- Paired R1−R5 MRR@5 difference = **+0.12469**; fixed-seed 10,000-resample within-cohort interval **[−0.0574, +0.3000]** includes zero.
- R5 graph-context target inclusion is **0.8148**; removing Ldep reduces to **0.4444**; removing Lcontract reduces to **0.7407**. These are **post-construction layer masks**, not full parser-stage retraining/rebuilding.
- Query labels remain source-inspected, **not independently human adjudicated**, and were hand constructed. No externally reproduced comparable published baseline is included.

## Scientific gates still open

1. **P1** — Obtain *two genuinely independent blinded human reviewers* and adjudicate complete representative closed scopes for all graph layers (Lsem with relevance rather than binary program-truth); use query/sample design with uncertainty intervals. The blank packets are not votes.
2. **P2** — Establish real complete producer/consumer bindings for gRPC generated stubs, Thrift C++ dispatch, HTTP hosts/callers, AMQP producers/exchanges/queues/handlers, with exhaustive hard negatives and abstention metrics.
3. **P3** — Supply externally verifiable attested artifact digest/build identity, authentic deployment rollout identity/digest, and matching OTLP resource records from the *same* deployed workload. GitHub private-organization attestation capability is a concrete blocker; self-reported source tags cannot substitute.
4. **P4** — Run independently reviewed fault-localization/impact-analysis queries, more repetitions/mutations (including multiple simultaneous files and distributed workspace updates), and same-task external baselines where output/language/protocol comparability exists.

**Do not state these experiments close all publication gaps or validate the old Paper1.pdf numbers.**
