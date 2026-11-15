"""Evidence-aware overload resolution for Java and C#.

This module filters method candidates by lexical/declared receiver type,
argument arity and literal types. It never promotes an unresolved dynamic
receiver to an exact target based solely on a method-name coincidence.
"""
from __future__ import annotations

import re


def normalized_type(value):
    if not value:
        return ""
    token = re.sub(r"<.*>", "", str(value).strip().rstrip("?")).split(".")[-1]
    return token.lower().replace("system.", "")


def literal_kind(expression):
    s = str(expression).strip()
    if re.fullmatch(r'(?s)"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', s):
        return "string"
    if re.fullmatch(r"-?\d+[lL]?", s):
        return "int"
    if re.fullmatch(r"-?(?:\d+\.\d*|\.\d+)(?:[fFdDmM])?", s):
        return "float"
    if s in ("true", "false", "True", "False"):
        return "bool"
    if s in ("null", "None", "nil"):
        return "null"
    return ""


def parameter_types(raw):
    """Parse ordinary Java/C# parameter declarations, tracking generic commas."""
    raw = str(raw).strip()
    if raw.startswith("(") and raw.endswith(")"):
        raw = raw[1:-1]
    if not raw.strip():
        return ()
    parts, piece, depth = [], [], 0
    for char in raw:
        if char in "<[(":
            depth += 1
        elif char in ">])":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            parts.append("".join(piece).strip())
            piece = []
        else:
            piece.append(char)
    parts.append("".join(piece).strip())
    parsed = []
    for part in parts:
        part = re.sub(r"@\w+(?:\([^)]*\))?", "", part)
        part = re.sub(r"\b(?:final|ref|out|in|params|this|readonly)\b", "", part)
        part = part.split("=", 1)[0].strip()
        m = re.search(r"[A-Za-z_]\w*\s*(?:\[\])?\s*$", part)
        parsed.append(part[:m.start()].strip() if m else "")
    return tuple(parsed)


def _type_match(value_kind, declared):
    if not value_kind:
        return True
    expected = normalized_type(declared)
    if not expected:
        return True
    candidates = {
        "string": {"string", "char", "charsequence"},
        "int": {"int", "integer", "int32", "long", "int64", "short", "byte", "number"},
        "float": {"float", "double", "decimal", "number"},
        "bool": {"bool", "boolean"},
        "null": {"object", "string"},
    }
    if value_kind == "null":
        return expected not in {"int", "long", "float", "double", "boolean", "bool"}
    known = candidates.get(value_kind, set())
    return expected not in {"int", "integer", "long", "short", "float", "double",
                            "decimal", "string", "char", "boolean", "bool"} or expected in known


def select_overloads(builder, caller_id, callee_name, source_file, records=None):
    """Return list of evidence-compatible method nodes or None if not applicable.

    A return of None leaves other call-resolution paths unchanged. Returning
    [] means declarations exist but source evidence excludes every candidate.
    """
    name = callee_name.rsplit(".", 1)[-1]
    if records is None:
        records = [r for r in getattr(builder, "callsite_evidence", ())
                   if r.get("caller") == caller_id and r.get("callee") == callee_name
                   and r.get("file") == source_file]
    if not records:
        return None
    candidates = [nid for nid in builder.symbols_by_name.get(name, ())
                  if nid in builder.graph and
                  builder.graph.nodes[nid].get("type") == "function" and
                  builder.graph.nodes[nid].get("overload_group")]
    if len(candidates) < 2:
        return None
    receiver = callee_name.rpartition(".")[0]
    if receiver in ("self", "this", ""):
        owner = caller_id.rsplit(".", 1)[0] if "." in caller_id else ""
        if owner:
            candidates = [nid for nid in candidates
                          if builder.graph.nodes[nid]["overload_group"].startswith(owner + ".")]
    else:
        inferred = builder.var_types.get(caller_id, {}).get(receiver)
        if not inferred:
            return None
        owners = [nid for nid in builder.symbols_by_name.get(inferred, ())
                  if nid in builder.graph and builder.graph.nodes[nid].get("type") == "class"]
        if len(owners) != 1:
            return None
        owner = owners[0]
        candidates = [nid for nid in candidates
                      if builder.graph.nodes[nid]["overload_group"].startswith(owner + ".")]
    if not candidates:
        return None
    picked = set()
    for evidence in records:
        kinds = evidence.get("argument_kinds", ())
        arity = len(evidence.get("arguments", ()))
        applicable = []
        for nid in candidates:
            meta = builder.graph.nodes[nid]
            if meta.get("arity") != arity:
                continue
            parameters = meta.get("param_types", ())
            if len(parameters) != arity:
                continue
            if all(_type_match(kind, typ) for kind, typ in zip(kinds, parameters)):
                applicable.append(nid)
        picked.update(applicable)
    return sorted(picked)
