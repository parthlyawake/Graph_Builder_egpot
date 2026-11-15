"""
GRAFT-CKG Multi-Repository Workspace Composition Engine (Phase 3).

Orchestrates multi-repository code knowledge graph construction, canonical
contract unification, cross-repository HTTP and gRPC resolution, and
multi-repo defect / contract skew detection.

Key Architectural Guarantees:
  1. Strict node namespacing (<repo_id>/<rel_path>:<qualname>) ensuring 0 ID collisions.
  2. Canonical contract unification across vendored protobuf schemas.
  3. SHA-256 schema hashing with automatic CONTRACT_SKEW defect detection.
  4. Cross-repository HTTP_CALLS and gRPC CONSUMES/IMPLEMENTS linkage.
  5. Multi-repo semantic plane (Lsem) indexing and subtree context grafting.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Ensure current directory is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from graft_ckg import CKGBuilder, HyperEdgeMetadata
from semantic_neighbors import sparse_semantic_pairs

try:
    from rank_bm25 import BM25Okapi
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False


@dataclass
class RepoConfig:
    id: str
    path: str
    language: Optional[str] = None
    role: Optional[str] = None


@dataclass
class WorkspaceConfig:
    name: str = "workspace"
    version: str = "1.0"
    base_dir: str = "."
    repositories: List[RepoConfig] = field(default_factory=list)
    shared_contracts: List[str] = field(default_factory=list)
    ignore_patterns: List[str] = field(default_factory=list)
    strict_http_source_evidence: bool = False  # opt-in: disable hostless path-only HTTP matches

    @classmethod
    def from_file(cls, config_path: str) -> "WorkspaceConfig":
        config_path = os.path.abspath(config_path)
        base_dir = os.path.dirname(config_path)
        with open(config_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        data: Dict[str, Any] = {}
        if config_path.endswith((".yaml", ".yml")):
            try:
                import yaml
                data = yaml.safe_load(raw_text) or {}
            except ImportError:
                data = cls._parse_simple_yaml(raw_text)
        else:
            data = json.loads(raw_text)

        return cls.from_dict(data, base_dir)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], base_dir: str = ".") -> "WorkspaceConfig":
        repos: List[RepoConfig] = []
        for r in data.get("repositories", []):
            if isinstance(r, dict):
                repos.append(RepoConfig(
                    id=r.get("id", os.path.basename(r.get("path", ""))),
                    path=r.get("path", ""),
                    language=r.get("language"),
                    role=r.get("role"),
                ))
            elif isinstance(r, str):
                repos.append(RepoConfig(id=os.path.basename(r), path=r))

        return cls(
            name=data.get("name", "workspace"),
            version=str(data.get("version", "1.0")),
            base_dir=base_dir,
            repositories=repos,
            shared_contracts=data.get("shared_contracts", []),
            ignore_patterns=data.get("ignore_patterns", []),
            strict_http_source_evidence=data.get("strict_http_source_evidence") is True,
        )

    @staticmethod
    def _parse_simple_yaml(text: str) -> Dict[str, Any]:
        """Lightweight YAML parser fallback when PyYAML is unavailable."""
        result: Dict[str, Any] = {"repositories": [], "shared_contracts": [], "ignore_patterns": []}
        current_section = None
        current_repo: Optional[Dict[str, Any]] = None

        for line in text.splitlines():
            line_str = line.split("#")[0].rstrip()
            if not line_str:
                continue
            stripped = line_str.strip()

            if stripped.startswith("name:"):
                result["name"] = stripped.split(":", 1)[1].strip().strip('"\'')
            elif stripped.startswith("version:"):
                result["version"] = stripped.split(":", 1)[1].strip().strip('"\'')
            elif stripped == "repositories:":
                current_section = "repositories"
            elif stripped == "shared_contracts:":
                current_section = "shared_contracts"
            elif stripped == "ignore_patterns:":
                current_section = "ignore_patterns"
            elif current_section == "repositories":
                if stripped.startswith("- "):
                    if current_repo:
                        result["repositories"].append(current_repo)
                    current_repo = {}
                    item = stripped[2:].strip()
                    if ":" in item:
                        k, v = item.split(":", 1)
                        current_repo[k.strip()] = v.strip().strip('"\'')
                elif ":" in stripped and current_repo is not None:
                    k, v = stripped.split(":", 1)
                    current_repo[k.strip()] = v.strip().strip('"\'')
            elif current_section in ("shared_contracts", "ignore_patterns"):
                if stripped.startswith("- "):
                    val = stripped[2:].strip().strip('"\'')
                    result[current_section].append(val)

        if current_repo:
            result["repositories"].append(current_repo)
        return result


class WorkspaceCKGBuilder:
    """Polyglot Multi-Repository Code Knowledge Graph Builder.

    Coordinates per-repository CKG builders, enforces global node namespacing,
    stitches canonical contract nodes with SHA-256 skew detection, and resolves
    cross-repository RPCs and REST HTTP dependencies.
    """

    def __init__(self, config_or_path: WorkspaceConfig | str | dict):
        if isinstance(config_or_path, WorkspaceConfig):
            self.config = config_or_path
        elif isinstance(config_or_path, str):
            self.config = WorkspaceConfig.from_file(config_or_path)
        elif isinstance(config_or_path, dict):
            self.config = WorkspaceConfig.from_dict(config_or_path)
        else:
            raise TypeError(f"Invalid config type: {type(config_or_path)}")

        self.graph = nx.MultiDiGraph()
        self.repo_builders: Dict[str, CKGBuilder] = {}
        self.canonical_contracts: Dict[str, Dict[str, Any]] = {}
        self.contract_skews: List[Dict[str, Any]] = []
        self.http_endpoints: Dict[Tuple[str, str], List[str]] = {}
        self.symbols_by_name: Dict[str, List[str]] = {}
        self.docstrings: Dict[str, str] = {}
        self.raw_file_lines: Dict[str, List[str]] = {}
        self.total_loc: int = 0
        self.edge_counter: int = 0

        # RAG index structures
        self.vectorizer = None
        self.tfidf_matrix = None
        self.indexed_node_ids: List[str] = []
        self.bm25_index = None

    @property
    def proto_services(self) -> Dict[str, Any]:
        return self.canonical_contracts

    @property
    def unresolved_contract_calls(self) -> List[Any]:
        calls = []
        for b in self.repo_builders.values():
            calls.extend(b.unresolved_contract_calls)
        return calls

    @property
    def http_calls_to_resolve(self) -> List[Any]:
        calls = []
        for b in self.repo_builders.values():
            calls.extend(b.http_calls_to_resolve)
        return calls

    @property
    def recorded_attr_calls(self) -> List[Any]:
        calls = []
        for b in self.repo_builders.values():
            calls.extend(b.recorded_attr_calls)
        return calls

    @property
    def grpc_client_vars(self) -> Dict[str, Any]:
        vars_map = {}
        for b in self.repo_builders.values():
            vars_map.update(b.grpc_client_vars)
        return vars_map

    def _resolve_path(self, rel_or_abs: str) -> str:
        if os.path.isabs(rel_or_abs):
            return rel_or_abs
        return os.path.normpath(os.path.join(self.config.base_dir, rel_or_abs))

    @staticmethod
    def _match_rpc_case(contract: Dict[str, Any], name: str) -> Optional[str]:
        """Match an RPC name case-insensitively (JS uses camelCase handlers)."""
        if "rpcs" in contract:
            if name in contract["rpcs"]:
                return contract["rpcs"][name]
            lowered = name.lower()
            for rpc_name, rpc_id in contract["rpcs"].items():
                if rpc_name.lower() == lowered:
                    return rpc_id
        return None

    def _contract_node_id(self, name: str) -> Optional[str]:
        """Resolve 'Service' or 'Service.Rpc' (case-insensitive rpc) to a canonical node id."""
        if name in self.graph and self.graph.nodes[name].get("type") in {"service_contract", "rpc_contract"}:
            return name
        candidate = name if name.startswith("contract::") else f"contract::{name}"
        if candidate in self.graph:
            return candidate
        if "." in candidate:
            service, _, rpc = candidate.rpartition(".")
            contract = self.proto_services.get(service.split("::", 1)[-1])
            if contract:
                matched = self._match_rpc_case(contract, rpc)
                if matched:
                    return matched
        return None

    def build(self) -> nx.MultiDiGraph:
        """Construct the unified multi-repository hyper-relational CKG."""
        print(f"[*] Initializing GRAFT-CKG Workspace: '{self.config.name}' (v{self.config.version})")
        print(f"[*] Repositories to index: {len(self.config.repositories)}")

        # A second build must not accumulate stale contracts or duplicate edges.
        self.graph.clear()
        self.repo_builders.clear()
        self.canonical_contracts.clear()
        self.contract_skews.clear()
        self.http_endpoints.clear()
        self.symbols_by_name.clear()
        self.docstrings.clear()
        self.raw_file_lines.clear()
        self.total_loc = 0
        self.edge_counter = 0
        self.vectorizer = self.tfidf_matrix = self.bm25_index = None
        self.indexed_node_ids = []

        t0 = time.perf_counter()

        # Step 1: Parse and build each repository graph with strict repo_id namespacing
        for repo_cfg in self.config.repositories:
            repo_full_path = self._resolve_path(repo_cfg.path)
            print(f"[*] ---> Building repository '{repo_cfg.id}' at: {repo_full_path}")
            if not os.path.isdir(repo_full_path):
                print(f"[!] Warning: Repository path does not exist: {repo_full_path}")
                continue

            builder = CKGBuilder(repo_full_path, repo_id=repo_cfg.id)
            if self.config.ignore_patterns:
                builder.ignore_patterns.extend(self.config.ignore_patterns)
            builder.build()
            self.repo_builders[repo_cfg.id] = builder

            # Aggregate statistics and registries
            self.total_loc += builder.total_loc
            for k, lines in builder.raw_file_lines.items():
                self.raw_file_lines[f"{repo_cfg.id}/{k}"] = lines
            for sym, nids in builder.symbols_by_name.items():
                self.symbols_by_name.setdefault(sym, []).extend(nids)
            for nid, doc in builder.docstrings.items():
                self.docstrings[nid] = doc

            # Register HTTP endpoints
            for (m, path), fids in builder.http_endpoints.items():
                self.http_endpoints.setdefault((m, path), []).extend(fids)

        # Step 2: Index shared contracts if configured
        self._index_shared_contracts()

        # Step 3: Compose individual repository multigraphs
        print("[*] Composing repository graphs into unified multi-repo topology...")
        for repo_id, builder in self.repo_builders.items():
            for n, d in builder.graph.nodes(data=True):
                if n not in self.graph:
                    self.graph.add_node(n, **d)
                else:
                    curr = self.graph.nodes[n]
                    if "definitions" in d:
                        curr.setdefault("definitions", []).extend(d["definitions"])

            for u, v, k, d in builder.graph.edges(keys=True, data=True):
                global_k = f"w_{repo_id}_{k}"
                self.graph.add_edge(u, v, key=global_k, **d)

        # Step 4: Unify canonical contract layer (Lcontract) & check for CONTRACT_SKEW
        self._unify_contract_layer()

        # Step 5: Resolve cross-repository gRPC server implementation bindings (producers)
        self._resolve_cross_repo_grpc_producers()
        from graph_builder_bindings import bind_managed_grpc
        for builder in self.repo_builders.values():
            bind_managed_grpc(builder, self.graph, self.canonical_contracts)

        # Step 6: Resolve cross-repository HTTP dependency calls
        self._resolve_cross_repo_http_calls()

        # Step 7: Resolve cross-repository unresolved gRPC calls (consumers)
        self._resolve_cross_repo_grpc_calls()

        # Step 8: Resolve cross-repository proto type identity (P8)
        self._resolve_cross_repo_proto_types()

        # Step 8b: Bind typed Thrift C++ clients and interface handlers.
        # This is source-evidenced and independent of any example repository.
        from thrift_bindings import bind_thrift_runtime
        self.thrift_bindings = bind_thrift_runtime(
            self.graph, self.repo_builders.values())

        # Step 9: Resolve inter-service dataflow through contract RPCs (P4)
        self._resolve_inter_service_dataflow()

        # Source-evidenced AMQP broker topology connects publish contracts to queues.
        from message_topology import bind_amqp_topology
        self.amqp_topology = bind_amqp_topology(
            self.graph, self.repo_builders.values())

        # Step 10: Index OpenAPI and GraphQL contract specs (P5)
        self._index_openapi_and_graphql()
        self._resolve_graphql_java_bindings()
        self._index_graphql_operations()

        # Typed Kafka payload links require unique Avro/PDL schema identities.
        from kafka_schema_links import bind_kafka_payload_schemas
        self.kafka_schema_links = bind_kafka_payload_schemas(
            self.graph, self.repo_builders.values())

        # Step 11: Build workspace-level Semantic Layer (Lsem)
        self._build_semantic_layer()

        elapsed = time.perf_counter() - t0
        kloc = self.total_loc / 1000.0 if self.total_loc else 0.001
        throughput = elapsed / kloc

        print(f"[*] Workspace Construction Complete:")
        print(f"    - Repositories:    {len(self.repo_builders)}")
        print(f"    - Total LOC:       {self.total_loc}")
        print(f"    - Graph Nodes:     {self.graph.number_of_nodes()}")
        print(f"    - Hyper-Edges:     {self.graph.number_of_edges()}")
        print(f"    - Build Latency:   {elapsed:.3f}s ({throughput:.4f} s/kLOC)")
        print(f"    - Contract Skews:  {len(self.contract_skews)}")
        self._print_layer_statistics()

        return self.graph

    def update_files(self, repo_id, changed_rel_paths, deleted_rel_paths=()):
        """Reparse only changed source files; recompose workspace relations."""
        from workspace_incremental import update_workspace_files
        return update_workspace_files(self, repo_id, changed_rel_paths, deleted_rel_paths)

    def _index_shared_contracts(self):
        """Parse standalone protobuf files declared in shared_contracts."""
        for contract_entry in self.config.shared_contracts:
            contract_full = self._resolve_path(contract_entry)
            if os.path.isfile(contract_full) and contract_full.endswith(".proto"):
                self._parse_single_shared_proto(contract_full)
            elif os.path.isdir(contract_full):
                for root, _, files in os.walk(contract_full):
                    for f in sorted(files):
                        if f.endswith(".proto"):
                            self._parse_single_shared_proto(os.path.join(root, f))

    def _parse_single_shared_proto(self, proto_path: str):
        from proto_parser import ProtoParser
        with open(proto_path, "rb") as f:
            raw = f.read()
        p_hash = hashlib.sha256(raw).hexdigest()
        rel_path = os.path.relpath(proto_path, self.config.base_dir).replace("\\", "/")
        file_id = f"file::shared/{rel_path}"

        self.graph.add_node(
            file_id,
            id=file_id,
            type="file",
            layer="Lsyn",
            name=os.path.basename(proto_path),
            file=rel_path,
            repo="shared_contracts",
            line_no=1,
            code=f"// Shared proto contract: {rel_path}",
        )

        from proto_compiler import compile_proto_file
        pf, parser_mode = compile_proto_file(proto_path, self.config.base_dir)
        if pf is None:
            pf = ProtoParser.parse_text(raw.decode("utf-8", errors="replace"))
        self.graph.graph.setdefault("proto_parse_modes", {})[rel_path] = (
            parser_mode if parser_mode == "protoc" else "source_fallback"
        )

        # Register message types (P8)
        for msg_name, msg_obj in pf.messages.items():
            msg_id = f"contract::message::{msg_name}"
            if not self.graph.has_node(msg_id):
                field_names = [f.name for f in msg_obj.fields.values()]
                self.graph.add_node(
                    msg_id, id=msg_id, type="contract", layer="Lcontract",
                    name=msg_name, file=rel_path, repo="shared_contracts",
                    code=f"message {msg_name} {{ " + ", ".join(field_names) + " }}"
                )
            self.graph.add_edge(file_id, msg_id, key=f"e_sh_{file_id}_{msg_id}", relation="CONTAINS", layer="Lsyn")
            from proto_field_graph import emit_message_fields
            emit_message_fields(self.graph, msg_id, msg_obj, file_path=rel_path)

        for service_name, s_obj in pf.services.items():
            service_id = f"contract::{service_name}"
            if not self.graph.has_node(service_id):
                self.graph.add_node(service_id, id=service_id, type="service_contract", layer="Lcontract", name=service_name)
            self.graph.nodes[service_id].setdefault("definitions", []).append({
                "file": rel_path,
                "file_id": file_id,
                "repo_id": "shared_contracts",
                "sha256": p_hash,
            })
            self.graph.add_edge(file_id, service_id, key=f"e_sh_{file_id}_{service_id}", relation="CONTAINS", layer="Lsyn")

            rpcs = {}
            for rpc_name, rpc_obj in s_obj.rpcs.items():
                req = rpc_obj.request_type
                resp = rpc_obj.response_type
                rpc_id = f"contract::{service_name}.{rpc_name}"
                if not self.graph.has_node(rpc_id):
                    self.graph.add_node(rpc_id, id=rpc_id, type="rpc_contract", layer="Lcontract", name=rpc_name)
                self.graph.nodes[rpc_id]["request_type"] = req
                self.graph.nodes[rpc_id]["response_type"] = resp
                self.graph.nodes[rpc_id].setdefault("definitions", []).append({
                    "file": rel_path,
                    "file_id": file_id,
                    "repo_id": "shared_contracts",
                    "sha256": p_hash,
                    "request_type": req,
                    "response_type": resp,
                })
                self.graph.add_edge(service_id, rpc_id, key=f"e_sh_{service_id}_{rpc_id}", relation="DEFINES_RPC", layer="Lcontract")

                req_msg_id = f"contract::message::{req}"
                if self.graph.has_node(req_msg_id):
                    self.graph.add_edge(req_msg_id, rpc_id, key=f"e_sh_use_{req}_{rpc_id}", relation="USES", layer="Ldep")
                from proto_field_graph import emit_rpc_message_types
                emit_rpc_message_types(self.graph, rpc_id, req, resp)

                rpcs[rpc_name] = rpc_id

            self.canonical_contracts[service_name] = {
                "node_id": service_id,
                "rpcs": rpcs,
                "file": rel_path,
                "file_id": file_id,
                "repo_id": "shared_contracts",
                "sha256": p_hash,
            }

    def _unify_contract_layer(self):
        """Merges contract nodes across repositories and detects CONTRACT_SKEW."""
        service_definitions: Dict[str, List[Dict[str, Any]]] = {}

        for repo_id, builder in self.repo_builders.items():
            for s_name, s_info in builder.proto_services.items():
                service_definitions.setdefault(s_name, []).append({
                    "repo_id": repo_id,
                    "file": s_info.get("file"),
                    "file_id": s_info.get("file_id"),
                    "sha256": s_info.get("sha256"),
                    "signatures": s_info.get("signatures", {}),
                    "rpcs": s_info.get("rpcs", {}),
                })
                if s_name not in self.canonical_contracts:
                    self.canonical_contracts[s_name] = dict(s_info)
                else:
                    self.canonical_contracts[s_name]["rpcs"].update(s_info.get("rpcs", {}))

        for s_name, defs in service_definitions.items():
            if len(defs) <= 1:
                continue

            unique_hashes = {d["sha256"] for d in defs if d.get("sha256")}
            unique_signatures = {}
            for d in defs:
                r_id = d["repo_id"]
                for rpc, sig in d.get("signatures", {}).items():
                    sig_str = f"({sig.get('request')}) -> ({sig.get('response')})"
                    unique_signatures.setdefault(rpc, {})[r_id] = sig_str

            is_skewed = len(unique_hashes) > 1
            skew_details = []

            for rpc, repo_sigs in unique_signatures.items():
                distinct_sigs = set(repo_sigs.values())
                if len(distinct_sigs) > 1:
                    is_skewed = True
                    skew_details.append(f"RPC '{rpc}' signature divergence: {repo_sigs}")

            service_node = f"contract::{s_name}"
            if is_skewed:
                skew_record = {
                    "type": "CONTRACT_SKEW",
                    "severity": "CRITICAL",
                    "service": s_name,
                    "contract_node": service_node,
                    "versions": {d["repo_id"]: d["sha256"] for d in defs},
                    "files": {d["repo_id"]: d["file"] for d in defs},
                    "details": skew_details or ["Vendored .proto file content hashes differ."],
                    "message": f"Contract schema skew detected for '{s_name}' across repositories: {[d['repo_id'] for d in defs]}",
                }
                self.contract_skews.append(skew_record)
                if self.graph.has_node(service_node):
                    self.graph.nodes[service_node]["skew"] = True
                    self.graph.nodes[service_node]["skew_details"] = skew_record
                print(f"[!] Warning: {skew_record['message']}")

    def _resolve_cross_repo_grpc_producers(self):
        """Binds server handlers across repositories to canonical contract nodes (IMPLEMENTS)."""
        resolved = 0

        def _already_bound(src: str, tgt: str) -> bool:
            return any(
                v == tgt and d.get("relation") == "IMPLEMENTS"
                for _, v, d in self.graph.out_edges(src, data=True)
            )

        for repo_id, builder in self.repo_builders.items():
            # 1. Python, Java, C# servicers: class inheriting from <Service>Servicer / ImplBase / ServiceBase
            subclasses_of = {}
            for sub_id, bases in builder.class_bases.items():
                for base_id in bases:
                    subclasses_of.setdefault(base_id, []).append(sub_id)

            def _descendants(cid, seen=None):
                seen = seen or set()
                for sub in subclasses_of.get(cid, []):
                    if sub not in seen:
                        seen.add(sub)
                        _descendants(sub, seen)
                return seen

            for class_id, service_name, file in builder.grpc_servicer_records:
                contract = self.canonical_contracts.get(service_name)
                if not contract:
                    continue
                # Add IMPLEMENTS edge from class to service contract node
                if class_id in self.graph and contract.get("node_id") in self.graph:
                    e_key = f"w_impl_{class_id}_{contract['node_id']}"
                    if not _already_bound(class_id, contract["node_id"]):
                        self.graph.add_edge(
                            class_id,
                            contract["node_id"],
                            key=e_key,
                            relation="IMPLEMENTS",
                            layer="Lcontract",
                        )
                        resolved += 1

                for rpc_name, rpc_id in contract.get("rpcs", {}).items():
                    for impl_class in [class_id, *sorted(_descendants(class_id))]:
                        candidates_to_try = [
                            f"{impl_class}.{rpc_name}",
                            f"{impl_class}.{rpc_name[0].lower()}{rpc_name[1:]}",
                            f"{impl_class}.{rpc_name.lower()}",
                        ]
                        for direct in candidates_to_try:
                            if direct in self.graph and self.graph.nodes[direct].get("type") in ("function", "method"):
                                e_key = f"w_impl_{direct}_{rpc_id}"
                                if not _already_bound(direct, rpc_id):
                                    self.graph.add_edge(
                                        direct,
                                        rpc_id,
                                        key=e_key,
                                        relation="IMPLEMENTS",
                                        layer="Lcontract",
                                    )
                                    resolved += 1
                                break

            # 2. Go servers: pb.Register<Service>Server(srv, impl)
            for service_name, impl_arg, file, scope_id in builder.grpc_server_registrations:
                contract = self.canonical_contracts.get(service_name)
                if not contract:
                    continue
                impl_type = (impl_arg or "").strip("&").strip()
                impl_type = builder.go_type_vars.get(file, {}).get(impl_type, impl_type)
                impl_id = f"{builder.repo_prefix}{file}:{impl_type}"
                if impl_id not in builder.graph:
                    candidates = [
                        nid for nid in builder.symbols_by_name.get(impl_type, [])
                        if builder.graph.nodes[nid].get("type") in ("class", "interface")
                    ]
                    if len(candidates) == 1:
                        impl_id = candidates[0]

                if impl_id in self.graph and contract.get("node_id") in self.graph:
                    e_key = f"w_impl_{impl_id}_{contract['node_id']}"
                    if not _already_bound(impl_id, contract["node_id"]):
                        self.graph.add_edge(
                            impl_id,
                            contract["node_id"],
                            key=e_key,
                            relation="IMPLEMENTS",
                            layer="Lcontract",
                        )
                        resolved += 1

                for rpc_name, rpc_id in contract.get("rpcs", {}).items():
                    method_id = builder._find_method(impl_id, rpc_name)
                    if not method_id:
                        for m_cand in builder.symbols_by_name.get(rpc_name, []):
                            if m_cand.startswith(f"{impl_id}."):
                                method_id = m_cand
                                break
                    if method_id and method_id in self.graph:
                        e_key = f"w_impl_{method_id}_{rpc_id}"
                        if not _already_bound(method_id, rpc_id):
                            self.graph.add_edge(
                                method_id,
                                rpc_id,
                                key=e_key,
                                relation="IMPLEMENTS",
                                layer="Lcontract",
                            )
                            resolved += 1

            # 3. JS servers: server.addService(pkg.<Service>.service, {rpc: handler})
            for service_name, handlers, file, scope_id in builder.js_add_service_records:
                contract = self.canonical_contracts.get(service_name)
                if not contract:
                    continue
                if scope_id in self.graph and contract.get("node_id") in self.graph:
                    e_key = f"w_impl_{scope_id}_{contract['node_id']}"
                    if not _already_bound(scope_id, contract["node_id"]):
                        self.graph.add_edge(
                            scope_id,
                            contract["node_id"],
                            key=e_key,
                            relation="IMPLEMENTS",
                            layer="Lcontract",
                        )
                        resolved += 1

                for rpc_key, handler_expr in handlers.items():
                    rpc_id = CKGBuilder._match_rpc_case(contract, rpc_key)
                    if not rpc_id:
                        continue
                    target_ids = builder._resolve_reference(file, handler_expr)
                    for tid in target_ids:
                        if tid in self.graph:
                            e_key = f"w_impl_{tid}_{rpc_id}"
                            if not _already_bound(tid, rpc_id):
                                self.graph.add_edge(
                                    tid,
                                    rpc_id,
                                    key=e_key,
                                    relation="IMPLEMENTS",
                                    layer="Lcontract",
                                )
                                resolved += 1

        if resolved:
            print(f"[*] Cross-Repository gRPC Producer Resolution: {resolved} cross-service producer bindings created.")

    def _resolve_cross_repo_http_calls(self):
        """Resolve source-evidenced and unique cross-repository HTTP calls."""
        from graph_builder_http import resolve_workspace_http
        return resolve_workspace_http(self)

    def _resolve_cross_repo_grpc_calls(self):
        """Binds stub calls in Repo A to contracts declared in Repo B or shared contracts."""
        resolved = 0
        for caller_repo_id, builder in self.repo_builders.items():
            for caller_id, service_name, method, id_ctx in builder.unresolved_contract_calls:
                contract = self.canonical_contracts.get(service_name)
                if not contract:
                    continue
                rpc_id = CKGBuilder._match_rpc_case(contract, method)
                if rpc_id and self.graph.has_node(rpc_id):
                    bound = any(
                        v == rpc_id and d.get("relation") == "CONSUMES"
                        for _, v, d in self.graph.out_edges(caller_id, data=True)
                    )
                    if not bound:
                        meta = HyperEdgeMetadata(d_scope=0, f_call=1.0, c_type=1.0, id_ctx=id_ctx)
                        e_id = f"w_grpc_{caller_id}_{rpc_id}"
                        self.graph.add_edge(
                            caller_id,
                            rpc_id,
                            key=e_id,
                            relation="CONSUMES",
                            layer="Lcontract",
                            metadata=meta.to_dict(),
                            d_scope=meta.d_scope,
                            f_call=meta.f_call,
                            c_type=meta.c_type,
                            id_ctx=meta.id_ctx,
                        )
                        resolved += 1
        if resolved:
            print(f"[*] Cross-Repository gRPC Resolution: {resolved} cross-service consumer bindings created.")

    def _resolve_cross_repo_proto_types(self):
        """P8: Binds cross-language type declarations to canonical proto message contracts."""
        resolved = 0
        proto_msg_nodes = [
            (n, d.get("name", n.split("::")[-1]))
            for n, d in self.graph.nodes(data=True)
            if n.startswith("contract::message::")
        ]
        if not proto_msg_nodes:
            return

        for msg_id, msg_name in proto_msg_nodes:
            for repo_id, builder in self.repo_builders.items():
                cands = [
                    nid for nid in builder.symbols_by_name.get(msg_name, [])
                    if builder.graph.has_node(nid) and builder.graph.nodes[nid].get("type") in ("class", "struct", "type")
                ]
                for cid in cands:
                    if cid in self.graph:
                        e_key = f"w_type_impl_{cid}_{msg_id}"
                        if not self.graph.has_edge(cid, msg_id, key=e_key):
                            meta = HyperEdgeMetadata(d_scope=0, f_call=1.0, c_type=1.0, id_ctx=repo_id)
                            self.graph.add_edge(
                                cid,
                                msg_id,
                                key=e_key,
                                relation="IMPLEMENTS",
                                layer="Lcontract",
                                metadata=meta.to_dict(),
                                d_scope=0,
                                f_call=1.0,
                                c_type=1.0,
                                id_ctx=repo_id,
                            )
                            resolved += 1
        if resolved:
            print(f"[*] Cross-Language Proto Type Identity: {resolved} type-to-contract bindings established.")

    def _resolve_inter_service_dataflow(self):
        """P4: Emits Lflow edges across service boundaries via canonical contract RPC nodes.
        
        Caller -[PASSES_ARG]-> RPC -[FLOWS_TO]-> Handler
        Handler -[RETURNS]-> RPC -[FLOWS_TO]-> Caller
        """
        resolved = 0
        canonical_rpcs = [
            n for n in self.graph.nodes
            if self.graph.nodes[n].get("type") == "rpc_contract" or (n.startswith("contract::") and "." in n and not n.startswith("contract::http:"))
        ]
        for rpc_id in canonical_rpcs:
            callers = [
                u for u, v, d in self.graph.in_edges(rpc_id, data=True)
                if d.get("relation") == "CONSUMES"
            ]
            handlers = [
                u for u, v, d in self.graph.in_edges(rpc_id, data=True)
                if d.get("relation") == "IMPLEMENTS"
            ]
            for u in callers:
                # Caller passes argument to RPC contract
                e_pass = f"w_flow_arg_{u}_{rpc_id}"
                if not self.graph.has_edge(u, rpc_id, key=e_pass):
                    meta = HyperEdgeMetadata(d_scope=0, f_call=1.0, c_type=1.0, id_ctx="cross_repo")
                    self.graph.add_edge(
                        u, rpc_id, key=e_pass, relation="PASSES_ARG", layer="Lflow",
                        metadata=meta.to_dict(), d_scope=0, f_call=1.0, c_type=1.0, id_ctx="cross_repo"
                    )
                    resolved += 1
                # Contract response flows back to caller
                e_resp = f"w_flow_resp_{rpc_id}_{u}"
                if not self.graph.has_edge(rpc_id, u, key=e_resp):
                    meta = HyperEdgeMetadata(d_scope=0, f_call=1.0, c_type=1.0, id_ctx="cross_repo")
                    self.graph.add_edge(
                        rpc_id, u, key=e_resp, relation="FLOWS_TO", layer="Lflow",
                        metadata=meta.to_dict(), d_scope=0, f_call=1.0, c_type=1.0, id_ctx="cross_repo"
                    )
                    resolved += 1
            for h in handlers:
                # Contract request flows into handler
                e_hflow = f"w_flow_req_{rpc_id}_{h}"
                if not self.graph.has_edge(rpc_id, h, key=e_hflow):
                    meta = HyperEdgeMetadata(d_scope=0, f_call=1.0, c_type=1.0, id_ctx="cross_repo")
                    self.graph.add_edge(
                        rpc_id, h, key=e_hflow, relation="FLOWS_TO", layer="Lflow",
                        metadata=meta.to_dict(), d_scope=0, f_call=1.0, c_type=1.0, id_ctx="cross_repo"
                    )
                    resolved += 1
                # Handler returns to contract
                e_hret = f"w_flow_ret_{h}_{rpc_id}"
                if not self.graph.has_edge(h, rpc_id, key=e_hret):
                    meta = HyperEdgeMetadata(d_scope=0, f_call=1.0, c_type=1.0, id_ctx="cross_repo")
                    self.graph.add_edge(
                        h, rpc_id, key=e_hret, relation="RETURNS", layer="Lflow",
                        metadata=meta.to_dict(), d_scope=0, f_call=1.0, c_type=1.0, id_ctx="cross_repo"
                    )
                    resolved += 1
        if resolved:
            print(f"[*] Inter-Service Dataflow: {resolved} cross-service Lflow edges established.")

    def _index_openapi_and_graphql(self):
        """P5: Extends Lcontract with OpenAPI REST endpoints and GraphQL schemas."""
        from openapi_graphql_parser import OpenAPIContractParser, GraphQLContractParser
        base_dir = self.config.base_dir if hasattr(self.config, "base_dir") else "."
        for root, _, files in os.walk(base_dir):
            if any(p in root for p in ("node_modules", ".git", ".pytest_cache", "tmp")):
                continue
            for f in files:
                f_path = os.path.join(root, f)
                rel_f = os.path.relpath(f_path, base_dir).replace("\\", "/")
                # OpenAPI
                if f.lower() in ("openapi.yaml", "openapi.json", "swagger.yaml", "swagger.json") or (
                    (f.endswith(".yaml") or f.endswith(".json")) and "openapi" in f.lower()
                ):
                    spec = OpenAPIContractParser.parse_file(f_path)
                    if spec and spec.operations:
                        file_id = f"file::{rel_f}"
                        if not self.graph.has_node(file_id):
                            self.graph.add_node(file_id, id=file_id, type="file", layer="Lsyn", name=f, file=rel_f, line_no=1)
                        for op in spec.operations:
                            ep_id = f"endpoint::{op.method}::{op.path}"
                            if not self.graph.has_node(ep_id):
                                self.graph.add_node(
                                    ep_id, id=ep_id, type="endpoint", layer="Lcontract",
                                    name=f"{op.method} {op.path}", path=op.path, method=op.method,
                                    operation_id=op.operation_id, spec="openapi"
                                )
                                self.graph.add_edge(file_id, ep_id, key=f"e_api_{file_id}_{ep_id}", relation="CONTAINS", layer="Lsyn")
                            from contract_schema_graph import emit_openapi_schema_edges
                            emit_openapi_schema_edges(self.graph, ep_id, op)
                            handlers = list(dict.fromkeys([
                                *self.http_endpoints.get((op.method, op.path), []),
                                *self.http_endpoints.get(("*", op.path), []),
                            ]))
                            for hid in handlers:
                                if hid in self.graph and not self.graph.has_edge(hid, ep_id):
                                    self.graph.add_edge(hid, ep_id, key=f"w_api_impl_{hid}_{ep_id}", relation="IMPLEMENTS", layer="Lcontract")

                # GraphQL
                elif f.endswith((".graphql", ".gql")):
                    try:
                        with open(f_path, "r", encoding="utf-8", errors="replace") as gfile:
                            g_text = gfile.read()
                        g_spec = GraphQLContractParser.parse_text(g_text)
                        if g_spec and g_spec.root_types:
                            self.graph.graph.setdefault("graphql_root_types", {}).update(
                                g_spec.root_types)
                        if g_spec and g_spec.types:
                            file_id = f"file::{rel_f}"
                            if not self.graph.has_node(file_id):
                                self.graph.add_node(file_id, id=file_id, type="file", layer="Lsyn", name=f, file=rel_f, line_no=1)
                            for tname, gtype in g_spec.types.items():
                                for fname, fobj in gtype.fields.items():
                                    gql_id = f"contract::graphql::{tname}::{fname}"
                                    if not self.graph.has_node(gql_id):
                                        self.graph.add_node(
                                            gql_id, id=gql_id, type="contract", layer="Lcontract",
                                            name=f"{tname}.{fname}", kind=gtype.kind.lower(),
                                            field=fname, return_type=fobj.type_name, spec="graphql"
                                        )
                                        self.graph.add_edge(file_id, gql_id, key=f"e_gql_{file_id}_{gql_id}", relation="CONTAINS", layer="Lsyn")
                    except Exception:
                        pass

    def _resolve_graphql_java_bindings(self):
        """Link explicit Java RuntimeWiring DataFetchers to known schema fields."""
        from graphql_java_bindings import bind_java_graphql_datafetchers
        return bind_java_graphql_datafetchers(self)

    def _index_graphql_operations(self):
        """Attach GraphQL document operation nodes to discovered schema roots."""
        from graphql_links import link_graphql_operations
        return link_graphql_operations(self, self.config.base_dir)

    def _build_semantic_layer(self, similarity_threshold: float = 0.60):
        """Constructs the unified Lsem semantic similarity plane across all repositories."""
        print("[*] Computing Workspace-Level Semantic Layer (Lsem)...")
        indexed_nodes = []
        corpus = []

        for nid, data in self.graph.nodes(data=True):
            ntype = data.get("type")
            if ntype in {"function", "class", "module", "service_contract", "rpc_contract"}:
                doc = data.get("docstring", "")
                name = data.get("name", "")
                code = data.get("code", "")
                split_name = " ".join(re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)", name))
                text = f"{name} {split_name} {doc} {code[:150]}".strip()
                if len(text) > 3:
                    indexed_nodes.append(nid)
                    corpus.append(text)

        self.indexed_node_ids = indexed_nodes
        if not corpus:
            return

        try:
            self.vectorizer = TfidfVectorizer(stop_words="english", max_features=2500)
            self.tfidf_matrix = self.vectorizer.fit_transform(corpus)
            if BM25_AVAILABLE:
                tokenized = [t.lower().split() for t in corpus]
                self.bm25_index = BM25Okapi(tokenized)

            links_added = 0
            for i, j, score in sparse_semantic_pairs(self.tfidf_matrix, threshold=similarity_threshold):
                u, v = indexed_nodes[i], indexed_nodes[j]
                meta = HyperEdgeMetadata(d_scope=0, f_call=1.0, c_type=score, id_ctx="workspace_semantic")
                self.graph.add_edge(
                    u, v, key=f"w_sem_{i}_{j}", relation="SEMANTIC_SIMILAR",
                    layer="Lsem", metadata=meta.to_dict(),
                    d_scope=0, f_call=1.0, c_type=score, id_ctx="workspace_semantic"
                )
                links_added += 1
            print(f"[*] Workspace Semantic Layer generated: {links_added} cross-concept relational links.")
        except Exception as exc:
            print(f"[!] Warning: Semantic layer generation failed: {exc}")

    def _print_layer_statistics(self):
        counts = {"Lsyn": 0, "Ldep": 0, "Lflow": 0, "Lsem": 0, "Lcontract": 0}
        for _, _, d in self.graph.edges(data=True):
            layer = d.get("layer", "Lsyn")
            if layer in counts:
                counts[layer] += 1
        print("    - Layer Distribution (Edges):")
        for layer, count in counts.items():
            print(f"      * {layer:12}: {count}")

    def verify_graph(self) -> Dict[str, Any]:
        """Produces a comprehensive verification report across the multi-repo system."""
        counts = {"Lsyn": 0, "Ldep": 0, "Lflow": 0, "Lsem": 0, "Lcontract": 0}
        implements_count = 0
        consumes_count = 0
        http_calls_count = 0
        produces_event_count = 0
        consumes_event_count = 0

        for u, v, d in self.graph.edges(data=True):
            layer = d.get("layer", "Lsyn")
            if layer in counts:
                counts[layer] += 1
            rel = d.get("relation")
            if rel == "IMPLEMENTS":
                implements_count += 1
            elif rel == "CONSUMES":
                consumes_count += 1
            elif rel == "HTTP_CALLS":
                http_calls_count += 1
            elif rel == "PRODUCES_EVENT":
                produces_event_count += 1
            elif rel == "CONSUMES_EVENT":
                consumes_event_count += 1

        repos_summary = {}
        for r_id, b in self.repo_builders.items():
            repos_summary[r_id] = {
                "loc": b.total_loc,
                "nodes": b.graph.number_of_nodes(),
                "edges": b.graph.number_of_edges(),
                "source_coverage_complete": b.get_language_report().get("full_source_coverage", False),
                "skipped_files": list(getattr(b, "skipped_files", [])),
            }

        return {
            "workspace_name": self.config.name,
            "version": self.config.version,
            "total_repositories": len(self.repo_builders),
            "repositories": repos_summary,
            "total_loc": self.total_loc,
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "layer_distribution": counts,
            "contract_services": len(self.canonical_contracts),
            "implements_edges": implements_count,
            "consumes_edges": consumes_count,
            "http_calls_edges": http_calls_count,
            "produces_event_edges": produces_event_count,
            "consumes_event_edges": consumes_event_count,
            "source_coverage_complete": all(
                r["source_coverage_complete"] for r in repos_summary.values()
            ) if repos_summary else False,
            "skipped_file_count": sum(len(r["skipped_files"]) for r in repos_summary.values()),
            "contract_skews": self.contract_skews,
            "skew_count": len(self.contract_skews),
        }

    def rag_query(self, query: str, top_k: int = 5, graft_subgraph: bool = True) -> Dict[str, Any]:
        """Workspace-wide natural language query with deterministic context grafting."""
        if not self.vectorizer or self.tfidf_matrix is None or not self.indexed_node_ids:
            return {"query": query, "top_matches": [], "error": "RAG index not initialized"}

        q_vec = self.vectorizer.transform([query])
        sims = cosine_similarity(q_vec, self.tfidf_matrix).flatten()

        if getattr(self, "bm25_index", None) is not None:
            bm25_tokens = query.lower().split()
            bm25_scores = self.bm25_index.get_scores(bm25_tokens)
            max_b = float(max(bm25_scores)) if len(bm25_scores) > 0 and max(bm25_scores) > 0 else 1.0
            hybrid_scores = 0.5 * sims + 0.5 * (bm25_scores / max_b)
            top_indices = hybrid_scores.argsort()[::-1][:top_k]
            scores_to_use = hybrid_scores
        else:
            top_indices = sims.argsort()[::-1][:top_k]
            scores_to_use = sims

        matches = []
        for idx in top_indices:
            score = float(scores_to_use[idx])
            if score <= 0:
                continue
            nid = self.indexed_node_ids[idx]
            ndata = self.graph.nodes.get(nid, {})
            matches.append({
                "node_id": nid,
                "name": ndata.get("name", nid),
                "type": ndata.get("type", "unknown"),
                "file": ndata.get("file", ""),
                "repo": ndata.get("repo", ""),
                "score": round(score, 4),
                "docstring": ndata.get("docstring", ""),
            })

        return {
            "query": query,
            "top_matches": matches,
            "workspace": self.config.name,
        }

    def export_graph(self, output_path: str, format: str = "json"):
        """Export workspace graph to JSON, GraphML, or GEXF."""
        output_path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        if format == "json":
            nodes = []
            for n, d in self.graph.nodes(data=True):
                item = dict(d)
                item["id"] = n
                nodes.append(item)
            edges = []
            for u, v, k, d in self.graph.edges(keys=True, data=True):
                item = dict(d)
                item["source"] = u
                item["target"] = v
                item["key"] = k
                edges.append(item)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump({"nodes": nodes, "edges": edges}, f, indent=2)
        elif format == "graphml":
            clean_g = nx.MultiDiGraph()
            for n, d in self.graph.nodes(data=True):
                clean_d = {k: str(v) if isinstance(v, (list, dict)) else v for k, v in d.items()}
                clean_g.add_node(n, **clean_d)
            for u, v, k, d in self.graph.edges(keys=True, data=True):
                clean_d = {k: str(v) if isinstance(v, (list, dict)) else v for k, v in d.items()}
                clean_g.add_edge(u, v, key=k, **clean_d)
            nx.write_graphml(clean_g, output_path)
        elif format == "gexf":
            clean_g = nx.MultiDiGraph()
            for n, d in self.graph.nodes(data=True):
                clean_d = {k: str(v) if isinstance(v, (list, dict)) else v for k, v in d.items()}
                clean_g.add_node(n, **clean_d)
            for u, v, k, d in self.graph.edges(keys=True, data=True):
                clean_d = {k: str(v) if isinstance(v, (list, dict)) else v for k, v in d.items()}
                clean_g.add_edge(u, v, key=k, **clean_d)
            nx.write_gexf(clean_g, output_path)
        print(f"[*] Workspace CKG exported to: {output_path} ({format})")
