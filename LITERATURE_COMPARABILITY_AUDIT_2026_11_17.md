# Related work and baseline comparability audit (2026-11-17)

All metadata below comes from the linked primary conference/standards pages, not guessed from historic benchmark JSON.

| Work | Verified primary source | Distinct task from GRAFT-CKG Objective 1 |
|---|---|---|
| **RepoGraph: Enhancing AI Software Engineering with Repository-level Code Graph** — Siru Ouyang et al., ICLR 2025 | https://proceedings.iclr.cc/paper_files/paper/2025/hash/4a4a3c197deac042461c677219efd36c-Abstract-Conference.html | Defines code-level graph/navigation as a plugin; reports SWE-bench issue resolution and CrossCodeEval, not independent multi-service gRPC/Thrift/AMQP extraction precision |
| **CodexGraph: Bridging Large Language Models and Code Repositories via Code Graph Databases** — Xiangyan Liu et al., NAACL 2025 | https://aclanthology.org/2025.naacl-long.7/ | LLM code graph database querying assessed on CrossCodeEval, SWE-bench and EvoCodeBench, not our exact code-to-deployment evidence chain |
| **LocAgent: Graph-Guided LLM Agents for Code Localization** — Zhaoling Chen et al., ACL 2025 | https://aclanthology.org/2025.acl-long.426/ | Uses heterogeneous code graphs for code localization; its published file-level/issue numbers do not transfer to our function-level 27-query MRR |
| **CodePlan: Repository-level Coding using LLMs and Planning** — Ramakrishna Bairi et al., FSE 2024 | https://www.microsoft.com/en-us/research/publication/codeplan-repository-level-coding-using-llms-and-planning-2/ | Incremental dependency/change-impact planning for multi-file edits; no directly equivalent four-microservice source graph closed-scope precision |
| **SLSA v1 provenance** | https://slsa.dev/spec/v1.0/provenance | Specifies build provenance fields, not self-authenticating JSON nor a deployment attestation |
| **OpenTelemetry resource and OTLP conventions** | https://opentelemetry.io/docs/specs/semconv/resource/ and https://opentelemetry.io/docs/specs/otlp/ | Identity and event schema standards, not proof that a specific source function caused a runtime span |

## Responsible comparison protocol

1. **Internal retrieval**: R0 BM25 vs R1 LSA vs R3/R5/R9 graph hybrids at the same source revision, 27 questions, exact IDs, candidates, token budget and k; honest within-cohort paired bootstrap. This is implemented and measured.
2. **Layer importance**: post-construction edge removal with held-fixed ranking or graft stage; do not call these parser training/independent graph construction ablations. These are implemented, measured and have limits.
3. **Build correctness**: on independently human-adjudicated complete code/contract scopes, compare true source-declaration/contract-edge TP/FP/FN against alternate builders. No same-task independent published baseline has been reproduced on the required polyglot protocol mix yet.
4. **Performance**: report real source, change type, CPU, Python, alloc tracer, three-run median, structural and semantic-attribute equivalence separately. Do not claim an update speedup with equivalent outputs unless semantic equivalence is true for the specified case.
5. **External methods**: if a method cannot ingest Thrift, AMQP, Go, Java or versioned artifact identities, report unsupported scope separately. Never assign it missing results as a measured zero or quote a non-matching published benchmark as a numerical baseline.

## Publication reference audit

The revised preprint `Paper_SCKG_v1.pdf` correctly lists RepoGraph (Ouyang et al., 2025) and CodexGraph (Liu et al., 2025) in the visible bibliography. The initial `Paper1.pdf` performance claims are marked non-citable in `PUBLICATION_EVIDENCE_AUDIT_2026_11_17.md`.

Neither a literature survey nor a working external code checkout substitutes for a same-task external baseline experiment. This audit does not invent one.
