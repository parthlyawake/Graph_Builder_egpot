"""JAX-RS and dispatcher handlers must resolve from grammar-backed declarations."""
from multi_repo import WorkspaceCKGBuilder
from framework_http_routes import regex_route_template


def test_limited_dispatcher_regex_literal():
    assert regex_route_template(r"/^\/ratings\/[0-9]*/") == "/ratings/{value}"
    assert regex_route_template(r"/^\/ratings\/\d+/") == "/ratings/{value}"
    assert regex_route_template(r"/(.*)/") is None
    assert regex_route_template(r"/^\/ratings\/(.+)/") is None


def test_jaxrs_and_dispatcher_registration(tmp_path):
    a, b = tmp_path / "reviews", tmp_path / "ratings"
    a.mkdir()
    b.mkdir()
    (a / "Review.java").write_text(
        'import javax.ws.rs.GET;\n'
        'import javax.ws.rs.Path;\n'
        '@Path("/") public class Review {\n'
        ' @GET @Path("/reviews/{id}") public String byId() { return ""; }\n'
        '}\n', encoding="utf8"
    )
    (b / "ratings.js").write_text(
        "var dispatcher = require('httpdispatcher');\n"
        r"dispatcher.onGet(/^\/ratings\/[0-9]*/, function(req, res) {});"+"\n",
        encoding="utf8"
    )
    workspace = WorkspaceCKGBuilder({
        "name": "frameworks",
        "repositories": [
            {"id": "reviews", "path": str(a)},
            {"id": "ratings", "path": str(b)},
        ],
    })
    workspace.build()
    assert ("GET", "/reviews/{id}") in workspace.http_endpoints
    assert ("GET", "/ratings/{value}") in workspace.http_endpoints
