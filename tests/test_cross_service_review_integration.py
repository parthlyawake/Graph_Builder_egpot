"""End-to-end source-to-graph integration for imported review binding semantics."""
from pathlib import Path

import pytest

from multi_repo import RepoConfig, WorkspaceConfig, WorkspaceCKGBuilder
from polyglot import _JAVA_AVAILABLE, _CSHARP_AVAILABLE


PROTO = '''syntax = "proto3";
service CartService { rpc GetCart (Request) returns (Response); }
service AdService { rpc GetAds (Request) returns (Response); }
message Request {}
message Response {}
'''


def _write(root, name, value):
    dest = root / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(value, encoding="utf-8")


def _workspace(root):
    return WorkspaceCKGBuilder(WorkspaceConfig(
        base_dir=str(root),
        repositories=[RepoConfig(id="svc", path="svc")],
        shared_contracts=["shared.proto"],
    ))


def _bindings(builder, relation="IMPLEMENTS"):
    return {(u, v) for u, v, d in builder.graph.edges(data=True)
            if d.get("relation") == relation}


@pytest.mark.parametrize("registered", [True, False])
def test_csharp_registration_required(tmp_path, registered):
    if not _CSHARP_AVAILABLE:
        pytest.skip("C# grammar unavailable")
    _write(tmp_path, "shared.proto", PROTO)
    _write(tmp_path, "svc/CartService.cs", '''
class CartService : Hipstershop.CartService.CartServiceBase {
    public override void GetCart() {}
    public void getCart() {}
}
class Unregistered : Hipstershop.CartService.CartServiceBase {
    public override void GetCart() {}
}
''')
    registration = 'class Startup { void Start(){ endpoints.MapGrpcService<CartService>(); } }' if registered else ''
    _write(tmp_path, "svc/Startup.cs", registration)
    b = _workspace(tmp_path)
    b.build()
    impls = _bindings(b)
    edge = ("svc/CartService.cs:CartService.GetCart", "contract::CartService.GetCart")
    assert (edge in impls) == registered
    assert not any(u.startswith("svc/CartService.cs:Unregistered") for u, _ in impls)
    assert not any(u.endswith(".getCart") for u, _ in impls)


@pytest.mark.parametrize("registered", [True, False])
def test_java_registration_required(tmp_path, registered):
    if not _JAVA_AVAILABLE:
        pytest.skip("Java grammar unavailable")
    _write(tmp_path, "shared.proto", PROTO)
    _write(tmp_path, "svc/Outer.java", '''
class Outer {
 static class AdServiceImpl extends hipstershop.AdServiceGrpc.AdServiceImplBase {
    @Override public void getAds() {}
 }
 static class Unregistered extends hipstershop.AdServiceGrpc.AdServiceImplBase {
    @Override public void getAds() {}
 }
}
''')
    registration = 'class Startup { void start(){ server.addService(new Outer.AdServiceImpl()); } }' if registered else ''
    _write(tmp_path, "svc/Startup.java", registration)
    b = _workspace(tmp_path)
    b.build()
    impls = _bindings(b)
    edge = ("svc/Outer.java:Outer.AdServiceImpl.getAds", "contract::AdService.GetAds")
    assert (edge in impls) == registered
    assert not any(u.startswith("svc/Outer.java:Outer.Unregistered") for u, _ in impls)


@pytest.mark.parametrize("host,should_bind", [
    ("orders", True),
    ("missing", False),
])
def test_http_resolves_only_known_host(tmp_path, host, should_bind):
    if not _JAVA_AVAILABLE:
        pytest.skip("Java grammar unavailable")
    _write(tmp_path, "client/client.py", '''import requests
def fetch():
    return requests.get("http://''' + host + '''/api/items/42")
''')
    _write(tmp_path, "orders/Controller.java", '''
@RestController
@RequestMapping("/api")
class Controller {
    @GetMapping("/items/{id}")
    public String read() { return "ok"; }
}
''')
    b = WorkspaceCKGBuilder(WorkspaceConfig(
        base_dir=str(tmp_path),
        repositories=[RepoConfig(id="client", path="client"),
                      RepoConfig(id="orders", path="orders")],
    ))
    b.build()
    source = "client/client.py:fetch"
    target = "orders/Controller.java:Controller.read"
    edges = [(u, v, d) for u, v, d in b.graph.edges(data=True)
             if d.get("relation") == "HTTP_CALLS" and u == source and v == target]
    assert bool(edges) == should_bind
    if should_bind:
        assert edges[0][2]["source_evidence"].startswith("client.py:")
        assert edges[0][2]["http_method"] == "GET"

def test_repeat_build_and_update_do_not_accumulate_contract_edges(tmp_path):
    _write(tmp_path, "shared.proto", PROTO)
    _write(tmp_path, "svc/server.py", "def hello():\n    return 1\n")
    builder = _workspace(tmp_path)
    builder.build()
    def snapshot():
        return (
            set(builder.graph.nodes),
            sorted((u, v, d.get("relation"), d.get("layer"))
                   for u, v, d in builder.graph.edges(data=True)),
        )
    baseline = snapshot()
    builder.build()
    assert snapshot() == baseline
    builder.update_files("svc", ["server.py"])
    assert snapshot() == baseline
    with pytest.raises(KeyError):
        builder.update_files("unknown", [])


@pytest.mark.parametrize("expression", [
    '"http://orders/api/items/42"',
    '"http://orders/api/items/" + id',
    'getServiceUrl("orders") + "/api/items/" + id',
    'url',
])
def test_java_http_exchange_resolves_source_url_and_verb(tmp_path, expression):
    if not _JAVA_AVAILABLE:
        pytest.skip("Java grammar unavailable")
    _write(tmp_path, "client/Client.java", '''
class Client {
  RestTemplate restTemplate;
  String getServiceUrl(String service) { return "http://" + service; }
  void send(String id) {
    String url = getServiceUrl("orders") + "/api/items/" + id;
    restTemplate.exchange(''' + expression + ''', HttpMethod.PUT, null, String.class);
  }
}''')
    _write(tmp_path, "orders/Controller.java", '''
@RestController
@RequestMapping("/api")
class Controller {
    @PutMapping("/items/{id}")
    public String update() { return "ok"; }
}''')
    b = WorkspaceCKGBuilder(WorkspaceConfig(
        base_dir=str(tmp_path),
        repositories=[RepoConfig(id="client", path="client"),
                      RepoConfig(id="orders", path="orders")],
    ))
    b.build()
    matched = [(u, v, data) for u, v, data in b.graph.edges(data=True)
               if data.get("relation") == "HTTP_CALLS"
               and u.endswith("Client.send") and v.endswith("Controller.update")]
    assert len(matched) == 1
    assert matched[0][2]["http_method"] == "PUT"


def test_java_branch_ambiguous_url_is_not_bound(tmp_path):
    if not _JAVA_AVAILABLE:
        pytest.skip("Java grammar unavailable")
    _write(tmp_path, "client/Client.java", '''
class Client {
  RestTemplate restTemplate;
  void send(boolean flag) {
    String url;
    if(flag) {url = "http://orders/api/items/42";}
    else {url = "http://orders/wrong/42";}
    restTemplate.getForObject(url, String.class);
  }
}''')
    _write(tmp_path, "orders/Controller.java", '''
@RestController class Controller {
    @GetMapping("/api/items/{id}")
    public String read() { return "ok"; }
}''')
    b = WorkspaceCKGBuilder(WorkspaceConfig(
        base_dir=str(tmp_path),
        repositories=[RepoConfig(id="client", path="client"),
                      RepoConfig(id="orders", path="orders")],
    ))
    b.build()
    assert not any(data.get("relation") == "HTTP_CALLS"
                   for _, _, data in b.graph.edges(data=True))
