"""Conservative C++ Apache Thrift client/handler bindings.

Thrift IDL declares interfaces but does not prove a running service. This pass
only emits exact contract links for source-evidenced typed clients or concrete
interface implementations. Unresolved dynamic client types remain unlinked.
"""
from __future__ import annotations

import re
from collections import defaultdict

_CPP_EXT = (".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx")


def _rpc_index(graph):
    services = defaultdict(dict)
    for nid, data in graph.nodes(data=True):
        if data.get("type") != "rpc_contract" or data.get("contract_format") != "thrift":
            continue
        owner, _, method = nid.rpartition(".")
        service = owner.rsplit(".", 1)[-1]
        services[service][method] = nid
    return services


def _add(graph, source, target, relation, file, line, how):
    if source not in graph or target not in graph:
        return False
    key = "thrift::" + relation + "::" + source + "::" + target
    if graph.has_edge(source, target, key=key):
        return False
    graph.add_edge(source, target, key=key, relation=relation,
                   layer="Lcontract", c_type=1.0,
                   source_evidence=f"{file}:{line}", binding_kind=how)
    return True


def _balanced_body(source, start):
    opening = source.find("{", start)
    if opening < 0:
        return ""
    depth, quoted, escaped = 0, None, False
    for pos in range(opening, len(source)):
        ch = source[pos]
        if quoted:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quoted:
                quoted = None
            continue
        if ch in ("'", '"'):
            quoted = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1:pos]
    return ""


def _function_for(builder, file, name, class_name=None):
    """Require one AST-extracted function; names alone across files are unsafe."""
    matches = [
        nid for nid, d in builder.graph.nodes(data=True)
        if d.get("type") in {"function", "method"}
        and d.get("name") == name
        and d.get("file") in {file, builder.repo_prefix + file}
        and (class_name is None or
             class_name in nid or class_name in (d.get("code") or "")[:200])
    ]
    return matches[0] if len(set(matches)) == 1 else None


def _client_pools(text):
    """ClientPool<ThriftClient<ServiceClient>> field -> exact Thrift service."""
    clients = defaultdict(set)
    pattern = re.compile(
        r"\bClientPool\s*<\s*(?:\w+::)*ThriftClient\s*<\s*"
        r"(?:\w+::)*([A-Za-z_]\w*)Client\s*>\s*>\s*[*&]?\s*"
        r"([A-Za-z_]\w*)"
    )
    for match in pattern.finditer(text):
        clients[match.group(2)].add(match.group(1))
    return clients


def _typed_local_clients(text):
    clients = defaultdict(set)
    pattern = re.compile(
        r"\b(?:\w+::)*([A-Za-z_]\w*)Client\s*[*&]?\s+"
        r"([A-Za-z_]\w*)\s*(?:[=;(,]|$)"
    )
    for match in pattern.finditer(text):
        clients[match.group(2)].add(match.group(1))
    # Generated Thrift clients are also held behind typed smart pointers.
    smart = re.compile(
        r"\b(?:std::)?(?:shared_ptr|unique_ptr)\s*<\s*"
        r"(?:\w+::)*([A-Za-z_]\w*)Client\s*>\s*([A-Za-z_]\w*)\b"
    )
    for match in smart.finditer(text):
        clients[match.group(2)].add(match.group(1))
    factory = re.compile(
        r"\b(?:auto|[A-Za-z_]\w*)\s+([A-Za-z_]\w*)\s*=\s*"
        r"(?:std::)?make_(?:shared|unique)\s*<\s*"
        r"(?:\w+::)*([A-Za-z_]\w*)Client\s*>\s*\("
    )
    for match in factory.finditer(text):
        clients[match.group(1)].add(match.group(2))
    return clients


def _function_source(lines, span, excerpt):
    first, first_col, last, last_col = span
    if not 0 <= first <= last < len(lines):
        return excerpt
    if first == last:
        full = lines[first][first_col:last_col]
    else:
        full = "\n".join([lines[first][first_col:], *lines[first + 1:last], lines[last][:last_col]])
    # Use the range only if its beginning matches the stored definition.
    return full if full.startswith(excerpt.replace("\r\n", "\n").rstrip("\r")) else excerpt


def bind_thrift_runtime(graph, builders):
    """Link typed C++ clients and interface implementers to canonical RPCs.

    Args:
        graph: standalone or composed NetworkX MultiDiGraph.
        builders: iterable of CKGBuilder instances.
    """
    services = _rpc_index(graph)
    if not services:
        return {"implements": 0, "consumes": 0}
    counts = {"implements": 0, "consumes": 0}
    for builder in builders:
        cpp = {name: "\n".join(lines) for name, lines in
               builder.raw_file_lines.items() if name.endswith(_CPP_EXT)}
        function_spans = getattr(builder, "_cpp_function_spans", {})
        for file, source in sorted(cpp.items()):
            # A Thrift implementation must inherit the generated interface,
            # not merely define a function with the same spelling.
            inheritance = re.compile(
                r"\b(?:class|struct)\s+([A-Za-z_]\w*)\s*:\s*"
                r"(?:(?:public|private|protected)\s+)?"
                r"(?:(?:\w+::)*)([A-Za-z_]\w*)If\b"
            )
            for match in inheritance.finditer(source):
                handler_class, service = match.groups()
                if service not in services:
                    continue
                block = _balanced_body(source, match.end())
                if not block:
                    continue
                for method, target in services[service].items():
                    declaration = re.search(
                        r"\b" + re.escape(method) + r"\s*\(", block
                    )
                    if declaration is None:
                        continue
                    implementer = _function_for(builder, file, method, handler_class)
                    if implementer is None:
                        # Class declaration is source evidence of an override.
                        # Preserve it as a declaration, not a verified body.
                        line = source.count("\n", 0, match.start()) + 1 + (
                            block.count("\n", 0, declaration.start()))
                        implementer = (builder.repo_prefix + file +
                                       ":thrift_decl:" + handler_class + "." + method +
                                       "@" + str(line))
                        if implementer not in graph:
                            graph.add_node(
                                implementer, id=implementer, type="function",
                                layer="Lsyn", name=method,
                                repo=builder.repo_id or "", file=builder.repo_prefix + file,
                                line_no=line, declaration_only=True,
                                code=block[max(0, declaration.start()-30):
                                           declaration.end()+100])
                    if _add(graph, implementer, target, "IMPLEMENTS", file,
                            source.count("\n", 0, match.start()) + 1,
                            "thrift_interface_declaration"):
                        counts["implements"] += 1

        # Restrict direct client calls to AST-extracted functions and typed
        # receivers. Avoid a name-only cross-service RPC match.
        file_pools = {file: _client_pools(src) for file, src in cpp.items()}
        for file, source in sorted(cpp.items()):
            for nid, data in list(builder.graph.nodes(data=True)):
                if data.get("type") not in {"function", "method"}:
                    continue
                if data.get("file") not in {file, builder.repo_prefix + file}:
                    continue
                snippet = data.get("code") or ""
                span = function_spans.get(file, {}).get(nid)
                if span is not None:
                    snippet = _function_source(builder.raw_file_lines[file], span, snippet)
                if not snippet or "Client" not in (source + snippet):
                    continue
                typed = _typed_local_clients(snippet)
                pool_types = file_pools[file]
                wrappers = defaultdict(set)
                for found in re.finditer(
                    r"\b([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)->Pop\s*\(", snippet
                ):
                    wrappers[found.group(1)].update(pool_types.get(found.group(2), ()))
                for found in re.finditer(
                    r"\b([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)->GetClient\s*\(", snippet
                ):
                    typed[found.group(1)].update(wrappers.get(found.group(2), ()))
                for found in re.finditer(
                    r"\b([A-Za-z_]\w*)\s*(?:->|\.)\s*([A-Za-z_]\w*)\s*\(", snippet
                ):
                    receiver, method = found.groups()
                    choices = {services[svc][method]
                               for svc in typed.get(receiver, ())
                               if method in services.get(svc, {})}
                    if len(choices) != 1:
                        continue
                    target = next(iter(choices))
                    line = int(data.get("line_no") or 1) + snippet.count(
                        "\n", 0, found.start())
                    if _add(graph, nid, target, "CONSUMES", file, line,
                            "typed_thrift_cpp_client"):
                        counts["consumes"] += 1
    return counts
