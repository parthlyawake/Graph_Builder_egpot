"""TSX syntax must use JSX-aware grammar, unlike ordinary TypeScript."""
from pathlib import Path

from graft_ckg import CKGBuilder
from polyglot import TreeSitterExtractor


def test_tsx_jsx_syntax_and_graph_entities(tmp_path):
    source = (
        'export function Badge(props: {name: string}): JSX.Element {\n'
        '  return <span className="badge">{props.name}</span>;\n'
        '}\n'
    )
    path = tmp_path / "Badge.tsx"
    path.write_text(source, encoding="utf-8")
    grammar = TreeSitterExtractor(".tsx").parser
    assert not grammar.parse(source.encode()).root_node.has_error

    builder = CKGBuilder(str(tmp_path))
    graph = builder.build()
    report = builder.get_language_report()["languages"]["typescript"]
    assert report["parsed"] == 1
    assert report["partial"] == 0
    assert "Badge.tsx:Badge" in graph


def test_tsx_object_type_and_multiline_jsx(tmp_path):
    source = (
        'type Props = { title?: string; count: number };\n'
        'export function Summary({title, count}: Props) {\n'
        '  return <section><h1>{title ?? "Unknown"}</h1>\n'
        '    <span data-count={count}>{count}</span></section>;\n'
        '}\n'
    )
    assert TreeSitterExtractor(".tsx").parser.parse(source.encode()).root_node.has_error is False
