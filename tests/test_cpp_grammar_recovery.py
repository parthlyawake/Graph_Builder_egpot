"""Parser projection never changes source size or claims original validation."""
from cpp_grammar_recovery import projected_cpp_source, recover_cpp_tree
from tree_sitter import Language, Parser
import tree_sitter_cpp


def test_generated_member_pointer_projection_offsets():
    original = (
        b"typedef void (ServiceProcessor::*ProcessFunction)(int32_t);\n"
        b"void f() { (this->*(fn->second))(1); }\n"
    )
    projected, mask, reasons = projected_cpp_source(original)
    assert len(projected) == len(original)
    assert projected.count(b"\n") == original.count(b"\n")
    assert b"(*ProcessFunction)" in projected
    assert "member_pointer_typedef" in reasons
    assert "member_pointer_dispatch" in reasons


def test_projection_does_not_recover_genuinely_invalid_cpp():
    parser = Parser(Language(tree_sitter_cpp.language()))
    tree, recovery, mask = recover_cpp_tree(
        parser, b"class Broken { void fn( { ;", "cpp")
    assert tree.root_node.has_error
    assert recovery is None
    assert not mask
