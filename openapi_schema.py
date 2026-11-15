"""Bounded OpenAPI JSON Pointer resolution for 2.0 and 3.x documents.

Only references within the same document are resolved. Cyclic $refs remain
explicit with a recursion marker; remote or file references remain unresolved.
This prevents graph builds from fetching arbitrary remote URLs.
"""
from __future__ import annotations

from copy import deepcopy


def resolve_local_refs(document, value, *, depth_limit=40):
    def lookup(pointer):
        if not pointer.startswith("#/"):
            return None
        current = document
        for encoded in pointer[2:].split("/"):
            key = encoded.replace("~1", "/").replace("~0", "~")
            if isinstance(current, dict) and key in current:
                current = current[key]
            elif isinstance(current, list) and key.isdigit() and int(key) < len(current):
                current = current[int(key)]
            else:
                return None
        return current

    def visit(obj, seen, depth):
        if depth > depth_limit:
            return {"$error": "ref_depth_exceeded"}
        if isinstance(obj, list):
            return [visit(item, seen, depth+1) for item in obj]
        if not isinstance(obj, dict):
            return obj
        uri = obj.get("$ref")
        if isinstance(uri, str):
            if not uri.startswith("#/"):
                return deepcopy(obj)
            if uri in seen:
                return {"$ref": uri, "recursive": True}
            target = lookup(uri)
            if target is None:
                return {"$ref": uri, "unresolved": True}
            expanded = visit(target, seen | {uri}, depth+1)
            # OpenAPI 3.1 permits sibling keywords next to a reference.
            siblings = {k: v for k, v in obj.items() if k != "$ref"}
            if siblings and isinstance(expanded, dict):
                expanded.update(visit(siblings, seen | {uri}, depth+1))
            return expanded
        return {key: visit(val, seen, depth+1) for key, val in obj.items()}
    return visit(value, frozenset(), 0)
