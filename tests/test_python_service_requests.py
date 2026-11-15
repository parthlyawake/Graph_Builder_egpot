"""Environment defaults are conditional while explicit deployment config is exact."""
from python_service_requests import extract_requests
from graft_ckg import CKGBuilder


def test_source_dictionary_wrapped_http_and_env_default(tmp_path):
    code = """
import os
import requests
host = "details" if os.environ.get("DETAILS_HOSTNAME") is None else os.environ.get("DETAILS_HOSTNAME")
port = "9080"
details = {"name": "http://{0}:{1}".format(host, port), "endpoint": "details"}
def get_details(product_id):
    url = details["name"] + "/" + details["endpoint"] + "/" + str(product_id)
    return send_request(url)
def send_request(url):
    return requests.get(url)
"""
    (tmp_path / "service.py").write_text(code)
    builder = CKGBuilder(str(tmp_path))
    builder.build()
    without_env = extract_requests(builder, "service.py", code, {})
    assert any("http://details:9080/details/*" == item[1]
               and item[-1] == "python_conditional_default" for item in without_env)
    given = extract_requests(builder, "service.py", code, {"DETAILS_HOSTNAME": "catalogue"})
    assert any(item[1] == "http://catalogue:9080/details/*"
               and item[-1] == "python_source_wrapper" for item in given)
