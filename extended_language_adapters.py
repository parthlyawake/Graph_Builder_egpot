"""Source-grounded Tree-sitter adapters for Ruby, Lua, C and C++.

The adapter is deliberately conservative: it emits declarations, lexical
containment, imports and call-site candidates. It does not guess call targets
from receiver names, infer dynamic dispatch or claim complete type resolution.
"""
from __future__ import annotations

import importlib
import re
from pathlib import Path

from tree_sitter import Language, Parser

GRAMMAR_MODULES = {
    "ruby": "tree_sitter_ruby",
    "lua": "tree_sitter_lua",
    "cpp": "tree_sitter_cpp",
    "c": "tree_sitter_c",
    "scala": "tree_sitter_scala",
}
EXTENSION_LANGUAGE = {
    ".rb": "ruby",
    ".lua": "lua",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".hxx": "cpp",
    ".h": "cpp",  # C-compatible headers can use the C++ grammar.
    ".c": "c",
    ".scala": "scala",
}
DECLARATIONS = {
    "ruby": {
        "class": "class",
        "module": "module",
        "method": "function",
        "singleton_method": "function",
    },
    "lua": {
        "function_declaration": "function",
        "function_definition": "function",
        "local_function": "function",
    },
    "cpp": {
        "namespace_definition": "module",
        "class_specifier": "class",
        "struct_specifier": "class",
        "function_definition": "function",
    },
    "c": {
        "struct_specifier": "class",
        "function_definition": "function",
    },
    "scala": {
        "class_definition": "class",
        "object_definition": "module",
        "trait_definition": "class",
        "function_definition": "function",
    },
}
CALLS = {
    "ruby": {"call", "command", "command_call", "method_call"},
    "lua": {"function_call", "method_call"},
    "cpp": {"call_expression"},
    "c": {"call_expression"},
    "scala": {"call_expression"},
}
IDENTIFIERS = frozenset({
    "identifier", "constant", "type_identifier", "field_identifier",
    "name", "method", "variable", "scope_resolution", "qualified_identifier",
    "namespace_identifier",
})


def grammar_available(language):
    try:
        module = importlib.import_module(GRAMMAR_MODULES[language])
        return callable(module.language)
    except (ImportError, AttributeError):
        return False


def source_text(node, raw):
    return raw[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _name_of(node, raw, lang):
    """Select a declaration's AST name, never its body or return type."""
    field = node.child_by_field_name("name")
    if field is None and lang in {"cpp", "c"} and node.type == "function_definition":
        field = node.child_by_field_name("declarator")
    if field is not None:
        if field.type in IDENTIFIERS:
            spelling = source_text(field, raw)
        else:
            # Function declarators nest inside pointer/ref/qualified declarators.
            p = field
            for _ in range(10):
                nested = p.child_by_field_name("declarator")
                if nested is None:
                    break
                p = nested
            candidate = p.child_by_field_name("name")
            spelling = source_text(candidate or p, raw)
    elif lang == "lua" and node.type == "function_definition":
        # Anonymous Lua expressions are not named function declarations.
        return None
    else:
        candidates = [x for x in node.named_children if x.type in IDENTIFIERS]
        if not candidates:
            return None
        spelling = source_text(candidates[0], raw)
    spelling = spelling.strip()
    if lang in {"cpp", "c"}:
        spelling = spelling.split("(", 1)[0].split("<", 1)[0].rsplit("::", 1)[-1]
        spelling = re.sub(r"^[*&\s]+", "", spelling)
    if lang == "scala":
        spelling = spelling.rsplit(".", 1)[-1]
    if lang == "ruby":
        spelling = spelling.rsplit(".", 1)[-1]
    if lang == "lua":
        spelling = spelling.rsplit(":", 1)[-1].rsplit(".", 1)[-1]
    return spelling if re.fullmatch(r"~?[A-Za-z_]\w*[!?=]?", spelling) else None


def _call_name(node, raw, lang):
    callee = node.child_by_field_name("function") or node.child_by_field_name("name")
    if callee is None:
        callee = next((x for x in node.named_children
                       if x.type not in {"arguments", "argument_list", "do_block", "block"}),
                      None)
    if callee is None:
        return None
    spelled = source_text(callee, raw).strip()
    if len(spelled) > 160:
        return None
    if lang == "ruby":
        # Ruby AST often keeps bare method identifiers inside call/method fields.
        spelled = spelled.lstrip(":")
    elif lang == "lua":
        spelled = spelled.replace(":", ".")
    else:
        spelled = spelled.replace("->", ".").replace("::", ".")
    return spelled if re.fullmatch(r"[A-Za-z_]\w*(?:[.!?]\w+|[.]\w+)*[!?]?", spelled) else None


def _import_literal(node, raw, lang):
    text = source_text(node, raw).strip()
    if lang == "ruby":
        match = re.match(r"(?:require|require_relative|load)\s*\(?\s*['\"]([^'\"]+)['\"]", text)
    elif lang == "lua":
        match = re.match(r"(?:local\s+\w+\s*=\s*)?require\s*\(?\s*['\"]([^'\"]+)['\"]", text)
    else:
        match = re.match(r"#\s*include\s*[<\"]([^>\"]+)[>\"]", text)
    return match.group(1) if match else None


def extract_legacy(builder, rel_path, full_path, language=None):
    lang = language or EXTENSION_LANGUAGE[Path(rel_path).suffix.lower()]
    module = importlib.import_module(GRAMMAR_MODULES[lang])
    parser = Parser(Language(module.language()))
    raw = Path(full_path).read_bytes()
    parsed = parser.parse(raw)
    builder.current_file = rel_path
    builder.current_scope = []
    builder.scope_depth = 0
    builder.imports_by_file[rel_path] = {}
    lines = raw.decode("utf-8", errors="replace").splitlines()
    builder.raw_file_lines[rel_path] = lines
    builder.total_loc += len(lines)
    root_id = builder.current_file_node_id
    builder.add_ckg_node(
        root_id, "file", "Lsyn", Path(rel_path).name, 1,
        code=f"// {lang} file: {rel_path}, {len(lines)} lines",
    )

    seen_imports = set()
    def add_import(path):
        if path in seen_imports:
            return
        seen_imports.add(path)
        module_id = "module::" + path
        if module_id not in builder.graph:
            builder.add_ckg_node(module_id, "module", "Ldep", path)
        builder.add_ckg_edge(root_id, module_id, "IMPORTS", "Ldep")
        builder.imports_by_file[rel_path][path.split("/")[-1]] = path

    def walk(node, parent_id, symbols, active_fn=None):
        kind = DECLARATIONS[lang].get(node.type)
        current_id = parent_id
        active = active_fn
        nested_symbols = symbols

        if kind:
            name = _name_of(node, raw, lang)
            if name:
                target = builder.current_file_ctx + ":" + ".".join([*symbols, name])
                # Distinguish overloads instead of overwriting definitions.
                if target in builder.graph:
                    target += f"@line:{node.start_point.row + 1}"
                snippet = source_text(node, raw)
                builder.add_ckg_node(target, kind, "Lsyn", name,
                                     node.start_point.row + 1, code=snippet[:4000])
                builder.register_symbol(target, name)
                builder.add_ckg_edge(parent_id, target, "CONTAINS", "Lsyn")
                current_id = target
                nested_symbols = [*symbols, name]
                if kind == "function":
                    active = target

        if node.type in CALLS[lang] and active is not None:
            called = _call_name(node, raw, lang)
            if called:
                builder.calls_to_resolve.append(
                    (active, called, len(nested_symbols), rel_path)
                )
                builder.callsite_evidence.append({
                    "caller": active, "callee": called,
                    "file": rel_path, "line": node.start_point.row + 1,
                    "column": node.start_point.column,
                    "arguments": [], "argument_kinds": [],
                })

        if node.type in {"preproc_include", "call", "function_call",
                         "command", "command_call"}:
            dep = _import_literal(node, raw, lang)
            if dep:
                add_import(dep)

        for child in node.named_children:
            walk(child, current_id, nested_symbols, active)

    walk(parsed.root_node, root_id, [])
    return {"syntax_errors": bool(parsed.root_node.has_error)}
