"""Correct source provenance for deferred contract edges, including updates."""
from __future__ import annotations

import contextlib
import io
from pathlib import Path
import shutil

from graft_ckg import CKGBuilder
from bench.paper_performance import semantic_graph_signature


def test_contract_edges_use_caller_or_implementer_source_file(tmp_path):
    original = Path(__file__).resolve().parents[1]/"examples"/"polyglot_system"
    repo = tmp_path/"polyglot"
    shutil.copytree(original, repo)
    with contextlib.redirect_stdout(io.StringIO()):
        initial = CKGBuilder(str(repo))
        initial.build()
    generated = [(u,v,attrs) for u,v,attrs in initial.graph.edges(data=True)
                 if attrs.get("relation") in {"CONSUMES","IMPLEMENTS"} and
                 attrs.get("layer")=="Lcontract" and "metadata" in attrs]
    assert generated, "fixture should have source-contract relations"
    for source, _target, attrs in generated:
        source_file=initial.graph.nodes[source].get("file")
        if source_file:
            assert attrs.get("id_ctx")==source_file
            assert attrs.get("metadata",{}).get("id_ctx")==source_file

    # An edit with no contract semantic change must not attribute unchanged
    # contracts to the last parsed Go/Python source file.
    rel="services/shipping_go/main.go"
    with (repo/rel).open("a",encoding="utf-8") as fd:
        fd.write("\n// harmless line comment added\n")
    with contextlib.redirect_stdout(io.StringIO()):
        initial.update_files([rel])
        fresh=CKGBuilder(str(repo))
        fresh.build()
    for graph in (initial.graph,fresh.graph):
        for source,target,attrs in graph.edges(data=True):
            if attrs.get("layer") != "Lcontract" or attrs.get("relation") not in {"CONSUMES","IMPLEMENTS"}:
                continue
            if "metadata" in attrs and graph.nodes[source].get("file"):
                assert attrs["id_ctx"]==graph.nodes[source]["file"]
    assert semantic_graph_signature(initial.graph)==semantic_graph_signature(fresh.graph)
