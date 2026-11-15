"""Cross-language IDL/Avro/PDL contracts and syntax extraction regression tests.

These fixtures exercise *syntax classes*, not application-name-specific logic.
No network or external repository clone is required.
"""
from pathlib import Path

import pytest

from graft_ckg import CKGBuilder
from language_adapters import advertised_capabilities, spec_for


@pytest.fixture
def indexed(tmp_path):
    files = {
        "services/catalog.thrift": """
namespace cpp catalog
namespace py catalog
struct Item {
  1: i64 id;
  2: string name;
}
service InventoryService {
  void UpdateItem(
    1: i64 request_id,
    2: map<string, string> metadata
  ) throws (1: Item failure)
  i64 ReadCount(1: string key)
}
""",
        "schemas/metadata.pdl": """
namespace com.example.metadata
record AuditStamp {
  actor: string
  count: optional long
}
typeref EventId = string
""",
        "schemas/events.avsc": """
{
 "type":"record", "name":"ChangeEvent", "namespace":"com.example",
 "fields":[
   {"name":"time","type":"long"},
   {"name":"actor","type":{"type":"record","name":"Actor",
     "fields":[{"name":"id","type":"string"}]}}
 ]
}
""",
        "ruby/service.rb": """
require 'json'
class Catalog
  def helper
    12
  end
  def index
    helper()
  end
end
""",
        "lua/service.lua": """
local function helper()
  return 12
end
function index()
  return helper()
end
""",
        "cpp/worker.cpp": """
#include <string>
namespace svc {
int helper() { return 12; }
int index() { return helper(); }
}
""",
        "c/worker.c": """
#include <stdio.h>
int helper() { return 12; }
int index() { return helper(); }
""",
        "scala/Action.scala": """
object Action {
  def helper(): Int = 12
  def index(): Int = helper()
}
""",
    }
    for path, content in files.items():
        full = tmp_path / path
        full.parent.mkdir(exist_ok=True, parents=True)
        full.write_text(content.lstrip(), encoding="utf-8")
    builder = CKGBuilder(str(tmp_path))
    graph = builder.build()
    return builder, graph


def test_12_language_registry_covers_new_sources():
    specs = advertised_capabilities()
    for path, language in (
        ("service.rb", "ruby"), ("server.lua", "lua"), ("server.cpp", "cpp"),
        ("headers.h", "cpp"), ("client.c", "c"), ("filters.scala", "scala"),
        ("entry.mjs", "javascript"), ("worker.cjs", "javascript"),
    ):
        assert spec_for(path).name == language
        assert specs[language]["installed"] is True


def test_new_language_files_have_structural_entities(indexed):
    builder, graph = indexed
    report = builder.get_language_report()
    names = ["ruby", "lua", "cpp", "c", "scala"]
    for name in names:
        assert report["languages"][name]["parsed"] == 1, (name, report["parse_errors"])
    actual = {d.get("name") for _, d in graph.nodes(data=True)
              if d.get("type") == "function"}
    assert {"helper", "index"} <= actual
    assert any(d.get("relation") == "IMPORTS" and v == "module::json"
               for _, v, d in graph.edges(data=True))
    assert any(d.get("relation") == "IMPORTS" and v == "module::string"
               for _, v, d in graph.edges(data=True))


def test_thrift_service_and_rpc_signatures_are_first_class(indexed):
    _, graph = indexed
    service = "contract::thrift::catalog.InventoryService"
    assert graph.nodes[service]["type"] == "service_contract"
    assert graph.nodes[service]["contract_format"] == "thrift"
    rpc = service + ".UpdateItem"
    assert graph.nodes[rpc]["type"] == "rpc_contract"
    assert graph.nodes[rpc]["return_type"] == "void"
    assert graph.nodes[rpc]["args"] == [
        "1: i64 request_id", "2: map<string, string> metadata"
    ]
    assert any(u == service and v == rpc and d.get("relation") == "DEFINES_RPC"
               for u, v, d in graph.edges(data=True))
    assert graph.nodes["contract::thrift::catalog.Item.field::name"]["field_tag"] == 2


def test_pdl_record_and_avro_nested_contracts(indexed):
    builder, graph = indexed
    assert "contract::pdl::com.example.metadata.AuditStamp" in graph
    assert "contract::pdl::com.example.metadata.AuditStamp.field::actor" in graph
    assert "contract::avro::com.example.ChangeEvent" in graph
    assert "contract::avro::com.example.Actor" in graph
    assert graph.nodes["contract::avro::com.example.ChangeEvent.field::actor"]["type"] == "schema_field"
    assert builder.get_language_report()["schema_contracts"]["parsed"] == 3


def test_bad_schema_has_exposed_failure(tmp_path):
    (tmp_path / "broken.avsc").write_text("{ broken json", encoding="utf-8")
    builder = CKGBuilder(str(tmp_path))
    builder.build()
    report = builder.get_language_report()
    assert report["schema_contracts"]["failed"] == 1
    assert report["full_source_coverage"] is False
    assert any(x["file"] == "broken.avsc" for x in builder.skipped_files)


def test_unbalanced_thrift_service_reports_source_error(tmp_path):
    (tmp_path / "bad.thrift").write_text(
        "service Bad { void ping(1: string thing)\n", encoding="utf-8"
    )
    b = CKGBuilder(str(tmp_path))
    b.build()
    assert b.get_language_report()["schema_contracts"]["failed"] == 1
