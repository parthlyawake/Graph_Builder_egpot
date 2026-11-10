"""Port boundaries: opt-in inclusion, source evidence and conservative helpers."""
from dataclasses import asdict
import json

import pytest

from graft_ckg import CKGBuilder
from multi_repo import RepoConfig, WorkspaceCKGBuilder, WorkspaceConfig
from graph_builder_http import source_requests


def build(tmp_path, client, helper=None, controller=None, **options):
    files = {'client/main.py':client, 'orders/Controller.java':controller or '''
@RestController @RequestMapping("/api") class Controller {
 @GetMapping("/items/{id}") void read(){}
}'''}
    if helper is not None:
        files['client/helper.py'] = helper
    for name, text in files.items():
        path = tmp_path/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    builder = WorkspaceCKGBuilder(WorkspaceConfig(base_dir=str(tmp_path),
        repositories=[RepoConfig('client','client'),RepoConfig('orders','orders')], **options))
    builder.build()
    return builder


def calls(builder):
    return [d for _,_,d in builder.graph.edges(data=True)
            if d.get('relation') == 'HTTP_CALLS' and d.get('source_evidence')]


@pytest.mark.parametrize('statement,call', [
    ('import urllib.request', 'urllib.request.urlopen'),
    ('import urllib.request as net', 'net.urlopen'),
    ('from urllib import request', 'request.urlopen'),
    ('from urllib.request import urlopen as fetch', 'fetch'),
])
def test_urllib_import_spellings_have_source_proof(tmp_path, statement, call):
    builder = build(tmp_path, statement+'\ndef send():\n return '+call+'("http://orders/api/items/42")\n')
    assert len(calls(builder)) == 1
    assert calls(builder)[0]['source_evidence'] == 'main.py:3'


@pytest.mark.parametrize('client,helper', [
    ('''from helper import fetch
def send(flag):
 if flag:
  url="http://orders/api/items/42"
 else:
  url="http://unknown/api/items/42"
 return fetch(url)
''', 'from requests import get\ndef fetch(url):\n return get(url)\n'),
    ('''from helper import Call
def send():
 call=Call("http://orders/api/items/42")
 return "not called"
''', '''import requests
class Call:
 def __init__(self,url): self.url=url
 def run(self): return requests.get(self.url)
'''),
    ('''from helper import fetch
def send():
 return "done"
 fetch("http://orders/api/items/42")
''', 'import requests\ndef fetch(url):\n return requests.get(url)\n'),
    ('''from helper import fetch
def send(): return fetch("http://orders/api/items/42")
''', 'import requests\ndef fetch(url): return requests.get(url)\ndef fetch(url): return requests.get(url)\n'),
])
def test_helpers_do_not_guess_or_emit_uncalled_methods(tmp_path, client, helper):
    assert not calls(build(tmp_path,client,helper))


def test_equal_branch_values_remain_provable(tmp_path):
    builder = build(tmp_path, '''from helper import fetch
def send(flag):
 if flag: url="http://orders/api/items/42"
 else: url="http://orders/api/items/42"
 return fetch(url)
''', 'from requests import get\ndef fetch(url):\n return get(url)\n')
    assert len(calls(builder)) == 1
    assert calls(builder)[0]['match_kind'] == 'helper'
    assert calls(builder)[0]['source_evidence'] == 'helper.py:3'


def test_single_repo_inclusion_is_opt_in(tmp_path):
    for name, text in {'main.py':'def keep(): pass',
                       'tests/test_main.py':'def test_one(): pass',
                       'generated_client.py':'# Auto-generated\ndef generated(): pass'}.items():
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    off=CKGBuilder(str(tmp_path));off.build()
    on=CKGBuilder(str(tmp_path),exclude_nonproduction=True);on.build()
    assert set(off.raw_file_lines)=={'main.py','tests/test_main.py','generated_client.py'}
    assert set(on.raw_file_lines)=={'main.py'}


def test_effective_config_and_yaml_fallback_include_both_options(tmp_path):
    builder=build(tmp_path,'def send(): pass',exclude_nonproduction=True)
    output=tmp_path/'out'/'graph.graphml';builder.export_graph(str(output),format='graphml')
    cfg=json.loads(output.with_suffix('.build_config.json').read_text())
    assert cfg['exclude_nonproduction'] is True and cfg['resolve_java_dispatch'] is False
    assert asdict(WorkspaceConfig.from_dict(cfg,cfg['base_dir']))==cfg
    raw=WorkspaceConfig._parse_simple_yaml('exclude_nonproduction: true\nresolve_java_dispatch: false')
    assert raw['exclude_nonproduction'] is True and raw['resolve_java_dispatch'] is False


def test_explicit_requestmapping_has_verb_and_annotation_evidence(tmp_path):
    builder=build(tmp_path, 'import requests\ndef send(): return requests.put("http://orders/api/items/42")',
                  controller='''@RestController @RequestMapping("/api") class Controller {
 @RequestMapping(value="/items/{id}",method={RequestMethod.PUT,RequestMethod.PATCH}) void update(){}
}''')
    assert len(calls(builder))==1 and calls(builder)[0]['http_method']=='PUT'
    proof=[d for _,_,d in builder.graph.edges(data=True)if d.get('match_kind')=='explicit_request_mapping']
    assert len(proof)==4  # IMPLEMENTS and PRODUCES for each declared verb.
    assert all(d['source_evidence']=='Controller.java:2' for d in proof)


def test_unknown_requestmapping_verb_does_not_default_to_get(tmp_path):
    builder=build(tmp_path,'def send(): pass',controller='''@RestController class Controller {
 @RequestMapping(value="/api/items/{id}",method=unknownVerb) void update(){}
}''')
    assert not [n for n,d in builder.graph.nodes(data=True)if d.get('type')=='http_endpoint']


def test_other_annotation_method_attribute_does_not_change_mapping(tmp_path):
    builder=build(tmp_path,'def send(): pass',controller='''@RestController class Controller {
 @Other(method="unrelated") @RequestMapping("/api/items/{id}") void read(){}
}''')
    assert ('GET','/api/items/{id}') in builder.http_endpoints


def test_direct_http_sites_in_exception_and_finally_are_retained(tmp_path):
    builder=build(tmp_path,'''import requests
def send():
 try: return requests.get("http://orders/api/items/1")
 except Exception: return requests.get("http://orders/api/items/2")
 finally: requests.get("http://orders/api/items/3")
''')
    requests=source_requests(builder.repo_builders['client'],{})
    assert {r[1] for r in requests}=={'http://orders/api/items/1',
                                   'http://orders/api/items/2',
                                   'http://orders/api/items/3'}
