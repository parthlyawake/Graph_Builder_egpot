"""Audit DataHub builder coverage. No retrieval and no candidate selection by edges."""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from contextlib import contextmanager
import ctypes
from fnmatch import fnmatchcase
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from time import perf_counter
from unittest.mock import patch
from xml.sax.saxutils import escape, quoteattr

import networkx as nx

from bench.analyze_dsb_distance import markdown_table
from bench.egpot_width_sweep_dev import guard
from graft_ckg import _GENERATED_SOURCE_HEADER, _NONPRODUCTION_FILENAME, _NONPRODUCTION_PATH_PARTS
from multi_repo import RepoConfig, WorkspaceCKGBuilder, WorkspaceConfig
import proto_compiler


SOURCE = Path("C:/dev/egpot_repos/datahub")
EVIDENCE = Path("C:/dev/egpot_repos/labels_draft/datahub_source_evidence_v2.md")
REVISION = "c2a82c97f0faf73c266d6525aead90557615147f"
BUILDER = "94aae7b8aef08ac2beddcbc7fc37a7e2b2cc69ce"
ROOTS = {
    "web": "datahub-web-react/src",
    "graphql": "datahub-graphql-core/src/main/java",
    "graphql-idl": "datahub-graphql-core/src/main/resources",
    "frontend": "datahub-frontend/app",
    "ingestion": "metadata-ingestion/src",
    "openapi": "metadata-service/openapi-servlet/src/main/java",
    "openapi-idl": "metadata-service/openapi-servlet/src/main/resources",
    "restli": "metadata-service/restli-servlet-impl/src/main/java",
    "restli-idl": "metadata-service/restli-api/src/main/idl",
}
IGNORE = ("*.generated.*", "*.min.js", "tests.graphql")
EXCLUDED = _NONPRODUCTION_PATH_PARTS | {".git", "docs", "examples", "example", "fixtures", "e2e-test",
                                     "smoke-test", "perf-test", "__pycache__", ".venv"}
RESULTS = Path("bench/results")
EXTENSIONS = {".ts":"TypeScript", ".tsx":"TypeScript", ".java":"Java", ".py":"Python",
              ".js":"JavaScript", ".jsx":"JavaScript", ".scala":"Scala", ".graphql":"GraphQL",
              ".gql":"GraphQL", ".json":"JSON", ".yaml":"YAML", ".yml":"YAML", ".avsc":"Avro",
              ".pdl":"PDL", ".proto":"Protobuf", ".thrift":"Thrift"}
CITATION = re.compile(r"`([^\x60]+):(\d+)`")


def canonical_contract_name(name):
    # Interface files and callers can name the same path variable differently.
    if name and " /" in name:
        path, mark, query = name.partition("?")
        return re.sub(r"(?<=/)\{[^/{}]+\}(?=/|$)", "{param}", path) + mark + query
    return name


def read_evidence(path):
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) != 7 or not re.fullmatch(r"DH\d\d", cells[0]):
            continue
        _, caller, dispatch, contract, handler, _, alternative = cells
        caller_file, caller_line = CITATION.search(caller).groups()
        handler_file, handler_line = CITATION.search(handler).groups()
        cname = contract.split("`")[1]
        evidence = {
            "id": cells[0], "caller": (caller_file, int(caller_line), caller.split("`")[1]),
            "handler": (handler_file, int(handler_line), handler.split("`")[1]),
            "contract_name": cname, "contract_citations": CITATION.findall(contract), "lookalike": alternative,
        }
        if cname.startswith(("Query.", "Mutation.")):
            document = next(p for p, _ in CITATION.findall(dispatch) if p.endswith(".graphql"))
            definition = re.search(r"`(?:query|mutation) (\w+)", dispatch)[1]
            hook = re.search(r"\b(use\w+(?:Mutation|Query))\(", dispatch)[1]
            evidence.update(pair="React → GraphQL", operation=(document, definition), hook=hook)
        else:
            evidence["pair"] = ("Python → Rest.li" if handler_file.startswith(
                "metadata-service/restli") else "Python → OpenAPI")
        entries.append(evidence)
    if [row["id"] for row in entries] != [f"DH{i:02}" for i in range(1, 27)]:
        raise ValueError("Expected 26 ordered and verified DataHub evidence entries")
    return entries


def source_path(path):
    value = str(path or "").replace("\\", "/")
    head, sep, tail = value.partition("/")
    return ROOTS[head] + "/" + tail if sep and head in ROOTS else value


class SourceIndex:
    """Index node attributes and stable IDs, with no access to graph edges."""

    def __init__(self, nodes):
        self.by_file = defaultdict(list)
        self.contracts = defaultdict(list)
        self.ids = set()
        for node, attrs in nodes:
            self.ids.add(node)
            file = source_path(attrs.get("file"))
            kind = attrs.get("type")
            if kind in {"function", "class", "graphql_operation", "file", "variable"} and file:
                self.by_file[file].append((node, attrs))
            if kind in {"contract", "endpoint", "http_endpoint", "rpc_contract"}:
                if attrs.get("method") and attrs.get("path"):
                    name = f"{attrs['method']} {attrs['path']}"
                else:
                    name = attrs.get("name")
                self.contracts[canonical_contract_name(name)].append((node, file))

    def declaration(self, evidence, kind="function"):
        file, line, qualified = evidence
        short = qualified.rsplit(".", 1)[-1]
        matched = []
        spanning = []
        for node, attrs in self.by_file[file]:
            if attrs.get("type") != kind or attrs.get("name") != short:
                continue
            declared_id = attrs.get("overload_group") or node
            suffix = declared_id.split(":", 1)[-1].split("@line:", 1)[0]
            if "." in qualified and suffix != qualified and not suffix.endswith("." + qualified):
                continue
            node_line = int(attrs.get("line_no", 0))
            # Evidence usually cites the method signature after its Java annotations.
            span_end = int(attrs.get("line_end", node_line)) if file.endswith(".java") else node_line
            tolerance = 8 if file.endswith(".java") else 1
            if node_line > 0:
                if node_line <= line <= span_end:
                    spanning.append((node, node_line))
                if abs(node_line - line) <= tolerance:
                    matched.append((node, node_line))
        exact = [m for m in matched if m[1] == line]
        candidates = exact or spanning or matched
        node, graph_line = candidates[0] if len(candidates) == 1 else (None, None)
        result = {"id": node, "evidence_line": line, "graph_line": graph_line, "candidates": candidates}
        if node is None:
            result["same_file_name_candidates"] = [
                (n, a.get("line_no"), a.get("line_end"), a.get("type"))
                for n, a in self.by_file[file] if a.get("name") == short
            ]
        return result

    def named_in_file(self, file, name, kind):
        ids = [node for node, attrs in self.by_file[file]
               if attrs.get("type") == kind and attrs.get("name") == name]
        return ids[0] if len(ids) == 1 else None

    def contract(self, name, citations, *, allow_other_files=False):
        candidates = self.contracts.get(canonical_contract_name(name), [])
        exact_files = {p for p, _ in citations}
        exact = [n for n, f in candidates if f in exact_files]
        if not exact:
            # Canonical SDL / endpoint nodes often have no file attribute.
            exact = [n for n, f in candidates if not f]
        if not exact and allow_other_files and len(candidates) == 1:
            exact = [candidates[0][0]]
        return {"id": exact[0] if len(exact) == 1 else None, "candidates": candidates,
                "file_provenance": "node attribute" if exact and any(f in exact_files for _, f in candidates)
                else "unique canonical name" if len(exact) == 1 else None}


def relation_list(graph, src, dst):
    if src is None or dst is None:
        return []
    return sorted({attrs.get("relation", "LINK")
                   for attrs in graph.get_edge_data(src, dst, default={}).values()})


def http_dispatch_paths(graph, start, contract, handler):
    """Check mapped targets through SDK call edges, separately from ID selection."""
    if start is None:
        return {}
    paths = {}
    visited = {start}
    pending = deque([(start, [])])
    while pending:
        node, prefix = pending.popleft()
        for target in sorted(graph.successors(node)):
            relations = set(relation_list(graph, node, target))
            for destination, kind in ((handler, "HTTP_CALLS"), (contract, "CONSUMES")):
                if target == destination and kind in relations:
                    paths.setdefault(kind, prefix + [(node, kind, target)])
            if "HTTP_REQUEST" in relations:
                for destination in sorted(graph.successors(target)):
                    if destination in (contract, handler) and "POSSIBLE_HTTP_TARGET" in relation_list(graph, target, destination):
                        paths.setdefault("POSSIBLE_HTTP_TARGET", prefix + [
                            (node, "HTTP_REQUEST", target), (target, "POSSIBLE_HTTP_TARGET", destination)])
            calls = relations & {"CALLS", "POLYMORPHIC_CALL", "INVOKES"}
            if calls and target.startswith("ingestion/") and target not in visited:
                visited.add(target)
                pending.append((target, prefix + [(node, min(calls), target)]))
    return paths


def inspect_links(graph, evidence, source=SOURCE):
    index = SourceIndex(graph.nodes(data=True))
    links = []
    for row in evidence:
        start = index.declaration(row["caller"])
        end = index.declaration(row["handler"])
        contract = index.contract(row["contract_name"], row["contract_citations"])
        s, h, c = start["id"], end["id"], contract["id"]
        consumes = relation_list(graph, s, c)
        implements = relation_list(graph, h, c)
        direct = relation_list(graph, s, h)
        result = {"id": row["id"], "pair": row["pair"], "caller": start, "contract": contract,
                  "handler": end, "start_to_contract": consumes, "handler_to_contract": implements,
                  "direct_caller_to_handler": direct}
        if row["id"] in {"DH15", "DH16", "DH18"}:
            result["http_dispatch_paths"] = http_dispatch_paths(graph, s, c, h)
        if "operation" in row:
            op_file, op_name = row["operation"]
            op = index.named_in_file(op_file, op_name, "graphql_operation")
            op_file_id = f"file::{op_file}"
            if op_file_id not in index.ids:
                op_file_id = None
            hook_path = op_file.removesuffix(".graphql") + ".generated.ts"
            hook = index.named_in_file(hook_path, row["hook"], "function")
            external_hook = "external::" + row["hook"]
            if external_hook not in index.ids:
                external_hook = None
            java_file, java_line, java_method = row["handler"]
            java_class = java_method.split(".")[0]
            class_lines = (source / java_file).read_text(encoding="utf-8").splitlines()
            class_line = next(i for i,l in enumerate(class_lines, 1)
                              if re.search(r"\bclass\s+" + re.escape(java_class) + r"\b", l))
            resolver_class = index.declaration((java_file, class_line, java_class), kind="class")["id"]
            result["graphql"] = {
                "hook_name": row["hook"], "hook_expected_file": hook_path, "hook_node": hook,
                "external_hook": external_hook, "operation_file_node": op_file_id, "operation_node": op,
                "start_to_generated_hook": relation_list(graph, s, hook),
                "start_to_external_hook": relation_list(graph, s, external_hook),
                "start_to_operation": relation_list(graph, s, op),
                "generated_hook_to_file": relation_list(graph, hook, op_file_id),
                "generated_hook_to_operation": relation_list(graph, hook, op),
                "file_to_operation": relation_list(graph, op_file_id, op),
                "operation_to_contract": relation_list(graph, op, c),
                "resolver_class": resolver_class,
                "resolver_class_to_contract": relation_list(graph, resolver_class, c),
            }
        if row["pair"] == "Python → Rest.li":
            verb, route = row["contract_name"].split(" ", 1)
            base = route.split("?", 1)[0]
            generic = index.contract(f"{verb} {base}", row["contract_citations"]) if base != route else contract
            result["restli"] = {"exact_action_or_resource": c, "generic_collection_candidates": generic["candidates"],
                                "action_collapsed": bool(base != route and not c and generic["candidates"])}
        if row["id"] == "DH17":
            names = ("POST /openapi/v2/relationship/scroll", "POST /openapi/v3/relationship/scroll")
            result["routes_to_same_handler"] = [
                {"name": name, "id": target, "handler_to_contract": relation_list(graph, h, target)}
                for name in names for target in [index.contract(
                    name, row["contract_citations"], allow_other_files=True)["id"]]]
            result["unprefixed_route_candidates"] = index.contract(
                "POST /scroll", row["contract_citations"])["candidates"]
        full = all((s, c, h)) and "CONSUMES" in consumes and "IMPLEMENTS" in implements
        result["status"] = "fully covered" if full else "partly covered" if any((s, c, h)) else "not covered"
        result["missing"] = [name for name, value in (("caller", s), ("contract", c), ("handler", h),
                             ("start-to-contract CONSUMES", "CONSUMES" in consumes),
                             ("handler-to-contract IMPLEMENTS", "IMPLEMENTS" in implements)) if not value]
        links.append(result)
    return links


@contextmanager
def source_scope(source, files=None):
    """Constrain discovery only. Keep all builder parsers and passes intact."""
    targets = [source / rel for rel in ROOTS.values()]
    if files is not None:
        files = {source / name for name in files}
        ancestors = {parent for file in files for parent in file.parents}
    original_walk, original_rglob = os.walk, Path.rglob

    def allowed(path):
        if files is not None and path not in files and path not in ancestors:
            return False
        if not any(path.is_relative_to(root) or root.is_relative_to(path) for root in targets):
            return False
        return (not (set(part.lower() for part in path.relative_to(source).parts) & EXCLUDED)
                and not any(fnmatchcase(path.name, pattern) for pattern in IGNORE))

    def walk(top, *args, **kwargs):
        path = Path(top)
        if not path.is_relative_to(source):
            yield from original_walk(top, *args, **kwargs)
            return
        for base, dirs, names in original_walk(top, *args, **kwargs):
            dirs[:] = sorted(d for d in dirs if allowed(Path(base) / d))
            files = []
            for name in sorted(names):
                sub = Path(base) / name
                if not allowed(sub) or _NONPRODUCTION_FILENAME.search(name):
                    continue
                if sub.suffix.lower() in EXTENSIONS:
                    with sub.open(encoding="utf-8", errors="replace") as stream:
                        if _GENERATED_SOURCE_HEADER.search(stream.read(5000)):
                            continue
                files.append(name)
            yield base, dirs, files

    def rglob(path, pattern, *args, **kwargs):
        if not path.is_relative_to(source):
            yield from original_rglob(path, pattern, *args, **kwargs)
            return
        for base, _, names in walk(path):
            for name in names:
                file = Path(base) / name
                if file.match(pattern):
                    yield file

    with patch("os.walk", walk), patch.object(Path, "rglob", rglob):
        yield


def build(source):
    start = perf_counter()
    config = WorkspaceConfig(name="datahub-production-coverage", base_dir=str(source),
                             repositories=[RepoConfig(name, rel) for name, rel in ROOTS.items()],
                             exclude_nonproduction=True, ignore_patterns=list(IGNORE))
    builder = WorkspaceCKGBuilder(config)
    with (source_scope(source),
          patch.object(proto_compiler, "compile_proto_file", return_value=(None, "guarded source fallback"))):
        graph = builder.build()
    report = {name: b.get_language_report() for name,b in builder.repo_builders.items()}
    return graph, report, perf_counter() - start


def peak_memory():
    """Return Windows PeakWorkingSetSize or Unix max RSS, in bytes."""
    if os.name == "nt":
        class Counters(ctypes.Structure):
            _fields_ = [("size", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [
                (name, ctypes.c_size_t) for name in ("peak", "working", "peak_paged", "paged",
                    "peak_nonpaged", "nonpaged", "page", "peak_page")]

        values = Counters()
        values.size = ctypes.sizeof(values)
        current_process = ctypes.WinDLL("kernel32", use_last_error=True).GetCurrentProcess
        current_process.restype = ctypes.c_void_p
        memory_info = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
        memory_info.argtypes = (ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_ulong)
        if not memory_info(current_process(), ctypes.byref(values), values.size):
            raise ctypes.WinError(ctypes.get_last_error())
        return values.peak
    import resource

    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if sys.platform == "darwin" else value * 1024


def graph_facts(graph, links):
    undirected = graph.to_undirected(as_view=True)
    facts = []
    for link in links:
        s, c, h = (link[k]["id"] for k in ("caller", "contract", "handler"))
        if not all((s,c,h)):
            continue
        def hops(target):
            try:
                return nx.shortest_path_length(undirected, s, target)
            except nx.NetworkXNoPath:
                return None

        pair = [hops(c), hops(h)]
        facts.append({
            "id": link["id"], "status": link["status"], "hops_to_contract": pair[0],
            "hops_to_handler": pair[1], "gold_depth": max(pair) if None not in pair else None,
            "start_degree": graph.degree(s), "contract_degree": graph.degree(c),
            "within_two_hops_including_start": len(nx.single_source_shortest_path_length(undirected, s, cutoff=2)),
        })
    return facts


def inventory(graph):
    def language(attrs):
        path = source_path(attrs.get("file"))
        if path.endswith(".restspec.json"):
            return "Rest.li IDL"
        if attrs.get("spec") == "graphql":
            return "GraphQL"
        return EXTENSIONS.get(Path(path).suffix.lower(), "Unattributed")

    lang = {node: language(attrs) for node, attrs in graph.nodes(data=True)}
    nodes = Counter((lang[node], attrs.get("type", "unknown")) for node, attrs in graph.nodes(data=True))
    edges = Counter()
    semantic = Counter()
    for u, v, key, attrs in graph.edges(keys=True, data=True):
        relation = attrs.get("relation", "LINK")
        edges[relation, attrs.get("layer", "unknown"), lang[u], lang[v]] += 1
        if relation == "SEMANTIC_SIMILAR":
            semantic["workspace" if str(key).startswith("w_sem_") else "child"] += 1
    return {
        "nodes": graph.number_of_nodes(), "edges": graph.number_of_edges(),
        "node_counts": [{"language": l, "type": kind, "count": n} for (l, kind), n in sorted(nodes.items())],
        "edge_counts": [{"relation": r, "layer": layer, "source_language": a, "target_language": b,
                         "count": n} for (r, layer, a, b), n in sorted(edges.items())],
        "semantic_similar": dict(semantic), "budget40_fraction": min(40, len(graph)) / len(graph),
    }


XML_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def write_graphml(graph, path):
    """Serialize incrementally to avoid a second graph-sized XML tree in memory."""
    def value_type(value):
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "long"
        if isinstance(value, float):
            return "double"
        return "string"

    controls = 0
    keys = {}
    for scope, records in (("node", graph.nodes(data=True)), ("edge", graph.edges(data=True))):
        for *_, attrs in records:
            for key, value in attrs.items():
                identity = scope, key, value_type(value)
                keys.setdefault(identity, f"d{len(keys)}")

    def data_line(scope, key, value):
        nonlocal controls
        kind = value_type(value)
        if kind == "boolean":
            value = str(value).lower()
        text, n = XML_CONTROL.subn("�", str(value))
        controls += n
        return f'<data key="{keys[scope, key, kind]}">{escape(text)}</data>'

    with path.open("x", encoding="utf-8", newline="\n", buffering=1024 * 1024) as stream:
        stream.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        stream.write('<graphml xmlns="http://graphml.graphdrawing.org/xmlns">\n')
        for (scope, name, kind), key in keys.items():
            stream.write(f'<key id="{key}" for="{scope}" attr.name={quoteattr(name)} attr.type="{kind}"/>\n')
        stream.write('<graph edgedefault="directed">\n')
        for node, attrs in graph.nodes(data=True):
            data = "".join(data_line("node", k, v) for k,v in attrs.items())
            stream.write(f'<node id={quoteattr(node)}>{data}</node>\n')
        for u, v, key, attrs in graph.edges(keys=True, data=True):
            data = "".join(data_line("edge", k, v) for k,v in attrs.items())
            stream.write(f'<edge source={quoteattr(u)} target={quoteattr(v)} id={quoteattr(str(key))}>{data}</edge>\n')
        stream.write("</graph>\n</graphml>\n")
    return controls


def markdown(report):
    facts, links = report["inventory"], report["links"]
    summary = defaultdict(Counter)
    for row in links:
        summary[row["pair"]][row["status"]] += 1
    lines = ["# DataHub source-to-builder coverage audit", "",
             "This report uses source labels and graph structure only. No retrieval methods or scoring ran.", "",
             f"Pinned source `{REVISION}`. Frozen builder `egpot-bench-builder-v1` at `{BUILDER}` already "
             "contains the C++ full-body binder fix used in the DeathStarBench builds.", "",
             "[Verified source evidence v2](../../../egpot_repos/labels_draft/datahub_source_evidence_v2.md) "
             f"SHA-256 `{report['evidence_sha256']}`.", "",
             f"GraphML SHA-256 `{report['graphml_sha256']}`. "
             f"{facts['nodes']:,} nodes and {facts['edges']:,} edges. "
             f"Build time {report['build_seconds']:.2f} s. Build process peak working set "
             f"{report['build_peak_rss_bytes'] / 2**30:.2f} GiB. Budget 40 represents "
             f"{100*facts['budget40_fraction']:.5f}% of this graph.", "",
             f"GraphML serialization replaced {report['graphml_removed_invalid_xml_chars']} invalid XML "
             "characters with U+FFFD. Non-scalar attributes are serialized as strings.", "",
             "## Exact scope", ""]
    lines += markdown_table(["Namespace", "Production root"], ROOTS.items())
    lines += ["`exclude_nonproduction=True` applies to every root. "
              f"Extra basename globs are `{', '.join(IGNORE)}`. "
              f"Excluded directory components are `{', '.join(sorted(EXCLUDED))}`. "
              "Frozen test filename and first-5,000-character generated-header checks also apply. "
              "Discovery for workspace SDL and operation scans is scoped to the same allowlist.", "",
              "## Coverage by module pair", ""]
    statuses = ("fully covered", "partly covered", "not covered")
    lines += markdown_table(["Pair", *statuses], ((p, *(counts[k] for k in statuses)) for p,counts in summary.items()))
    lines += ["A fully covered row requires the exact caller, contract and handler method, "
              "with caller-to-contract CONSUMES and handler-to-contract IMPLEMENTS. "
              "Canonical contract nodes without a file attribute were matched by complete qualified name or verb and path only. "
              "The JSON records source-line offsets and ambiguous candidates. Edges were inspected only after node selection.", "",
              "## All links", ""]
    value = lambda row, key: f"`{row[key]['id']}`" if row[key]["id"] else "—"
    rels = lambda names: ", ".join(names) or "—"
    lines += markdown_table(["Link", "Caller", "Contract", "Handler", "Start → contract",
                             "Handler → contract", "Start → handler", "Coverage / missing"], (
        (r["id"],value(r,"caller"),value(r,"contract"),value(r,"handler"),rels(r["start_to_contract"]),
         rels(r["handler_to_contract"]),rels(r["direct_caller_to_handler"]),
         r["status"] + (" · " + ", ".join(r["missing"]) if r["missing"] else "")) for r in links))
    lines += ["## GraphQL operation paths", "",
              "The hook and operation were located independently from the verified operation document and generated-hook name. "
              "An external hook symbol, where present, is a fallback symbol without source provenance.", ""]
    lines += markdown_table(["Link", "Generated hook file/name", "Exact hook ID", "Start → hook / external",
                             "External hook ID", "Document", "Hook → doc / op", "Document → operation", "Operation",
                             "Operation → field", "Start → operation", "Resolver class → field"], (
        (r["id"],f"`{g['hook_expected_file']}:{g['hook_name']}`",g["hook_node"] or "—",
         f"{rels(g['start_to_generated_hook'])} / {rels(g['start_to_external_hook'])}",
         g["external_hook"] or "—",g["operation_file_node"] or "—",
         f"{rels(g['generated_hook_to_file'])} / {rels(g['generated_hook_to_operation'])}",
         rels(g["file_to_operation"]),g["operation_node"] or "—",rels(g["operation_to_contract"]),
         rels(g["start_to_operation"]),
         f"{g['resolver_class'] or '—'} · {rels(g['resolver_class_to_contract'])}")
        for r in links if "graphql" in r for g in [r["graphql"]]))
    lines += ["## Rest.li action identity", ""]
    lines += markdown_table(["Link","Exact action or resource","Collection candidates","Collapsed"],(
        (r["id"], item["exact_action_or_resource"] or "—", item["generic_collection_candidates"],
         "yes" if item["action_collapsed"] else "no")
        for r in links if "restli" in r for item in [r["restli"]]))
    routes = next(r["routes_to_same_handler"] for r in links if r["id"] == "DH17")
    lines += ["## HTTP dispatch and DH17 shared handler", "",
              "Dispatch checks follow SDK-local call edges, then look for a confirmed HTTP_CALLS to the "
              "mapped handler or a CONSUMES to the mapped contract. Tentative HTTP targets are shown separately.", ""]
    lines += markdown_table(["Link", "Found dispatch path"], (
        (r["id"], "<br>".join(" → ".join(f"`{u}` —{rel}→ `{v}`" for u,rel,v in path)
                            for path in r["http_dispatch_paths"].values()) or "—")
        for r in links if "http_dispatch_paths" in r))
    lines += markdown_table(["Route","Contract ID","Handler → contract"],(
        (route["name"],route["id"] or "—",rels(route["handler_to_contract"])) for route in routes))
    unprefixed = next(r["unprefixed_route_candidates"] for r in links if r["id"] == "DH17")
    lines += ["Unprefixed route candidates from the same contract-name index:", ""]
    lines += markdown_table(["Candidate", "Source file"], unprefixed)
    lines += ["## Depth and degree", "",
              "Depth counts raw undirected GraphML hops. Multigraph degree counts parallel edges. "
              "Rows with three independently matched nodes are shown for description even when required edges are missing.", ""]
    lines += markdown_table(["Link","Coverage","Contract hops","Handler hops","Max depth","Start degree",
                             "Contract degree","Within 2 hops including start"],(
        tuple(r[k] if r[k] is not None else "unreachable" for k in
              ("id","status","hops_to_contract","hops_to_handler","gold_depth","start_degree","contract_degree",
               "within_two_hops_including_start")) for r in report["topology"]))
    node_counts, edge_counts, lang_counts = Counter(), Counter(), Counter()
    for r in facts["node_counts"]:
        node_counts[r["type"]] += r["count"]
        lang_counts[r["language"]] += r["count"]
    for r in facts["edge_counts"]:
        edge_counts[r["relation"], r["layer"]] += r["count"]
    lines += ["## Inventory and semantic growth", ""]
    lines += markdown_table(["Node type","Count"],node_counts.most_common())
    lines += markdown_table(["Node language","Count"],lang_counts.most_common())
    lines += markdown_table(["Relation","Layer","Count"],((r,l,n) for (r,l),n in edge_counts.most_common()))
    semantic = facts["semantic_similar"]
    lines += [f"Child graphs contributed {semantic.get('child',0):,} SEMANTIC_SIMILAR edges. "
              f"The workspace pass added {semantic.get('workspace',0):,}. "
              "The JSON includes the full node-type × language and relation × source/target-language inventories. "
              "No same-scope older DataHub semantic count was available in the source recon evidence, "
              "so the growth shown here is the child-to-workspace increment.", "",
              "## Root causes and bounded recovery", "",
              "See the per-link missing elements above. The following are source-based proposals only.", ""]
    for cause in report["causes"]:
        lines.append("- " + cause)
    lines.append("")
    return "\n".join(lines)


def causes_for(links):
    graphql = [r for r in links if "graphql" in r]
    ready = [r for r in graphql if r["caller"]["id"] and r["contract"]["id"] and
             r["handler"]["id"] and "CONSUMES" in r["graphql"]["operation_to_contract"]]
    classes = sum("IMPLEMENTS" in r["graphql"]["resolver_class_to_contract"] for r in ready)
    callback_gaps = [r["id"] for r in graphql if not r["caller"]["id"] and any(
        candidate[3] == "variable" for candidate in r["caller"].get("same_file_name_candidates", ()))]
    causes = [
        "GraphQL operation discovery emits operation → field and document → operation "
        "(`graphql_links.py:218–255`). The embedded binder handles literal tags "
        "(`graphql_embedded.py:108–146`). The pinned source does not track the near-operation hook files configured in "
        "`datahub-web-react/codegen.yml:20–29`. "
        "Resolve the generated-hook name back to the checked-in operation from codegen metadata, then emit "
        "the UI caller → field CONSUMES with the operation as provenance. "
        f"{len(ready)} rows have independently matched caller, handler and field plus an existing operation → field edge. "
        "Those rows are the immediate candidates for fixing the missing start link.",
        "Java GraphQL binding emits IMPLEMENTS from the resolver class, not its get method "
        "(`graphql_java_bindings.py:89–113`). Resolve the unique DataFetcher get declaration in that same class "
        f"before adding the method edge. {classes} of the preceding candidates already have a class-edge binding. "
        "These counts are ceilings, not a measured recovery.",
        "HTTP workspace binding is evidence-gated by URL and server ownership "
        "(`graph_builder_http.py:501–572`). Spring method registration uses the class route prefix and "
        "a directly annotated method (`polyglot.py:1242–1263`). Propagate a proven SDK base URL through "
        "its request wrappers and bind inherited mappings to each concrete route. "
        "Keep provisional paths distinct from confirmed HTTP_CALLS or CONSUMES.",
        "Rest.li restspec JSON does not meet the OpenAPI filename selector (`multi_repo.py:849–854`). "
        "Read the restspec collection, verb and action identity, then match annotation registration and "
        "the literal action selector. This is the prerequisite for DH20–DH26. A collection-only edge cannot "
        "recover an action-specific gold path.",
    ]
    if callback_gaps:
        causes.insert(2, f"{', '.join(callback_gaps)} map to same-line variables for `useCallback` initializers. "
                      "The JavaScript adapter recognizes a directly assigned arrow or function expression "
                      "(`polyglot.py:541–545`). Representing the callback as a named function could recover "
                      f"the missing starts for {len(callback_gaps)} more rows, alongside both GraphQL binding changes.")
    return causes


def run():
    def git(*args, root=None):
        prefix = ["git"] if root is None else ["git","-c",f"safe.directory={root.as_posix()}","-C",str(root)]
        return subprocess.check_output([*prefix,*args],text=True).strip()

    if git("rev-parse","HEAD",root=SOURCE) != REVISION or git("status","--porcelain",root=SOURCE):
        raise ValueError("DataHub source is not clean at the pinned revision")
    paths = [":(top,glob)*.py", ":(top,exclude)eg_pot.py", "contracts/", "pyproject.toml", ":(top,glob)requirements*.txt"]
    if (git("rev-parse","egpot-bench-builder-v1") != BUILDER or
            git("diff","--name-only",BUILDER,"--",*paths)):
        raise ValueError("Builder scope differs from the frozen tag")
    output = RESULTS / "datahub_graph.graphml"
    report_paths = [RESULTS / f"datahub_coverage_report.{ext}" for ext in ("json","md")]
    if any(p.exists() for p in (output,*report_paths)):
        raise ValueError("Refusing to replace an existing DataHub artifact")
    evidence = read_evidence(EVIDENCE)
    active = True

    def audited(event,args):
        if active:
            guard(event,args)

    sys.addaudithook(audited)
    try:
        graph, build_report, duration = build(SOURCE)
        peak = peak_memory()
        links = inspect_links(graph, evidence)
        facts = inventory(graph)
        topology = graph_facts(graph, links)
    finally:
        active = False
    controls = write_graphml(graph, output)
    with output.open("rb") as stream:
        checksum = hashlib.file_digest(stream,"sha256").hexdigest()
    report = {"source": REVISION, "builder": BUILDER, "roots": ROOTS, "ignore_globs": IGNORE,
              "excluded_directory_components": sorted(EXCLUDED), "exclude_nonproduction": True,
              "build_seconds": duration, "build_peak_rss_bytes": peak,
              "builder_language_reports": build_report, "graphml_sha256": checksum,
              "graphml_removed_invalid_xml_chars": controls,
              "evidence_sha256": hashlib.sha256(EVIDENCE.read_bytes()).hexdigest(),
              "inventory": facts, "links": links, "topology": topology, "causes": causes_for(links)}
    for path, content in zip(report_paths, (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n",
                                           markdown(report)), strict=True):
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
    print(checksum, facts["nodes"], facts["edges"], duration, peak, flush=True)


if __name__ == "__main__":
    run()
