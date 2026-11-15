"""Standards-oriented structural contracts for Apache Thrift, Avro and Pegasus PDL.

Models schema declarations and documented RPC signatures, not runtime calls.
The surface is repo-agnostic: parsing is based on source syntax and extension.
A partially understood construct is preserved as source text rather than
promoted to a fabricated cross-service link.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def _clean(text):
    def replace(m):
        return "".join("\n" if c == "\n" else " " for c in m.group(0))
    return re.sub(r"//[^\n]*|/\*[\s\S]*?\*/|#[^\n]*", replace, text)


def _brace(text, start):
    """Return a balanced-body substring and the closing index."""
    opening = text.find("{", start)
    if opening < 0:
        return "", -1
    depth, string, escaped = 0, None, False
    for i in range(opening, len(text)):
        c = text[i]
        if string:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == string:
                string = None
            continue
        if c in ("'", '"'):
            string = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if not depth:
                return text[opening + 1:i], i
    return text[opening + 1:], -1


def _schema_node(builder, file_id, node_id, kind, name, line, snippet):
    if node_id in builder.graph:
        # Do not overwrite another file's declaration with the same name.
        defs = builder.graph.nodes[node_id].setdefault("definitions", [])
        if builder.current_file_ctx not in defs:
            defs.append(builder.current_file_ctx)
        return
    builder.add_ckg_node(node_id, kind, "Lcontract", name,
                         line, code=snippet[:3000])
    builder.graph.nodes[node_id]["definitions"] = [builder.current_file_ctx]
    builder.add_ckg_edge(file_id, node_id, "CONTAINS", "Lsyn")


def _contract_file(builder, rel_path, text):
    builder.current_file = rel_path
    builder.current_scope = []
    builder.scope_depth = 0
    lines = text.splitlines()
    builder.raw_file_lines[rel_path] = lines
    builder.total_loc += len(lines)
    file_id = builder.current_file_node_id
    if file_id not in builder.graph:
        builder.add_ckg_node(file_id, "file", "Lsyn", Path(rel_path).name,
                             1, code=f"// Schema: {rel_path} ({len(lines)} lines)")
    return file_id


def _line(source, offset):
    return source.count("\n", 0, offset) + 1


def _split_signature_args(data):
    # Commas inside generic maps/lists are not separators.
    result, current, nested = [], "", 0
    for char in data:
        nested += (char in "<([{") - (char in ">)]}")
        if char == "," and nested == 0:
            if current.strip():
                result.append(current.strip())
            current = ""
        else:
            current += char
    if current.strip():
        result.append(current.strip())
    return result


def parse_thrift(builder, rel_path, full_path):
    text = Path(full_path).read_text(encoding="utf-8")
    file_id = _contract_file(builder, rel_path, text)
    clean = _clean(text)
    namespaces = dict(re.findall(r"(?m)^\s*namespace\s+(\w+)\s+([\w.]+)", clean))
    # "namespace * foo" is the fallback for clients without a language alias.
    fallback = re.search(r"(?m)^\s*namespace\s+\*\s+([\w.]+)", clean)
    ns = (fallback.group(1) if fallback else
          next(iter(namespaces.values()), ""))
    qualified = lambda name: ".".join(filter(None, (ns, name)))

    for include in re.findall(r'(?m)^\s*include\s+["\']([^"\']+)["\']', clean):
        mid = "module::" + include
        if mid not in builder.graph:
            builder.add_ckg_node(mid, "module", "Ldep", include)
        builder.add_ckg_edge(file_id, mid, "IMPORTS", "Ldep")

    declared = 0
    for decl in re.finditer(
            r"\b(struct|union|exception|enum|service)\s+([A-Za-z_]\w*)"
            r"(?:\s+extends\s+[A-Za-z_.]\w*)?\s*\{", clean):
        kind, name = decl.group(1), decl.group(2)
        body, close = _brace(clean, decl.start())
        if close < 0:
            raise ValueError(f"Unclosed Thrift {kind} {name} at line {_line(clean, decl.start())}")
        line = _line(clean, decl.start())
        node_id = f"contract::thrift::{qualified(name)}"
        node_type = "service_contract" if kind == "service" else "schema_contract"
        _schema_node(builder, file_id, node_id, node_type, name, line, text[decl.start():close+1])
        builder.graph.nodes[node_id]["contract_format"] = "thrift"
        builder.graph.nodes[node_id]["namespace_by_language"] = namespaces
        declared += 1
        if kind != "service":
            # Typed fields use Thrift numeric tags; track their tag/name/type.
            for match in re.finditer(
                    r"(?m)^\s*(\d+)\s*:\s*(?:(?:required|optional)\s+)?"
                    r"(.+?)\s+([A-Za-z_]\w*)\s*(?:[=;,]|$)", body):
                tag, dtype, field = match.groups()
                fid = node_id + ".field::" + field
                _schema_node(builder, file_id, fid, "schema_field",
                             field, line + _line(body, match.start()) - 1, match.group(0))
                builder.graph.nodes[fid].update(field_type=dtype.strip(), field_tag=int(tag))
                builder.add_ckg_edge(node_id, fid, "DEFINES", "Lcontract")
            continue

        # Parse RPC name/return using a balanced parameter list (generic maps).
        rpc_pattern = re.compile(
            r"(?:^|[;\n])\s*(?:oneway\s+)?"
            r"([A-Za-z_]\w*(?:\s*<[^;()]+>)?(?:\.[A-Za-z_]\w*)?)"
            r"\s+([A-Za-z_]\w*)\s*\(", re.M)
        for rpc in rpc_pattern.finditer(body):
            result_type, rpc_name = rpc.groups()
            begin = rpc.end()
            depth, end = 1, begin
            while end < len(body) and depth:
                depth += (body[end] == "(") - (body[end] == ")")
                end += 1
            if depth:
                raise ValueError(f"Unclosed Thrift RPC {rpc_name}")
            args = _split_signature_args(body[begin:end - 1])
            rpc_id = node_id + "." + rpc_name
            _schema_node(builder, file_id, rpc_id, "rpc_contract", rpc_name,
                         line + _line(body, rpc.start()) - 1, rpc.group(0) + body[begin:end])
            builder.graph.nodes[rpc_id].update(
                return_type=result_type.strip(), args=args, contract_format="thrift")
            builder.add_ckg_edge(node_id, rpc_id, "DEFINES_RPC", "Lcontract")
    return {"file": rel_path, "format": "thrift", "declarations": declared}


def parse_pdl(builder, rel_path, full_path):
    text = Path(full_path).read_text(encoding="utf-8")
    file_id = _contract_file(builder, rel_path, text)
    clean = _clean(text)
    namespace = re.search(r"(?m)^\s*namespace\s+([\w.]+)", clean)
    ns = namespace.group(1) if namespace else ""
    declarations = 0
    for decl in re.finditer(
            r"\b(record|enum|typeref|fixed|union)\s+([A-Za-z_]\w*)\b", clean):
        kind, name = decl.groups()
        nid = "contract::pdl::" + ".".join(filter(None, (ns, name)))
        body, end = _brace(clean, decl.end())
        snippet = text[decl.start():end+1] if end >= 0 else text[decl.start():decl.end()+120]
        _schema_node(builder, file_id, nid, "schema_contract",
                     name, _line(clean, decl.start()), snippet)
        builder.graph.nodes[nid]["contract_format"] = "pdl"
        builder.graph.nodes[nid]["schema_kind"] = kind
        declarations += 1
        if kind != "record" or end < 0:
            continue
        for field in re.finditer(
                r"(?m)^\s*([A-Za-z_]\w*)\s*:\s*(?:optional\s+)?"
                r"([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)", body):
            fname, ftype = field.groups()
            fid = nid + ".field::" + fname
            _schema_node(builder, file_id, fid, "schema_field", fname,
                         _line(clean, decl.start()) + _line(body, field.start()) - 1,
                         field.group(0))
            builder.graph.nodes[fid]["field_type"] = ftype
            builder.add_ckg_edge(nid, fid, "DEFINES", "Lcontract")
    return {"file": rel_path, "format": "pdl", "declarations": declarations}


def parse_avsc(builder, rel_path, full_path):
    text = Path(full_path).read_text(encoding="utf-8")
    data = json.loads(text)
    file_id = _contract_file(builder, rel_path, text)
    seen = set()
    def walk(schema, namespace="", depth=0):
        if depth > 50:
            raise ValueError("Avro schema exceeds supported maximum nesting depth 50")
        if isinstance(schema, list):
            for item in schema:
                walk(item, namespace, depth + 1)
            return
        if not isinstance(schema, dict):
            return
        kind = schema.get("type")
        if isinstance(kind, (dict, list)):
            walk(kind, namespace, depth + 1)
        if isinstance(kind, str) and kind in {"array", "map"}:
            walk(schema.get("items") if kind == "array" else schema.get("values"),
                 namespace, depth + 1)
        if not isinstance(kind, str) or kind not in {"record", "enum", "fixed"}:
            return
        name = schema.get("name")
        if not isinstance(name, str) or not name:
            return
        ns = schema.get("namespace", namespace)
        full = name if "." in name else ".".join(filter(None, (ns, name)))
        nid = "contract::avro::" + full
        if full not in seen:
            seen.add(full)
            _schema_node(builder, file_id, nid, "schema_contract", name,
                         1, json.dumps(schema, ensure_ascii=False)[:3000])
        for field in schema.get("fields", []):
            if not isinstance(field, dict) or not isinstance(field.get("name"), str):
                continue
            fid = nid + ".field::" + field["name"]
            _schema_node(builder, file_id, fid, "schema_field", field["name"], 1,
                         json.dumps(field, ensure_ascii=False)[:1000])
            builder.add_ckg_edge(nid, fid, "DEFINES", "Lcontract")
            walk(field.get("type"), ns, depth + 1)
    walk(data)
    return {"file": rel_path, "format": "avsc", "declarations": len(seen)}


def parse_schema(builder, rel_path, full_path):
    ext = Path(rel_path).suffix.lower()
    if ext == ".thrift":
        return parse_thrift(builder, rel_path, full_path)
    if ext == ".pdl":
        return parse_pdl(builder, rel_path, full_path)
    if ext == ".avsc":
        return parse_avsc(builder, rel_path, full_path)
    raise ValueError(f"Unknown schema type: {rel_path}")
