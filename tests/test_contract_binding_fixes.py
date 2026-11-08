"""Producer binding regressions, using temporary source repositories."""

from collections import Counter
import json

import pytest

from graft_ckg import CKGBuilder
from multi_repo import RepoConfig, WorkspaceCKGBuilder, WorkspaceConfig


PROTO = '''syntax = "proto3";
service DemoService { rpc Ping (Request) returns (Response); }
message Request {}
message Response {}
'''
GO = '''package main
import pb "example/proto"
type server struct {}
func (s *server) Ping(ctx context.Context, req *pb.Request) (*pb.Response, error) {
    return nil, nil
}
func main() {
    svc := &server{}
    pb.RegisterDemoServiceServer(grpcServer, svc)
}
'''
PYTHON = '''import demo_pb2_grpc
class Base(demo_pb2_grpc.DemoServiceServicer):
    pass
class Handler(Base):
    def Ping(self, request, context):
        return "old"
class Dummy(Base):
    def Ping(self, request, context):
        return "dummy"
'''
JS = '''class LocalServer {
  static PingHandler(call, callback) {}
  register(server) {
    server.addService(pkg.DemoService.service, {
      ping: LocalServer.PingHandler.bind(this)
    });
  }
}
'''


def workspace(tmp_path, language):
    filename, text = {"go": ("main.go", GO), "python": ("server.py", PYTHON),
                      "js": ("server.js", JS)}[language]
    service = tmp_path / "service"
    service.mkdir()
    (service / filename).write_text(text, encoding="utf-8")
    (tmp_path / "shared.proto").write_text(PROTO, encoding="utf-8")
    config = WorkspaceConfig(base_dir=str(tmp_path),
                             repositories=[RepoConfig("svc", "service")],
                             shared_contracts=["shared.proto"])
    builder = WorkspaceCKGBuilder(config)
    builder.build()
    return builder, service / filename


def implements(graph):
    return Counter((u, v) for u, v, d in graph.edges(data=True)
                   if d.get("relation") == "IMPLEMENTS")


def snapshot(graph):
    """Compare all attributes and parallel edges, excluding allocated edge IDs."""
    nodes = {n: json.dumps(d, sort_keys=True) for n, d in graph.nodes(data=True)}
    edges = Counter((u, v, json.dumps(d, sort_keys=True))
                    for u, v, d in graph.edges(data=True))
    return nodes, edges


@pytest.mark.parametrize("language, handlers", [
    ("go", ["svc/main.go:server.Ping"]),
    ("python", ["svc/server.py:Handler.Ping", "svc/server.py:Dummy.Ping"]),
])
def test_shared_proto_producers(tmp_path, language, handlers):
    builder, _ = workspace(tmp_path, language)
    # Producer binding succeeds even though the service has no local .proto.
    assert builder.repo_builders["svc"].proto_services == {}
    for handler in handlers:
        assert implements(builder.graph)[handler, "contract::DemoService.Ping"] == 1


@pytest.mark.parametrize("language", ["go", "python", "js"])
def test_rebinding_is_idempotent_and_recomposition_deterministic(tmp_path, language):
    builder, _ = workspace(tmp_path, language)
    before = snapshot(builder.graph)
    builder._resolve_cross_repo_producers()
    builder._resolve_cross_repo_producers()
    assert snapshot(builder.graph) == before
    builder._compose_workspace()
    assert snapshot(builder.graph) == before


def test_js_bound_class_handler_and_no_unrelated_receiver(tmp_path):
    builder, path = workspace(tmp_path, "js")
    handler = "svc/server.js:LocalServer.PingHandler"
    assert implements(builder.graph)[handler, "contract::DemoService.Ping"] == 1
    local = builder.repo_builders["svc"]
    assert local._resolve_reference("server.js", "Unknown.PingHandler") == []
    # An imported receiver must not be treated as the same-file local class.
    local.imports_by_file.setdefault("server.js", {})["LocalServer"] = "external-package"
    assert local._resolve_reference("server.js", "LocalServer.PingHandler") == []


def test_local_proto_producer_pass_is_idempotent(tmp_path):
    (tmp_path / "demo.proto").write_text(PROTO, encoding="utf-8")
    (tmp_path / "server.js").write_text(JS, encoding="utf-8")
    builder = CKGBuilder(str(tmp_path))
    builder.build()
    assert implements(builder.graph)["server.js:LocalServer.PingHandler", "contract::DemoService.Ping"] == 1
    before = snapshot(builder.graph)
    builder._bind_contract_producers()
    builder._bind_contract_producers()
    assert snapshot(builder.graph) == before


@pytest.mark.parametrize("language", ["go", "python", "js"])
def test_incremental_equals_full_and_replaces_registrations(tmp_path, language):
    builder, path = workspace(tmp_path, language)
    text = path.read_text(encoding="utf-8")
    # Change the implementation class/type, not just a comment: stale records
    # must not recreate the old source nodes or old producer edges.
    old, new = {"go": ("server", "replacement"), "python": ("Handler", "Replacement"),
                "js": ("LocalServer", "Replacement")}[language]
    path.write_text(text.replace(old, new), encoding="utf-8")
    builder.update_files("svc", [path.name])
    full = WorkspaceCKGBuilder(builder.config)
    full.build()
    assert snapshot(builder.graph) == snapshot(full.graph)
    assert builder.total_loc == full.total_loc
    assert all(old not in n.rsplit(":", 1)[-1] for n in builder.graph
               if n.startswith("svc/"))
    before = snapshot(builder.graph)
    builder.update_files("svc", [path.name])
    assert snapshot(builder.graph) == before


def test_deleted_registration_does_not_reappear(tmp_path):
    builder, path = workspace(tmp_path, "python")
    path.unlink()
    builder.update_files("svc", [], [path.name])
    assert not implements(builder.graph)
    full = WorkspaceCKGBuilder(builder.config)
    full.build()
    assert snapshot(builder.graph) == snapshot(full.graph)


def test_shared_proto_update_rebinds_unchanged_source(tmp_path):
    builder, _ = workspace(tmp_path, "go")
    proto = tmp_path / "shared.proto"
    proto.write_text(PROTO.replace("Ping", "Other"), encoding="utf-8")
    builder.update_files("svc", [])
    full = WorkspaceCKGBuilder(builder.config)
    full.build()
    assert snapshot(builder.graph) == snapshot(full.graph)
    assert "contract::DemoService.Ping" not in builder.graph
