"""Source-only, unique-destination HTTP resolution and opt-in inclusion policy."""
from pathlib import Path

import pytest

from multi_repo import RepoConfig, WorkspaceConfig, WorkspaceCKGBuilder


def put(root, path, text):
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text, encoding="utf-8")


def workspace(root, client, server=None, **options):
    put(root, "client/Client.java" if "class Client" in client else "client/client.py", client)
    put(root, "orders/Controller.java", server or '''
@RestController
@RequestMapping("/api")
class Controller {
 @GetMapping("/items/{id}") public String get() {return "ok";}
 @PutMapping("/items/{id}") public String put() {return "ok";}
}
''')
    return WorkspaceCKGBuilder(WorkspaceConfig(base_dir=str(root), repositories=[
        RepoConfig("client", "client"), RepoConfig("orders", "orders")], **options))


def bindings(builder):
    return [(u, v, d) for u, v, d in builder.graph.edges(data=True)
            if d.get("relation") == "HTTP_CALLS" and d.get("match_kind")]


@pytest.mark.parametrize("expression", [
    '"http://orders:8080/api/items/42"',
    '"http://orders:8080/api/items/" + id',
    'getServiceUrl("orders") + "/api/items/" + id',
    'url',
])
def test_java_exchange_host_verb_and_parameters(tmp_path, expression):
    b = workspace(tmp_path, '''class Client {
 RestTemplate restTemplate;
 String getServiceUrl(String service) { return "http://" + service; }
 void send(String id) {
 String url = getServiceUrl("orders") + "/api/items/" + id;
 restTemplate.exchange(''' + expression + ''', HttpMethod.PUT, null, String.class);
 }}''')
    b.build()
    edges = bindings(b)
    assert len(edges) == 1
    assert edges[0][1].endswith("Controller.put")
    assert edges[0][2]["http_method"] == "PUT"
    assert edges[0][2]["source_evidence"].startswith("Client.java:")
    assert edges[0][2]["layer"] == "Ldep"
    assert edges[0][2]["c_type"] == 1.0


@pytest.mark.parametrize("url,verb", [
    ("http://orders/api/items/42", "POST"),
    ("http://orders/wrong/42", "GET"),
    ("http://unknown/api/items/42", "GET"),
    ("http://orders/api/items/42/extra", "GET"),
])
def test_java_no_wrong_path_verb_or_host(tmp_path, url, verb):
    b = workspace(tmp_path, f'''class Client {{ RestTemplate restTemplate;
 void send() {{restTemplate.exchange("{url}", HttpMethod.{verb}, null, String.class);}} }}''')
    b.build()
    assert not bindings(b)
    assert not [d for _, _, d in b.graph.edges(data=True) if d.get("relation") == "HTTP_CALLS"]


def test_ambiguous_host_rejected(tmp_path):
    b = workspace(tmp_path, '''class Client {RestTemplate restTemplate;
 void send(){restTemplate.getForObject("http://orders/api/items/42", String.class);} }''')
    put(tmp_path, "other/orders/Controller.java", '@RestController class Other {@GetMapping("/api/items/{id}") void get(){}}')
    b.config.repositories.append(RepoConfig("other", "other/orders"))
    b.build()
    assert not bindings(b)


def test_ambiguous_endpoint_rejected(tmp_path):
    b = workspace(tmp_path, '''class Client {RestTemplate restTemplate;
 void send(){restTemplate.getForObject("http://orders/api/items/42", String.class);} }''', '''
@RestController class Controller {
 @GetMapping("/api/items/{id}") void first(){}
 @GetMapping("/api/items/{other}") void second(){}
}''')
    b.build()
    assert not bindings(b)


def test_overloaded_handler_node_is_not_a_unique_definition(tmp_path):
    b = workspace(tmp_path, '''class Client { RestTemplate restTemplate;
 void send(){restTemplate.getForObject("http://orders/api/items/42", String.class);} }''', '''
@RestController class Controller {
 @GetMapping("/api/items/{id}") void read(String id){}
 @PostMapping("/api/items") void read(List<String> ids){}
}''')
    b.build()
    assert not bindings(b)


def test_requestmapping_explicit_verbs(tmp_path):
    b = workspace(tmp_path, '''class Client { RestTemplate restTemplate;
 void send(){restTemplate.exchange("http://orders/api/items/42", HttpMethod.PUT, null, String.class);} }''', '''
@RestController @RequestMapping("/api") class Controller {
 @RequestMapping(value="/items/{id}", method={RequestMethod.PUT, RequestMethod.PATCH}) void update(){}
}''')
    b.build()
    assert len(bindings(b)) == 1


def test_java_unknown_branch_does_not_choose_last_url(tmp_path):
    b = workspace(tmp_path, '''class Client {RestTemplate restTemplate;
 void send(boolean flag){String url;
 if(flag){url="http://orders/api/items/42";}
 else {url="http://orders/wrong/42";}
 restTemplate.getForObject(url, String.class);
 }}''')
    b.build()
    assert not bindings(b)


@pytest.mark.parametrize("call", [
    'web.get().uri("http://orders/api/items/42").retrieve()',
    'http.send(request, handler)',
])
def test_java_webclient_and_httpclient(tmp_path, call):
    b = workspace(tmp_path, '''class Client {WebClient web; HttpClient http;
 void send(){
 HttpRequest request = HttpRequest.newBuilder().uri(URI.create("http://orders/api/items/42")).GET().build();
 ''' + call + ';} }')
    b.build()
    assert bindings(b)


@pytest.mark.parametrize("library,call", [
    ("requests", 'requests.get(url)'),
    ("httpx", 'httpx.get(url=url)'),
    ("urllib.request", 'urllib.request.urlopen(url)'),
])
def test_python_compose_environment(tmp_path, library, call):
    b = workspace(tmp_path, f'''import os
import {library}
url = "http://" + os.environ.get("API_HOST") + "/api/items/42"
def send():
    return {call}
''')
    put(tmp_path, "compose.yml", 'services:\n  client:\n    environment:\n      API_HOST: "orders:8080"\n')
    b.build()
    assert len(bindings(b)) == 1
    assert bindings(b)[0][2]["match_kind"] == "env_via_config"


@pytest.mark.parametrize("value", [None, "unknown:8080"])
def test_unknown_environment_never_falls_back(tmp_path, value):
    b = workspace(tmp_path, '''import os, requests
def send():
    return requests.get("http://" + os.getenv("API_HOST") + "/api/items/42")
''')
    if value:
        put(tmp_path, "compose.yml", f'services:\n  client:\n    environment:\n      API_HOST: "{value}"\n')
    b.build()
    assert not bindings(b)


def test_kubernetes_envfrom_and_imported_function(tmp_path):
    b = workspace(tmp_path, '''import os
from helper import fetch
config = {}
config["URL"] = "http://{}/api/items/42".format(os.environ.get("API_HOST"))
def send():
    return fetch(config["URL"])
''')
    put(tmp_path, "client/helper.py", 'from requests import get\ndef fetch(url):\n    return get(url=url)\n')
    put(tmp_path, "deploy.yml", '''kind: ConfigMap
metadata: {name: api-config}
data: {API_HOST: "orders:8080"}
---
kind: Deployment
metadata: {name: client}
spec:
  template:
    spec:
      containers:
      - name: client
        envFrom:
        - configMapRef: {name: api-config}
''')
    b.build()
    assert len(bindings(b)) == 1
    assert bindings(b)[0][0].endswith("client.py:send")
    assert bindings(b)[0][2]["match_kind"] == "helper"
    assert bindings(b)[0][2]["source_evidence"] == "helper.py:3"


def test_imported_helper_objects_carry_url(tmp_path):
    b = workspace(tmp_path, '''from helper import Request, Call
def send(id):
    call = Call(Request(url=f"http://orders/api/items/{id}"))
    return call.run()
''')
    put(tmp_path, "client/helper.py", '''from requests import get
class Request:
    def __init__(self, url):
        self.url = url
class Call:
    def __init__(self, request):
        self.request = request
    def run(self):
        return get(url=self.request.url)
''')
    b.build()
    assert bindings(b)


def test_inclusion_is_opt_in_and_config_roundtrips(tmp_path):
    b = workspace(tmp_path, 'def send():\n    pass\n', exclude_nonproduction=True)
    for path, header in [('tests/test_example.py', ''), ('generated/output.py', ''),
                         ('vendor/lib.py', ''), ('generated_client.py', '# Auto-generated\n')]:
        put(tmp_path, 'client/' + path, header + 'def generated():\n    pass\n')
    b.build()
    assert set(b.repo_builders['client'].raw_file_lines) == {'client.py'}
    b.config.exclude_nonproduction = False
    b.build()
    assert 'tests/test_example.py' in b.repo_builders['client'].raw_file_lines
    assert WorkspaceConfig.from_dict({'exclude_nonproduction': True}).exclude_nonproduction


def test_recomposition_and_incremental_equal_full(tmp_path):
    b = workspace(tmp_path, '''class Client { RestTemplate restTemplate;
 void send(){restTemplate.getForObject("http://orders/api/items/42", String.class);} }''')
    b.build()
    expected = {(u, v, d['http_method']) for u, v, d in bindings(b)}
    b._compose_workspace()
    assert {(u, v, d['http_method']) for u, v, d in bindings(b)} == expected
    b.update_files('client', ['Client.java'])
    assert {(u, v, d['http_method']) for u, v, d in bindings(b)} == expected
