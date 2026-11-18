"""Offline comparison assets and glossary coverage."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
VIZ = ROOT / "viz"


def script_data(path, name):
    text = path.read_text(encoding="utf-8")
    prefix = "window." + name + " = "
    assert text.startswith(prefix)
    return json.loads(text[len(prefix):].rstrip(";\n"))


def test_glossary_covers_all_methods_and_metrics():
    glossary = script_data(VIZ / "js/glossary.js", "VIZ_GLOSSARY")
    results = script_data(VIZ / "data/online_boutique/results.js", "VIZ_RESULTS")
    index = json.loads((VIZ / "data/online_boutique/traces_index.json").read_text())
    assert {r["method"] for r in [*results["rows"], *index]} <= set(glossary)
    for key in ("hit", "gold_recall", "precision", "path_coverage", "ordered_path_match",
                "nodes_returned", "nodes_to_hit", "latency_s", "score_relevance", "score_hop",
                "score_contract", "score_entropy", "pareto_front", "explicit", "indirect"):
        assert key in glossary
    for key, entry in glossary.items():
        assert set(entry) == {"key", "label", "short", "long"}
        assert entry["key"] == key
        assert all(isinstance(v, str) and v for v in entry.values())
    view = (VIZ / "js/results_view.js").read_text(encoding="utf-8")
    metric_keys = re.findall(r'(\w+):"[^"]+"', view.split("const metrics={", 1)[1].split("};", 1)[0])
    assert set(metric_keys) <= set(glossary)


def test_verified_glossary_wording_and_mcts_variants():
    glossary = script_data(VIZ / "js/glossary.js", "VIZ_GLOSSARY")
    assert glossary["egpot_full"]["short"] == "Walks outward from the start node, scoring each neighbor on four things and keeping the Pareto-best."
    assert glossary["score_contract"]["short"] == "1.0 if the step crosses a service contract (or lands on a contract node), otherwise 0.6."
    for key in ("pareto", "entropy", "contracts", "choke_point"):
        base = glossary["egpot_no_" + key]
        variant = glossary["egpot_no_" + key + "_mcts"]
        assert base["short"] in variant["short"]
        assert base["long"] in variant["long"]
        assert "with the MCTS lookahead on" in variant["long"]


def test_all_application_assets_are_offline():
    # Source-data prose and vendor license text may contain URLs. App code
    # and markup may not reference network resources or remote loaders.
    sources = [VIZ / "index.html", *sorted((VIZ / "js").glob("*.js")),
               *sorted((VIZ / "css").glob("*.css"))]
    for source in sources:
        assert not re.search(r"fetch\s*\(|XMLHttpRequest|https?://|\bCDN\b", source.read_text(encoding="utf-8"), re.I), source
    for ref in re.findall(r'(?:src|href)="([^"]+)"', sources[0].read_text(encoding="utf-8")):
        assert not ref.startswith(("/", "//"))
        assert (VIZ / ref).is_file()
    assert 'id="compare-panel"' in sources[0].read_text(encoding="utf-8")
