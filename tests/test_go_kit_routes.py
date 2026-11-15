"""Go-kit Gorilla mux route chains are registered as source-located endpoints."""
from multi_repo import WorkspaceCKGBuilder


def test_mux_methods_path_handler(tmp_path):
    service = tmp_path / "catalogue"
    service.mkdir()
    (service / "transport.go").write_text(
        'package catalogue\n'
        'import "github.com/gorilla/mux"\n'
        'func MakeHTTPHandler() {\n'
        '  r := mux.NewRouter().StrictSlash(false)\n'
        '  r.Methods("GET").Path("/catalogue/{id}").Handler(handler)\n'
        '  r.Methods("GET").PathPrefix("/images/").Handler(images)\n'
        '}\n'
        '// r.Methods("POST").Path("/fake").Handler(fake)\n'
    )
    config = {
        "name": "generic", "repositories": [
            {"id": "catalogue", "path": str(service)}]}
    workspace = WorkspaceCKGBuilder({
        "name": "generic",
        "repositories": [{"id": "catalogue", "path": str(service)}]
    })
    workspace.build()
    routes = workspace.http_endpoints
    assert ("GET", "/catalogue/{id}") in routes
    assert ("GET", "/images/") in routes
    assert ("POST", "/fake") not in routes
    handler = routes[("GET", "/images/")][0]
    assert workspace.graph.nodes[handler]["http_prefix_mount"] is True
