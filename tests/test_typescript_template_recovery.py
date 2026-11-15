"""CSS-in-JS recovery never modifies offsets or ordinary GraphQL templates."""
from tree_sitter import Language, Parser
import tree_sitter_typescript

from typescript_template_recovery import project_css_templates


def test_tsx_styled_template_projection_preserves_all_offsets():
    source = (b"const A = styled.div<{ active: boolean }>\x60\n"
              b" color: \x24{props => props.active ? 'red' : 'blue'};\n\x60;\n")
    parser = Parser(Language(tree_sitter_typescript.language_tsx()))
    tree = parser.parse(source)
    projected, spans = project_css_templates(source, tree.root_node)
    assert len(projected) == len(source)
    assert projected.count(b"\n") == source.count(b"\n")
    assert spans
    assert b"const A" in projected


def test_non_css_graphql_template_is_not_blank():
    source = b"const Query = gql\x60query Get { user { id } }\x60;\n"
    parser = Parser(Language(tree_sitter_typescript.language_tsx()))
    tree = parser.parse(source)
    projected, spans = project_css_templates(source, tree.root_node)
    assert projected == source
    assert spans == []
