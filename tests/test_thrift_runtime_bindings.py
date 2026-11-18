"""Typed Thrift runtime source must not use RPC-name-only guesses."""
import pytest

from graft_ckg import CKGBuilder
from thrift_bindings import bind_thrift_runtime


@pytest.mark.parametrize("padding", ["", ("   // " + "x" * 80 + " {}\n") * 50],
                         ids=["short-body", "call-after-snippet-limit"])
def test_thrift_cpp_handler_and_client_bind_to_idl(tmp_path, padding):
    (tmp_path / "api.thrift").write_text(
        "namespace cpp demo\n"
        "service InventoryService { void Reserve(1: i64 product) }\n"
        "service AuditService { void Reserve(1: i64 product) }\n",
        encoding="utf8",
    )
    rpc = "   client->Reserve(17);\n"
    function = (
        "void perform() {\n"
        "   auto wrapper = pool->Pop();\n"
        "   auto client = wrapper->GetClient();\n"
        + padding + rpc + " }"
    )
    source = (
        "class InventoryHandler : public InventoryServiceIf {\n"
        " public: void Reserve(long product) override { }\n"
        "};\n"
        "struct Caller {\n"
        " ClientPool<ThriftClient<InventoryServiceClient>> *pool;\n"
        " /* é */ " + function + " void neighbor() { AuditServiceClient *client; }\n"
        "};\n"
    ).replace("\n", "\r\n")
    (tmp_path / "handler.cpp").write_bytes(source.encode("utf-8"))
    builder = CKGBuilder(str(tmp_path))
    builder.build()
    graph = builder.graph
    # CKGBuilder already invokes the binder during build().
    target = "contract::thrift::demo.InventoryService.Reserve"
    caller = next(n for n, d in graph.nodes(data=True) if d.get("name") == "perform")
    original_excerpt = function.replace("\n", "\r\n")[:4000]
    assert graph.nodes[caller]["code"] == original_excerpt
    assert ("client->Reserve" in original_excerpt) == (not padding)
    rpc_line = source.splitlines().index(rpc.rstrip("\n")) + 1
    assert graph.edges[caller, target, f"thrift::CONSUMES::{caller}::{target}"] == {
        "relation": "CONSUMES", "layer": "Lcontract", "c_type": 1.0,
        "source_evidence": f"handler.cpp:{rpc_line}", "binding_kind": "typed_thrift_cpp_client",
    }
    assert any(v == target and d.get("relation") == "IMPLEMENTS"
               for _, v, d in graph.edges(data=True))
    assert not any(v == "contract::thrift::demo.AuditService.Reserve"
                   and d.get("relation") in {"IMPLEMENTS", "CONSUMES"}
                   for _, v, d in graph.edges(data=True))
    again = bind_thrift_runtime(graph, [builder])
    assert again == {"implements": 0, "consumes": 0}
