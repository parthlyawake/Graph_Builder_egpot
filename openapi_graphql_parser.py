"""
OpenAPI and GraphQL Schema Parsers for Lcontract
=================================================
Extends the GRAFT-CKG contract layer (Lcontract) beyond gRPC/Protobuf
to support:
1. OpenAPI (Swagger 2.0 and OpenAPI 3.0/3.1) in YAML/JSON
2. GraphQL Schema Definition Language (SDL) (.graphql, .gql)
"""

from __future__ import annotations
import os
import re
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False


@dataclass
class OpenAPIOperation:
    method: str
    path: str
    operation_id: str = ""
    summary: str = ""
    parameters: List[Dict[str, Any]] = field(default_factory=list)
    request_body: Dict[str, Any] = field(default_factory=dict)
    responses: Dict[str, Any] = field(default_factory=dict)
    request_schema: Dict[str, Any] = field(default_factory=dict)
    response_schemas: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OpenAPISpec:
    title: str = ""
    version: str = ""
    operations: List[OpenAPIOperation] = field(default_factory=list)


class OpenAPIContractParser:
    """Parses OpenAPI 2.0 / 3.x documents into canonical contract structures."""

    @classmethod
    def parse_file(cls, file_path: str) -> Optional[OpenAPISpec]:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            return None

        data = None
        if file_path.endswith((".yaml", ".yml")) and _YAML_AVAILABLE:
            try:
                data = yaml.safe_load(content)
            except Exception:
                pass
        elif file_path.endswith(".json"):
            try:
                data = json.loads(content)
            except Exception:
                pass

        if not isinstance(data, dict):
            return None

        # Check for openapi or swagger key
        if not ("openapi" in data or "swagger" in data or "paths" in data):
            return None

        spec = OpenAPISpec()
        info = data.get("info", {})
        if isinstance(info, dict):
            spec.title = info.get("title", "")
            spec.version = str(info.get("version", ""))

        from openapi_schema import resolve_local_refs
        paths = data.get("paths", {})
        if isinstance(paths, dict):
            for path, item in paths.items():
                path_item = resolve_local_refs(data, item)
                if not isinstance(path_item, dict):
                    continue
                inherited = path_item.get("parameters", [])
                for method in ("get", "post", "put", "delete", "patch", "head", "options"):
                    op_data = path_item.get(method)
                    if not isinstance(op_data, dict):
                        continue
                    definition = resolve_local_refs(data, op_data)
                    params = [*inherited, *definition.get("parameters", [])]
                    unique_params = {
                        (p.get("name"), p.get("in")): p for p in params
                        if isinstance(p, dict)
                    }
                    request = definition.get("requestBody", {})
                    responses = definition.get("responses", {})
                    if not isinstance(request, dict):
                        request = {}
                    if not isinstance(responses, dict):
                        responses = {}
                    # Swagger 2 request bodies are represented as in:body params.
                    if not request:
                        body = next((p for p in unique_params.values()
                                     if p.get("in") == "body"), None)
                        if body:
                            request = {"content": {
                                data.get("consumes", ["application/json"])[0]:
                                {"schema": body.get("schema", {})}
                            }}
                    request_content = request.get("content", {})
                    request_schema = {
                        media: spec.get("schema", {})
                        for media, spec in request_content.items()
                        if isinstance(spec, dict)
                    } if isinstance(request_content, dict) else {}
                    response_schemas = {}
                    for status, response in responses.items():
                        if not isinstance(response, dict):
                            continue
                        content = response.get("content")
                        if isinstance(content, dict):
                            response_schemas[str(status)] = {
                                media: body.get("schema", {})
                                for media, body in content.items()
                                if isinstance(body, dict)
                            }
                        elif isinstance(response.get("schema"), dict):
                            response_schemas[str(status)] = {
                                "application/json": response["schema"]
                            }
                    spec.operations.append(OpenAPIOperation(
                        method=method.upper(), path=path,
                        operation_id=definition.get("operationId", ""),
                        summary=definition.get("summary", ""),
                        parameters=list(unique_params.values()),
                        request_body=request, responses=responses,
                        request_schema=request_schema,
                        response_schemas=response_schemas,
                    ))
        return spec


@dataclass
class GraphQLField:
    name: str
    type_name: str
    arguments: Dict[str, str] = field(default_factory=dict)


@dataclass
class GraphQLType:
    name: str
    kind: str  # "Query", "Mutation", "Subscription", "Type", "Interface", "Input"
    fields: Dict[str, GraphQLField] = field(default_factory=dict)


@dataclass
class GraphQLSpec:
    types: Dict[str, GraphQLType] = field(default_factory=dict)
    root_types: Dict[str, str] = field(default_factory=dict)
    invalid: bool = False


class GraphQLContractParser:
    """Parses GraphQL Schema Definition Language (.graphql / .gql) files."""

    @classmethod
    def parse_text(cls, text: str) -> GraphQLSpec:
        spec = GraphQLSpec()
        from graphql_ast_support import parse_schema_ast
        parsed = parse_schema_ast(text)
        if parsed is not None:
            spec.invalid = bool(parsed.get("invalid"))
            spec.root_types.update(parsed.get("root_types", {}))
            for name, entity in parsed.get("types", {}).items():
                item = GraphQLType(name=name, kind=entity["kind"])
                for field_name, definition in entity["fields"].items():
                    item.fields[field_name] = GraphQLField(
                        name=field_name, type_name=definition["type_name"],
                        arguments=definition["arguments"],
                    )
                spec.types[name] = item
            return spec
        # Strip comments
        cleaned = re.sub(r'#[^\n]*', '', text)

        # Match type declarations: type/interface/input Name { ... }
        type_pattern = re.compile(r'\b(type|interface|input|enum)\s+([a-zA-Z0-9_]+)\s*(?:implements\s+[a-zA-Z0-9_,\s]+)?\s*\{([^}]+)\}')
        for m in type_pattern.finditer(cleaned):
            kind, name, body = m.group(1), m.group(2), m.group(3)
            gt = GraphQLType(name=name, kind=kind)

            # Match fields: fieldName(arg: Type): ReturnType
            field_pattern = re.compile(r'^\s*([a-zA-Z0-9_]+)(?:\(([^)]+)\))?\s*:\s*([a-zA-Z0-9_!\[\]]+)', re.MULTILINE)
            for fm in field_pattern.finditer(body):
                f_name = fm.group(1)
                f_args_raw = fm.group(2) or ""
                f_return = fm.group(3).strip()

                args = {}
                if f_args_raw:
                    for arg in f_args_raw.split(","):
                        if ":" in arg:
                            aname, atype = arg.split(":", 1)
                            args[aname.strip()] = atype.strip()

                gt.fields[f_name] = GraphQLField(name=f_name, type_name=f_return, arguments=args)

            if name in spec.types:
                spec.types[name].fields.update(gt.fields)
            else:
                spec.types[name] = gt
        return spec
