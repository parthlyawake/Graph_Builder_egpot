# GRAFT-CKG Objective 1 (Build): evidence audit and completion gate

Date: 2026-11-16. Scope: Phase 2 of Vikas Ranjan's BITS PhD proposal, *not* the forward coding agent or autonomous remediation agent.

## Input provenance

- Implementation baseline: `krishna` branch of `Vikas-Personal-Research-Org/Graph_Builder`.
- Initial paper: `Paper_SCKG_v1.pdf`; revised six-page `Paper_SCKG_v1.pdf` explicitly limits exploratory claims.
- Proposal Phase 2: four *proposal* planes: symbolic code structure; cross-service contracts; operational CI/deployment lineage; runtime telemetry at the schema/ingestion level. The implementation's current five *source graph* layers (`Lsyn, Ldep, Lflow, Lsem, Lcontract`) need not be renamed to match proposal layers. Operational evidence is a separate `Loperational` namespace.
- Existing `lineage.py` derives Git commit-to-file `TOUCHES` but does not itself establish commit -> artifact -> deployment -> telemetry bindings.

## Completed implementation increment

- `operational_evidence.py` ingests an explicit `schema_version=1` JSON manifest of builds, artifact SHA-256 digests, deployment intervals and OpenTelemetry-style log/metric/span records into a *copy* of a NetworkX MultiDiGraph.
- Binds a source revision to build, build to artifact and deployment, deployment to environment, and an explicitly attributed telemetry signal to deployment.
- Preserves existing source graph edges and guarantees repeat ingestion replaces only nodes owned by `Loperational`.
- Refuses invalid source revision formats, invalid digests, duplicate IDs, missing build/deployment keys, impossible deployment intervals, contradictory service names or out-of-window telemetry.
- Telemetry without explicit deployment ID stays unlinked; no guess-based cross-service or causal link is emitted.
- All records are marked `reported_unverified`. A valid manifest is NOT evidence of a signed and verified SLSA attestation. No source function is inferred to have caused an observed incident.
- `bench/ingest_operational_manifest.py` integrates with the existing `graph_io.load_graph_json` and writes a deterministic graph JSON export plus a provenance report. Unit regression tests cover valid chains and adversarial cases.
- `otlp_manifest.py` parses OTLP/JSON exports with `resourceSpans`, `resourceLogs`, and `resourceMetrics`; only explicit `sckg.deployment.id` can associate a signal with a deployment. No service-only guessing.
- `slsa_manifest.py` parses explicitly identified SLSA provenance v1 source revisions and SHA-256 artifact subjects into manifest build rows. This does not verify cryptographic signatures or builder trust.
- Local focused tests: 10 passed (including CLI export/reload). GitHub Actions runs the complete repository regression suite; do not equate passing fixture tests with empirical accuracy.

## Schema example

```json
{
  "schema_version": 1,
  "builds": [{"id": "build1", "repo_id": "checkout", "commit_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "artifact_digest": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "builder_id": "https://ci.example/builder", "service_name": "checkout", "timestamp": "2026-11-15T09:00:00Z"}],
  "deployments": [{"id": "deploy1", "build_id": "build1", "environment": "staging", "start_time": "2026-11-15T10:00:00Z"}],
  "signals": [{"id": "span1", "type": "span", "timestamp": "2026-11-15T10:02:00Z", "deployment_id": "deploy1", "resource": {"service.name": "checkout", "service.version": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}]
}
```

```bash
python bench/ingest_operational_manifest.py \
  --graph /path/to/exported_code_graph.json \
  --manifest /path/to/operational_manifest.json \
  --output /path/to/combined_graph.json \
  --report /path/to/operational_ingestion_report.json
```

## What remains before submission

| Gate | Current evidence | Required outcome |
|---|---|---|
| Symbolic accuracy | Source parser tests and grammar coverage, not exhaustive real-repo node annotation | Independent reference labels and per-language node P/R/F1 on pinned realistic sources |
| Contract accuracy | Controlled 6-positive HTTP and 21-triple seven-relation fixtures | Independently adjudicated, *closed* real-source scopes with hard negatives, precision/recall and evidence spans on four proposal systems |
| Operational data acquisition | JSON manifest bridge, Git `TOUCHES`, and unverified SLSA v1 statement parser | Import real CI provenance, validate signed SLSA statements (if available), ingest real deployment metadata, and prove identity joins against trusted records |
| Telemetry acquisition | OTLP/JSON logs, traces and metric data-point adapter plus conservative manifest joins | Live OTLP ingestion or representative exported traces from all four benchmark systems, service/deployment identity controls, complete scope audit |
| Persistence | NetworkX and JSON export/import, Neo4j export | Repeat-process durable storage with tested graph migrations, query contracts, concurrency and restart validation |
| Incremental maintenance | 3/3 equivalence for two pinned single-repo edit cases | Real cross-repo contract + deployment deltas, file deletion, history reorder, multi-edit and scaling study; compare node attributes, typed edge multiplicities and provenance |
| Comparative baselines | In-project BM25/LSA/hybrids | Rerun selected published/official implementations on identical tasks and candidate sets; no imported scores |
| Human annotation | 27 source-inspected localization questions | Second independent annotator, measured agreement, adjudication and cross-service fault/impact tasks |

### Known benchmark risk

The existing `bench/results/graph_builder_audit/sock-shop/summary.json` audits **four parsed files**, 31 nodes and 64 edges; do **not** portray that as full Sock Shop coverage. Train-Ticket and DeathStarBench summaries count graph construction but are not edge precision/recall gold labels. Use absolute pinned commit hashes and audited source scopes in all tables.

### Paper correction

The original draft's 0.894 MRR@5, 14.8% token redundancy, 46% tool-call improvement and 60% agent-latency claims must not be published. The existing corrected study reports LSA 0.638 MRR@5 vs static/contract hybrid 0.514 on 27 tasks; graph context inclusion decreases from 0.815 to 0.444 without dependency edges. Results remain exploratory without independent adjudication.

## Research references (not same-dataset numerical baselines)

- RepoGraph (ICLR 2025): https://proceedings.iclr.cc/paper_files/paper/2025/hash/4a4a3c197deac042461c677219efd36c-Abstract-Conference.html
- LocAgent (ACL 2025): https://aclanthology.org/2025.acl-long.426/
- CodexGraph (NAACL 2025): https://aclanthology.org/2025.naacl-long.7/
- GraphCoder (ASE 2024): https://conf.researchr.org/details/ase-2024/ase-2024-research/46/GraphCoder-Enhancing-Repository-Level-Code-Completion-via-Coarse-to-fine-Retrieval-B
- SLSA Provenance specification: https://slsa.dev/spec/v1.0/provenance
- OpenTelemetry service resource conventions: https://opentelemetry.io/docs/specs/semconv/resource/service/
- OTLP transport and JSON mapping: https://opentelemetry.io/docs/specs/otlp/

**Interpretation:** This increment implements one missing Build substrate capability. It does not complete all Phase 2 deliverables and is not a submission-ready evaluation.
