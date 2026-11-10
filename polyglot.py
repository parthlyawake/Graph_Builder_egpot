"""Tree-sitter extraction for JavaScript, TypeScript, and Go adapters.

The adapters deliberately emit the same node IDs and edge vocabulary used by
the Python builder. That keeps query, export, and evaluation code language
agnostic while language-specific parsing remains isolated here.
"""

from __future__ import annotations

import os
import re

from tree_sitter import Language, Parser
import tree_sitter_javascript
import tree_sitter_typescript

try:  # Go adapter is optional: the engine degrades to JS/TS without it.
    import tree_sitter_go

    _GO_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on environment
    _GO_AVAILABLE = False

try:  # Java adapter — install with: pip install tree-sitter-java
    import tree_sitter_java  # type: ignore

    _JAVA_AVAILABLE = True
except ImportError:
    _JAVA_AVAILABLE = False

try:  # C# adapter — install with: pip install tree-sitter-c-sharp
    import tree_sitter_c_sharp  # type: ignore

    _CSHARP_AVAILABLE = True
except ImportError:
    _CSHARP_AVAILABLE = False


class TreeSitterExtractor:
    # Core extensions always supported; Java/C# enabled if packages installed.
    EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".go"}
    if _JAVA_AVAILABLE:
        EXTENSIONS.add(".java")
    if _CSHARP_AVAILABLE:
        EXTENSIONS.add(".cs")

    def __init__(self, extension):
        if extension == ".go":
            if not _GO_AVAILABLE:
                raise RuntimeError("tree-sitter-go is not installed. Run: pip install tree-sitter-go")
            grammar = tree_sitter_go.language()
        elif extension == ".java":
            if not _JAVA_AVAILABLE:
                raise RuntimeError("tree-sitter-java is not installed. Run: pip install tree-sitter-java")
            grammar = tree_sitter_java.language()
        elif extension == ".cs":
            if not _CSHARP_AVAILABLE:
                raise RuntimeError("tree-sitter-c-sharp is not installed. Run: pip install tree-sitter-c-sharp")
            grammar = tree_sitter_c_sharp.language()
        elif extension in {".ts", ".tsx"}:
            grammar = tree_sitter_typescript.language_typescript()
        else:
            grammar = tree_sitter_javascript.language()
        self.parser = Parser(Language(grammar))
        self.is_go = extension == ".go"
        self.is_java = extension == ".java"
        self.is_csharp = extension == ".cs"

    @staticmethod
    def _text(node, source):
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    @staticmethod
    def _line(node):
        return node.start_point.row + 1

    @staticmethod
    def _extract_doc_comment(node, source):
        """Extract preceding JSDoc (/** ... */) or Go (// ...) doc comments."""
        def get_comment_node(n):
            curr = n.prev_sibling
            while curr and curr.type in {"comment", "line_comment", "block_comment"}:
                return curr
            if n.parent and n.parent.type in {
                "export_statement", "lexical_declaration", "variable_declaration", "variable_declarator"
            }:
                return get_comment_node(n.parent)
            return None

        c_node = get_comment_node(node)
        if not c_node:
            return None

        comments = []
        curr = c_node
        while curr and curr.type in {"comment", "line_comment", "block_comment"}:
            raw_c = source[curr.start_byte:curr.end_byte].decode("utf-8", errors="replace").strip()
            comments.insert(0, raw_c)
            curr = curr.prev_sibling

        if not comments:
            return None

        full_comment = "\n".join(comments)
        cleaned = re.sub(r"^/\*\*|\*/$", "", full_comment)
        cleaned = re.sub(r"(?m)^\s*\*\s?", "", cleaned)
        cleaned = re.sub(r"(?m)^\s*//\s?", "", cleaned)
        return cleaned.strip() or None

    @staticmethod
    def _extract_java_annotations(node, source):
        """Extract Java annotations from node or its modifiers child.
        Returns dict: {AnnotationName: string_value or ""}
        """
        annotations = {}
        modifiers = next((c for c in node.named_children if c.type == "modifiers"), None)
        target_nodes = [node]
        if modifiers:
            target_nodes.extend(modifiers.named_children)
        for c in target_nodes:
            if c.type in ("annotation", "marker_annotation"):
                name_node = c.child_by_field_name("name") or (c.named_children[0] if c.named_children else None)
                if not name_node:
                    continue
                ann_name = TreeSitterExtractor._text(name_node, source).lstrip("@")
                ann_value = ""
                args_node = c.child_by_field_name("arguments") or next(
                    (ch for ch in c.named_children if ch.type == "annotation_argument_list"), None
                )
                if args_node:
                    raw_args = TreeSitterExtractor._text(args_node, source)
                    str_match = re.search(r'["\']([^"\']+)["\']', raw_args)
                    if str_match:
                        ann_value = str_match.group(1)
                annotations[ann_name] = ann_value
        return annotations

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
        file_id = getattr(builder, "current_file_node_id", f"file::{rel_path}")
        builder.add_ckg_node(
            file_id, "file", "Lsyn", os.path.basename(rel_path), 1,
            code=f"// File: {rel_path}\n// Lines: {len(builder.raw_file_lines[rel_path])}",
        )
        self._register_imports(builder, rel_path, text, file_id)
        self._visit(builder, self.parser.parse(source).root_node, source)
        # Next-style file routes have no explicit router-registration call.
        parts = rel_path.replace("\\", "/").split("/")
        if len(parts) >= 3 and parts[-1] in {"route.ts", "route.tsx", "route.js", "route.jsx"}:
            api_positions = [i for i in range(len(parts) - 2) if parts[i:i + 2] == ["app", "api"]]
            if api_positions:
                suffix = "/".join(parts[api_positions[-1] + 2:-1])
                route_path = "/api" + ("/" + suffix if suffix else "")
                for method in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
                    handler_id = f"{builder.current_file_ctx}:{method}"
                    if handler_id in builder.graph and builder.graph.nodes[handler_id].get("type") == "function":
                        builder.http_endpoints.setdefault((method, route_path), []).append(handler_id)

    # ------------------------------------------------------------------
    # IMPORTS
    # ------------------------------------------------------------------
    def _register_imports(self, builder, rel_path, text, file_id):
        for names, specifier in re.findall(
            r"import\s+([\s\S]+?)\s+from\s+[\"']([^\"']+)[\"']", text
        ):
            target_module = builder.resolve_js_module_specifier(rel_path, specifier)
            aliases = []
            clean_names = names.strip()
            if clean_names.startswith("{"):
                for item in clean_names.strip(" {} \r\n\t").split(","):
                    item = item.strip()
                    if not item:
                        continue
                    source_name, _, alias = item.partition(" as ")
                    aliases.append(((alias or source_name).strip(), f"{target_module}.{source_name.strip()}"))
            elif clean_names.startswith("*"):
                alias = clean_names.split(" as ")[-1].strip()
                aliases.append((alias, target_module))
            else:
                aliases.append((clean_names.split(",")[0].strip(), target_module))
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

        # Go: import "path" / import alias "path" / import ( "path" ... )
        for alias, specifier in re.findall(
            r"(?m)^\s*(?:([A-Za-z_][\w.]*)\s+)?\"([a-zA-Z0-9_./-]+)\"\s*$", text
        ):
            if "import" not in text:
                continue
            if not re.search(r"(?m)^\s*import\b", text):
                continue
            module_key = builder._module_key_for_path(specifier)
            local_alias = alias or specifier.rsplit("/", 1)[-1]
            builder.imports_by_file[rel_path][local_alias] = module_key
            symbol = f"module::{specifier}"
            if symbol not in builder.graph:
                builder.add_ckg_node(symbol, "module", "Ldep", specifier)
            builder.add_ckg_edge(file_id, symbol, "IMPORTS", "Ldep")

        # Java: import [static] package.Class; / import package.*;
        if self.is_java or rel_path.endswith(".java"):
            for imp in re.findall(r"(?m)^\s*import\s+(?:static\s+)?([a-zA-Z0-9_.]+)(?:\.\*)?\s*;", text):
                simple_name = imp.rsplit(".", 1)[-1]
                self._add_import(builder, rel_path, file_id, simple_name, imp)

    @staticmethod
    def _add_import(builder, rel_path, file_id, alias, target):
        builder.imports_by_file[rel_path][alias] = target
        symbol = f"symbol::{target}"
        if symbol not in builder.graph:
            builder.add_ckg_node(symbol, "symbol_ref", "Ldep", alias)
        builder.add_ckg_edge(file_id, symbol, "IMPORTS", "Ldep")

    # ------------------------------------------------------------------
    # AST WALK
    # ------------------------------------------------------------------
    def _visit(self, builder, node, source):
        if node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = self._text(name_node, source)
                class_id = builder.get_node_id(name)
                builder.add_ckg_node(class_id, "class", "Lsyn", name, self._line(node))
                builder.register_symbol(class_id, name)
                # Record the proto service declared by managed generated bases.
                # Registration is recorded separately and is mandatory for binding.
                if self.is_java or self.is_csharp:
                    base_kind = "superclass" if self.is_java else "base_list"
                    heritage_node = next((c for c in node.named_children if c.type == base_kind), None)
                    if heritage_node:
                        heritage_text = self._text(heritage_node, source)
                        pattern = (r"(?:^|\.)\b(\w+)Grpc\.\1ImplBase\s*$" if self.is_java
                                   else r"(?:^|\.)\b(\w+)\.\1Base\s*$")
                        for base in re.sub(r"^(?:extends\s+|:\s*)", "", heritage_text).split(","):
                            match = re.search(pattern, base.strip())
                            if match:
                                namespace = []
                                ancestor = node.parent
                                while ancestor is not None:
                                    if ancestor.type in {"namespace_declaration", "file_scoped_namespace_declaration"}:
                                        namespace_node = ancestor.child_by_field_name("name")
                                        if namespace_node is not None:
                                            namespace.insert(0, self._text(namespace_node, source))
                                    ancestor = ancestor.parent
                                if self.is_java:
                                    root = node
                                    while root.parent is not None:
                                        root = root.parent
                                    package = next((c for c in root.named_children if c.type == "package_declaration"), None)
                                    if package is not None:
                                        namespace = [re.sub(r"^package\s+|;\s*$", "", self._text(package, source)).strip()]
                                builder.graph.nodes[class_id].update(
                                    grpc_service=match.group(1),
                                    grpc_language="java" if self.is_java else "csharp",
                                    grpc_qualified_name=".".join([*namespace, *builder.current_scope, name]))
                docstring = self._extract_doc_comment(node, source)
                if docstring:
                    builder.docstrings[class_id] = docstring
                    builder.graph.nodes[class_id]["docstring"] = docstring
                builder.add_ckg_edge(builder.get_current_scope_id(), class_id, "CONTAINS", "Lsyn")
                
                # Java Spring route prefix & Feign client handling
                old_prefix = getattr(builder, "_current_route_prefix", "")
                if self.is_java:
                    ann = self._extract_java_annotations(node, source)
                    if "RequestMapping" in ann:
                        builder._current_route_prefix = ann["RequestMapping"].rstrip("/")
                    if "FeignClient" in ann and ann["FeignClient"]:
                        builder.grpc_client_vars.setdefault(builder.current_file, {})[name] = ann["FeignClient"]

                heritage = next((c for c in node.named_children if c.type in ("class_heritage", "superclass", "super_interfaces")), None)
                if heritage:
                    heritage_text = self._text(heritage, source)
                    base = re.sub(r"^(?:extends|implements)\s+", "", heritage_text).split("implements", 1)[0].strip()
                    if base:
                        builder.class_base_records.append((class_id, base, builder.current_file, builder.scope_depth))
                    implemented = re.search(r"\bimplements\s+(.+)$", heritage_text)
                    if implemented:
                        for spelling in implemented.group(1).split(","):
                            builder.interface_implementation_records.append(
                                (class_id, spelling.strip(), builder.current_file, builder.scope_depth)
                            )
                self._with_scope(builder, name, lambda: self._visit_children(builder, node, source))
                if self.is_java:
                    builder._current_route_prefix = old_prefix
                return

        if node.type == "type_declaration" and self.is_go:
            self._go_type_declaration(builder, node, source)
            return

        if node.type in {"interface_declaration", "abstract_class_declaration", "type_alias_declaration", "enum_declaration"}:
            name_node = node.child_by_field_name("name")
            if name_node:
                name = self._text(name_node, source)
                type_kind = ("interface" if node.type == "interface_declaration" else
                             "class" if "class" in node.type else "type")
                node_id = builder.get_node_id(name)
                builder.add_ckg_node(node_id, type_kind, "Lsyn", name, self._line(node),
                                     code=self._text(node, source)[:4000])
                builder.register_symbol(node_id, name)
                docstring = self._extract_doc_comment(node, source)
                if docstring:
                    builder.docstrings[node_id] = docstring
                    builder.graph.nodes[node_id]["docstring"] = docstring
                builder.add_ckg_edge(builder.get_current_scope_id(), node_id, "CONTAINS", "Lsyn")
                if self.is_java and node.type == "interface_declaration":
                    ann = self._extract_java_annotations(node, source)
                    if "FeignClient" in ann and ann["FeignClient"]:
                        builder.grpc_client_vars.setdefault(builder.current_file, {})[name] = ann["FeignClient"]
                if type_kind == "interface":
                    heritage = next((c for c in node.named_children if c.type == "extends_type_clause"), None)
                    if heritage:
                        for spelling in re.sub(r"^extends\s+", "", self._text(heritage, source)).split(","):
                            builder.interface_extension_records.append(
                                (node_id, spelling.strip(), builder.current_file, builder.scope_depth)
                            )
                self._with_scope(builder, name, lambda: self._visit_children(builder, node, source))
                return

        if node.type in {"method_signature", "property_signature"} and builder.current_scope:
            owner_id = builder.get_current_scope_id()
            if builder.graph.nodes.get(owner_id, {}).get("type") == "interface":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = self._text(name_node, source)
                    member_id = builder.get_node_id(name)
                    kind = "method" if node.type == "method_signature" else "property"
                    builder.add_ckg_node(member_id, kind, "Lcontract", name, self._line(node),
                                         code=self._text(node, source))
                    builder.add_ckg_edge(owner_id, member_id, "DECLARES", "Lcontract")
                return

        if node.type in {"function_declaration", "method_definition", "method_declaration"}:
            name_node = node.child_by_field_name("name")
            if name_node:
                receiver = None
                if node.type == "method_declaration":
                    receiver = self._go_receiver_type(node, source)
                self._add_function(builder, node, source, self._text(name_node, source), receiver=receiver)
                return

        # Arrow function or function expression assigned to a variable / export
        if node.type == "variable_declarator":
            name_node = node.child_by_field_name("name")
            value_node = node.child_by_field_name("value")
            if name_node and value_node and value_node.type in {"arrow_function", "function_expression"}:
                name = self._text(name_node, source)
                self._add_function(builder, value_node, source, name)
                return

        # Constructor call: new Store(...)
        if node.type == "new_expression":
            constructor_node = node.child_by_field_name("constructor")
            if constructor_node:
                raw_callee = self._text(constructor_node, source)
                match = re.search(r"(\w+Service)$", raw_callee)
                if match:
                    curr_p = node.parent
                    while curr_p and curr_p.type != "variable_declarator":
                        curr_p = curr_p.parent
                    if curr_p and curr_p.type == "variable_declarator":
                        var_ident = curr_p.child_by_field_name("name")
                        if var_ident:
                            var_name = self._text(var_ident, source)
                            builder.grpc_client_vars.setdefault(builder.current_file, {})[var_name] = match.group(1)
                if builder.current_scope:
                    scope_id = builder.get_current_scope_id()
                    target_name = raw_callee.rsplit(".", 1)[-1]
                    builder.calls_to_resolve.append(
                        (scope_id, target_name, builder.scope_depth, builder.current_file)
                    )

        # Java constructor call: new OrderResponse(...)
        if node.type == "object_creation_expression" and builder.current_scope:
            type_node = node.child_by_field_name("type")
            if type_node:
                target_name = self._text(type_node, source).rsplit(".", 1)[-1]
                builder.calls_to_resolve.append(
                    (builder.get_current_scope_id(), target_name, builder.scope_depth, builder.current_file)
                )

        if self.is_csharp and node.type == "invocation_expression":
            function = node.child_by_field_name("function")
            generic = function
            if function is not None and function.type == "member_access_expression":
                generic = function.child_by_field_name("name")
            if generic is not None and generic.type == "generic_name":
                identifier = next((c for c in generic.named_children if c.type == "identifier"), None)
                types = next((c for c in generic.named_children if c.type == "type_argument_list"), None)
                if (identifier is not None and self._text(identifier, source) == "MapGrpcService"
                        and types is not None and len(types.named_children) == 1):
                    builder.managed_grpc_registrations.append((
                        "csharp", self._text(types.named_children[0], source),
                        builder.current_file, builder.get_current_scope_id()))

        # Java method invocation: object.method(...) or method(...)
        if node.type == "method_invocation":
            name_node = node.child_by_field_name("name")
            object_node = node.child_by_field_name("object")
            arguments = node.child_by_field_name("arguments")
            if name_node and builder.current_scope:
                m_name = self._text(name_node, source)
                obj_text = self._text(object_node, source) if object_node else ""
                scope_id = builder.get_current_scope_id()
                if self.is_java and m_name == "addService" and arguments is not None:
                    args = arguments.named_children
                    if len(args) == 1 and args[0].type == "object_creation_expression":
                        created_type = args[0].child_by_field_name("type")
                        if created_type is not None:
                            builder.managed_grpc_registrations.append((
                                "java", self._text(created_type, source), builder.current_file, scope_id))

                # Kafka / event publishing: kafkaTemplate.send("topic", ...)
                if m_name == "send" and ("kafka" in obj_text.lower() or "producer" in obj_text.lower()):
                    if arguments and arguments.named_children:
                        first_arg = self._text(arguments.named_children[0], source).strip("'\"")
                        if first_arg:
                            topic_id = f"topic::{first_arg}"
                            if not builder.graph.has_node(topic_id):
                                builder.add_ckg_node(topic_id, "topic_contract", "Lcontract", first_arg)
                            builder.add_ckg_edge(scope_id, topic_id, "PRODUCES_EVENT", "Lcontract")

                # Java HTTP calls: restTemplate.getForObject(...) or webClient.get().uri(...)
                if "resttemplate" in obj_text.lower() or "webclient" in obj_text.lower():
                    if arguments and arguments.named_children:
                        arg0_text = self._text(arguments.named_children[0], source)
                        p_match = re.search(r'["\'](?:https?://[^/"\']+)?(/[^"\']+)["\']', arg0_text)
                        if p_match:
                            # exchange's verb is an argument, not encoded in its name.
                            verb = re.search(r"HttpMethod\.(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)",
                                             self._text(arguments, source))
                            h_method = verb.group(1) if verb else next(
                                (v for v in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS")
                                 if m_name.lower().startswith(v.lower())), None)
                            if h_method:
                                builder.http_calls_to_resolve.append((scope_id, p_match.group(1), h_method, builder.current_file))

                # Feign client method call: inventoryClient.checkStock(...)
                if obj_text and obj_text in builder.grpc_client_vars.get(builder.current_file, {}):
                    target_svc = builder.grpc_client_vars[builder.current_file][obj_text]
                    builder.grpc_calls_to_resolve.append((scope_id, target_svc, m_name, builder.current_file))

                callee = f"{obj_text}.{m_name}" if obj_text else m_name
                builder.calls_to_resolve.append((scope_id, callee, builder.scope_depth, builder.current_file))

        if node.type == "call_expression":
            function = node.child_by_field_name("function")
            if function:
                raw_callee = self._text(function, source)
                # Express route registration: app.get("/path", handler)
                express_match = re.match(r"^(?:app|router)\.(get|post|put|delete|patch)$", raw_callee)
                if express_match:
                    method = express_match.group(1).upper()
                    arguments = node.child_by_field_name("arguments")
                    if arguments and len(arguments.named_children) >= 2:
                        path_str = self._text(arguments.named_children[0], source).strip("'\"")
                        if path_str.startswith("/"):
                            h_node = arguments.named_children[1]
                            h_name = self._text(h_node, source)
                            h_id = builder.get_node_id(h_name) if h_node.type == "identifier" else builder.get_current_scope_id()
                            builder.http_endpoints.setdefault((method, path_str), []).append(h_id)

                if builder.current_scope:
                    if self.is_go:
                        self._go_call(builder, node, raw_callee, source)
                    else:
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
                        # JS gRPC client call: client.getQuote(...)
                        if "." in raw_callee:
                            var_name, _, method = raw_callee.partition(".")
                            service = builder.grpc_client_vars.get(builder.current_file, {}).get(var_name)
                            if service:
                                builder.grpc_calls_to_resolve.append(
                                    (builder.get_current_scope_id(), service, method, builder.current_file)
                                )
                        # JS gRPC server: server.addService(proto.XService.service, {rpc: handler})
                        add_service = re.match(r"^(?:\w+\.)*addService$", raw_callee)
                        if add_service:
                            self._js_add_service(builder, node, source)

        if node.type == "return_statement" and builder.current_scope:
            scope_id = builder.get_current_scope_id()
            return_id = f"{scope_id}.return::{self._line(node)}"
            builder.add_ckg_node(return_id, "return", "Lflow", "return", self._line(node))
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

        if node.type == "assignment_statement" and self.is_go and builder.current_scope:
            scope_id = builder.get_current_scope_id()
            left = node.child_by_field_name("left")
            if left:
                for ident in (left.named_children if left.named_children else [left]):
                    if ident.type == "identifier":
                        name = self._text(ident, source)
                        variable_id = builder.var_defs.get(scope_id, {}).get(name)
                        if variable_id:
                            builder.add_ckg_edge(scope_id, variable_id, "MUTATES", "Lflow")

        if node.type == "var_spec" and builder.current_scope:
            scope_id = builder.get_current_scope_id()
            name_node = node.child_by_field_name("name")
            if name_node:
                name = self._text(name_node, source)
                variable_id = f"{scope_id}.var::{name}"
                if variable_id not in builder.graph:
                    builder.add_ckg_node(variable_id, "variable", "Lflow", name, self._line(name_node))
                builder.var_defs.setdefault(scope_id, {})[name] = variable_id
                builder.add_ckg_edge(scope_id, variable_id, "DEFINES", "Lflow")

        if node.type == "short_var_declaration" and builder.current_scope:
            scope_id = builder.get_current_scope_id()
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left:
                for ident in left.named_children:
                    if ident.type == "identifier":
                        name = self._text(ident, source)
                        variable_id = f"{scope_id}.var::{name}"
                        if variable_id not in builder.graph:
                            builder.add_ckg_node(variable_id, "variable", "Lflow", name, self._line(ident))
                        builder.var_defs.setdefault(scope_id, {})[name] = variable_id
                        builder.add_ckg_edge(scope_id, variable_id, "DEFINES", "Lflow")
            # gRPC client var: cl := pb.NewXServiceClient(conn)
            if left and right and right.named_children:
                call = right.named_children[0]
                if call.type == "call_expression":
                    fn = call.child_by_field_name("function")
                    if fn:
                        fn_text = self._text(fn, source)
                        match = re.match(r"^(\w+)\.New(\w+)Client$", fn_text)
                        if match:
                            for ident in left.named_children:
                                if ident.type == "identifier":
                                    builder.grpc_client_vars.setdefault(builder.current_file, {})[
                                        self._text(ident, source)
                                    ] = match.group(2)
                        # impl var: svc := new(checkoutService)  or  svc := &checkoutService{}
                        if fn_text == "new":
                            arg = self._call_argument_text(call, source, index=0)
                            if arg:
                                for ident in left.named_children:
                                    if ident.type == "identifier":
                                        builder.go_type_vars.setdefault(builder.current_file, {})[
                                            self._text(ident, source)
                                        ] = arg.strip()
                if call.type == "unary_expression":
                    # svc := &checkoutService{}
                    inner = call.named_children[0] if call.named_children else None
                    if inner is not None and inner.type == "composite_literal":
                        type_node = inner.child_by_field_name("type")
                        if type_node:
                            for ident in left.named_children:
                                if ident.type == "identifier":
                                    builder.go_type_vars.setdefault(builder.current_file, {})[
                                        self._text(ident, source)
                                    ] = self._text(type_node, source)

        if node.type == "variable_declarator" and builder.current_scope:
            scope_id = builder.get_current_scope_id()
            if builder.graph.nodes.get(scope_id, {}).get("type") == "function":
                name_node = node.child_by_field_name("name")
                if name_node and name_node.type == "identifier":
                    name = self._text(name_node, source)
                    variable_id = f"{scope_id}.var::{name}"
                    if variable_id not in builder.graph:
                        builder.add_ckg_node(variable_id, "variable", "Lflow", name, self._line(name_node))
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

    def _js_add_service(self, builder, node, source):
        """Capture server.addService(pkg.<Service>.service, {handler...}) bindings."""
        arguments = node.child_by_field_name("arguments")
        if not arguments:
            return
        positional = [c for c in arguments.named_children]
        if len(positional) < 2:
            return
        service_expr = self._text(positional[0], source)
        match = re.search(r"\.(\w+)\.service\s*$", service_expr)
        if not match:
            return
        service = match.group(1)
        handler_map = positional[1]
        handlers = {}
        if handler_map.type == "object":
            for pair in handler_map.named_children:
                if pair.type in {"shorthand_property_identifier", "shorthand_property_identifier_pattern"}:
                    name = self._text(pair, source)
                    handlers[name] = name
                    continue
                if pair.type == "pair":
                    key_node = pair.child_by_field_name("key")
                    value_node = pair.child_by_field_name("value")
                    if key_node and value_node:
                        key = self._text(key_node, source).strip("'\"")
                        value = self._text(value_node, source)
                        value = re.sub(r"\.bind\(.*\)$", "", value)
                        handlers[key] = value
        builder.js_add_service_records.append(
            (service, handlers, builder.current_file, builder.get_current_scope_id())
        )

    # ------------------------------------------------------------------
    # GO-SPECIFIC HANDLING
    # ------------------------------------------------------------------
    def _go_type_declaration(self, builder, node, source):
        """Register Go struct/interface type declarations as class-like nodes."""
        for spec in node.named_children:
            if spec.type not in {"type_spec", "type_alias"}:
                continue
            name_node = spec.child_by_field_name("name")
            if not name_node:
                continue
            name = self._text(name_node, source)
            type_id = builder.get_node_id(name)
            body = spec.child_by_field_name("type")
            type_kind = "interface" if body and body.type == "interface_type" else "class"
            builder.add_ckg_node(type_id, type_kind, "Lsyn", name, self._line(spec),
                                 code=self._text(spec, source)[:4000])
            builder.register_symbol(type_id, name)
            docstring = self._extract_doc_comment(spec, source) or self._extract_doc_comment(node, source)
            if docstring:
                builder.docstrings[type_id] = docstring
                builder.graph.nodes[type_id]["docstring"] = docstring
            builder.add_ckg_edge(builder.get_current_scope_id(), type_id, "CONTAINS", "Lsyn")
            if body and body.type == "struct_type":
                fields = builder.go_struct_fields.setdefault(type_id, {})
                for field_list in body.named_children:
                    for field in field_list.named_children:
                        if field.type != "field_declaration":
                            continue
                        declared_type = field.child_by_field_name("type")
                        if not declared_type:
                            continue
                        type_text = self._text(declared_type, source)
                        type_match = re.search(r"([A-Za-z_]\w*)\s*$", type_text)
                        if not type_match:
                            continue
                        for name_part in field.named_children:
                            if name_part.type == "field_identifier":
                                fields[self._text(name_part, source)] = type_match.group(1)

    @staticmethod
    def _go_receiver_type(node, source):
        receiver = node.child_by_field_name("receiver")
        if not receiver:
            return None
        text = TreeSitterExtractor._text(receiver, source)
        match = re.search(r"[\w$]+\s+\*?([A-Za-z_][\w]*)\s*\)", text)
        if match:
            return match.group(1)
        match = re.search(r"\(\s*\*?([A-Za-z_][\w]*)", text)
        return match.group(1) if match else None

    def _go_call(self, builder, node, raw_callee, source):
        """Handle Go call expressions, including gRPC client and server patterns."""
        function_node = node.child_by_field_name("function")
        if function_node and function_node.type == "func_literal":
            return  # An invoked closure is not an external function named by its source text.
        scope_id = builder.get_current_scope_id()
        callee = raw_callee

        # gRPC client: pb.NewXServiceClient(conn).Method(...)  (chained call)
        match = re.match(r"^(\w+)\.New(\w+)Client\(([^)]*)\)\.\s*(\w+)$", raw_callee.strip())
        if match:
            _, service, _, method = match.groups()
            builder.grpc_calls_to_resolve.append((scope_id, service, method, builder.current_file))
            callee = f"grpc.{service}.{method}"
        else:
            # gRPC client: cl.Method(...) where cl was bound via NewXServiceClient
            sel = re.match(r"^(\w+)\.(\w+)$", raw_callee)
            if sel:
                var, method = sel.groups()
                service = builder.grpc_client_vars.get(builder.current_file, {}).get(var)
                if service:
                    builder.grpc_calls_to_resolve.append((scope_id, service, method, builder.current_file))
                    callee = f"grpc.{service}.{method}"

        # gRPC server registration: pb.RegisterXServiceServer(srv, impl)
        match = re.match(r"^(\w+)\.Register(\w+)Server$", raw_callee)
        if match:
            _, service = match.groups()
            impl_arg = self._call_argument_text(node, source, index=1)
            builder.grpc_server_registrations.append(
                (service, impl_arg, builder.current_file, scope_id)
            )

        # HTTP route registration: http.HandleFunc("/path", handler)
        if raw_callee == "http.HandleFunc":
            path_arg = self._call_argument_text(node, source, index=0)
            handler_arg = self._call_argument_text(node, source, index=1)
            if path_arg and handler_arg:
                path = path_arg.strip("'\"`")
                if path.startswith("/"):
                    h_name = handler_arg.rsplit(".", 1)[-1]
                    h_id = f"{builder.current_file_ctx}:{h_name}"
                    builder.http_endpoints.setdefault(("*", path), []).append(h_id)

        # Go client HTTP call: http.Get("http://...") or http.Post("...")
        if raw_callee in ("http.Get", "http.Post"):
            method = "GET" if raw_callee == "http.Get" else "POST"
            url_arg = self._call_argument_text(node, source, index=0)
            if url_arg:
                path_match = re.match(r"['\"`](?:https?://[^/'\"`]+)?(/[^'\"`]+)['\"`]", url_arg)
                if path_match:
                    path = path_match.group(1)
                    builder.http_calls_to_resolve.append((scope_id, path, method, builder.current_file))

        # http.NewRequestWithContext(ctx, "POST", base+"/path", ...)
        # retains the visible path while keeping the host unresolved.
        if raw_callee in {"http.NewRequestWithContext", "http.NewRequest"}:
            method_index, url_index = (1, 2) if raw_callee.endswith("WithContext") else (0, 1)
            method_arg = self._call_argument_text(node, source, index=method_index)
            url_arg = self._call_argument_text(node, source, index=url_index)
            method = method_arg.strip("'\"`").upper() if method_arg else ""
            if method in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"} and url_arg:
                literal = re.fullmatch(r"""["'`](?:https?://[^/"'`]+)?(/[^"'`]+)["'`]""", url_arg)
                if literal:
                    builder.http_calls_to_resolve.append(
                        (scope_id, literal.group(1), method, builder.current_file)
                    )
                else:
                    suffix = re.search(r"""\+\s*["'`](/[^"'`]+)["'`]\s*$""", url_arg)
                    if suffix:
                        builder.dynamic_http_calls.append(
                            (scope_id, method, suffix.group(1), builder.current_file,
                             self._line(node), node.start_point.column)
                        )

        builder.calls_to_resolve.append(
            (scope_id, callee, builder.scope_depth, builder.current_file)
        )

    def _call_argument_text(self, node, source, index):
        arguments = node.child_by_field_name("arguments")
        if not arguments:
            return None
        positional = [c for c in arguments.named_children]
        if index < len(positional):
            return self._text(positional[index], source)
        return None

    # ------------------------------------------------------------------
    # JS/TS HTTP LITERALS
    # ------------------------------------------------------------------
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

    def _add_function(self, builder, node, source, name, receiver=None):
        if receiver:
            # Go method: scope under its receiver type so IDs read Type.Method.
            type_id = builder.get_node_id(receiver)
            if type_id not in builder.graph:
                builder.add_ckg_node(type_id, "class", "Lsyn", receiver, self._line(node))
                builder.register_symbol(type_id, receiver)
                builder.add_ckg_edge(builder.get_current_scope_id(), type_id, "CONTAINS", "Lsyn")
            builder.current_scope.append(receiver)
            builder.scope_depth += 1
        function_id = builder.get_node_id(name)
        ambiguous_definition = (self.is_java and function_id in builder.graph
                                and builder.graph.nodes[function_id].get("type") == "function")
        builder.add_ckg_node(function_id, "function", "Lsyn", name, self._line(node))
        if ambiguous_definition:
            builder.graph.nodes[function_id]["http_ambiguous_definition"] = True
        if self.is_csharp and any(c.type == "modifier" and self._text(c, source) == "override"
                                  for c in node.named_children):
            builder.graph.nodes[function_id]["is_override"] = True
        builder.register_symbol(function_id, name)
        docstring = self._extract_doc_comment(node, source)
        if docstring:
            builder.docstrings[function_id] = docstring
            builder.graph.nodes[function_id]["docstring"] = docstring
        builder.add_ckg_edge(builder.get_current_scope_id(), function_id, "CONTAINS", "Lsyn")
        if builder.graph.nodes.get(builder.get_current_scope_id(), {}).get("type") == "interface":
            builder.add_ckg_edge(builder.get_current_scope_id(), function_id, "DECLARES", "Lcontract")
        if receiver and self.is_go:
            receiver_node = node.child_by_field_name("receiver")
            receiver_text = self._text(receiver_node, source) if receiver_node else ""
            receiver_match = re.match(r"\(\s*([A-Za-z_]\w*)\s+", receiver_text)
            if receiver_match:
                builder.var_types.setdefault(function_id, {})[receiver_match.group(1)] = receiver

        # Java Spring REST endpoints and Event Listeners
        if self.is_java:
            ann = self._extract_java_annotations(node, source)
            http_verbs = {
                "GetMapping": "GET",
                "PostMapping": "POST",
                "PutMapping": "PUT",
                "DeleteMapping": "DELETE",
                "PatchMapping": "PATCH",
                "RequestMapping": "*",
            }
            for ann_name, verb in http_verbs.items():
                if ann_name in ann:
                    if ann_name == "RequestMapping":
                        modifiers = next((c for c in node.named_children if c.type == "modifiers"), node)
                        verbs = re.findall(r"RequestMethod\.(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)",
                                           self._text(modifiers, source))
                    m_path = ann[ann_name]
                    prefix = getattr(builder, "_current_route_prefix", "")
                    if not m_path.startswith("/") and prefix and m_path:
                        m_path = "/" + m_path
                    full_path = (prefix + m_path) if (prefix or m_path) else "/"
                    if not full_path.startswith("/"):
                        full_path = "/" + full_path
                    for effective_verb in (verbs if ann_name == "RequestMapping" and verbs else [verb]):
                        builder.http_endpoints.setdefault((effective_verb, full_path), []).append(function_id)
                    break

            if "KafkaListener" in ann or "RabbitListener" in ann:
                topic_name = ann.get("KafkaListener") or ann.get("RabbitListener") or "event-stream"
                topic_id = f"topic::{topic_name}"
                if not builder.graph.has_node(topic_id):
                    builder.add_ckg_node(topic_id, "topic_contract", "Lcontract", topic_name)
                builder.add_ckg_edge(function_id, topic_id, "CONSUMES_EVENT", "Lcontract")

        builder.var_defs.setdefault(function_id, {})
        parameters = node.child_by_field_name("parameters") or node.child_by_field_name("parameter")
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
        if receiver:
            builder.current_scope.pop()
            builder.scope_depth -= 1

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


class JavaDispatchResolver:
    """Source-only, service-local Java dispatch; never changes parser state.

    Used only by the workspace's opt-in additive pass. Read the already indexed
    source files, resolve explicit receiver declarations using Java package/import
    context, and return matches between EXISTING graph function nodes. Unknown
    types, generic-dependent types, anonymous/lambda contexts, chained receivers,
    ambiguous declarations/implementors and same-arity overloads are abstentions.
    Method/field inheritance is limited to one superclass. This is static
    declaration resolution, not a claim about runtime dependency injection.
    """

    def __init__(self, builder):
        self.builder = builder
        self.types = {}
        self.workspace_types = self.types
        self.service_types = {}
        self.files = {}
        self.node_index = {}
        prefix = builder.repo_prefix
        for nid, data in builder.graph.nodes(data=True):
            file = data.get("file", "")
            if prefix and file.startswith(prefix):
                file = file[len(prefix):]
            key = (file, data.get("line_no"), data.get("name"), data.get("type"))
            self.node_index.setdefault(key, []).append(nid)
        if not _JAVA_AVAILABLE:
            return
        parser = TreeSitterExtractor(".java").parser
        for file, lines in sorted(builder.raw_file_lines.items()):
            if not file.endswith(".java"):
                continue
            source = "\n".join(lines).encode("utf-8")
            tree = parser.parse(source)
            package, imports, wildcards = "", {}, []
            for child in tree.root_node.named_children:
                text = self._text(child, source)
                if child.type == "package_declaration":
                    package = text.removeprefix("package").strip().rstrip(";").strip()
                elif child.type == "import_declaration" and not text.startswith("import static "):
                    name = text.removeprefix("import").strip().rstrip(";").strip()
                    if name.endswith(".*"):
                        wildcards.append(name[:-2])
                    else:
                        imports.setdefault(name.rsplit(".", 1)[-1], []).append(name)
            context = dict(file=file, source=source, tree=tree, package=package,
                           imports=imports, wildcards=wildcards, classes=[])
            self.files[file] = context
            self._index_types(tree.root_node, context, [])

    @staticmethod
    def _text(node, source):
        return TreeSitterExtractor._text(node, source) if node is not None else ""

    @staticmethod
    def _walk(node):
        yield node
        for child in node.named_children:
            yield from JavaDispatchResolver._walk(child)

    def _index_types(self, node, context, owners):
        if node.type in {"class_declaration", "interface_declaration"}:
            source = context["source"]
            name = self._text(node.child_by_field_name("name"), source)
            qualname = ".".join([*owners, name])
            fqn = ".".join(x for x in (context["package"], qualname) if x)
            mods = next((self._text(c, source) for c in node.named_children
                         if c.type == "modifiers"), "")
            record = dict(node=node, name=name, qualname=qualname, fqn=fqn,
                          repo=self.builder.repo_id,
                          context=context, abstract=node.type == "interface_declaration"
                          or bool(re.search(r"\babstract\b", mods)),
                          generic=node.child_by_field_name("type_parameters") is not None,
                          interface=node.type == "interface_declaration", methods=[], fields={})
            self.types.setdefault(fqn, []).append(record)
            context["classes"].append(record)
            kind = "interface" if record["interface"] else "class"
            ids = self.node_index.get((context["file"], node.start_point.row + 1, name, kind), [])
            record["id"] = ids[0] if len(ids) == 1 else None
            record["super"] = None
            record["bases"] = []
            for child in node.named_children:
                if child.type == "superclass":
                    values = child.named_children
                    if len(values) == 1:
                        record["super"] = self._text(values[0], source)
                        record["bases"].append(record["super"])
                elif child.type in {"super_interfaces", "extends_interfaces"}:
                    for item in child.named_children:
                        values = item.named_children if item.type == "type_list" else [item]
                        record["bases"].extend(self._text(c, source) for c in values)
            body = node.child_by_field_name("body")
            for child in body.named_children if body else []:
                if child.type == "field_declaration":
                    spelling = self._text(child.child_by_field_name("type"), source)
                    for variable in child.named_children:
                        if variable.type == "variable_declarator":
                            field = self._text(variable.child_by_field_name("name"), source)
                            record["fields"].setdefault(field, []).append(spelling)
                elif child.type == "method_declaration":
                    params = child.child_by_field_name("parameters")
                    name = self._text(child.child_by_field_name("name"), source)
                    mid = f'{record["id"]}.{name}' if record["id"] else None
                    record["methods"].append(dict(
                        node=child, owner=record, name=name,
                        arity=len(params.named_children) if params else 0,
                        id=mid if mid in self.builder.graph
                        and self.builder.graph.nodes[mid].get("type") == "function" else None))
            # Retain nested named classes, but not anonymous class bodies.
            owners = [*owners, record["name"]]
        for child in node.named_children:
            self._index_types(child, context, owners)

    def _type(self, spelling, owner):
        if not re.fullmatch(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*", spelling or ""):
            return None
        if spelling in {"var", "void"}:
            return None
        context = owner["context"]
        local_types = self.service_types.get(owner["repo"], self.types)

        def definitions(name):
            return local_types.get(name, self.workspace_types.get(name, []))

        candidates = []
        # Lexically enclosing types, then explicit imports, then package scope.
        lexical = owner["qualname"].split(".")
        for count in range(len(lexical), 0, -1):
            candidates.append(".".join(x for x in
                              (context["package"], ".".join(lexical[:count]), spelling) if x))
        for name in candidates:
            found = local_types.get(name, [])
            if found:
                return found[0] if len(found) == 1 and not found[0]["generic"] else None
        candidates = []
        head, *tail = spelling.split(".")
        imported = context["imports"].get(head, [])
        if len(imported) > 1:
            return None
        if imported:
            imported_name = ".".join([imported[0], *tail])
            found = definitions(imported_name)
            return found[0] if len(found) == 1 and not found[0]["generic"] else None
        candidates.append(".".join(x for x in (context["package"], spelling) if x))
        if "." in spelling or not context["package"]:
            candidates.append(spelling)  # Fully qualified type, or the unnamed package.
        for name in dict.fromkeys(candidates):
            found = definitions(name)
            if found:
                return found[0] if len(found) == 1 and not found[0]["generic"] else None
        found = [r for package in context["wildcards"]
                 for r in definitions(package + "." + spelling)]
        return found[0] if len(found) == 1 and not found[0]["generic"] else None

    def _parent(self, owner):
        return self._type(owner["super"], owner) if owner["super"] else None

    def _implements(self, owner, target, seen=None):
        seen = set() if seen is None else seen
        if owner["fqn"] in seen:
            return False
        seen = seen | {owner["fqn"]}
        for spelling in owner["bases"]:
            base = self._type(spelling, owner)
            if base and (base is target or self._implements(base, target, seen)):
                return True
        return False

    def _methods(self, owner, name, arity, declaration=False):
        found = [m for m in owner["methods"] if m["name"] == name and m["arity"] == arity]
        if not found:
            parents = ([self._type(b, owner) for b in owner["bases"]]
                       if declaration and owner["interface"] else [self._parent(owner)])
            found = [m for p in parents if p for m in p["methods"]
                     if m["name"] == name and m["arity"] == arity]
        if len(found) != 1 or not found[0]["id"]:
            return None
        if not declaration and found[0]["node"].child_by_field_name("body") is None:
            return None
        return found[0]

    def _receiver(self, method, invocation, spelling):
        owner, context = method["owner"], method["owner"]["context"]
        source, node = context["source"], method["node"]
        if spelling == "this":
            return owner if not owner["generic"] else None
        explicit_field = spelling.startswith("this.")
        name = spelling.removeprefix("this.")
        if not re.fullmatch(r"[A-Za-z_$][\w$]*", name):
            return None
        if not explicit_field:
            locals_ = []
            for variable in self._walk(node):
                if variable.type != "variable_declarator" or variable.start_byte >= invocation.start_byte:
                    continue
                declaration = variable.parent
                if (declaration.type != "local_variable_declaration"
                        or self._text(variable.child_by_field_name("name"), source) != name):
                    continue
                scope = declaration.parent
                if scope.start_byte <= invocation.start_byte < scope.end_byte:
                    locals_.append((scope.end_byte - scope.start_byte,
                                    self._text(declaration.child_by_field_name("type"), source)))
            if locals_:
                depth = min(size for size, _ in locals_)
                types = [t for size, t in locals_ if size == depth]
                return self._type(types[0], owner) if len(types) == 1 else None
            params = node.child_by_field_name("parameters")
            types = [self._text(p.child_by_field_name("type"), source)
                     for p in params.named_children if self._text(p.child_by_field_name("name"), source) == name]
            if types:
                return self._type(types[0], owner) if len(types) == 1 else None
        types = owner["fields"].get(name)
        field_owner = owner
        if types is None:
            parent = self._parent(owner)
            if parent:
                types, field_owner = parent["fields"].get(name), parent
        return self._type(types[0], field_owner) if types and len(types) == 1 else None

    def resolve(self):
        matches = []
        for context in self.files.values():
            for owner in context["classes"]:
                for method in owner["methods"]:
                    if not method["id"]:
                        continue
                    # Collapsed overload IDs cannot identify the caller's body.
                    if sum(m["name"] == method["name"] for m in owner["methods"]) != 1:
                        continue
                    for call in self._walk(method["node"]):
                        if call.type != "method_invocation":
                            continue
                        if (call.parent.type == "method_invocation"
                                and call.parent.child_by_field_name("object") == call):
                            continue
                        parent = call.parent
                        while parent and parent != method["node"]:
                            if parent.type in {"lambda_expression", "class_body", "method_declaration"}:
                                break
                            parent = parent.parent
                        if parent != method["node"]:
                            continue
                        receiver = self._text(call.child_by_field_name("object"), context["source"])
                        if not re.fullmatch(r"(?:this\.)?[A-Za-z_$][\w$]*", receiver):
                            continue
                        static = self._receiver(method, call, receiver)
                        if not static:
                            continue
                        name = self._text(call.child_by_field_name("name"), context["source"])
                        args = call.child_by_field_name("arguments")
                        arity = len(args.named_children) if args else 0
                        via, concrete, kind = "", static, "direct"
                        if static["abstract"]:
                            declared = self._methods(static, name, arity, declaration=True)
                            if not declared:
                                continue
                            impls = [r for records in self.types.values() for r in records
                                     if not r["abstract"] and self._implements(r, static)]
                            if len(impls) != 1:
                                continue
                            concrete, via, kind = impls[0], declared["id"], "single_impl"
                        target = self._methods(concrete, name, arity)
                        if not target:
                            continue
                        target_context = target["owner"]["context"]
                        matches.append(dict(
                            caller=method["id"], target=target["id"], match_kind=kind, via=via,
                            static_type=static["fqn"], receiver=receiver, method_name=name, arity=arity,
                            source_evidence=f'{context["file"]}:{call.start_point.row + 1}',
                            source_column=call.start_point.column,
                            target_source_evidence=f'{target_context["file"]}:'
                            f'{target["node"].child_by_field_name("name").start_point.row + 1}',
                            scope_depth=owner["qualname"].count(".") + 2))
        return matches
