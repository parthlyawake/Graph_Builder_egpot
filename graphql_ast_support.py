"""Optional standards-based GraphQL parser integration.

graphql-core handles SDL extensions, directives, multiline argument lists,
operation variables, aliases, and quoted literals. The legacy lightweight
parser remains a fallback when graphql-core is unavailable.
"""
from __future__ import annotations


def parse_schema_ast(text):
    """Return schema type information, or None if graphql-core unavailable."""
    try:
        from graphql import parse, print_ast
    except ImportError:
        return None
    try:
        doc = parse(text)
    except Exception:
        return {"types": {}, "root_types": {}, "invalid": True}

    kinds = {
        "object_type_definition": "type",
        "object_type_extension": "type",
        "interface_type_definition": "interface",
        "interface_type_extension": "interface",
        "input_object_type_definition": "input",
        "input_object_type_extension": "input",
        "enum_type_definition": "enum",
        "enum_type_extension": "enum",
    }
    types, root_types = {}, {}
    for definition in doc.definitions:
        if definition.kind in {"schema_definition", "schema_extension"}:
            for operation in definition.operation_types or ():
                root_types[operation.operation.value] = operation.type.name.value
            continue
        kind = kinds.get(definition.kind)
        if not kind:
            continue
        name = definition.name.value
        current = types.setdefault(name, {"kind": kind, "fields": {}})
        for field in getattr(definition, "fields", None) or ():
            arguments = {
                arg.name.value: print_ast(arg.type)
                for arg in getattr(field, "arguments", None) or ()
            }
            current["fields"][field.name.value] = {
                "name": field.name.value,
                "type_name": print_ast(field.type),
                "arguments": arguments,
            }
    return {"types": types, "root_types": root_types, "invalid": False}


def parse_operations_ast(text):
    """Return (kind,name,root_fields) tuples, or None if dependency missing."""
    try:
        from graphql import parse
    except ImportError:
        return None
    try:
        doc = parse(text)
    except Exception:
        return []
    operations = []
    for definition in doc.definitions:
        if definition.kind != "operation_definition":
            continue
        kind = definition.operation.value
        name = definition.name.value if definition.name else (
            "anonymous" if not operations else f"anonymous_{len(operations)+1}"
        )
        fields = []
        for selection in definition.selection_set.selections:
            if selection.kind == "field":
                fields.append(selection.name.value)
        operations.append((kind, name, tuple(dict.fromkeys(fields))))
    return operations
