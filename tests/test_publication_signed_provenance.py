"""Cryptographic fixture verifies trust gate behavior, not production provenance."""
from __future__ import annotations

import base64
import hashlib
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from provenance_verification import verify_dsse_build_provenance, _pae


BUILDER = "https://trusted.example/builder/v1"
SOURCE = "git+https://github.com/example/service.git"
SHA = "a" * 40


def _signed(tmp_path):
    artifact = tmp_path / "app.bin"
    artifact.write_bytes(b"compiled fixture artifact")
    subject_digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    statement = {
        "_type": "https://in-toto.io/Statement/v1",
        "predicateType": "https://slsa.dev/provenance/v1",
        "subject": [{"name": "app.bin", "digest": {"sha256": subject_digest}}],
        "predicate": {
            "buildDefinition": {"resolvedDependencies": [
                {"uri": SOURCE, "digest": {"gitCommit": SHA}}]},
            "runDetails": {"builder": {"id": BUILDER},
                           "metadata": {"finishedOn": "2026-11-16T09:00:00Z"}}
        }
    }
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)
    payload = json.dumps(statement, sort_keys=True).encode()
    envelope = {"payloadType": "application/vnd.in-toto+json",
                "payload": base64.b64encode(payload).decode(),
                "signatures": [{"keyid": "known-fixture-key",
                                "sig": base64.b64encode(private_key.sign(
                                    _pae("application/vnd.in-toto+json", payload))).decode()}]}
    expected = {"trusted_public_keys": {"known-fixture-key": public_key},
                "expected_builder_id": BUILDER, "expected_source_uri": SOURCE,
                "expected_commit_sha": SHA, "expected_repo_id": "service",
                "service_name": "app", "artifact_path": artifact}
    return envelope, expected


def test_valid_configured_dsse_signature_and_bytes(tmp_path):
    envelope, args = _signed(tmp_path)
    result = verify_dsse_build_provenance(envelope, **args)
    assert result["verification"] == "dsse_ed25519_valid_under_caller_trust_policy"
    assert result["artifact_sha256"] == hashlib.sha256(args["artifact_path"].read_bytes()).hexdigest()
    assert "SLSA level" in result["limitations"][0]


@pytest.mark.parametrize("condition", [
    "tampered-signature", "untrusted-key", "wrong-builder", "wrong-source",
    "wrong-sha", "different-artifact", "wrong-payload-type", "unsigned"
])
def test_provenance_fails_closed(tmp_path, condition):
    envelope, args = _signed(tmp_path)
    if condition == "tampered-signature":
        envelope["signatures"][0]["sig"] = base64.b64encode(b"wrong signature").decode()
    elif condition == "untrusted-key":
        args["trusted_public_keys"] = {}
    elif condition == "wrong-builder":
        args["expected_builder_id"] = "https://untrusted.example/builder"
    elif condition == "wrong-source":
        args["expected_source_uri"] = "git+https://example.net/unrelated.git"
    elif condition == "wrong-sha":
        args["expected_commit_sha"] = "c" * 40
    elif condition == "different-artifact":
        args["artifact_path"].write_bytes(b"tampered binary")
    elif condition == "wrong-payload-type":
        envelope["payloadType"] = "text/plain"
    elif condition == "unsigned":
        envelope["signatures"] = []
    with pytest.raises(ValueError):
        verify_dsse_build_provenance(envelope, **args)
