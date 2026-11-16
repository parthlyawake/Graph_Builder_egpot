"""End-to-end *workflow-local fixture*, not production CI/deployment proof."""
from __future__ import annotations

import base64
import contextlib
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import io
import json
import subprocess

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from graft_ckg import CKGBuilder
from lineage import LineageLayer
from lineage_bridge import bridge_git_lineage
from operational_evidence import ingest_operational_evidence
from provenance_verification import annotate_verified_build, _pae
from sqlite_graph_store import SQLiteGraphStore


def git(root,*args):
    return subprocess.check_output(["git",*args],cwd=root,text=True).strip()


def test_full_chain_preserves_verified_and_unverified_boundaries(tmp_path):
    git(tmp_path,"init","-q")
    git(tmp_path,"config","user.name","Fixture")
    git(tmp_path,"config","user.email","fixture@example.test")
    (tmp_path/"app.py").write_text("def handle():\n    return 1\n",encoding="utf-8")
    git(tmp_path,"add",".")
    git(tmp_path,"commit","-qm","pinned source")
    commit=git(tmp_path,"rev-parse","HEAD")
    with contextlib.redirect_stdout(io.StringIO()):
        builder=CKGBuilder(str(tmp_path))
        builder.build()
        LineageLayer(builder).ingest(max_commits=1)
    commit_time=datetime.fromtimestamp(int(git(tmp_path,"show","-s","--format=%ct",commit)), tz=timezone.utc)
    build_time=(commit_time + timedelta(seconds=10)).isoformat()
    deploy_time=(commit_time + timedelta(seconds=20)).isoformat()
    trace_time=(commit_time + timedelta(seconds=30)).isoformat()
    artifact=tmp_path/"artifact.bin"
    artifact.write_bytes(b"deterministic output artifact from this CI fixture")
    digest=sha256(artifact.read_bytes()).hexdigest()
    builder_id="https://ci.example/fixture-builder"
    source_uri="git+https://github.com/example/fixture.git"
    manifest={
        "schema_version":1,
        "builds":[{"id":"build-1","repo_id":"demo","service_name":"demo",
                   "builder_id":builder_id,"commit_sha":commit,
                   "artifact_digest":"sha256:"+digest,"timestamp":build_time}],
        "deployments":[{"id":"deployment-1","build_id":"build-1",
                        "environment":"fixture-staging",
                        "start_time":deploy_time}],
        "signals":[{"id":"span-1","type":"span","timestamp":trace_time,
                    "deployment_id":"deployment-1",
                    "resource":{"service.name":"demo","service.version":commit}}]
    }
    graph, report=ingest_operational_evidence(builder.graph, manifest)
    assert report["verification"]=="reported_unverified"
    graph, link_report=bridge_git_lineage(graph,repo_id="demo",checkout=tmp_path)
    assert len(link_report["linked"])==1
    statement={
        "_type":"https://in-toto.io/Statement/v1",
        "predicateType":"https://slsa.dev/provenance/v1",
        "subject":[{"name":"artifact.bin","digest":{"sha256":digest}}],
        "predicate":{
            "buildDefinition":{"resolvedDependencies":[{"uri":source_uri,
                                                         "digest":{"gitCommit":commit}}]},
            "runDetails":{"builder":{"id":builder_id},
                          "metadata":{"finishedOn":build_time}}
        }
    }
    key=Ed25519PrivateKey.generate()
    pub=key.public_key().public_bytes(encoding=serialization.Encoding.Raw,
                                      format=serialization.PublicFormat.Raw)
    payload=json.dumps(statement,sort_keys=True).encode("utf-8")
    env={"payloadType":"application/vnd.in-toto+json",
         "payload":base64.b64encode(payload).decode("ascii"),
         "signatures":[{"keyid":"fixture-key","sig":base64.b64encode(key.sign(
             _pae("application/vnd.in-toto+json",payload))).decode("ascii")}]}
    signed, evidence=annotate_verified_build(
        graph,"build-1",env,trusted_public_keys={"fixture-key":pub},
        expected_builder_id=builder_id,expected_source_uri=source_uri,
        expected_commit_sha=commit,expected_repo_id="demo",
        service_name="demo",artifact_path=artifact)
    assert evidence["verification"]=="dsse_ed25519_valid_under_caller_trust_policy"
    assert signed.has_edge("source_revision::demo::"+commit,"commit::"+commit[:12])
    assert signed.has_edge("commit::"+commit[:12],"file::app.py")
    assert signed.nodes["build::build-1"]["verification"]==evidence["verification"]
    assert signed["build::build-1"]["deployment::deployment-1"][
        "Loperational:DEPLOYED_AS:deployment::deployment-1"]["verification"]=="reported_unverified"
    assert signed["telemetry::span-1"]["deployment::deployment-1"][
        "Loperational:OBSERVED_DURING:deployment::deployment-1"]["verification"]=="reported_unverified"
    db=SQLiteGraphStore(tmp_path/"graph.sqlite")
    db.save("revision-1",signed)
    recovered=SQLiteGraphStore(tmp_path/"graph.sqlite").load()
    assert recovered.number_of_nodes()==signed.number_of_nodes()
    assert recovered.number_of_edges()==signed.number_of_edges()
    assert recovered.nodes["build::build-1"]["signing_key_id"]=="fixture-key"
