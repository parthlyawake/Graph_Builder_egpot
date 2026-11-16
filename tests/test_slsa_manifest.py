import pytest
from slsa_manifest import slsa_to_builds
from operational_evidence import ingest_operational_evidence
import networkx as nx


def example():
    return {"predicateType": "https://slsa.dev/provenance/v1",
            "subject": [{"name": "checkout", "digest": {"sha256": "b"*64}}],
            "predicate": {"buildDefinition": {"resolvedDependencies": [
                {"uri": "git+https://example.org/checkout.git", "digest": {"gitCommit": "a"*40}}]},
                "runDetails": {"builder": {"id": "https://ci.example/builder"},
                               "metadata": {"finishedOn": "2026-11-15T09:00:00Z"}}}}


def test_translates_provenance_as_unverified_manifest():
    builds = slsa_to_builds(example(), repo_id="checkout", service_name="checkout", build_id="build-1")
    graph, report = ingest_operational_evidence(nx.MultiDiGraph(), {"schema_version": 1, "builds": builds})
    assert report["builds"] == 1
    assert graph.has_edge("source_revision::checkout::"+"a"*40, "build::build-1-0")
    assert graph.nodes["build::build-1-0"]["verification"] == "reported_unverified"


def test_rejects_ambiguous_or_missing_identity():
    data = example()
    data["predicate"]["buildDefinition"]["resolvedDependencies"].append(
        {"uri": "git+https://example.org/other.git", "digest": {"gitCommit": "c"*40}})
    with pytest.raises(ValueError, match="exactly one"):
        slsa_to_builds(data, repo_id="checkout", service_name="checkout", build_id="x")
    data = example()
    data["subject"][0]["digest"] = {}
    with pytest.raises(ValueError, match="SHA-256"):
        slsa_to_builds(data, repo_id="checkout", service_name="checkout", build_id="x")
