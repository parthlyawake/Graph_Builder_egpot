"""Schema changes must never leave stale global contract identity nodes."""
from __future__ import annotations

import contextlib
import io

import pytest

from graft_ckg import CKGBuilder
from bench.paper_performance import semantic_graph_signature


@pytest.mark.parametrize("filename,initial,old,new,old_id,new_id", [
    (
        "contracts/service.thrift",
        "namespace py demo\nservice InventoryService {\n"
        "  void Ping(1: string token)\n}\n",
        "Ping(", "Pong(",
        "contract::thrift::demo.InventoryService.Ping",
        "contract::thrift::demo.InventoryService.Pong",
    ),
    (
        "schemas/item.avsc",
        '{"type":"record","name":"Item","namespace":"com.example",'
        '"fields":[{"name":"price","type":"int"}]}',
        '"price"', '"total"',
        "contract::avro::com.example.Item.field::price",
        "contract::avro::com.example.Item.field::total",
    ),
    (
        "schemas/metadata.pdl",
        "namespace com.example.metadata\nrecord AuditStamp {\n"
        "  actor: string\n}\n",
        "actor:", "owner:",
        "contract::pdl::com.example.metadata.AuditStamp.field::actor",
        "contract::pdl::com.example.metadata.AuditStamp.field::owner",
    ),
    (
        "openapi.yaml",
        "openapi: 3.0.0\ninfo:\n  title: Service\n  version: '1.0'\n"
        "paths:\n  /hello:\n    get:\n      responses:\n"
        "        '200':\n          description: success\n",
        "/hello:", "/goodbye:",
        "endpoint::GET::/hello",
        "endpoint::GET::/goodbye",
    ),
])
def test_global_schema_mutations_reindex_exactly(
        tmp_path,filename,initial,old,new,old_id,new_id):
    f=tmp_path/filename
    f.parent.mkdir(parents=True,exist_ok=True)
    f.write_text(initial,encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        updated=CKGBuilder(str(tmp_path))
        updated.build()
    assert old_id in updated.graph
    raw=f.read_text(encoding="utf-8")
    assert raw.count(old)==1
    f.write_text(raw.replace(old,new,1),encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        updated.update_files([filename])
        fresh=CKGBuilder(str(tmp_path))
        fresh.build()
    assert old_id not in updated.graph
    assert new_id in updated.graph
    assert semantic_graph_signature(updated.graph)==semantic_graph_signature(fresh.graph)


def test_deleted_thrift_schema_cannot_leave_stale_contracts(tmp_path):
    source=tmp_path/"api.thrift"
    source.write_text("namespace py demo\nservice PingService {\n"
                      " void Ping(1: string request)\n}\n",encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        builder=CKGBuilder(str(tmp_path))
        builder.build()
    assert "contract::thrift::demo.PingService.Ping" in builder.graph
    source.unlink()
    with contextlib.redirect_stdout(io.StringIO()):
        builder.update_files([],deleted_rel_paths=["api.thrift"])
        fresh=CKGBuilder(str(tmp_path))
        fresh.build()
    assert "contract::thrift::demo.PingService.Ping" not in builder.graph
    assert semantic_graph_signature(builder.graph)==semantic_graph_signature(fresh.graph)
