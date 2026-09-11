# GRAFT-CKG / SCKG — Status, Verification, Gap Analysis and Completion Plan

**Prepared for:** Krishna S N (Batch 1 — BUILD, Objective 1) · Vikas Ranjan PhD (BITS Pilani, Prof. V. Chamola)
**Inputs audited:** `SCKG_Build-main.zip` (upstream commit `1c56617` + polyglot change-set), `Paper1.pdf` (GRAFT-CKG draft), `Vikas_Ranjan_PhD_Proposal_BITS.pdf`, `SCKG_Tracker_Personal.xlsx`
**Audit date:** 2026-09-11 (Tracker Week 13 of 16)
**Deliverable code:** `SCKG_Build-v2.zip` (this audit's implementation; all numbers below are reproduced from it)

---

## 0. Executive summary

| Question | Short answer |
|---|---|
| **How much is done?** | A working *single-repository, static* 4-layer code graph (Lsyn/Ldep/Lflow/Lsem) for **Python + JS/TS**, with CLI, browser workbench, GraphML/GEXF export, RAG + subtree grafting, 9 passing regression tests and honest internal docs. Roughly **Objective-1 Layer-1 (symbolic structure) ≈ 70 % complete**; **Layer 2 (contracts) 0 %** in the zip; Layers 3–4 (lineage, telemetry) 0 %. |
| **Is it working properly?** | **Yes, as engineering** — every test and both eval scripts pass and the `BENCHMARK_REPORT.md` scorecard reproduces exactly. **No, as science** — *none* of Paper1's headline numbers (Table I, Table II, 96.8 %, 93.5 %, −46 % tool calls, −60 % latency, ablations) is produced by any code in the repo. The only paper figure that a real run supports is construction throughput (measured 0.036–0.091 s/kLOC on real repos vs. 0.042–0.055 claimed). |
| **How to verify?** | §2 gives the exact commands. New in v2: a **dynamic-trace oracle** (`bench/trace_oracle.py`) that measures call-edge precision/recall, polymorphic disambiguation accuracy and 2-hop F1 against a repo's own test-suite execution — the first ground truth this project has had. |
| **Biggest finding** | Measured **polymorphic disambiguation accuracy is 2–10 %**, not 96.8 %: the engine has no receiver-type inference and the paper's Eq. (4) softmax confidence is not implemented (c_type is a uniform 1/k). Static call-edge recall on OO-heavy repos is 13–48 %. This must be fixed before the paper can make any Ldep accuracy claim. |
| **What v2 adds (this delivery)** | ① Go adapter (tree-sitter-go); ② **Protobuf/gRPC Contract Layer (`Lcontract`)** — the proposal's Layer 2 / Gap 1.1 — binding producers and consumers across Python, Go and JS, **P = R = 1.00 on 21 hand-labelled consumer and 7 producer bindings in Google Online Boutique**; ③ contract-violation **fault-injection + blast-radius detector** (Tracker Week 11); ④ dynamic-trace **construction-accuracy oracle** (Gap 1.3, Tracker Weeks 8/13); ⑤ hand-labelled benchmark harness; ⑥ 7 new regression tests (16 total, all passing); ⑦ `who_consumes` / `who_implements` traversal APIs (Tracker Week 10). |
| **What remains** | P0 for the paper: receiver-type inference + class-hierarchy analysis + Eq. (4); a real retrieval benchmark with leakage control and the six baselines; layer ablations; incremental (streaming) build; a correct token-redundancy metric. P1 for the proposal: Layer 3 lineage, Layer 4 telemetry, Neo4j persistence, Java/C# adapters. P2: the agent tool-call/latency experiment (or drop those claims). Full plan with designs in §7. |

---

## 1. Inventory: what exists in `SCKG_Build-main.zip` and its verified status

| Component | File(s) | LOC | What it does | Verified? |
|---|---|---|---|---|
| Core 4-layer engine | `graft_ckg.py` | 1 157 | Python `ast` → file/class/function/variable nodes; `CONTAINS`, `IMPORTS`, `EXTENDS`, `CALLS`, `PASSES_ARG`, `DEFINES`, `USES`, `HTTP_CALLS`, `SEMANTIC_SIMILAR`; 4-D edge metadata `m=[d_scope,f_call,c_type,id_ctx]`; import-alias / relative-import / `self.` / `super().` resolution; TF-IDF docstring similarity; `explain`, `adjacency`, `rag_query`, `deterministic_subtree_graft`, `verify_graph`; CLI + REPL; GraphML/GEXF export | ✅ runs on 5 real repos (1.5k–29k LOC) and Online Boutique (22k LOC) without error |
| JS/TS adapter | `polyglot.py` | 255 | Tree-sitter JS/JSX/TS/TSX → same schema; ES/CommonJS imports, tsconfig `paths`, workspace `package.json`; params/locals/return/mutation flow; literal `fetch`/`axios` → Flask-style route binding | ✅ 9/9 tests; `eval_polyglot.py` 2/2 bindings |
| Toy evaluation | `eval_ckg.py` | 347 | Generates a 49-LOC 3-file payment repo; 5 unit tests; 5 hand-written queries; prints MRR@5/Hits/Recall/"token ratio"/latency next to the paper's Table I/II numbers | ✅ reproduces `BENCHMARK_REPORT.md` exactly (MRR 0.840, Hits@1 80 %, Hits@5 100 %, Recall 80 %, token 24.3 %) — **but it is a toy, not a benchmark** (the authors say so themselves) |
| Polyglot fixture eval | `eval_polyglot.py`, `examples/mixed_service` | 54+34 | Frozen TS→Python HTTP binding check | ✅ 2/2 |
| Web workbench | `serve_ckg.py` | 1 107 | localhost:8080 D3 viewer, n-hop isolation, inspector | ✅ imports & serves (not load-tested) |
| Exporter | `visualize.py` | 182 | GraphML → GEXF/JSON/HTML | ✅ |
| Tests | `tests/` | 280 | Python/JS/TS import & inheritance resolution, JS flow, HTTP binding | ✅ 9/9 |
| Docs | `README.md`, `IMPLEMENTATION_STATUS.md`, `BENCHMARK_REPORT.md`, `presentation_guide.md` | — | Honest about limits ("toy repository… should not be presented as a benchmark") | ⚠️ README references a `math_app/` folder that is **not in the zip** |

**Completion estimate against Paper1's own architecture (Fig. 1):** Input parser (Python ✅, TS/JS ✅, Java ❌, C++ ❌, Go ❌→✅ in v2) · Lsyn ✅ · Ldep ⚠️ (no type inference, no polymorphic dispatch) · Lflow ⚠️ (intra-procedural only; Python lacks `RETURNS`/`MUTATES`/`FLOWS_TO` that JS has) · Lsem ⚠️ (TF-IDF over docstrings only; no type contracts) · Hyper-relational edge synthesizer ✅ (metadata vector present, `c_type` not computed by Eq. 4) · Subtree grafting ✅ (depth-2 BFS, no token budget) · Streaming/incremental HR-Build ❌ · Evaluation ❌.

---

## 2. Is the work working? — Verification protocol and results

### 2.1 Commands (all reproduced in this audit)

```bash
pip install -r requirements.txt            # v2 adds tree-sitter-go, rank_bm25
python -m unittest discover -s tests -v    # v1: 9/9 OK  → v2: 16/16 OK
python eval_ckg.py                         # toy scorecard (reproduces BENCHMARK_REPORT.md)
python eval_polyglot.py                    # 2/2 HTTP bindings
python graft_ckg.py /path/to/repo --verify # health report on any repo

# v2 — real measurements
python bench/run_benchmark.py --repo <online-boutique> --labels bench/labels/online_boutique_contracts.json
python bench/trace_oracle.py  --repo <repo> --pytest-args tests           # construction accuracy vs dynamic trace
python bench/inject_contract_fault.py --repo <online-boutique> --service ShippingService --rpc GetQuote --fault rename-rpc
python graft_ckg.py <online-boutique> --who-consumes EmailService --who-implements ShippingService.GetQuote
```

### 2.2 Construction on real repositories (Table I — **measured**, replaces placeholders)

| Repository (real) | LOC | Nodes | Hyper-edges | s/kLOC | Internal call resolution | Lcontract edges |
|---|---:|---:|---:|---:|---:|---:|
| tomli (Python) | 1 570 | 535 | 1 603 | 0.091 | 31.4 % | – |
| pluggy (Python) | 5 700 | 2 181 | 5 280 | 0.036 | 59.5 % | – |
| toolz (Python) | 7 155 | 1 925 | 5 411 | 0.047 | 46.9 % | – |
| jinja (Python) | 22 875 | 8 211 | 21 481 | 0.043 | 40.4 % | – |
| click (Python) | 29 121 | 8 005 | 21 478 | 0.044 | 17.6 % | – |
| **Online Boutique** (Go+Py+JS+proto; C#/Java unparsed) | 22 093 | 7 639 | 20 432 | 0.052–0.061 | 9.8 %* | **110** (23 IMPLEMENTS, 21 CONSUMES) |

\*Go/JS call resolution is name-based only; most calls are to stdlib/gRPC-generated code (correctly left external).
Throughput claim (0.042–0.055 s/kLOC) is **plausible** — measured 0.036–0.091, small repos dominated by fixed start-up cost. Note "resolution rate" is *not* accuracy: it counts edges created, not edges that are correct.

### 2.3 Construction **accuracy** vs. dynamic ground truth (new `bench/trace_oracle.py`)

Method: run each repo's own pytest suite under `sys.setprofile`, record every repo-internal (caller→callee) frame pair, normalise to graph node ids (`Foo()`≡`Foo.__init__`, strip `<locals>`), compare with static `CALLS` edges.
*Recall* = static∩dynamic / dynamic. *Precision (lower bound)* = static∩dynamic / static edges whose caller executed. *Disambiguation accuracy* = among dynamic calls whose callee **name** has ≥2 definitions in the repo (true ambiguous/polymorphic sites), fraction where the static graph links to the observed callee. *2-hop F1* over transitive (2-hop) reachability pairs.

| Repo | tests run | static edges | dynamic edges | **Edge recall** | **Edge precision (LB)** | ambiguous sites | **Disambiguation acc.** | **2-hop F1** |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| tomli | 17 | 94 | 103 | **0.82** | **0.98** | 0 | n/a | 0.73 |
| pluggy | 144 | 892 | 880 | 0.43 | 0.46 | 322 | **0.02** | 0.57 |
| toolz | 165 | 535 | 532 | 0.48 | 0.58 | 202 | **0.07** | 0.37 |
| jinja | 911 | 1 825 | 3 191 | 0.43 | 0.80 | 1 181 | **0.10** | 0.43 |
| click | 2 059 | 876 | 4 026 | **0.13** | 0.75 | 2 591 | **0.03** | 0.12 |

**Reading:** on a procedural repo (tomli) the engine is excellent (P 0.98 / R 0.82). On OO code, recall collapses because `obj.method()` with an inferred receiver type is never resolved and there is no class-hierarchy analysis; the paper's *"96.8 % polymorphic resolution accuracy"* and *"93.5 % multi-hop F1"* are contradicted by measurement (2–10 % and 12–73 %). The proposal's Layer-1 target (node P/R ≥ 0.90, edge P ≥ 0.85 / R ≥ 0.80) is met only on tomli.

### 2.4 Contract layer (proposal Layer 2 / Gap 1.1) — **new in v2, measured**

Ground truth: `bench/labels/online_boutique_contracts.json` — 21 consumer call-sites and 9 producer services hand-labelled from `protos/demo.proto` and service source (2 producers are C#/Java and excluded as unparseable).

| Binding type | Labelled (parseable) | Graph edges | TP | FP | FN | **Precision** | **Recall** |
|---|---:|---:|---:|---:|---:|---:|---:|
| CONSUMES (client call-site → rpc) — Go, Python | 21 | 21 | 21 | 0 | 0 | **1.00** | **1.00** |
| IMPLEMENTS (server method/class → rpc/service) — Go, Python, JS | 7 services / 12 rpc methods | 23 | 23 | 0 | 0 | **1.00** | **1.00** |

Proposal target (Layer 2: P ≥ 0.85, R ≥ 0.80) — **met**, on one system with one labeller. Needs Train-Ticket / Sock Shop / DeathStarBench and a second labeller before it is a paper claim.

### 2.5 Contract-violation fault injection (Tracker Week 11) — **new in v2**

| Injected fault (copy of repo, consumers untouched) | Detected | Bindings lost | Blast radius reported |
|---|---|---:|---|
| rename `ShippingService.GetQuote` → `GetQuoteV2` | ✅ | 3 | consumers `checkoutservice.quoteShipping`, `frontend.getShippingQuote`; producer `shippingservice.server.GetQuote`; services {checkout, frontend, shipping} |
| remove `CartService.GetCart` | ✅ | 2 | consumers `checkoutservice.getUserCart`, `frontend.getCart` (producer is C# → correctly reported as unparsed) |

---

## 3. Defects found in the original code (all confirmed by execution)

| # | Defect | Impact on paper claims | Fixed in v2? |
|---|---|---|---|
| D1 | `rag_query` indexes **only nodes with a docstring > 10 chars**; docstring coverage on real repos is 16–30 % → 70–84 % of functions are *unretrievable* | Table II MRR/Hits/Recall would be meaningless on real repos | ❌ (design in §7.2) |
| D2 | "Token Redundancy" = `grafted_chars/4 ÷ (total_LOC × 8)` — a *context-size ratio*, not redundancy (share of retrieved tokens that are irrelevant) | Table II last column is undefined | ❌ (definition in §7.2) |
| D3 | `c_type` for multi-candidate calls is a uniform `1/k`; Eq. (4) softmax with temperature τ is **not implemented**; no receiver-type inference; `self.m()` only searches declared bases, not overriding subclasses | §IV-A, Fig. 3, "96.8 %" unsupported | ❌ (design in §7.1) |
| D4 | Semantic threshold is 0.55 in code vs θ_sim = 0.70 in Algorithm 1; Lsem uses dense O(n²) pairwise cosine, contradicting the O(N log N) claim in §VII-A | Complexity and algorithm text inconsistent with code | ❌ trivial; note in §8 |
| D5 | Module-level calls ignored (`visit_Call` requires an enclosing scope); `for`/`with`/comprehension targets never `DEFINES` → their `USES` never link | Lflow recall understated | ❌ |
| D6 | One `USES` edge per variable *read* (MultiDiGraph) → edge counts inflated (e.g. click: 13 305 Lflow edges of 21 478) | Table I "Hyper-Edges" inflated; metadata `f_call` should aggregate instead | ❌ |
| D7 | Python Lflow has no `RETURNS`/`MUTATES`/`FLOWS_TO` (JS has them); **no inter-procedural** arg→param or return→assignment flow | §I "inter-procedural def-use chains" unsupported | ❌ |
| D8 | No incremental / streaming construction — full rebuild only | Fig. 3 "incremental AST delta parsing" unsupported | ❌ (design in §7.4) |
| D9 | `explain_node` fuzzy match returns the first arbitrary substring hit | Non-deterministic explanations | ❌ trivial |
| D10 | `eval_ckg.py` "Context Recall@10" uses top-5 + depth-2 graft; queries are hand-written to match docstrings (leakage) | Toy numbers over-state retrieval quality | ❌ (protocol in §7.2) |
| D11 | Proto parser I first wrote (and the original had none) — stops at first `{}` → only the first rpc per service captured | Lcontract recall would be 33 % | ✅ brace-balanced parser + test |
| D12 | README documents `math_app/` sample that is missing from the zip | Onboarding | ⚠️ documented |

---

## 4. Claim-by-claim audit of Paper1 (GRAFT-CKG)

Legend: ✅ implemented & measured · ⚠️ implemented, not measured or partially · ❌ absent · 🔢 number is a placeholder with no producing code.

| § | Claim in Paper1 | Status | Evidence / measured value | Required action |
|---|---|---|---|---|
| Abstract, I | Four synchronized layers Lsyn/Ldep/Lflow/Lsem | ✅/⚠️ | All present; Lsem = TF-IDF lexical similarity over docstrings (paper says "intent embeddings", "type contracts", "pre/post-conditions") | Either implement embeddings + `USES_TYPE`/`RETURNS_TYPE` contract edges from annotations, or reword Lsem honestly |
| I, Fig. 1 | Polyglot input: Python, TS, Java, C++ | ⚠️ | Python, JS/TS (v1), Go (v2). Java, C++, C# absent | Add tree-sitter-java (AdService), tree-sitter-c-sharp (CartService) or change Fig. 1 |
| I | Typed links `uses, produces, validates, configures, mutates` | ❌ | Only `USES`, `MUTATES` exist; `produces/validates/configures` never appear in code | Define them (e.g. `produces` = `RETURNS`+`FLOWS_TO`, `configures` = env/config reads) or remove |
| I, VIII | −46 % agent tool calls, −60 % latency | 🔢 | No agent, no harness, no log | Run OpenHands/SWE-agent with and without a CKG tool on ≥30 tasks; else delete |
| II-B, III | Hyper-edge metadata m=⟨d_scope,f_call,c_type,id_ctx⟩ | ✅ | Present on every edge (test `test_hyper_edge_metadata`) | — |
| III-A Eq. (1) | G=(V,E,L,Φ,Ψ,M) | ✅ | NetworkX MultiDiGraph with layer/relation/metadata attrs | — |
| IV Alg. 1 | Two-pass HR-Build; θ_sim = 0.70 | ⚠️ | Two-pass ✅; θ in code is 0.55 | Align constant |
| IV | "incremental streaming construction", Fig. 3 file-diff watching, AST delta parsing, live subgraph stitching | ❌ | Full rebuild only | Implement `update_files()` (§7.4) and measure rebuild-vs-incremental latency |
| IV-A Eq. (4) | Softmax confidence over implementations with temperature τ, constraint propagation over class tree; CHA/RTA in Fig. 3 | ❌ | `c_type = 1/k`; no CHA; no receiver typing | Implement (§7.1) |
| VI-A Table I | RepoBench-P 2 450 LOC / 312 nodes…; latency 0.042–0.055; disamb. 97.3–96.4 %; multi-hop F1 94.5–93.5 % | 🔢 except latency | Latency measured 0.036–0.091 ✅-ish; **disambiguation measured 2–10 %**, 2-hop F1 12–73 %; LOC/node/edge figures fabricated (RepoBench-P is not a 2 450-LOC repo) | Replace with §2.2–2.3 tables; run on RepoBench-P/CrossCodeEval repos |
| VI-B Table II | 6 baselines; MRR 0.894, Hits@1 84.7, Hits@5 96.5, Recall@10 95.2, redundancy 14.8 vs 64.2 | 🔢 | Zero baselines implemented; toy fixture gives MRR 0.840 on 5 hand-made queries | Implement protocol + baselines (§7.2) |
| VII-A | Total complexity O(N log N) | ❌ | Lsem pairwise cosine is Θ(n²) dense; polymorphic step absent | Sparse thresholded similarity / ANN; restate |
| VII-B | Ablations: −18.4 % (Lflow), −31.2 % (Ldep), −22.6 % (Lsem) | 🔢 | No ablation code | Add layer masks to retrieval harness (§7.3) |
| V-A | Datasets RepoBench-P, CrossCodeEval, Py150, "Enterprise-scale repository" | ❌ | None downloaded or evaluated | See §7.2 |
| V-B | Baselines incl. OpenAI text-embedding-3-large, Contriever, CodeBERT hybrid, GraphCodeBERT, cAST, Naive CPG | ❌ | — | Realistic set: BM25 (done in v2), TF-IDF 512-token chunks, one dense model, Lsyn-only "Naive CPG"; cite others as not re-run |
| Fig. 2 | "eliminates token bloat by 75 %", "zero hallucination" | 🔢 | No measurement | Measure with §7.2 redundancy metric; drop "zero hallucination" |
| Keywords/Intro | "Deterministic Subtree Grafting" | ✅ | BFS over CALLS/DEFINES/PASSES_ARG/CONTAINS, depth 2, no token budget, no callers (blast radius) | Add token budget, `POLYMORPHIC_CALL` threshold, incoming edges option |

**Bottom line for the paper:** the architecture, schema and grafting mechanism are real and demonstrable; every quantitative claim except throughput must be regenerated by the harness in `bench/` (partly delivered) before submission.

---

## 5. Gaps relative to the PhD proposal and the Batch-1 tracker

### 5.1 Proposal Objective 1 (Build) — layer status

| SCKG layer (proposal §4 Phase 2) | Status in zip | Status in v2 | Gap |
|---|---|---|---|
| L1 Symbolic structure (tree-sitter/LSP; Java, Python, Go) | Python ✅, JS/TS ✅ (not in proposal scope), Go ❌, Java ❌; NetworkX, **no Neo4j** | + Go ✅ | Java/C#; LSP-grade type resolution; property-graph persistence (Neo4j loader) |
| L2 Service contracts (Protobuf/gRPC/OpenAPI, canonical contract node, per-language producer/consumer edges) | ❌ (only literal `fetch`→Flask) | ✅ Protobuf/gRPC: `contract::Service`, `contract::Service.Rpc` canonical nodes; `IMPLEMENTS`/`CONSUMES` from Python servicers/stubs, Go `Register*Server`/`New*Client` (incl. multi-line chains, `new()`/`&T{}` impl vars, cross-file types), JS `addService` (pair + shorthand). P=R=1.0 on Online Boutique | OpenAPI/REST contracts; message-field level edges (`RPC_INPUT`/`RPC_OUTPUT`); Train-Ticket (Java), Sock Shop (Go/Java/Node), DeathStarBench (C++/Lua) |
| L3 Operational lineage (commit→artifact→environment→window) | ❌ | ❌ | Design in §7.5 |
| L4 Runtime telemetry (OTel logs/metrics/traces → schema) | ❌ | ❌ | Design in §7.5 |
| Incremental maintenance protocol | ❌ | ❌ | §7.4 |
| Construction accuracy measured (Gap 1.3) | ❌ | ✅ L1 via dynamic trace; ✅ L2 via hand labels | Multi-labeller, more systems |

### 5.2 Tracker weeks (Krishna — Batch 1) vs. evidence found

| Wk | Task | Tracker status | Evidence in zip / v2 | Assessment |
|---|---|---|---|---|
| 1 | Run Online Boutique; service/language table | Done | — | Done |
| 2 | tree-sitter Go+Python functions | Done | JS/TS instead of Go in zip; **Go adapter added in v2** | Done (v2) |
| 3 | LSP definitions/references; CALLS/DEFINES | — | AST-based `CALLS`/`DEFINES` exist; no LSP | Partial — LSP would fix the D3 recall problem |
| 4 | Gap Brief + hand-trace proto producer→consumer | — | This report §4–5; §2.4 traces all 21 | Delivered here |
| 5 | Layer-1 schema; 1 service in Neo4j; 5 Cypher queries | — | Schema ✅ (NetworkX); Neo4j ❌ | Partial |
| 6 | Layer-1 for ALL services | — | ✅ Python/Go/JS services parsed (C#/Java not) | Mostly done |
| 7 | Reproduce RepoGraph; 3 differences | — | Not found | Open |
| 8 | Accuracy harness: hand-label 30 edges; P/R | — | ✅ v2: 21+7 labelled contract bindings; dynamic-trace oracle for L1 | Done (v2) |
| 9 | Parse .proto → canonical contract nodes | — | ✅ v2 `_parse_proto_file` | Done (v2) |
| 10 | Producer–consumer edges 2–3 pairs; "who consumes X" | — | ✅ v2 all pairs; `--who-consumes/--who-implements` | Done (v2) |
| 11 | Inject breaking .proto change; flag inconsistency | — | ✅ v2 `bench/inject_contract_fault.py` | Done (v2) |
| 12 | Layer-2 P/R vs targets (≥0.85/0.80) | — | ✅ 1.00/1.00 (one system) | Done (v2), needs breadth |
| 13 | Layer-1 node/edge P/R (≥0.90) | — | ✅ trace oracle: met on tomli only; 0.13–0.48 recall on OO repos | Measured — target **not met** |
| 14 | Incremental update; latency | — | ❌ | Open (§7.4) |
| 15 | Technical report + graph read API doc for Batch 2 | — | This document + `README` v2 section | Draft delivered |
| 16 | Finalize/present; MSR/ASE targets | — | — | Open |

---

## 6. What v2 changed (files)

| File | Change |
|---|---|
| `polyglot.py` | Go adapter (`function_declaration`, `method_declaration` with receiver → `Type.Method` ids, `type_declaration` → class nodes, `short_var_declaration` defs, Go imports); gRPC capture: `pb.New<Svc>Client(...).<Rpc>` (single- and multi-line), client vars, `Register<Svc>Server(srv, impl)`, `new(T)` / `&T{}` impl-var typing; JS `addService(pkg.<Svc>.service, {…})` pair **and shorthand** handlers; fixed a bug where the `return`/assignment/identifier handlers had been swallowed |
| `graft_ckg.py` | `.proto` discovery + brace-balanced parser → `contract::` nodes (`service_contract`, `rpc_contract` with `request_type`/`response_type`), layer `Lcontract`; `_resolve_contract_layer` (Python servicer classes **and their subclasses**, Go registrations with cross-file type lookup, JS handler maps, deferred stub-variable resolution incl. module-level/`__main__` bindings, consumer de-dup); `who_consumes` / `who_implements` + CLI flags; BM25 baseline index; module-alias cross-file call resolution; vendor-dir skipping; layer stats/verify include `Lcontract` |
| `bench/run_benchmark.py` | Throughput + contract P/R vs labels + retrieval MRR/Hits vs BM25 |
| `bench/trace_oracle.py` | Dynamic-trace construction-accuracy oracle (§2.3) |
| `bench/inject_contract_fault.py` | Fault injection (rename-rpc / remove-rpc / rename-service) + blast radius |
| `bench/labels/online_boutique_contracts.json` | Hand labels (21 consumers, 9 producers) |
| `bench/results/*.json` | All numbers in this report |
| `tests/test_contract_layer.py` | 7 new tests (proto parsing, Py/Go/JS bindings, deferred stub, multi-line Go chain, queries) |
| `requirements.txt` | `tree-sitter-go`, `rank_bm25` |

All 16 tests pass; `eval_ckg.py` and `eval_polyglot.py` behave as before.

---

## 7. Completion plan — what to build next and how

### 7.1 P0 — Receiver-type inference, class-hierarchy analysis and Eq. (4) (fixes D3; unlocks Table I accuracy columns)
1. **Type facts** during the AST pass: `x = ClassName(...)` → `type[scope][x]=ClassName`; annotated params `def f(x: T)`; `self.attr = T(...)` → `attr_type[class][attr]=T`; function return annotations → type of `y = f()`.
2. **Resolution order** for `base.m()`: (a) `self`/`cls` → declared class, then *all overriding subclasses* (`POLYMORPHIC_CALL`); (b) known receiver type T → `_find_method(T)` ∪ overrides in `subclasses(T)`; (c) module/import-qualified (exists); (d) name-based CHA fallback: all methods named `m` if ≤ K candidates (K≈8), else external.
3. **Eq. (4)**: fit one TF-IDF over all entity texts (name tokens + docstring + code); `c_type_j = softmax(cos(e_caller, e_impl_j)/τ)`, τ≈0.2; store per-edge; expose `--tau`.
4. **Measure** with `bench/trace_oracle.py`: expect recall on click/jinja to rise from 0.13/0.43 toward 0.6–0.8 and disambiguation accuracy from 3–10 % to the 60–90 % range typical of CHA+type-hints; report the *real* number.
5. Also fix D5 (`for`/`with` targets, module-level calls), D6 (aggregate `USES` count into `f_call`), D7 (Python `RETURNS`/`MUTATES`/`FLOWS_TO`; arg→param and return→assignment `FLOWS_TO` edges once calls resolve).

### 7.2 P0 — A real retrieval benchmark and honest Table II (fixes D1, D2, D10)
* **Index every function/class**, not just docstring'd ones: text = split identifiers (camel/snake) + docstring + code.
* **Leakage-free protocol on real repos:** queries = first sentence of a docstring; **strip all docstrings from the index for every method**; target = that function; gold context = target ∪ its *dynamically observed* callees (from the trace oracle) — never from our own static graph.
* **Public data:** CrossCodeEval-Python (has gold cross-file context per example) and RepoBench-R (retrieval split) — both downloadable; Py150 is a corpus, not a retrieval benchmark — drop or use as scale stress only.
* **Metrics:** MRR@5, Hits@1/5, Context Recall@10 (gold ⊆ returned context under a fixed token budget, e.g. 1 500 tokens via `tiktoken`), **Token Redundancy = tokens in returned context not belonging to gold entities ÷ total returned tokens** — same budget for every method.
* **Baselines that can actually be run:** BM25 over entities (done, v2) · TF-IDF over 512-token sliding chunks ("flat dense-style RAG", lexical) · one dense model (`text-embedding-3-large` via API key, or `all-MiniLM-L6-v2` locally) · "Naive CPG" = our graph with Lsyn only · GraphCodeBERT/cAST/Contriever: cite as not re-run unless a checkpoint is wired.

### 7.3 P0 — Ablations (§VII-B)
Add `layers=` masks to `rag_query`/`deterministic_subtree_graft` and rerun §7.2 with Ldep, Lflow, Lsem removed one at a time; report measured deltas instead of −18.4/−31.2/−22.6.

### 7.4 P0 — Incremental (streaming) HR-Build (fixes D8; Tracker Week 14)
Partition all parse facts by owning file (`file_nodes[rel]`, call records, class bases, docstrings, var defs, type facts). `update_files(changed)`: drop owned nodes and file facts → drop all *derived* edges globally (`CALLS/POLYMORPHIC_CALL/EXTENDS/HTTP_CALLS/IMPLEMENTS/CONSUMES/SEMANTIC_SIMILAR`) and orphan stubs → re-parse changed files only → re-run resolution. Parse cost O(Δ), resolution O(|calls|) hash look-ups. **Verify** by asserting node set and edge multiset equality against a from-scratch build after each update; report rebuild-vs-incremental latency per repo (the proposal explicitly wants this measured, not promised).

### 7.5 P1 — Proposal Layers 3–4 and persistence
* **L3 lineage:** `git log --numstat` → `commit::sha` nodes with `TOUCHES` edges to file/function nodes (line ranges); parse CI/CD (`.github/workflows`, `kubernetes-manifests/*.yaml`, `skaffold.yaml` in Online Boutique) → `artifact::image:tag`, `deploy::env/service` nodes; `BUILDS`/`DEPLOYS` edges with time windows.
* **L4 telemetry:** ingest OTel traces (Online Boutique ships OTel; run `docker compose` or use recorded JSON) → `span::` nodes bound to `contract::Service.Rpc` by `rpc.service`/`rpc.method` attributes, then to `IMPLEMENTS` targets → the telemetry→lineage→contract→function path the proposal's Objective 3 needs.
* **Persistence:** Neo4j loader (Cypher `UNWIND` batches from GraphML) so Batch 2 can query with `MATCH (c:rpc_contract)<-[:CONSUMES]-(f)`.
* **Languages:** `tree-sitter-java` (AdService; Train-Ticket is Java) and `tree-sitter-c-sharp` (CartService) through the same adapter contract.

### 7.6 P2 — Agent experiment (or delete the claims)
Wire `deterministic_subtree_graft` as a tool in OpenHands or SWE-agent; run ≥30 cross-service tasks (e.g. the proposal's contract-touching PRs) with/without the tool; log tool-call counts, wall-clock, tokens, resolution rate. Only then can −46 %/−60 % (or whatever is measured) appear in the paper.

---

## 8. Paper1 revision notes (concrete edits)

1. **Abstract/Conclusion:** remove or bracket `96.8 %`, `MRR 0.894`, `95.2 %`, `14.8 %`, `46 %`, `60 %` until §7.1–7.3/7.6 are run; keep throughput with the measured range "0.04–0.09 s/kLOC on 1.5k–29k-LOC repositories".
2. **Fig. 1:** input languages → Python, JavaScript/TypeScript, Go (+ Protobuf contracts); remove Java/C++ or add adapters.
3. **§I typed links:** replace `uses, produces, validates, configures, mutates` with the implemented vocabulary (`CONTAINS, IMPORTS, EXTENDS, CALLS, PASSES_ARG, DEFINES, USES, MUTATES, RETURNS, FLOWS_TO, HTTP_CALLS, IMPLEMENTS, CONSUMES, SEMANTIC_SIMILAR`) or define the missing ones.
4. **§III/§IV:** add the Contract Layer `Lcontract` (this is the proposal's actual novelty and now works) — canonical `service_contract`/`rpc_contract` nodes, `IMPLEMENTS`/`CONSUMES` edges, cross-language binding rules; this differentiates the paper from RepoGraph/LocAgent/CodexGraph (all single-repo).
5. **§IV-A:** either implement Eq. (4) or state that `c_type` is currently uniform over CHA candidates.
6. **§VII-A complexity:** Lsem is Θ(n²) as written; either use sparse thresholded similarity/ANN and re-state, or scope the O(N log N) claim to Lsyn/Ldep.
7. **Table I:** replace with §2.2 + §2.3 (real repos, dynamic-trace P/R, disambiguation accuracy, 2-hop F1) and §2.4 (contract P/R). Rename "Disambiguation Acc" to the oracle definition.
8. **Table II:** regenerate with §7.2 protocol; list only baselines actually run.
9. **§VII-B ablation:** replace with §7.3 measured deltas.
10. **Evaluation section:** add the fault-injection blast-radius experiment (§2.5) — it is a compelling, fully reproducible demonstration of "exact blast-radius awareness".
11. **Threats to validity (new):** single labeller, one microservice system, dynamic trace under-approximates the true call graph (precision is a lower bound), name-based binding heuristics for Go/JS.

---

## 9. Verification checklist for the supervisor (5 minutes)

```bash
unzip SCKG_Build-v2.zip && cd SCKG_Build-v2 && pip install -r requirements.txt
python -m unittest discover -s tests            # expect: Ran 16 tests ... OK
git clone --depth 1 https://github.com/GoogleCloudPlatform/microservices-demo ob
python bench/run_benchmark.py --repo ob --labels bench/labels/online_boutique_contracts.json   # expect P=R=1.0
python bench/inject_contract_fault.py --repo ob --service ShippingService --rpc GetQuote        # expect detected: true, 3 lost
git clone --depth 1 https://github.com/hukkin/tomli && python bench/trace_oracle.py --repo tomli --pytest-args tests  # expect recall≈0.82, precision≈0.98
```
