"""Tree-sitter extraction for the first JavaScript and TypeScript adapters.

The adapter deliberately emits the same node IDs and edge vocabulary used by
the Python builder. That keeps query, export, and evaluation code language
agnostic while language-specific parsing remains isolated here.
"""

from __future__ import annotations

import os
import re

from tree_sitter import Language, Parser
import tree_sitter_javascript
import tree_sitter_typescript


class TreeSitterExtractor:
    EXTENSIONS = {".js", ".jsx", ".ts", ".tsx"}

    def __init__(self, extension):
        grammar = (
            tree_sitter_typescript.language_typescript()
            if extension in {".ts", ".tsx"}
            else tree_sitter_javascript.language()
        )
        self.parser = Parser(Language(grammar))

    @staticmethod
    def _text(node, source):
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    @staticmethod
    def _line(node):
        return node.start_point.row + 1

    def extract(self, builder, rel_path, full_path):
        with open(full_path, "rb") as source_file:
            source = source_file.read()
        text = source.decode("utf-8", errors="replace")
        builder.current_file = rel_path
        builder.current_scope = []
        builder.scope_depth = 0
        builder.imports_by_file[rel_path] = {}
        builder.raw_file_lines[rel_path] = text.splitlines()
        builder.total_loc += len(builder.raw_file_lines[rel_path])
        file_id = f"file::{rel_path}"
        builder.add_ckg_node(
            file_id, "file", "Lsyn", os.path.basename(rel_path), 1,
            code=f"// File: {rel_path}\n// Lines: {len(builder.raw_file_lines[rel_path])}",
        )
        self._register_imports(builder, rel_path, text, file_id)
        self._visit(builder, self.parser.parse(source).root_node, source)

    def _register_imports(self, builder, rel_path, text, file_id):
        for names, specifier in re.findall(
            r"import\s+(.+?)\s+from\s+[\"']([^\"']+)[\"']", text
        ):
            target_module = builder.resolve_js_module_specifier(rel_path, specifier)
            aliases = []
            if names.strip().startswith("{"):
                for item in names.strip(" {} ").split(","):
                    source_name, _, alias = item.strip().partition(" as ")
                    aliases.append((alias or source_name, f"{target_module}.{source_name}"))
            elif names.strip().startswith("*"):
                alias = names.split(" as ")[-1].strip()
                aliases.append((alias, target_module))
            else:
                aliases.append((names.strip().split(",")[0], target_module))
            for alias, target in aliases:
                self._add_import(builder, rel_path, file_id, alias, target)

        # CommonJS: const { original: local } = require("./module")
        for names, specifier in re.findall(
            r"(?:const|let|var)\s+\{([^}]+)\}\s*=\s*require\(\s*[\"']([^\"']+)[\"']\s*\)",
            text,
        ):
            target_module = builder.resolve_js_module_specifier(rel_path, specifier)
            for item in names.split(","):
                source_name, _, alias = item.strip().partition(":")
                self._add_import(
                    builder, rel_path, file_id, (alias or source_name).strip(),
                    f"{target_module}.{source_name.strip()}",
                )

        # CommonJS: const helpers = require("./helpers")
        for alias, specifier in re.findall(
            r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*require\(\s*[\"']([^\"']+)[\"']\s*\)",
            text,
        ):
            target_module = builder.resolve_js_module_specifier(rel_path, specifier)
            self._add_import(builder, rel_path, file_id, alias, target_module)

    @staticmethod
    def _add_import(builder, rel_path, file_id, alias, target):
        builder.imports_by_file[rel_path][alias] = target
        symbol = f"symbol::{target}"
        if symbol not in builder.graph:
            builder.add_ckg_node(symbol, "symbol_ref", "Ldep", alias)
        builder.add_ckg_edge(file_id, symbol, "IMPORTS", "Ldep")


    def _visit(self, builder, node, source):
        if node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = self._text(name_node, source)
                class_id = builder.get_node_id(name)
                builder.add_ckg_node(class_id, "class", "Lsyn", name, self._line(node))
                builder.register_symbol(class_id, name)
                builder.add_ckg_edge(builder.get_current_scope_id(), class_id, "CONTAINS", "Lsyn")
                heritage = next((child for child in node.named_children if child.type == "class_heritage"), None)
                if heritage:
                    base = re.sub(r"^extends\s+", "", self._text(heritage, source)).strip()
                    if base:
                        builder.class_base_records.append((class_id, base, builder.current_file, builder.scope_depth))
                self._with_scope(builder, name, lambda: self._visit_children(builder, node, source))
                return
        if node.type in {"function_declaration", "method_definition"}:
            name_node = node.child_by_field_name("name")
            if name_node:
                self._add_function(builder, node, source, self._text(name_node, source))
                return
        if node.type == "call_expression" and builder.current_scope:
            function = node.child_by_field_name("function")
            if function:
                raw_callee = self._text(function, source)
                http_call = self._literal_http_call(node, raw_callee, source)
                if http_call:
                    path, method = http_call
                    builder.http_calls_to_resolve.append(
                        (builder.get_current_scope_id(), path, method, builder.current_file)
                    )
                callee = raw_callee.replace("this.", "self.")
                if callee.startswith("super."):
                    callee = "super()." + callee[len("super."):]
                builder.calls_to_resolve.append(
                    (builder.get_current_scope_id(), callee, builder.scope_depth, builder.current_file)
                )
        if node.type == "return_statement" and builder.current_scope:
            scope_id = builder.get_current_scope_id()
            return_id = f"{scope_id}.return::{self._line(node)}"
            builder.add_ckg_node(
                return_id, "return", "Lflow", "return", self._line(node)
            )
            builder.add_ckg_edge(scope_id, return_id, "RETURNS", "Lflow")
            variable_id = self._first_local_variable(builder, node, source, scope_id)
            if variable_id:
                builder.add_ckg_edge(variable_id, return_id, "FLOWS_TO", "Lflow")
        if node.type in {"assignment_expression", "augmented_assignment_expression", "update_expression"} and builder.current_scope:
            scope_id = builder.get_current_scope_id()
            target = node.child_by_field_name("left") or node.child_by_field_name("argument")
            if target and target.type == "identifier":
                variable_id = builder.var_defs.get(scope_id, {}).get(self._text(target, source))
                if variable_id:
                    builder.add_ckg_edge(scope_id, variable_id, "MUTATES", "Lflow")
        if node.type == "variable_declarator" and builder.current_scope:
            scope_id = builder.get_current_scope_id()
            if builder.graph.nodes.get(scope_id, {}).get("type") == "function":
                name_node = node.child_by_field_name("name")
                if name_node and name_node.type == "identifier":
                    name = self._text(name_node, source)
                    variable_id = f"{scope_id}.var::{name}"
                    if variable_id not in builder.graph:
                        builder.add_ckg_node(
                            variable_id, "variable", "Lflow", name, self._line(name_node)
                        )
                    builder.var_defs.setdefault(scope_id, {})[name] = variable_id
                    builder.add_ckg_edge(scope_id, variable_id, "DEFINES", "Lflow")
                    self._visit_children(builder, node, source, skip_nodes=(name_node,))
                    return
        if node.type == "identifier" and builder.current_scope:
            scope_id = builder.get_current_scope_id()
            variable_id = builder.var_defs.get(scope_id, {}).get(self._text(node, source))
            if variable_id:
                builder.add_ckg_edge(scope_id, variable_id, "USES", "Lflow")
        self._visit_children(builder, node, source)

    @staticmethod
    def _literal_http_call(node, callee, source):
        """Return a literal (path, method) for fetch/axios calls, else None."""
        method = None
        if callee == "fetch":
            method = "GET"
        else:
            match = re.fullmatch(r"axios\.(get|post|put|patch|delete)", callee)
            if match:
                method = match.group(1).upper()
        if not method:
            return None
        arguments = node.child_by_field_name("arguments")
        if not arguments:
            return None
        argument_text = TreeSitterExtractor._text(arguments, source)
        path_match = re.match(r"\(\s*['\"]([^'\"]+)['\"]", argument_text)
        if not path_match:
            return None
        if callee == "fetch":
            explicit_method = re.search(
                r"\bmethod\s*:\s*['\"]([A-Za-z]+)['\"]", argument_text
            )
            if explicit_method:
                method = explicit_method.group(1).upper()
        return path_match.group(1), method

    def _first_local_variable(self, builder, node, source, scope_id):
        """Find the first local identifier read by a return expression."""
        for child in node.named_children:
            if child.type == "identifier":
                variable_id = builder.var_defs.get(scope_id, {}).get(self._text(child, source))
                if variable_id:
                    return variable_id
            variable_id = self._first_local_variable(builder, child, source, scope_id)
            if variable_id:
                return variable_id
        return None

    def _add_function(self, builder, node, source, name):
        function_id = builder.get_node_id(name)
        builder.add_ckg_node(function_id, "function", "Lsyn", name, self._line(node))
        builder.register_symbol(function_id, name)
        builder.add_ckg_edge(builder.get_current_scope_id(), function_id, "CONTAINS", "Lsyn")
        builder.var_defs.setdefault(function_id, {})
        parameters = node.child_by_field_name("parameters")
        if parameters:
            parameter_text = self._text(parameters, source).strip("()")
            for entry in parameter_text.split(","):
                match = re.match(r"\s*([A-Za-z_$][\w$]*)", entry)
                if not match:
                    continue
                parameter = match.group(1)
                var_id = f"{function_id}.var::{parameter}"
                builder.add_ckg_node(var_id, "variable", "Lflow", parameter, self._line(parameters))
                builder.var_defs[function_id][parameter] = var_id
                builder.add_ckg_edge(function_id, var_id, "PASSES_ARG", "Lflow")
        self._with_scope(
            builder, name,
            lambda: self._visit_children(builder, node, source, skip_nodes=(parameters,)),
        )

    @staticmethod
    def _with_scope(builder, name, callback):
        builder.current_scope.append(name)
        builder.scope_depth += 1
        try:
            callback()
        finally:
            builder.scope_depth -= 1
            builder.current_scope.pop()

    def _visit_children(self, builder, node, source, skip_nodes=()):
        for child in node.named_children:
            if child in skip_nodes:
                continue
            self._visit(builder, child, source)
