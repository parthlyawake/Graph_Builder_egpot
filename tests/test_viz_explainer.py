"""The guided page is local, linked, and separate from the other tabs."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
VIZ = ROOT / "viz"


def test_explainer_assets_and_tab_wiring():
    html = (VIZ / "index.html").read_text(encoding="utf-8")
    for name in ("explainer_logic.js", "explainer_view.js"):
        assert (VIZ / "js" / name).is_file()
        assert f'src="js/{name}"' in html
        assert html.index(f'src="js/{name}"') < html.index('src="js/app.js"')
    assert 'id="how-panel"' in html
    assert 'aria-label="How EG-POT works"' in html
    app = (VIZ / "js/app.js").read_text(encoding="utf-8")
    assert 'name === "how"' in app
    assert "new window.ExplainerView()" in app
    assert '"graph","how","player"' in app


def test_explainer_reuses_existing_data_components_and_pure_logic():
    view = (VIZ / "js/explainer_view.js").read_text(encoding="utf-8")
    for dependency in ("TraceData.load", "VIZ_GLOSSARY", "VIZ_GRAPH", "VIZ_RESULTS",
                       "TraversalPlayer.prototype.parallel"):
        assert dependency in view
    logic = (VIZ / "js/explainer_logic.js").read_text(encoding="utf-8")
    assert not re.search(r"\bdocument\b|createElement|querySelector", logic)
    # Measured facts must come from loaded payloads, not copied graph totals.
    assert "2153" not in view and "5813" not in view


def test_explainer_and_application_are_offline():
    # Raw source prose and bundled license text may contain URLs as data;
    # application code, resource references and markup must be local.
    sources = [VIZ / "index.html", *sorted((VIZ / "js").glob("*.js")),
               *sorted((VIZ / "css").glob("*.css"))]
    for source in sources:
        assert not re.search(r"fetch\s*\(|XMLHttpRequest|https?://|\bCDN\b",
                             source.read_text(encoding="utf-8"), re.I), source
    for reference in re.findall(r'(?:src|href)="([^"]+)"', sources[0].read_text(encoding="utf-8")):
        assert not reference.startswith(("/", "//"))
        assert (VIZ / reference).is_file()
