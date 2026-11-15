"""Typed Thrift runtime source must not use RPC-name-only guesses."""
from graft_ckg import CKGBuilder
from thrift_bindings import bind_thrift_runtime


def test_thrift_cpp_handler_and_client_bind_to_idl(tmp_path):
    (tmp_path / "api.thrift").write_text(
        "namespace cpp demo\n"
        "service InventoryService { void Reserve(1: i64 product) }\n"
        "service AuditService { void Reserve(1: i64 product) }\n",
        encoding="utf8",
    )
    (tmp_path / "handler.cpp").write_text(
        "class InventoryHandler : public InventoryServiceIf {\n"
        " public: void Reserve(long product) override { }\n"
        "};\n"
        "struct Caller {\n"
        " ClientPool<ThriftClient<InventoryServiceClient>> *pool;\n"
        " void perform() {\n"
        "   auto wrapper = pool->Pop();\n"
        "   auto client = wrapper->GetClient();\n"
        "   client->Reserve(17);\n"
        " }\n"
        "};\n",
        encoding="utf8",
    )
    builder = CKGBuilder(str(tmp_path))
    builder.build()
    graph = builder.graph
    # CKGBuilder already invokes the binder during build().
    target = "contract::thrift::demo.InventoryService.Reserve"
    assert any(v == target and d.get("relation") == "IMPLEMENTS"
               for _, v, d in graph.edges(data=True))
    assert not any(v == "contract::thrift::demo.AuditService.Reserve"
                   and d.get("relation") in {"IMPLEMENTS", "CONSUMES"}
                   for _, v, d in graph.edges(data=True))
    again = bind_thrift_runtime(graph, [builder])
    assert again == {"implements": 0, "consumes": 0}
