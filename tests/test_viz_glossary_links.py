"""Shared glossary markup and permitted seventh-tab regression correction."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_old_glossary_icon_markup_and_css_removed():
    for path in (ROOT/"viz").rglob("*"):
        if not path.is_file() or path.suffix not in {".js",".html",".css",".cjs"}:
            continue
        assert "term-help" not in path.read_text(encoding="utf-8"),path
    source = (ROOT/"viz/js/glossary_view.js").read_text(encoding="utf-8")
    assert 'el("span","term-help","?")' not in source
    assert 'node.textContent+=" ?"' not in source
    assert 'el("button","glossary-link"' in source


def test_shared_glossary_accessibility_and_offline_resources():
    source = (ROOT/"viz/js/glossary_view.js").read_text(encoding="utf-8")
    assert "GLOSSARY_LINK_FIRST_ONLY_PER_BLOCK" in source
    assert 'aria-haspopup' in source and 'aria-expanded' in source
    for name in ("help","label","panel","selectorHelp","svgHelp"):
        assert f"function {name}(" in source
    for path in [ROOT/"viz/index.html",*(ROOT/"viz/js").glob("*.js"),*(ROOT/"viz/css").glob("*.css")]:
        assert not re.search(r"fetch\s*\(|XMLHttpRequest|https?://|\bCDN\b",path.read_text(encoding="utf-8"),re.I),path
