"""Parse explicitly evidenced stack-frame locations without double-counting.

Specific traceback grammars run before generic file:line matches. A generic
match overlapping a named frame is suppressed; otherwise it can reintroduce
false candidates if a line falls within a different nested function.
"""
from __future__ import annotations

import re


_FRAME_PATTERNS = (
    # Python interpreter / unittest tracebacks
    re.compile(
        r'(?m)^[ \t]*File\s+"(?P<path>[^"\r\n]+)",\s+line\s+'
        r'(?P<line>\d+)(?:,\s+in\s+(?P<function>[\w.<>]+))?'
    ),
    # pytest --tb=short (including Windows drive letters and file paths with '-')
    re.compile(
        r'(?m)^[ \t]*(?P<path>(?:[A-Za-z]:)?[^:\r\n]+?\.'
        r'(?:py|pyw|go|js|jsx|ts|tsx|java|cs|kt))'
        r':(?P<line>\d+):\s+in\s+(?P<function>[\w.<>]+)'
    ),
    # Java JVM thread stack frames
    re.compile(
        r'(?m)^[ \t]*at\s+(?:[\w.$]+)\('
        r'(?P<path>[\w./\\-]+\.(?:java|go)):(?P<line>\d+)\)'
    ),
    # Go/Node/python tracebacks with bare path:line
    re.compile(
        r'(?P<path>(?:[A-Za-z]:)?[\w./\\-]+\.'
        r'(?:go|js|jsx|ts|tsx|py|pyw|java|cs|kt)):(?P<line>\d+)'
    ),
)


def parse_stack_frames(stack_trace: str) -> list[tuple[str, int, str]]:
    """Yield (file, one-based line, printed function) in textual frame order.

    A parseable but unresolved stack frame is still evidence: the caller must
    not substitute a generic service-level guess for that frame.
    """
    if not stack_trace:
        return []
    matches: list[tuple[int, int, str, int, str]] = []
    occupied: list[tuple[int, int]] = []
    for priority, pattern in enumerate(_FRAME_PATTERNS):
        for match in pattern.finditer(stack_trace):
            start, end = match.span()
            if any(start < hi and lo < end for lo, hi in occupied):
                continue
            line = int(match.group("line"))
            if line <= 0:
                continue
            path = match.group("path").strip()
            if not path:
                continue
            function = (match.group("function") or "").strip() if "function" in match.re.groupindex else ""
            # <module> isn't a named function; retain a line-only frame.
            if function in ("<module>", "<lambda>"):
                function = ""
            occupied.append((start, end))
            matches.append((start, priority, path, line, function))
    matches.sort(key=lambda x: (x[0], x[1]))
    return [(path, line, function) for _, _, path, line, function in matches]
