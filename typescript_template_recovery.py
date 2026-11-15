"""Conservative TS/TSX CSS-in-JS template AST recovery.

Only erroring source files and literal template-string AST spans associated
with CSS-in-JS tags are considered. Source spans are replaced with spaces
without changing byte offsets. Recovered ASTs are marked as projections,
not exact-source syntax verification. GraphQL and regular JS templates
are deliberately untouched.
"""
from __future__ import annotations

import re


_CSS_TAG = re.compile(
    rb"\b(?:styled|css|keyframes|createGlobalStyle)\b",
    re.IGNORECASE,
)


def _walk(root):
    todo = [root]
    while todo:
        node = todo.pop()
        yield node
        todo.extend(reversed(node.named_children))


def project_css_templates(raw, root):
    out = bytearray(raw)
    spans = []
    for node in _walk(root):
        if node.type not in {"template_string", "template_literal"}:
            continue
        if node.end_byte <= node.start_byte+2:
            continue
        prefix = raw[max(0, node.start_byte-240):node.start_byte]
        # Tag must be syntactically adjacent to this template (with optional
        # type arguments). Do not blank random templates merely because a
        # styled import occurred earlier in the file.
        if b";" in prefix.rsplit(b"\n", 1)[-1]:
            continue
        if not _CSS_TAG.search(prefix):
            continue
        if raw[node.start_byte:node.start_byte+1] != b"\x60":
            continue
        if raw[node.end_byte-1:node.end_byte] != b"\x60":
            continue
        start, end = node.start_byte+1, node.end_byte-1
        if start >= end:
            continue
        for i in range(start, end):
            if raw[i] not in (10, 13):
                out[i] = 32
        spans.append((start, end))
    return bytes(out), spans
