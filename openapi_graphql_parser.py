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

        paths = data.get("paths", {})
        if isinstance(paths, dict):
            for path, path_item in paths.items():
                if not isinstance(path_item, dict):
                    continue
                for method in ("get", "post", "put", "delete", "patch", "head", "options"):
                    op_data = path_item.get(method)
                    if isinstance(op_data, dict):
                        op = OpenAPIOperation(
                            method=method.upper(),
                            path=path,
                            operation_id=op_data.get("operationId", ""),
                            summary=op_data.get("summary", ""),
                            parameters=op_data.get("parameters", []) if isinstance(op_data.get("parameters"), list) else [],
                            request_body=op_data.get("requestBody", {}) if isinstance(op_data.get("requestBody"), dict) else {},
                            responses=op_data.get("responses", {}) if isinstance(op_data.get("responses"), dict) else {},
                        )
                        spec.operations.append(op)
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


class GraphQLContractParser:
    """Parses GraphQL Schema Definition Language (.graphql / .gql) files."""

    @classmethod
    def parse_text(cls, text: str) -> GraphQLSpec:
        spec = GraphQLSpec()
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

            spec.types[name] = gt
        return spec
