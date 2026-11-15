"""A TS/TSX fallback is valid only when the replacement AST is error-free."""
from polyglot import TreeSitterExtractor


def test_ts_and_tsx_reparse_preserves_original_source():
    src = b"const X = <T,>(value: T) => value;\n"
    for extension in (".ts", ".tsx"):
        extractor = TreeSitterExtractor(extension)
        parsed, selected = extractor.parse_source(src)
        assert selected in {"ts", "tsx"}
        assert parsed.root_node.end_byte == len(src)


def test_unparseable_typescript_does_not_claim_success():
    src = b"const value = {\n"
    result, selected = TreeSitterExtractor(".ts").parse_source(src)
    assert result.root_node.has_error
    assert selected == "ts"


def test_parser_projection_state_is_file_local():
    extractor = TreeSitterExtractor(".ts")
    extractor.last_projection = {"kind": "prior_file_projection"}
    result, _ = extractor.parse_source(b"export const simple = 2;\n")
    assert not result.root_node.has_error
    assert extractor.last_projection is None
