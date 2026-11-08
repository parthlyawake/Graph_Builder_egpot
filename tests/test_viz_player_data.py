"""Read-only checks of trace wrappers and offline player assets."""
import json
from pathlib import Path
import re

import pytest

from bench.export_traces_js import wrappers
from bench.egpot_eval import split_by_link

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "viz/data/online_boutique"
LABELS = ROOT / "bench/labels/online_boutique_egpot_queries.json"


@pytest.fixture(scope="module")
def generated():
    return wrappers(DATA, LABELS)


def decode(content):
    return json.loads(content.decode("utf-8").split(" = ")[-1].rstrip(";\n"))


def test_wrappers_equal_sources_and_are_installed(generated):
    sources = list((DATA / "traces").glob("*.json"))
    assert len(sources) == 320
    for source in sources:
        relative = f"traces_js/{source.stem}.js"
        assert decode(generated[relative]) == json.loads(source.read_text(encoding="utf-8"))
        assert (DATA / relative).read_bytes() == generated[relative]
    assert decode(generated["traces_index.js"]) == json.loads((DATA / "traces_index.json").read_text())


def test_wrapper_bytes_deterministic(generated):
    assert wrappers(DATA, LABELS) == generated


def test_no_gold_fields_in_trace_wrappers(generated):
    def check(value):
        if isinstance(value, dict):
            assert not any(str(k).lower().startswith("gold") for k in value)
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)
    for name, content in generated.items():
        if name.startswith("traces_js/"):
            check(decode(content))


def test_gold_is_dev_only_and_loaded_on_reveal(generated):
    rows = json.loads(LABELS.read_text(encoding="utf-8"))
    dev = split_by_link(rows)["dev"]
    gold = decode(generated["gold.js"])
    assert set(gold) == {q["id"] for q in dev}
    assert len(gold) == 16
    for row in dev:
        assert gold[row["id"]] == {key: row[key] for key in ("gold_nodes", "gold_path")}
    html = (ROOT / "viz/index.html").read_text(encoding="utf-8")
    assert "gold.js" not in html
    view = (ROOT / "viz/js/player_view.js").read_text(encoding="utf-8")
    assert view.index('loadScript("data/online_boutique/gold.js"') > view.index("async reveal()")


def test_offline_app_assets():
    # The bundled library and source-data text can contain URLs as text;
    # executable app code and markup must have no remote resource access.
    files = [ROOT / "viz/index.html", *sorted((ROOT / "viz/js").glob("*.js")),
             *sorted((ROOT / "viz/css").glob("*.css"))]
    for path in files:
        assert not re.search(r"fetch\s*\(|XMLHttpRequest|https?://|\bCDN\b",
                             path.read_text(encoding="utf-8"), re.IGNORECASE), path
    for reference in re.findall(r'(?:src|href)="([^"]+)"', files[0].read_text(encoding="utf-8")):
        assert not reference.startswith(("/", "//"))
        assert (ROOT / "viz" / reference).is_file()
