"""Evidence-grounded CI/CD and OpenTelemetry graph enrichment for GRAFT-CKG.

This is ingestion, not causal attribution. A caller-supplied manifest is unverified
until independently authenticated; the graph preserves that provenance status.
The function returns a new graph and never mutates an existing code graph.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any

import networkx as nx

_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
_DIGEST = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
_TYPES = frozenset({"log", "metric", "span"})
_LAYER = "Loperational"


def _text(record: dict, key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a nonempty string")
    return value.strip()


def _timestamp(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def _records(doc: dict, field: str) -> dict[str, dict]:
    rows = doc.get(field, [])
    if not isinstance(rows, list):
        raise ValueError(f"{field} must be an array")
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"{field} entries must be objects")
        rid = _text(row, "id")
        if rid in result:
            raise ValueError(f"duplicate {field} id: {rid}")
        result[rid] = row
    return result


def _node(graph: nx.MultiDiGraph, ident: str, **attrs: Any) -> None:
    if ident in graph:
        raise ValueError(f"operational ID collides with an existing node: {ident}")
    graph.add_node(ident, layer=_LAYER, **attrs)


def _edge(graph: nx.MultiDiGraph, src: str, dst: str, relation: str) -> None:
    if src not in graph or dst not in graph:
        raise ValueError(f"dangling operational edge: {src} -> {dst}")
    graph.add_edge(src, dst, key=f"{_LAYER}:{relation}:{dst}",
                   relation=relation, layer=_LAYER,
                   evidence="manifest", verification="reported_unverified")


def ingest_operational_evidence(
    code_graph: nx.MultiDiGraph, manifest: dict
) -> tuple[nx.MultiDiGraph, dict]:
    """Materialize validated operational evidence as a separate, replaceable layer.

    Schema version 1 manifest contains builds, deployments and signals. Build
    records explicitly bind repo_id+commit_sha to a digest-identified artifact.
    Deployments explicitly identify their build, and signals their deployment.
    Signals with no deployment_id remain unlinked rather than being joined by
    an ambiguous service name or time alone. All inputs remain *unverified*.
    """
    if not isinstance(code_graph, nx.MultiDiGraph):
        raise TypeError("code_graph must be a networkx.MultiDiGraph")
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("expected operational evidence schema_version=1")
    builds = _records(manifest, "builds")
    deployments = _records(manifest, "deployments")
    signals = _records(manifest, "signals")
    digest = sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":")).encode("utf-8")).hexdigest()
    graph = code_graph.copy()
    for nid, attrs in list(graph.nodes(data=True)):
        if attrs.get("layer") == _LAYER:
            graph.remove_node(nid)
    graph.graph["operational_manifest_sha256"] = digest
    graph.graph["operational_evidence_verification"] = "reported_unverified"
    build_nodes = {}
    for key, record in builds.items():
        repo = _text(record, "repo_id")
        revision = _text(record, "commit_sha").lower()
        if not _SHA.fullmatch(revision):
            raise ValueError("commit_sha must be a full 40-hex Git SHA-1 identifier")
        artifact = _text(record, "artifact_digest").lower()
        if not _DIGEST.fullmatch(artifact):
            raise ValueError("artifact_digest must be sha256:<64 hex digits>")
        timestamp = _timestamp(_text(record, "timestamp")).isoformat()
        name = f"build::{key}"
        _node(graph, name, type="build", name=key, repo_id=repo,
              service_name=_text(record, "service_name"), timestamp=timestamp,
              builder_id=_text(record, "builder_id"), verification="reported_unverified")
        commit_id = f"source_revision::{repo}::{revision}"
        if commit_id not in graph:
            _node(graph, commit_id, type="source_revision", name=revision,
                  repo_id=repo, sha=revision, verification="reported_unverified")
        artifact_id = f"artifact::{artifact}"
        if artifact_id not in graph:
            _node(graph, artifact_id, type="artifact", name=artifact,
                  digest=artifact, verification="reported_unverified")
        _edge(graph, commit_id, name, "BUILT_BY")
        _edge(graph, name, artifact_id, "PRODUCED_ARTIFACT")
        build_nodes[key] = (name, _text(record, "service_name"), revision, artifact,
                            _timestamp(_text(record, "timestamp")))
    deployment_nodes = {}
    for key, record in deployments.items():
        build_key = _text(record, "build_id")
        if build_key not in build_nodes:
            raise ValueError(f"deployment {key} references unknown build {build_key}")
        begin = _timestamp(_text(record, "start_time"))
        end_str = record.get("end_time")
        end = _timestamp(end_str) if end_str is not None else None
        if end is not None and end <= begin:
            raise ValueError("deployment end_time must follow start_time")
        if begin < build_nodes[build_key][4]:
            raise ValueError("deployment cannot start before its build completed")
        name = f"deployment::{key}"
        env = _text(record, "environment")
        env_id = f"environment::{env}"
        _node(graph, name, type="deployment", name=key, environment=env,
              start_time=begin.isoformat(), end_time=end.isoformat() if end else None,
              service_name=build_nodes[build_key][1], verification="reported_unverified")
        if env_id not in graph:
            _node(graph, env_id, type="environment", name=env,
                  verification="reported_unverified")
        _edge(graph, build_nodes[build_key][0], name, "DEPLOYED_AS")
        _edge(graph, name, env_id, "DEPLOYED_IN")
        deployment_nodes[key] = (name, build_nodes[build_key][1], begin, end,
                                 build_nodes[build_key][2], build_nodes[build_key][3])
    unmatched = []
    for key, record in signals.items():
        kind = _text(record, "type")
        if kind not in _TYPES:
            raise ValueError(f"signal type must be one of {sorted(_TYPES)}")
        event_time = _timestamp(_text(record, "timestamp"))
        resource = record.get("resource", {})
        if not isinstance(resource, dict):
            raise ValueError("signal resource must be an object")
        service = resource.get("service.name")
        if service is not None and (not isinstance(service, str) or not service):
            raise ValueError("service.name must be a nonempty string")
        version = resource.get("service.version")
        if version is not None and (not isinstance(version, str) or not version):
            raise ValueError("service.version must be a nonempty string")
        event_id = f"telemetry::{key}"
        _node(graph, event_id, type="telemetry", name=key, signal_type=kind,
              timestamp=event_time.isoformat(), service_name=service,
              service_version=version, verification="reported_unverified")
        deployment_key = record.get("deployment_id")
        if deployment_key is None:
            unmatched.append(key)
            continue
        if not isinstance(deployment_key, str) or deployment_key not in deployment_nodes:
            raise ValueError(f"signal {key} references unknown deployment {deployment_key}")
        dep_node, deployed_service, start, end, revision, artifact = deployment_nodes[deployment_key]
        if service is not None and service != deployed_service:
            raise ValueError(f"signal {key} service differs from deployed service")
        # When the resource version *explicitly* uses a Git SHA or artifact
        # digest, a contradictory identity must not be linked to deployment.
        if version is not None and _SHA.fullmatch(version) and version.lower() != revision:
            raise ValueError(f"signal {key} revision differs from deployed source")
        if version is not None and _DIGEST.fullmatch(version) and version.lower() != artifact:
            raise ValueError(f"signal {key} digest differs from deployed artifact")
        if event_time < start or (end is not None and event_time >= end):
            raise ValueError(f"signal {key} falls outside deployment interval")
        _edge(graph, event_id, dep_node, "OBSERVED_DURING")
    return graph, {"manifest_sha256": digest, "builds": len(builds),
                   "deployments": len(deployments), "signals": len(signals),
                   "unlinked_signals": sorted(unmatched),
                   "verification": "reported_unverified"}
