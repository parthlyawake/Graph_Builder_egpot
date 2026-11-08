"""Frozen-record-only export parity, offline resources and immutable source."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

import pytest

from bench.export_test_results_js import build_payload, encode, find_record, main, non_latency_content

ROOT = Path(__file__).resolve().parents[1]
SOURCE = find_record(ROOT/"bench/results")
OUTPUT = ROOT/"viz/data/online_boutique/results_test.js"


@pytest.fixture(scope="module")
def exported():
    text = OUTPUT.read_text(encoding="utf-8")
    prefix = "window.VIZ_RESULTS_TEST = "
    assert text.startswith(prefix)
    return json.loads(text[len(prefix):].rstrip(";\n"))


def test_global_provenance_and_saved_bytes(exported):
    source = json.loads(SOURCE.read_bytes())
    assert exported["provenance"]["commit"] == source["commit"]
    assert exported["provenance"]["timestamp_utc"] == source["utc_timestamp"]
    assert exported["provenance"]["versions"] == source["versions"]
    assert exported["provenance"]["split_links"] == source["split_links"]
    assert exported["provenance"]["source_record_sha256"] == hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    assert exported["provenance"]["deterministic_sha256"] == source["deterministic_sha256"]
    assert OUTPUT.read_bytes() == encode(build_payload(SOURCE))


def test_rows_exactly_match_both_splits_and_experiments(exported):
    source = json.loads(SOURCE.read_bytes())
    for key,experiments in {"rows":{"main"},"choke":{"choke"},"seeds":{"seeds"},"weights":{"weights","pareto_reference"}}.items():
        assert exported[key] == [r for r in source["rows"] if r["experiment"] in experiments]
    assert len(exported["rows"]) == 1350
    assert sum(r["split"]=="dev" for r in exported["rows"]) == 720
    assert sum(r["split"]=="test" for r in exported["rows"]) == 630
    assert {r["node_budget"] for r in exported["rows"]} == {10,20,40}
    assert exported["summary"] == source["summary"]


def test_no_full_gold_lists_or_label_inputs(exported):
    for key in ("rows","choke","seeds","weights"):
        for row in exported[key]:
            assert not {"gold_nodes","gold_path","accepted_alternatives","handler_node","contract_node"} & row.keys()
            assert isinstance(row["gold_found"],list)
    # Stored misses are the one other required list of answer IDs, not labels.
    assert exported["summary"]["test_misses_budget20"] == json.loads(SOURCE.read_bytes())["summary"]["test_misses_budget20"]
    source = (ROOT/"bench/export_test_results_js.py").read_text(encoding="utf-8")
    assert not re.search(r"import .*egpot_eval|retrieve\(|read_graphml|test-final",source)


def test_two_exports_identical_and_source_unchanged(tmp_path,capsys):
    before = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    outputs = [tmp_path/"one.js",tmp_path/"two.js"]
    for output in outputs:
        assert main(["--results-dir",str(SOURCE.parent),"--output",str(output)]) == 0
    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == before
    printed = capsys.readouterr().out
    assert printed.index("TOP_LEVEL_KEYS") < printed.index("EXPORTED")
    assert "SAMPLE_ROW" in printed and "ROW_COUNTS" in printed


def test_latency_retained_but_excluded_from_content_comparison(exported):
    changed = deepcopy(exported)
    def alter(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key=="latency_s":value[key]=item+123
                else:alter(item)
        elif isinstance(value,list):
            for item in value:alter(item)
    alter(changed)
    changed["provenance"]["source_record_sha256"] = "timing changes source bytes"
    assert encode(changed) != encode(exported)
    assert non_latency_content(changed) == non_latency_content(exported)
    assert all("latency_s" in r for r in exported["rows"])


def test_multiple_non_secondlook_records_refused(tmp_path):
    for name in ("test_final_a.json","test_final_b.json","test_final_c_secondlook.json"):
        (tmp_path/name).write_text("{}")
    with pytest.raises(ValueError,match="found 2"):
        find_record(tmp_path)
    (tmp_path/"test_final_b.json").unlink()
    assert find_record(tmp_path).name == "test_final_a.json"


def test_missing_fields_are_disclosed(exported):
    warnings = " ".join(exported["provenance"]["missing_fields"])
    assert "DEV weight" in warnings and "graph and label SHA-256" in warnings
    assert not any(r["split"]=="dev" for r in exported["weights"])


def test_offline_scripts_and_tab_integration():
    sources = [ROOT/"viz/index.html",*sorted((ROOT/"viz/js").glob("*.js")),*sorted((ROOT/"viz/css").glob("*.css"))]
    for path in sources:
        assert not re.search(r"fetch\s*\(|XMLHttpRequest|https?://|\bCDN\b",path.read_text(encoding="utf-8"),re.I),path
    html = sources[0].read_text(encoding="utf-8")
    for ref in re.findall(r'(?:src|href)="([^"]+)"',html):
        assert not ref.startswith(("/","//")) and (ROOT/"viz"/ref).is_file()
    assert html.index('data-tab="results"') < html.index('data-tab="finaltest"')
    assert html.count('role="tab"') == 7  # Six existing tabs plus the requested final tab.
    assert 'src="data/online_boutique/results_test.js"' in html
    assert "See the Final test tab for the locked held-out run." in (ROOT/"viz/js/results_view.js").read_text()
