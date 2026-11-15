"""
Robust Protobuf AST Parser (Proto2 & Proto3)
=============================================
Provides full AST extraction for .proto files:
- Package, syntax, and imports
- Service declarations with RPC signatures (including stream, packages, options)
- Message declarations with typed fields, tags, and repeated modifiers
- Enum declarations
- Comment stripping (single-line // and multiline /* ... */)
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple


@dataclass
class ProtoField:
    name: str
    type_name: str
    tag: int
    repeated: bool = False
    optional: bool = False
    map_key_type: str = ""
    map_value_type: str = ""


@dataclass
class ProtoRPC:
    name: str
    request_type: str
    response_type: str
    request_stream: bool = False
    response_stream: bool = False
    options: Dict[str, str] = field(default_factory=dict)


@dataclass
class ProtoMessage:
    name: str
    fields: Dict[str, ProtoField] = field(default_factory=dict)
    nested_messages: Dict[str, ProtoMessage] = field(default_factory=dict)
    enums: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class ProtoService:
    name: str
    rpcs: Dict[str, ProtoRPC] = field(default_factory=dict)


@dataclass
class ProtoFile:
    syntax: str = "proto3"
    package: str = ""
    imports: List[str] = field(default_factory=list)
    options: Dict[str, str] = field(default_factory=dict)
    services: Dict[str, ProtoService] = field(default_factory=dict)
    messages: Dict[str, ProtoMessage] = field(default_factory=dict)
    enums: Dict[str, List[str]] = field(default_factory=dict)


class ProtoParser:
    """Robust parser for Protocol Buffer definition files."""

    @staticmethod
    def strip_comments(text: str) -> str:
        """Strip C and C++ style comments while preserving quoted string literals."""
        output = []
        i = 0
        n = len(text)
        in_string = False
        quote_char = ""

        while i < n:
            c = text[i]
            if in_string:
                output.append(c)
                if c == "\\" and i + 1 < n:
                    i += 1
                    output.append(text[i])
                elif c == quote_char:
                    in_string = False
                i += 1
                continue

            if c in ('"', "'"):
                in_string = True
                quote_char = c
                output.append(c)
                i += 1
                continue

            if c == "/" and i + 1 < n:
                next_c = text[i + 1]
                if next_c == "/":
                    # Line comment: skip to newline
                    i += 2
                    while i < n and text[i] != "\n":
                        i += 1
                    if i < n:
                        output.append("\n")
                        i += 1
                    continue
                elif next_c == "*":
                    # Block comment: skip to */
                    i += 2
                    while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                        if text[i] == "\n":
                            output.append("\n")
                        i += 1
                    i += 2  # skip */
                    continue

            output.append(c)
            i += 1

        return "".join(output)

    @classmethod
    def validate_structure(cls, raw_text: str) -> None:
        """Reject unmatched Protobuf braces when protoc cannot resolve imports.

        This is a structural check, not a complete grammar or type validator.
        """
        cleaned = cls.strip_comments(raw_text)
        depth = 0
        quoted = None
        escape_next = False
        for char in cleaned:
            if quoted is not None:
                if escape_next:
                    escape_next = False
                elif char == "\\":
                    escape_next = True
                elif char == quoted:
                    quoted = None
            elif char in ("'", '"'):
                quoted = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth < 0:
                    raise ValueError("unexpected closing brace in protobuf schema")
        if depth:
            raise ValueError("unclosed brace in protobuf schema")
        if quoted is not None:
            raise ValueError("unterminated string in protobuf schema")

    @classmethod
    def parse_text(cls, raw_text: str) -> ProtoFile:
        cleaned = cls.strip_comments(raw_text)
        pf = ProtoFile()

        # Syntax
        syntax_match = re.search(r'syntax\s*=\s*["\']([^"\']+)["\']\s*;', cleaned)
        if syntax_match:
            pf.syntax = syntax_match.group(1)

        # Package
        pkg_match = re.search(r'package\s+([a-zA-Z0-9_.]+)\s*;', cleaned)
        if pkg_match:
            pf.package = pkg_match.group(1)

        # Imports
        for imp in re.finditer(r'import\s+(?:public\s+|weak\s+)?["\']([^"\']+)["\']\s*;', cleaned):
            pf.imports.append(imp.group(1))

        # File-level options
        for opt in re.finditer(r'option\s+([a-zA-Z0-9_.]+)\s*=\s*([^;]+);', cleaned):
            pf.options[opt.group(1)] = opt.group(2).strip().strip('"\'')

        # Extract top-level blocks by brace matching
        blocks = cls._extract_top_blocks(cleaned)

        for kind, name, body in blocks:
            if kind == "service":
                pf.services[name] = cls._parse_service_body(name, body)
            elif kind == "message":
                pf.messages[name] = cls._parse_message_body(name, body)
            elif kind == "enum":
                pf.enums[name] = cls._parse_enum_body(body)

        return pf

    @staticmethod
    def _extract_top_blocks(text: str) -> List[Tuple[str, str, str]]:
        """Extract top-level service, message, enum blocks with balanced braces."""
        results = []
        pattern = re.compile(r'\b(service|message|enum)\s+([a-zA-Z0-9_]+)\s*\{')
        i = 0
        while i < len(text):
            m = pattern.search(text, i)
            if not m:
                break
            kind, name = m.group(1), m.group(2)
            start_body = m.end()
            depth = 1
            j = start_body
            while j < len(text) and depth > 0:
                char = text[j]
                if char == '{':
                    depth += 1
                elif char == '}':
                    depth -= 1
                j += 1
            body = text[start_body:j - 1]
            results.append((kind, name, body))
            i = j
        return results

    @classmethod
    def _parse_service_body(cls, service_name: str, body: str) -> ProtoService:
        service = ProtoService(name=service_name)
        # Normalize `{ ... }` option blocks or `;`
        # rpc Name ( [stream] Req ) returns ( [stream] Resp ) [ { ... } | ; ]
        rpc_pattern = re.compile(
            r'rpc\s+([a-zA-Z0-9_]+)\s*\(\s*(?:stream\s+)?([a-zA-Z0-9_.]+)\s*\)\s*returns\s*\(\s*(?:stream\s+)?([a-zA-Z0-9_.]+)\s*\)'
        )
        for m in rpc_pattern.finditer(body):
            rpc_name = m.group(1)
            req_type = m.group(2).rsplit(".", 1)[-1]
            resp_type = m.group(3).rsplit(".", 1)[-1]
            req_stream = "stream" in body[m.start():m.end()].split("(")[1]
            resp_stream = "stream" in body[m.start():m.end()].split("returns")[1]

            service.rpcs[rpc_name] = ProtoRPC(
                name=rpc_name,
                request_type=req_type,
                response_type=resp_type,
                request_stream=req_stream,
                response_stream=resp_stream,
            )
        return service

    @classmethod
    def _parse_message_body(cls, message_name: str, body: str) -> ProtoMessage:
        msg = ProtoMessage(name=message_name)
        # Nested blocks
        nested = cls._extract_top_blocks(body)
        for kind, name, sub_body in nested:
            if kind == "message":
                msg.nested_messages[name] = cls._parse_message_body(name, sub_body)
            elif kind == "enum":
                msg.enums[name] = cls._parse_enum_body(sub_body)

        # Remove child message/enum bodies before extracting parent fields.
        # Retain oneof contents, whose members are fields of the parent.
        visible = list(body)
        declaration = re.compile(r"\b(?:message|enum)\s+[A-Za-z_][\w]*\s*\{")
        offset = 0
        while True:
            match = declaration.search(body, offset)
            if not match:
                break
            depth, end = 1, match.end()
            while end < len(body) and depth:
                depth += (body[end] == "{") - (body[end] == "}")
                end += 1
            for pos in range(match.start(), end):
                if visible[pos] != "\n":
                    visible[pos] = " "
            offset = end
        visible_text = "".join(visible)

        # Supports standard field modifiers, fully qualified types, oneof
        # members, and map<K, V> declarations.
        field_pattern = re.compile(
            r"(?:(?<=;)|(?<=\{)|^)\s*(repeated|optional|required)?\s*"
            r"(map\s*<\s*[\w.]+\s*,\s*[\w.]+\s*>|[\w.]+)"
            r"\s+([A-Za-z_]\w*)\s*=\s*(\d+)\b",
            re.MULTILINE,
        )
        for match in field_pattern.finditer(visible_text):
            modifier, raw_type, name, tag = (
                match.group(1) or "", match.group(2),
                match.group(3), int(match.group(4))
            )
            map_match = re.fullmatch(
                r"map\s*<\s*([\w.]+)\s*,\s*([\w.]+)\s*>", raw_type
            )
            if name in msg.fields:
                raise ValueError(f"Duplicate protobuf field {message_name}.{name}")
            msg.fields[name] = ProtoField(
                name=name,
                type_name=re.sub(r"\s+", "", raw_type)
                    if map_match else raw_type.rsplit(".", 1)[-1],
                tag=tag,
                repeated=modifier == "repeated",
                optional=modifier == "optional",
                map_key_type=map_match.group(1) if map_match else "",
                map_value_type=map_match.group(2) if map_match else "",
            )
        return msg

    @staticmethod
    def _parse_enum_body(body: str) -> List[str]:
        values = []
        for line in body.splitlines():
            line = line.strip()
            m = re.match(r'([a-zA-Z0-9_]+)\s*=\s*(-?\d+)\s*;', line)
            if m:
                values.append(m.group(1))
        return values
