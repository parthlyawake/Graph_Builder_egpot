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
    return {"verification": "dsse_ed25519_valid_under_caller_trust_policy",
            "signing_key_id": key_id, "builder_id": expected_builder_id,
            "source_uri": expected_source_uri, "source_commit": expected_commit_sha.lower(),
            "artifact_sha256": artifact_digest,
            "statement_subject_count": len(builds),
            "limitations": [
                "Not a SLSA level assessment or Sigstore transparency validation.",
                "Trust in the caller-supplied signing key is an external assumption.",
                "A signed artifact claim does not authenticate deployment or telemetry events."
            ]}
