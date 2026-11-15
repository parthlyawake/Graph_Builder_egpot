"""CommonJS request-package endpoints are propagated with conditional DNS suffixes."""
from graft_ckg import CKGBuilder
from node_request_calls import extract_node_request_calls


def test_request_package_local_module_exported_endpoints(tmp_path):
    (tmp_path / "api").mkdir()
    (tmp_path / "api/endpoints.js").write_text(
        'var util = require("util");\n'
        'var domain = "";\n'
        'process.argv.forEach(function (value) { if (value === "--domain") domain = ".dev"; });\n'
        'module.exports = { cartsUrl: util.format("http://carts%s/carts", domain) };',
        encoding="utf8")
    (tmp_path / "api/client.js").write_text(
        "var request = require('request');\n"
        "var endpoints = require('./endpoints');\n"
        "function checkout() { request(endpoints.cartsUrl, function() {}); }\n"
        "// request('http://other/internal');\n",
        encoding="utf8")
    builder = CKGBuilder(str(tmp_path))
    graph = builder.build()
    result = extract_node_request_calls(builder, graph)
    assert len(result) == 1
    assert result[0][1] == "http://carts/carts"
    assert result[0][-1] == "js_request_conditional_default"


def test_comma_separated_commonjs_import_declarations(tmp_path):
    (tmp_path / "endpoints.js").write_text(
        'var util = require("util"); var domain = ""; '
        'module.exports = {service: util.format("http://inventory%s/items",domain)};')
    (tmp_path / "client.js").write_text(
        "var express = require('express'), request = require('request'), "
        "endpoints = require('./endpoints');\n"
        "function client() { request(endpoints.service, function() {}); }\n")
    builder = CKGBuilder(str(tmp_path))
    graph = builder.build()
    result = extract_node_request_calls(builder, graph)
    assert len(result) == 1
    assert result[0][1] == "http://inventory/items"
