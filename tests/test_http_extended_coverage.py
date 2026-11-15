"""End-to-end framework HTTP extraction: positive and negative evidence."""
from pathlib import Path

import pytest

from graph_builder_http import path_matches
from multi_repo import WorkspaceCKGBuilder


@pytest.fixture(scope="module")
def system(tmp_path_factory):
    root = tmp_path_factory.mktemp("extended_http")
    files = {
        "orders/app.py": '''
from fastapi import FastAPI, APIRouter
app = FastAPI()
router = APIRouter(prefix="/v2")
@router.get("/items")
def list_items():
    return []
app.include_router(router, prefix="/api")
''',
        "billing/app.py": '''
from fastapi import FastAPI
app = FastAPI()
@app.get("/api/v2/items")
def billing_items():
    return []
''',
        "web/client.py": '''
import httpx
def check():
    return httpx.get("http://orders:8000/api/v2/items")
''',
        "ui/routes.js": '''
const express = require("express");
const router = express.Router();
function listItems(req, res) { return res.json([]); }
router.get("/list", listItems);
// router.get("/ghost", listItems);
/* router.post("/secret", listItems); */
module.exports = router;
''',
        "ui/app.js": '''
const express = require("express");
const router = require("./routes");
const app = express();
app.use("/api", router);
''',
        "ui/client.js": '''
const BASE = "http://ui:3000";
const api = axios.create({baseURL: BASE});
async function viaUrl() {
  const path = "/api/list";
  return fetch(new URL(path, BASE));
}
async function viaTemplate() {
  const target = `${BASE}/api/list`;
  return fetch(target);
}
async function viaAxios() { return api.get("/api/list"); }
async function unknownHost(host) {
  return fetch(`http://${host}/api/list`);
}
''',
        "django/root_urls.py": '''
from django.urls import path, include
urlpatterns = [path("v1/", include("api.urls"))]
''',
        "django/api/urls.py": '''
from django.urls import path
from . import views
urlpatterns = [path("status/", views.status)]
''',
        "django/api/views.py": '''
def status(request):
    return "OK"
''',
        "go_api/main.go": '''
package main
import "github.com/gin-gonic/gin"
func Stock(c *gin.Context) {}
func main() {
    r := gin.Default()
    api := r.Group("/v1")
    api.GET("/stock", Stock)
}
''',
        "orders/api.py": '''
from fastapi import APIRouter
router = APIRouter(prefix="/v3")
@router.get("/check")
def external_status():
    return "OK"
''',
        "orders/main.py": '''
from fastapi import FastAPI
from api import router as imported_router
app = FastAPI()
app.include_router(imported_router, prefix="/external")
''',
        "web/external_client.py": '''
import httpx
def external():
    return httpx.get("http://orders:8000/external/v3/check")
''',
        "ui/fastify.js": '''
const fastify = require("fastify")();
function fastHandler(request, reply) { return "fast"; }
fastify.route({ method: "GET", url: "/fastify", handler: fastHandler });
''',
        "ui/chained.js": '''
const express = require("express");
const app = express();
function chainedHandler(req, res) { return "ok"; }
app.route("/chain").get(chainedHandler);
''',
        "chi_api/main.go": '''
package main
import "github.com/go-chi/chi/v5"
func Read(w interface{}, r interface{}) {}
func main() {
    r := chi.NewRouter()
    r.Route("/api", func(r chi.Router) {
        r.Get("/items", Read)
    })
}
''',
        "go_client/client.go": '''
package client
import "net/http"
func CheckStock() {
    base := "http://go_api:8080"
    http.NewRequest("GET", base + "/v1/stock", nil)
}
''',
    }
    for file, content in files.items():
        target = root / file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content.strip() + "\n", encoding="utf-8")
    names = ("orders", "billing", "web", "ui", "django", "go_api", "go_client", "chi_api")
    (root / "workspace.yaml").write_text(
        "name: extended_http\nversion: '1.0'\nrepositories:\n"
        + "".join("  - id: " + name + "\n    path: ./" + name + "\n" for name in names),
        encoding="utf-8",
    )
    workspace = WorkspaceCKGBuilder(str(root / "workspace.yaml"))
    workspace.build()
    return workspace


def edges(system, node, relation="HTTP_CALLS"):
    return {
        v for _, v, d in system.graph.out_edges(node, data=True)
        if d.get("relation") == relation
    }


def test_fastapi_router_prefix_and_host_specific_link(system):
    assert "orders/app.py:list_items" in edges(system, "web/client.py:check")
    assert "billing/app.py:billing_items" not in edges(system, "web/client.py:check")
    assert ("GET", "/api/v2/items") in system.http_endpoints
    assert "orders/app.py:list_items" not in system.http_endpoints.get(("GET", "/items"), [])


def test_express_imported_router_prefix_and_host_urls(system):
    for function in ("viaUrl", "viaTemplate", "viaAxios"):
        assert "ui/routes.js:listItems" in edges(system, "ui/client.js:" + function)
    assert not edges(system, "ui/client.js:unknownHost")
    assert "ui/routes.js:listItems" in system.http_endpoints[("GET", "/api/list")]
    assert "ui/routes.js:listItems" not in system.http_endpoints.get(("GET", "/list"), [])
    assert ("GET", "/ghost") not in system.http_endpoints
    assert ("POST", "/secret") not in system.http_endpoints


def test_go_gin_group_and_static_new_request(system):
    assert "go_api/main.go:Stock" in edges(system, "go_client/client.go:CheckStock")
    assert "go_api/main.go:Stock" in system.http_endpoints[("GET", "/v1/stock")]


def test_django_nested_include_and_view_binding(system):
    assert "django/api/views.py:status" in system.http_endpoints[("*", "/v1/status")]


def test_static_path_parameters_do_not_match_other_routes():
    assert path_matches("/users/{id}", "/users/42")
    assert not path_matches("/users/{id}", "/users/42/delete")


def test_cross_file_fastapi_router_and_imported_prefix(system):
    assert "orders/api.py:external_status" in edges(
        system, "web/external_client.py:external")
    assert "orders/api.py:external_status" in system.http_endpoints[
        ("GET", "/external/v3/check")
    ]
    assert "orders/api.py:external_status" not in system.http_endpoints.get(
        ("GET", "/check"), [])


def test_fastify_object_routes_and_express_chain(system):
    assert "ui/fastify.js:fastHandler" in system.http_endpoints[
        ("GET", "/fastify")
    ]
    assert "ui/chained.js:chainedHandler" in system.http_endpoints[
        ("GET", "/chain")
    ]


def test_chi_lexical_router_prefix(system):
    assert "chi_api/main.go:Read" in system.http_endpoints[("GET", "/api/items")]
    assert "chi_api/main.go:Read" not in system.http_endpoints.get(("GET", "/items"), [])
