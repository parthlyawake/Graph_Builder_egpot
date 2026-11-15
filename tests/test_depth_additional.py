"""Additional evidence-path regression tests for paper-level depth features.

No assertions of whole-program soundness: source-bound argument flow and
ambiguous compiler definitions must remain explicitly conservative.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from graft_ckg import CKGBuilder
from lsp_augmenter import LSPIndexProvider


def _flow(graph):
    return {(u, v) for u, v, data in graph.edges(data=True)
            if data.get("relation") == "FLOWS_TO" and
            data.get("flow_kind") == "interprocedural"}


def _typed(graph):
    return (set(graph.nodes), Counter(
        (str(u), str(v), d.get("relation"), d.get("layer"))
        for u, v, d in graph.edges(data=True)))


def test_python_keyword_default_and_nested_expression_flow(tmp_path):
    (tmp_path / "f.py").write_text(
        "def combine(x, y=5):\n"
        "    return x + y\n\n"
        "def run(v):\n"
        "    total = combine(y=v+1, x=3)\n"
        "    return total\n", encoding="utf-8")
    builder = CKGBuilder(str(tmp_path))
    builder.build()
    graph = builder.graph
    flow = _flow(graph)
    assert ("f.py:combine.return::2", "f.py:run.var::total") in flow
    assert any(v == "f.py:combine.var::y" and
               graph.nodes[u].get("name") == "v + 1"
               for u, v in flow)
    assert any(u == "f.py:run.var::v" and
               graph.nodes[v].get("name") == "v + 1"
               for u, v in flow)
    assert any(v == "f.py:combine.var::x" and
               graph.nodes[u].get("name") == "3"
               for u, v in flow)
    assert not any(v == "f.py:combine.var::x" and
                   u == "f.py:run.var::v" for u, v in flow)

    # A source delta does not erase or mis-map the keyword dataflow.
    (tmp_path / "f.py").write_text(
        "def combine(x, y=5):\n"
        "    return x + y\n\n"
        "def run(v):\n"
        "    total = combine(y=v+2, x=3)\n"
        "    return total\n", encoding="utf-8")
    builder.update_files(["f.py"])
    fresh = CKGBuilder(str(tmp_path))
    fresh.build()
    assert _typed(builder.graph) == _typed(fresh.graph)


def test_python_optional_positional_default_does_not_invent_argument(tmp_path):
    (tmp_path / "f.py").write_text(
        "def foo(x, y=5):\n"
        "    return x\n\n"
        "def bar(z):\n"
        "    return foo(z)\n", encoding="utf-8")
    builder = CKGBuilder(str(tmp_path))
    builder.build()
    flow = _flow(builder.graph)
    assert ("f.py:bar.var::z", "f.py:foo.var::x") in flow
    assert not any(v == "f.py:foo.var::y" for _, v in flow)


def test_unresolved_unpacking_does_not_claim_exact_parameter_flow(tmp_path):
    (tmp_path / "f.py").write_text(
        "def foo(x, y):\n"
        "    return x\n\n"
        "def bar(data):\n"
        "    return foo(**data)\n", encoding="utf-8")
    builder = CKGBuilder(str(tmp_path))
    builder.build()
    flow = _flow(builder.graph)
    assert not any(v in {"f.py:foo.var::x", "f.py:foo.var::y"}
                   for _, v in flow)


def test_lsp_conflicting_occurrences_are_not_promoted_to_exact():
    provider = LSPIndexProvider()
    provider.register("src/a.py", "run", "a.py:run", line=3)
    provider.register("src/a.py", "run", "b.py:run", line=5)
    assert provider.resolve("src/a.py", "run", line=3) == "a.py:run"
    assert provider.resolve("src/a.py", "run", line=5) == "b.py:run"
    assert provider.resolve("src/a.py", "run") is None
    provider.register("src/a.py", "run", "other.py:run", line=3)
    assert provider.resolve("src/a.py", "run", line=3) is None

    provider.register("lib/util.py", "send", "lib/util.py:send")
    provider.register("test/util.py", "send", "test/util.py:send")
    assert provider.resolve("app/util.py", "send") is None
    assert provider.resolve("lib/util.py", "send") == "lib/util.py:send"


def test_expression_assignment_and_return_dependency_flow(tmp_path):
    (tmp_path / "calc.py").write_text(
        "def total(a, b):\n"
        "    intermediate = a * 2 + b\n"
        "    return intermediate + a\n", encoding="utf-8")
    builder = CKGBuilder(str(tmp_path))
    builder.build()
    edges = {(u, v) for u, v, data in builder.graph.edges(data=True)
             if data.get("relation") == "FLOWS_TO" and
             data.get("layer") == "Lflow"}
    assert ("calc.py:total.var::a", "calc.py:total.var::intermediate") in edges
    assert ("calc.py:total.var::b", "calc.py:total.var::intermediate") in edges
    assert ("calc.py:total.var::a", "calc.py:total.return::3") in edges
    assert ("calc.py:total.var::intermediate", "calc.py:total.return::3") in edges


def test_expression_dependency_survives_incremental_edit(tmp_path):
    (tmp_path / "math.py").write_text(
        "def calc(x):\n    amount = x + 3\n    return amount * x\n",
        encoding="utf-8")
    builder = CKGBuilder(str(tmp_path))
    builder.build()
    (tmp_path / "math.py").write_text(
        "def calc(x):\n    amount = x * 3\n    return amount + x\n",
        encoding="utf-8")
    builder.update_files(["math.py"])
    clean = CKGBuilder(str(tmp_path))
    clean.build()
    assert _typed(builder.graph) == _typed(clean.graph)


def test_lsp_same_basename_different_directory_is_not_exact():
    provider = LSPIndexProvider()
    provider.register("lib/shared.py", "execute", "lib/shared.py:execute")
    assert provider.resolve("src/shared.py", "execute") is None
    # A bare basename is permitted only when it identifies one unique source.
    assert provider.resolve("shared.py", "execute") == "lib/shared.py:execute"
