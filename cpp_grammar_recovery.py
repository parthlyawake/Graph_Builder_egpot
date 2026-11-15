"""Offset-preserving recovery projections for C and C++ grammar limitations.

The original source remains the graph evidence. These projections allow
Tree-sitter to extract unaffected declarations when a valid C++ pointer-to-
member type or a macro-adjacent string causes error recovery. Projected input
does NOT establish exact-source grammar completeness.
"""
from __future__ import annotations

import re


def projected_cpp_source(original):
    """Return (projected bytes, masked spans, applied transforms)."""
    out = bytearray(original)
    spans, reasons = [], []

    def blank(start, end, reason):
        for i in range(start, end):
            if original[i] not in (10, 13):
                out[i] = 32
        spans.append((start, end))
        reasons.append(reason)

    # typedef void (Class::*Method)(args) and similar pointer-to-member forms:
    # hide only the member qualification, leaving (*Method)(args) parseable.
    for match in re.finditer(
        rb"\(\s*((?:[A-Za-z_]\w*::)*[A-Za-z_]\w*)::\*([A-Za-z_]\w*)\s*\)",
        original,
    ):
        blank(match.start(1), match.end(1) + 2, "member_pointer_typedef")

    # (this->*(iterator->second))(...) is a valid C++ pointer-to-member call;
    # retain the dereference while hiding the unsupported receiver syntax.
    for match in re.finditer(rb"\b(this)(->\*)(?=\s*\()", original):
        blank(match.start(1), match.end(1)+2, "member_pointer_dispatch")

    # String-literal macros expanded by the preprocessor are not parsable
    # without preprocessor context. Handle only locally defined string macros.
    macros = set(re.findall(
        rb"(?m)^[ \t]*#[ \t]*define[ \t]+([A-Z_][A-Z0-9_]*)[ \t]+\"[^\"\n]*\"",
        original,
    ))
    for name in macros:
        pat = rb'"[^"\n]*"[ \t]+(' + re.escape(name) + rb')[ \t]+"'
        for match in re.finditer(pat, original):
            blank(match.start(1), match.end(1), "adjacent_string_macro")

    # A preprocessor macro may sit between two string literals. The parser
    # does not expand that macro, although the C/C++ compiler does. Replace the
    # entire sequence with one placeholder literal and equal-length spaces;
    # never alter names, signatures or executable call targets.
    for name in macros:
        pattern = (rb'"(?:[^"\\\n]|\\.)*"[ \t]*' +
                   re.escape(name) +
                   rb'[ \t]*"(?:[^"\\\n]|\\.)*"')
        for match in re.finditer(pattern, original):
            start, end = match.span()
            if end - start < 2:
                continue
            out[start:end] = b'""' + b" " * (end - start - 2)
            spans.append((start, end))
            reasons.append("expanded_adjacent_string_macro")

    # A C ABI declaration may use a compile-time visibility macro just before
    # a real primitive return type: LUALIB_API int foo(...). This is syntax
    # scaffolding, not an independently resolved type. Bound the rewrite to
    # uppercase *_API / *_EXPORT prefixes preceding an explicit C return type.
    abi_pattern = (rb"(?m)(?:^|[;{}]\s*)[ \t]*"
                   rb"([A-Z][A-Z0-9_]*(?:_API|_EXPORT))[ \t]+"
                   rb"(?=(?:int|void|char|long|short|double|float|size_t|bool)\b)")
    for match in re.finditer(abi_pattern, original):
        blank(match.start(1), match.end(1), "visibility_macro_prefix")

    return bytes(out), spans, sorted(set(reasons))


def recover_cpp_tree(parser, original, language="cpp"):
    """Return original tree or an error-free projection, with provenance."""
    primary = parser.parse(original)
    if not primary.root_node.has_error or language not in {"cpp", "c"}:
        return primary, None, ()
    projected, masked, reasons = projected_cpp_source(original)
    if not masked or projected == original:
        return primary, None, ()
    alternate = parser.parse(projected)
    if not alternate.root_node.has_error:
        return alternate, {
            "kind": "offset_preserving_source_projection",
            "transforms": reasons,
            "validated": "projected_ast_only",
            "exact_source_syntax_verified": False,
            "masked_bytes": sum(b-a for a,b in masked),
        }, masked
    return primary, None, ()


def intersects_mask(node, masks):
    return any(node.start_byte < b and node.end_byte > a for a, b in masks)
