"""Closed-fixture tests for operational graph integration; not field accuracy."""
import copy
import networkx as nx
import pytest
from operational_evidence import ingest_operational_evidence


def example():
    return {
        "schema_version": 1,
        "builds": [{"id": "ci-1", "repo_id": "checkout", "commit_sha": "a"*40,
                    "artifact_digest": "sha256:"+"b"*64, "service_name": "checkout",
                    "builder_id": "https://ci.example/builder", "timestamp": "2026-11-15T09:00:00Z"}],
        "deployments": [{"id": "rollout-1", "build_id": "ci-1", "environment": "staging",
                         "start_time": "2026-11-15T10:00:00Z",
                         "end_time": "2026-11-15T12:00:00Z"}],
        "signals": [{"id": "span-1", "type": "span", "timestamp": "2026-11-15T11:00:00Z",
                     "deployment_id": "rollout-1", "resource": {"service.name": "checkout", "service.version": "a"*40}},
                    {"id": "unlinked-1", "type": "metric", "timestamp": "2026-11-15T11:02:00Z"}]
    }


def test_evidence_chain_and_idempotent_replacement():
    base = nx.MultiDiGraph()
    base.add_node("checkout/main.go:PlaceOrder", type="function", layer="Lsyn")
    base.add_edge("checkout/main.go:PlaceOrder", "checkout/main.go:PlaceOrder", key="old",
                  relation="CALLS", layer="Ldep")
    before = (base.number_of_nodes(), base.number_of_edges())
    out, report = ingest_operational_evidence(base, example())
    assert before == (base.number_of_nodes(), base.number_of_edges())
    assert out.has_edge("source_revision::checkout::"+"a"*40, "build::ci-1")
    assert out.has_edge("build::ci-1", "artifact::sha256:"+"b"*64)
    assert out.has_edge("build::ci-1", "deployment::rollout-1")
    assert out.has_edge("telemetry::span-1", "deployment::rollout-1")
    assert out.out_degree("telemetry::unlinked-1") == 0
    assert report["unlinked_signals"] == ["unlinked-1"]
    assert out.graph["operational_evidence_verification"] == "reported_unverified"
    twice, _ = ingest_operational_evidence(out, example())
    assert nx.utils.graphs_equal(out, twice)
    assert out.has_edge("checkout/main.go:PlaceOrder", "checkout/main.go:PlaceOrder", key="old")


def test_bad_references_fail_closed_and_keep_original():
    original = nx.MultiDiGraph()
    original.add_node("existing", layer="Lsyn")
    for field, value in [("build_id", "missing"), ("end_time", "2026-11-15T09:00:00Z")]:
        data = example()
        data["deployments"][0][field] = value
        with pytest.raises(ValueError):
            ingest_operational_evidence(original, data)
        assert list(original.nodes) == ["existing"]


def test_signal_mismatch_and_interval_fail_closed():
    for variant in ("unknown", "wrong-service", "outside"):
        data = example()
        row = data["signals"][0]
        if variant == "unknown":
            row["deployment_id"] = "unknown"
        elif variant == "wrong-service":
            row["resource"]["service.name"] = "payment"
        else:
            row["timestamp"] = "2026-11-15T12:00:00Z"
        with pytest.raises(ValueError):
            ingest_operational_evidence(nx.MultiDiGraph(), data)


def test_hash_validation_timezone_collision_and_duplicates():
    data = example()
    data["builds"][0]["commit_sha"] = "short"
    with pytest.raises(ValueError, match="40-hex"):
        ingest_operational_evidence(nx.MultiDiGraph(), data)
    data = example()
    data["builds"][0]["timestamp"] = "2026-11-15T09:00:00"
    with pytest.raises(ValueError, match="timezone"):
        ingest_operational_evidence(nx.MultiDiGraph(), data)
    data = example()
    data["signals"].append(copy.deepcopy(data["signals"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        ingest_operational_evidence(nx.MultiDiGraph(), data)
    base = nx.MultiDiGraph()
    base.add_node("build::ci-1", layer="Lsyn")
    with pytest.raises(ValueError, match="collides"):
        ingest_operational_evidence(base, example())


def test_different_manifest_replaces_only_operational_layer():
    base = nx.MultiDiGraph()
    old, _ = ingest_operational_evidence(base, example())
    modified = example()
    modified["signals"] = []
    new, report = ingest_operational_evidence(old, modified)
    assert "telemetry::span-1" not in new
    assert "telemetry::unlinked-1" not in new
    assert old.graph["operational_manifest_sha256"] != report["manifest_sha256"]


def test_rejects_deployment_before_build_and_contradictory_resource_version():
    data = example()
    data["deployments"][0]["start_time"] = "2026-11-15T08:00:00Z"
    with pytest.raises(ValueError, match="before its build"):
        ingest_operational_evidence(nx.MultiDiGraph(), data)
    data = example()
    data["signals"][0]["resource"]["service.version"] = "c" * 40
    with pytest.raises(ValueError, match="revision differs"):
        ingest_operational_evidence(nx.MultiDiGraph(), data)
    data = example()
    data["signals"][0]["resource"]["service.version"] = "sha256:" + "c" * 64
    with pytest.raises(ValueError, match="digest differs"):
        ingest_operational_evidence(nx.MultiDiGraph(), data)
    data = example()
    data["signals"][0]["resource"]["service.version"] = "v2.0.0"
    graph, result = ingest_operational_evidence(nx.MultiDiGraph(), data)
    assert result["signals"] == 2
