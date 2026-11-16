"""Opt-in DSSE Ed25519 signature verification for SLSA v1 provenance.

Only verifies an envelope under a caller-configured trusted key, expected
builder, expected source and artifact digest. This is *not* an SLSA level
assessment, Sigstore/Fulcio/Rekor verification or proof of a real deployment.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from slsa_manifest import slsa_to_builds


def _b64(value: str) -> bytes:
    if not isinstance(value, str):
        raise ValueError("DSSE value must be base64 string")
    try:
        return base64.b64decode(value, validate=True)
    except Exception as exc:
        raise ValueError("Invalid DSSE base64 encoding") from exc


def _pae(payload_type: str, payload: bytes) -> bytes:
    # DSSE pre-authentication encoding: https://github.com/secure-systems-lab/dsse
    typ = payload_type.encode("utf-8")
    return b"DSSEv1 " + str(len(typ)).encode() + b" " + typ + b" " + str(len(payload)).encode() + b" " + payload


def verify_dsse_build_provenance(
    envelope: dict, *,
    trusted_public_keys: dict[str, bytes],
    expected_builder_id: str,
    expected_source_uri: str,
    expected_commit_sha: str,
    expected_repo_id: str,
    service_name: str,
    artifact_path: str | Path,
) -> dict:
    """Return measured verification facts, fail closed on any mismatch.

    The caller is responsible for securely provisioning trusted public keys
    and for associating expected repository and builder identities with a
    trust policy. A passing *locally generated* fixture is not real-world
    production provenance.
    """
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    if not isinstance(envelope, dict):
        raise ValueError("DSSE envelope must be an object")
    payload_type = envelope.get("payloadType")
    if payload_type != "application/vnd.in-toto+json":
        raise ValueError("Unsupported DSSE payload type")
    payload = _b64(envelope.get("payload"))
    signatures = envelope.get("signatures")
    if not isinstance(signatures, list) or len(signatures) != 1:
        raise ValueError("Require exactly one configured DSSE signature")
    signature = signatures[0]
    if not isinstance(signature, dict):
        raise ValueError("Malformed DSSE signature")
    key_id = signature.get("keyid")
    if not isinstance(key_id, str) or key_id not in trusted_public_keys:
        raise ValueError("Untrusted provenance signing key")
    raw_key = trusted_public_keys[key_id]
    try:
        Ed25519PublicKey.from_public_bytes(raw_key).verify(
            _b64(signature.get("sig")), _pae(payload_type, payload))
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("Invalid provenance DSSE signature") from exc
    try:
        statement = json.loads(payload)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Malformed signed statement JSON") from exc
    if not isinstance(statement, dict) or statement.get("_type") != "https://in-toto.io/Statement/v1":
        raise ValueError("Expected in-toto Statement v1")
    if not all(isinstance(value, str) and value for value in (
            expected_builder_id, expected_source_uri, expected_commit_sha,
            expected_repo_id, service_name)):
        raise ValueError("All expected source and builder identities are required")
    if statement.get("predicate", {}).get("runDetails", {}).get("builder", {}).get("id") != expected_builder_id:
        raise ValueError("Unexpected builder identity")
    deps = statement.get("predicate", {}).get("buildDefinition", {}).get("resolvedDependencies", [])
    exact = [d for d in deps if isinstance(d, dict) and d.get("uri") == expected_source_uri]
    if len(exact) != 1 or exact[0].get("digest", {}).get("gitCommit", "").lower() != expected_commit_sha.lower():
        raise ValueError("Wrong source repository or commit")
    builds = slsa_to_builds(statement, repo_id=expected_repo_id,
                           service_name=service_name, build_id="signature-verified")
    artifact_digest = hashlib.sha256(Path(artifact_path).read_bytes()).hexdigest()
    matched = [b for b in builds if b["artifact_digest"] == "sha256:" + artifact_digest]
    if len(matched) != 1 or matched[0]["commit_sha"] != expected_commit_sha.lower():
        raise ValueError("Signed provenance subject does not match artifact bytes")
    from datetime import datetime, timezone
    finished_at = matched[0]["timestamp"]
    try:
        parsed = datetime.fromisoformat(finished_at.replace("Z","+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("missing timezone")
        finished_at_utc = parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError) as exc:
        raise ValueError("Signed build finish time must be a timezone-aware timestamp") from exc
    return {"verification": "dsse_ed25519_valid_under_caller_trust_policy",
            "build_finished_at_utc": finished_at_utc,
            "signing_key_id": key_id, "builder_id": expected_builder_id,
            "source_uri": expected_source_uri, "source_commit": expected_commit_sha.lower(),
            "artifact_sha256": artifact_digest,
            "statement_subject_count": len(builds),
            "limitations": [
                "Not a SLSA level assessment or Sigstore transparency validation.",
                "Trust in the caller-supplied signing key is an external assumption.",
                "A signed artifact claim does not authenticate deployment or telemetry events."
            ]}


def annotate_verified_build(
    graph, build_id: str, envelope: dict, *,
    trusted_public_keys: dict[str, bytes],
    expected_builder_id: str, expected_source_uri: str,
    expected_commit_sha: str, expected_repo_id: str,
    service_name: str, artifact_path: str | Path,
):
    """Return a copy with ONLY verified build edges promoted.

    Never upgrade DEPLOYED_AS, DEPLOYED_IN or OBSERVED_DURING edges:
    an authenticated build statement does not attest to a deployment.
    """
    import networkx as nx
    if not isinstance(graph, nx.MultiDiGraph):
        raise TypeError("Expected MultiDiGraph")
    verified = verify_dsse_build_provenance(
        envelope, trusted_public_keys=trusted_public_keys,
        expected_builder_id=expected_builder_id,
        expected_source_uri=expected_source_uri,
        expected_commit_sha=expected_commit_sha,
        expected_repo_id=expected_repo_id, service_name=service_name,
        artifact_path=artifact_path)
    build_nid = "build::" + build_id
    src_nid = f"source_revision::{expected_repo_id}::{verified['source_commit']}"
    art_nid = "artifact::sha256:" + verified["artifact_sha256"]
    if build_nid not in graph or src_nid not in graph or art_nid not in graph:
        raise ValueError("Signed build objects do not match graph identities")
    data = graph.nodes[build_nid]
    if (data.get("builder_id") != expected_builder_id or
            data.get("service_name") != service_name or
            data.get("repo_id") != expected_repo_id or
            data.get("timestamp") != verified["build_finished_at_utc"]):
        raise ValueError("Signed build metadata differs from graph")
    for u,v,relation in ((src_nid,build_nid,"BUILT_BY"),
                         (build_nid,art_nid,"PRODUCED_ARTIFACT")):
        found = [(k, d) for k,d in graph[u][v].items()
                 if d.get("relation")==relation] if graph.has_edge(u,v) else []
        if len(found) != 1:
            raise ValueError("Missing or ambiguous signed build edge: " + relation)
    result=graph.copy()
    result.nodes[build_nid]["verification"] = verified["verification"]
    result.nodes[build_nid]["signing_key_id"] = verified["signing_key_id"]
    result.nodes[build_nid]["verified_artifact_sha256"] = verified["artifact_sha256"]
    for u,v,relation in ((src_nid,build_nid,"BUILT_BY"),
                         (build_nid,art_nid,"PRODUCED_ARTIFACT")):
        for key, attrs in result[u][v].items():
            if attrs.get("relation") == relation:
                attrs["verification"] = verified["verification"]
                attrs["signing_key_id"] = verified["signing_key_id"]
    return result, verified
