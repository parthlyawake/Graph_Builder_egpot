"""Managed gRPC registrations: explicit registration and generated base required."""

from collections import Counter
import json

import pytest

from multi_repo import RepoConfig, WorkspaceCKGBuilder, WorkspaceConfig
from polyglot import _CSHARP_AVAILABLE, _JAVA_AVAILABLE


PROTO = '''syntax = "proto3";
service CartService {
 rpc GetCart (Request) returns (Response);
 rpc AddItem (Request) returns (Response);
 rpc EmptyCart (Request) returns (Response);
}
service AdService { rpc GetAds (Request) returns (Response); }
message Request {}
message Response {}
'''
CS = '''class CartService : Hipstershop.CartService.CartServiceBase {
 public override void GetCart() {}
 public override void AddItem() {}
 public override void EmptyCart() {}
 public void getCart() {}
}
class Unregistered : Hipstershop.CartService.CartServiceBase {
 public override void GetCart() {}
}
'''
JAVA = '''class Outer {
 static class AdServiceImpl extends hipstershop.AdServiceGrpc.AdServiceImplBase {
  @Override public void getAds() {}
  public void GetAds() {}
 }
 static class Unregistered extends AdServiceGrpc.AdServiceImplBase {
  @Override public void getAds() {}
 }
}
'''


def fixture_workspace(tmp_path, language, registration=None, proto=PROTO):
    if language == "csharp" and not _CSHARP_AVAILABLE:
        pytest.skip("tree-sitter-c-sharp is not installed")
    if language == "java" and not _JAVA_AVAILABLE:
        pytest.skip("tree-sitter-java is not installed")
    folder = tmp_path / "svc"
    folder.mkdir()
    if language == "csharp":
        implementation = folder / "CartService.cs"
        implementation.write_text(CS, encoding="utf-8")
        registration_file = folder / "Startup.cs"
        registration_file.write_text(
            registration if registration is not None else
            'class Startup { void Start() { endpoints.MapGrpcService<CartService>(); } }', encoding="utf-8")
    else:
        implementation = folder / "Outer.java"
        implementation.write_text(JAVA, encoding="utf-8")
        registration_file = folder / "Startup.java"
        registration_file.write_text(
            registration if registration is not None else
            'class Startup { void start() { ServerBuilder.forPort(8080).addService(new Outer.AdServiceImpl()); } }',
            encoding="utf-8")
    (tmp_path / "shared.proto").write_text(proto, encoding="utf-8")
    config = WorkspaceConfig(base_dir=str(tmp_path), repositories=[RepoConfig("svc", "svc")],
                             shared_contracts=["shared.proto"])
    builder = WorkspaceCKGBuilder(config)
    builder.build()
    return builder, implementation, registration_file


def bindings(graph):
    return Counter((u, v) for u, v, data in graph.edges(data=True)
                   if data.get("relation") == "IMPLEMENTS")


def snapshot(graph):
    return ({n: json.dumps(d, sort_keys=True) for n, d in graph.nodes(data=True)},
            Counter((u, v, json.dumps(d, sort_keys=True)) for u, v, d in graph.edges(data=True)))


@pytest.mark.parametrize("receiver", ["", "endpoints.", "app."])
def test_csharp_map_grpc_service_variants(tmp_path, receiver):
    builder, _, _ = fixture_workspace(tmp_path, "csharp",
        f'class Startup {{ void Start() {{ {receiver}MapGrpcService<CartService>(); }} }}')
    pairs = bindings(builder.graph)
    assert pairs["svc/CartService.cs:CartService", "contract::CartService"] == 1
    for rpc in ("GetCart", "AddItem", "EmptyCart"):
        assert pairs[f"svc/CartService.cs:CartService.{rpc}", f"contract::CartService.{rpc}"] == 1
    assert not any("Unregistered" in u or u.endswith(".getCart") for u, _ in pairs)


@pytest.mark.parametrize("registration", [
    'class Startup { void start(){ server.addService(new Outer.AdServiceImpl()); } }',
    'class Startup { void start(){ ServerBuilder.forPort(8080).addService(new Outer.AdServiceImpl(1)); } }',
])
def test_java_nested_class_and_builder_chain(tmp_path, registration):
    builder, _, _ = fixture_workspace(tmp_path, "java", registration)
    pairs = bindings(builder.graph)
    assert pairs["svc/Outer.java:Outer.AdServiceImpl", "contract::AdService"] == 1
    assert pairs["svc/Outer.java:Outer.AdServiceImpl.getAds", "contract::AdService.GetAds"] == 1
    assert not any("Unregistered" in u or u.endswith(".GetAds") for u, _ in pairs)


def test_java_nested_lexical_resolution(tmp_path):
    builder, implementation, registration = fixture_workspace(tmp_path, "java", "")
    text = JAVA.replace('class Outer {', 'class Outer { void start(){ server.addService(new AdServiceImpl()); }')
    implementation.write_text(text, encoding="utf-8")
    builder.update_files("svc", [implementation.name])
    assert bindings(builder.graph)["svc/Outer.java:Outer.AdServiceImpl.getAds", "contract::AdService.GetAds"] == 1


@pytest.mark.parametrize("language", ["csharp", "java"])
def test_no_registration_no_binding(tmp_path, language):
    builder, _, _ = fixture_workspace(tmp_path, language, "")
    assert not bindings(builder.graph)


@pytest.mark.parametrize("language", ["csharp", "java"])
def test_unknown_contract_not_invented(tmp_path, language):
    builder, _, _ = fixture_workspace(tmp_path, language,
        proto='syntax = "proto3"; service Other { rpc Ping(Request) returns(Response); }')
    assert not bindings(builder.graph)
    assert "contract::CartService" not in builder.graph
    assert "contract::AdService" not in builder.graph


@pytest.mark.parametrize("language", ["csharp", "java"])
def test_idempotence_and_deterministic_composition(tmp_path, language):
    builder, _, _ = fixture_workspace(tmp_path, language)
    expected = snapshot(builder.graph)
    builder._resolve_cross_repo_producers()
    builder._resolve_cross_repo_producers()
    assert snapshot(builder.graph) == expected
    builder._compose_workspace()
    assert snapshot(builder.graph) == expected
    assert snapshot(WorkspaceCKGBuilder(builder.config).build()) == expected


@pytest.mark.parametrize("language", ["csharp", "java"])
def test_incremental_handler_update_equals_full(tmp_path, language):
    builder, implementation, _ = fixture_workspace(tmp_path, language)
    # Keep the registration file unchanged; remove a real RPC override.
    text = implementation.read_text(encoding="utf-8")
    method = "GetCart" if language == "csharp" else "getAds"
    implementation.write_text(text.replace(method + "()", "Unrelated()"), encoding="utf-8")
    builder.update_files("svc", [implementation.name])
    full = WorkspaceCKGBuilder(builder.config)
    full.build()
    assert snapshot(builder.graph) == snapshot(full.graph)
    assert not any(u.endswith("." + method) for u, _ in bindings(builder.graph))


@pytest.mark.parametrize("language", ["csharp", "java"])
def test_registration_removal_equals_full(tmp_path, language):
    builder, _, registration = fixture_workspace(tmp_path, language)
    registration.write_text("", encoding="utf-8")
    builder.update_files("svc", [registration.name])
    full = WorkspaceCKGBuilder(builder.config)
    full.build()
    assert not bindings(builder.graph)
    assert snapshot(builder.graph) == snapshot(full.graph)


def test_csharp_non_override_method_is_not_bound(tmp_path):
    builder, implementation, _ = fixture_workspace(tmp_path, "csharp")
    implementation.write_text(CS.replace("override ", ""), encoding="utf-8")
    builder.update_files("svc", [implementation.name])
    assert all(not target.startswith("contract::CartService.") for _, target in bindings(builder.graph))


@pytest.mark.parametrize("language", ["csharp", "java"])
def test_namespace_qualified_registration(tmp_path, language):
    builder, implementation, registration = fixture_workspace(tmp_path, language)
    if language == "csharp":
        implementation.write_text("namespace Shop.Services {\n" + CS + "\n}", encoding="utf-8")
        registration.write_text('class Startup { void Start(){ app.MapGrpcService<Shop.Services.CartService>(); } }', encoding="utf-8")
        target = ("svc/CartService.cs:CartService.GetCart", "contract::CartService.GetCart")
    else:
        implementation.write_text("package shop;\n" + JAVA, encoding="utf-8")
        registration.write_text('class Startup { void start(){ server.addService(new shop.Outer.AdServiceImpl()); } }', encoding="utf-8")
        target = ("svc/Outer.java:Outer.AdServiceImpl.getAds", "contract::AdService.GetAds")
    builder.update_files("svc", [implementation.name, registration.name])
    assert bindings(builder.graph)[target] == 1


@pytest.mark.parametrize("language", ["csharp", "java"])
def test_wrong_qualified_namespace_does_not_match_local_type(tmp_path, language):
    registration = ('class Startup { void Start(){ app.MapGrpcService<Wrong.CartService>(); } }'
                    if language == "csharp" else
                    'class Startup { void start(){ server.addService(new Wrong.Outer.AdServiceImpl()); } }')
    builder, _, _ = fixture_workspace(tmp_path, language, registration)
    assert not bindings(builder.graph)
