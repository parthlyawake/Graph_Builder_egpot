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
import copy
import hashlib
import json
import os
import re
import sys
import time
from urllib.parse import urlsplit
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Ensure current directory is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from graft_ckg import CKGBuilder, HyperEdgeMetadata

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
    exclude_nonproduction: bool = False
    resolve_java_dispatch: bool = False

    def __post_init__(self):
        if type(self.resolve_java_dispatch) is not bool:
            raise ValueError("resolve_java_dispatch must be a boolean")

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
            exclude_nonproduction=data.get("exclude_nonproduction", False),
            resolve_java_dispatch=data.get("resolve_java_dispatch", False),
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
            elif stripped.startswith("resolve_java_dispatch:"):
                value = stripped.split(":", 1)[1].strip().lower()
                if value not in {"true", "false"}:
                    raise ValueError("resolve_java_dispatch must be a boolean")
                result["resolve_java_dispatch"] = value == "true"
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

        t0 = time.perf_counter()
        self.repo_builders = {}

        # Step 1: Parse and build each repository graph with strict repo_id namespacing
        for repo_cfg in self.config.repositories:
            repo_full_path = self._resolve_path(repo_cfg.path)
            print(f"[*] ---> Building repository '{repo_cfg.id}' at: {repo_full_path}")
            if not os.path.isdir(repo_full_path):
                print(f"[!] Warning: Repository path does not exist: {repo_full_path}")
                continue

            builder = CKGBuilder(repo_full_path, repo_id=repo_cfg.id)
            builder.exclude_nonproduction = self.config.exclude_nonproduction
            if self.config.ignore_patterns:
                builder.ignore_patterns.extend(self.config.ignore_patterns)
            builder.build()
            self.repo_builders[repo_cfg.id] = builder

        self._compose_workspace()

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

    def _compose_workspace(self):
        """Refresh composition from parsed repositories, including shared producers."""
        self.graph.clear()
        self.canonical_contracts = {}
        self.contract_skews = []
        self.http_endpoints = {}
        self.symbols_by_name = {}
        self.docstrings = {}
        self.raw_file_lines = {}
        self.total_loc = 0
        self.edge_counter = 0
        self.vectorizer = self.tfidf_matrix = self.bm25_index = None
        self.indexed_node_ids = []
        for repo_id, builder in self.repo_builders.items():
            # Aggregate statistics and registries
            self.total_loc += builder.total_loc
            for k, lines in builder.raw_file_lines.items():
                self.raw_file_lines[f"{repo_id}/{k}"] = lines
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
                    self.graph.add_node(n, **copy.deepcopy(d))
                else:
                    curr = self.graph.nodes[n]
                    if "definitions" in d:
                        curr.setdefault("definitions", []).extend(d["definitions"])

            for u, v, k, d in builder.graph.edges(keys=True, data=True):
                global_k = f"w_{repo_id}_{k}"
                self.graph.add_edge(u, v, key=global_k, **d)

        # Step 4: Unify canonical contract layer (Lcontract) & check for CONTRACT_SKEW
        self._unify_contract_layer()
        self._resolve_cross_repo_producers()

        # Step 5: Resolve cross-repository HTTP dependency calls
        self._resolve_cross_repo_http_calls()

        # Step 6: Resolve cross-repository unresolved gRPC calls
        self._resolve_cross_repo_grpc_calls()

        # Step 7: Build workspace-level Semantic Layer (Lsem)
        self._build_semantic_layer()

        # Additive, opt-in pass after all legacy construction. Existing nodes,
        # edges, keys and semantic indexing are unchanged, including externals.
        if self.config.resolve_java_dispatch:
            self._resolve_java_dispatch()

        return self.graph

    def _resolve_java_dispatch(self):
        from polyglot import JavaDispatchResolver

        resolvers = {repo_id: JavaDispatchResolver(builder)
                     for repo_id, builder in sorted(self.repo_builders.items())}
        workspace_types = {}
        for resolver in resolvers.values():
            for name, records in resolver.types.items():
                workspace_types.setdefault(name, []).extend(records)
        for repo_id, resolver in resolvers.items():
            resolver.workspace_types = workspace_types
            resolver.service_types = {rid: r.types for rid, r in resolvers.items()}
            for match in resolver.resolve():
                caller, target = match.pop("caller"), match.pop("target")
                identity = json.dumps([repo_id, caller, target, match["source_evidence"],
                                       match["source_column"]], separators=(",", ":"))
                key = "java_dispatch_" + hashlib.sha256(identity.encode()).hexdigest()
                meta = HyperEdgeMetadata(d_scope=match.pop("scope_depth"),
                                         id_ctx=match["source_evidence"].rsplit(":", 1)[0])
                self.graph.add_edge(caller, target, key=key, relation="CALLS", layer="Ldep",
                                    metadata=meta.to_dict(), **meta.to_dict(), **match)

    def _resolve_cross_repo_producers(self):
        """Revisit registrations skipped before shared contracts were available."""
        for builder in self.repo_builders.values():
            builder._bind_contract_producers(self.canonical_contracts, self.graph)

    def update_files(self, repo_id, changed_rel_paths, deleted_rel_paths=()):
        """Update one service, then refresh shared bindings and workspace indexes."""
        self.repo_builders[repo_id].update_files(changed_rel_paths, deleted_rel_paths)
        return self._compose_workspace()

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

        text = raw.decode("utf-8", errors="replace")
        text = re.sub(r"//[^\n]*", "", text)
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        text = re.sub(r"\)\s*\{\s*\}", ");", text)

        for s_match in re.finditer(r"service\s+(\w+)\s*\{", text):
            service_name = s_match.group(1)
            depth, i = 1, s_match.end()
            while i < len(text) and depth:
                depth += {"{": 1, "}": -1}.get(text[i], 0)
                i += 1
            body = text[s_match.end():i - 1]
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
            for r_match in re.finditer(r"rpc\s+(\w+)\s*\(\s*(\w+)\s*\)\s*returns\s*\(\s*(\w+)\s*\)", body):
                rpc_name, req, resp = r_match.groups()
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

    def _resolve_cross_repo_http_calls(self):
        """Binds frontend and client HTTP calls in Repo A to routes declared in Repo B."""
        aliases, environments = self._http_deployment_context()
        resolved = 0
        for caller_repo_id, builder in self.repo_builders.items():
            requests = self._source_http_requests(builder, environments.get(caller_repo_id, {}))
            for request in requests:
                caller_id, url, method, source_file, line, kind = request
                parsed = urlsplit(url)
                host = (parsed.hostname or "").lower()
                # Unknown/ambiguous authorities must never fall back to path-only matching.
                repos = aliases.get(host, set())
                if len(repos) != 1 or "{" in host:
                    continue
                destination = next(iter(repos))
                if destination == caller_repo_id:
                    continue
                matches = set()
                for (verb, path), handlers in self.http_endpoints.items():
                    if verb not in {method, "*"} or not self._http_path_matches(path, parsed.path):
                        continue
                    matches.update(h for h in handlers if self.graph.nodes[h].get("repo") == destination)
                if len(matches) != 1:
                    continue
                target_id = next(iter(matches))
                if self.graph.nodes[target_id].get("http_ambiguous_definition"):
                    continue
                meta = HyperEdgeMetadata(d_scope=0, f_call=1.0, c_type=1.0, id_ctx=source_file)
                evidence = f"{source_file}:{line}"
                key = f"w_http_source_{caller_id}_{target_id}_{source_file}_{line}"
                self.graph.add_edge(caller_id, target_id, key=key, relation="HTTP_CALLS", layer="Ldep",
                                    metadata=meta.to_dict(), **meta.to_dict(), match_kind=kind,
                                    source_evidence=evidence, http_method=method, http_url=url)
                resolved += 1
            for caller_id, clean_path, method, id_ctx in builder.http_calls_to_resolve:
                # These languages are resolved from complete source expressions above;
                # legacy Java tuples discard the host and used to guess exchange's verb.
                if id_ctx.endswith((".java", ".py")) and not clean_path.startswith("/"):
                    continue
                if id_ctx.endswith(".java"):
                    continue
                if id_ctx.endswith(".py") and any(r[0] == caller_id for r in requests):
                    continue
                targets = list(dict.fromkeys([
                    *self.http_endpoints.get((method.upper(), clean_path), []),
                    *self.http_endpoints.get(("*", clean_path), []),
                ]))
                if len(targets) != 1:
                    continue
                for target_id in targets:
                    if target_id == caller_id:
                        continue
                    already_bound = any(
                        target == target_id and d.get("relation") == "HTTP_CALLS"
                        for _, target, d in self.graph.out_edges(caller_id, data=True)
                    )
                    if already_bound:
                        continue
                    meta = HyperEdgeMetadata(d_scope=0, f_call=1.0, c_type=1.0, id_ctx=id_ctx)
                    e_id = f"w_http_{caller_id}_{target_id}"
                    self.graph.add_edge(
                        caller_id,
                        target_id,
                        key=e_id,
                        relation="HTTP_CALLS",
                        layer="Ldep",
                        metadata=meta.to_dict(),
                        d_scope=meta.d_scope,
                        f_call=meta.f_call,
                        c_type=meta.c_type,
                        id_ctx=meta.id_ctx,
                    )
                    resolved += 1
        if resolved:
            print(f"[*] Cross-Repository HTTP Resolution: {resolved} cross-service HTTP bindings created.")

    @staticmethod
    def _http_path_matches(route, requested):
        """Match complete path segments; parameters cannot absorb slashes or prefixes."""
        def segments(path):
            return path.split("/")
        left, right = segments(route), segments(requested)
        if len(left) != len(right):
            return False
        for a, b in zip(left, right):
            variable = re.fullmatch(r"\{[^{}]+\}|<[^<>]+>", a)
            if variable:
                if not b:
                    return False
            elif a != b or "{" in b or "<" in b:
                return False
        return True

    def _http_deployment_context(self):
        """Read literal compose/Kubernetes host aliases and scoped environment values.

        Conflicting declarations stay ambiguous. No process environment, DNS,
        interpolation, deployment execution or network lookup is consulted.
        """
        from collections import defaultdict
        aliases, envs = defaultdict(set), defaultdict(lambda: defaultdict(set))
        roots = {r.id: Path(self._resolve_path(r.path)).resolve() for r in self.config.repositories}
        for rid, root in roots.items():
            aliases[root.name.lower()].add(rid)
            aliases[rid.lower()].add(rid)
        try:
            import yaml
        except ImportError:
            return aliases, {}
        documents = []
        for base, dirs, files in os.walk(self.config.base_dir):
            dirs[:] = sorted(d for d in dirs if d not in {".git", "node_modules", "vendor", "build", "dist", "target", ".venv"})
            for name in sorted(files):
                if not name.endswith((".yaml", ".yml")):
                    continue
                path = Path(base, name)
                if path.stat().st_size > 2_000_000:
                    continue
                try:
                    documents.extend((path, doc) for doc in yaml.safe_load_all(path.read_text(encoding="utf-8")) if isinstance(doc, dict))
                except (OSError, ValueError, yaml.YAMLError):
                    continue
        configmaps = defaultdict(list)
        for _, doc in documents:
            if doc.get("kind") == "ConfigMap":
                configmaps[doc.get("metadata", {}).get("name")].append(doc.get("data", {}))
        def owners(names):
            return set().union(*(aliases.get(str(n).lower(), set()) for n in names)) if names else set()
        def add_env(rids, values):
            for rid in rids:
                for key, value in values.items():
                    if isinstance(value, (str, int)) and "$" not in str(value):
                        envs[rid][key].add(str(value))
        for path, doc in documents:
            services = doc.get("services", {})
            if isinstance(services, dict):
                for name, service in services.items():
                    if not isinstance(service, dict):
                        continue
                    build = service.get("build", {})
                    context = build.get("context") if isinstance(build, dict) else build
                    rids = owners([name, service.get("container_name", "")])
                    if context and "$" not in str(context):
                        resolved = (path.parent / str(context)).resolve()
                        rids |= {rid for rid, root in roots.items() if resolved == root}
                    if len(rids) == 1:
                        aliases[str(name).lower()].update(rids)
                    values = service.get("environment", {})
                    if isinstance(values, list):
                        values = dict(v.split("=", 1) for v in values if isinstance(v, str) and "=" in v)
                    if isinstance(values, dict):
                        add_env(rids, values)
            metadata = doc.get("metadata", {})
            spec = doc.get("spec", {})
            if not isinstance(spec, dict):
                continue
            template = spec.get("template", {})
            podspec = template.get("spec", spec) if isinstance(template, dict) else spec
            labels = template.get("metadata", {}).get("labels", {}) if isinstance(template, dict) else {}
            containers = podspec.get("containers", [])
            if doc.get("kind") == "Service":
                selector = spec.get("selector", {})
                rids = owners(list(selector.values()) if isinstance(selector, dict) else [])
                aliases[str(metadata.get("name", "")).lower()].update(rids)
            for container in containers if isinstance(containers, list) else []:
                rids = owners([metadata.get("name", ""), container.get("name", ""), *labels.values()])
                for ref in container.get("envFrom", []):
                    for values in configmaps.get(ref.get("configMapRef", {}).get("name"), []):
                        add_env(rids, values)
                for entry in container.get("env", []):
                    if "value" in entry:
                        add_env(rids, {entry.get("name"): entry["value"]})
                    else:
                        ref = entry.get("valueFrom", {}).get("configMapKeyRef", {})
                        for values in configmaps.get(ref.get("name"), []):
                            if ref.get("key") in values:
                                add_env(rids, {entry.get("name"): values[ref["key"]]})
        return aliases, {rid: {k: next(iter(v)) for k, v in values.items() if len(v) == 1}
                         for rid, values in envs.items()}

    def _source_http_requests(self, builder, environment):
        requests = []
        for file, lines in sorted(builder.raw_file_lines.items()):
            text = "\n".join(line.rstrip("\r\n") for line in lines)
            if file.endswith(".java"):
                requests.extend(self._java_http_requests(builder, file, text))
            elif file.endswith(".py"):
                requests.extend(self._python_http_requests(builder, file, text, environment))
        return list(dict.fromkeys(requests))

    @staticmethod
    def _http_caller(builder, file, line):
        candidates = [(int(d.get("line_no", 0)), n) for n, d in builder.graph.nodes(data=True)
                      if n.startswith(f"{builder.repo_prefix}{file}:") and d.get("type") == "function"
                      and int(d.get("line_no", 0)) <= line]
        return max(candidates, default=(0, None))[1]

    def _java_http_requests(self, builder, file, text):
        """Evaluate literal Java URL expressions and one-level pure string helpers."""
        from polyglot import TreeSitterExtractor
        source = text.encode("utf-8")
        root = TreeSitterExtractor(".java").parser.parse(source).root_node
        def raw(n):
            return source[n.start_byte:n.end_byte].decode("utf-8") if n else ""
        def walk(n):
            yield n
            for child in n.named_children:
                yield from walk(child)
        methods = [n for n in walk(root) if n.type == "method_declaration"]
        helpers = {}
        for method in methods:
            returns = [n for n in walk(method) if n.type == "return_statement"]
            if len(returns) == 1 and returns[0].named_children:
                params = method.child_by_field_name("parameters")
                names = [raw(p.child_by_field_name("name")) for p in params.named_children] if params else []
                helpers.setdefault(raw(method.child_by_field_name("name")), []).append((names, returns[0].named_children[0]))
        def evaluate(n, values, depth=0):
            if n is None:
                return None
            if n.type == "string_literal":
                try:
                    return json.loads(raw(n))
                except ValueError:
                    return None
            if n.type in {"identifier", "field_access"}:
                return values.get(raw(n), "{*}")
            if n.type == "parenthesized_expression" and n.named_children:
                return evaluate(n.named_children[0], values, depth)
            if n.type == "binary_expression" and n.child_by_field_name("operator") and raw(n.child_by_field_name("operator")) == "+":
                a, b = evaluate(n.child_by_field_name("left"), values, depth), evaluate(n.child_by_field_name("right"), values, depth)
                return a + b if isinstance(a, str) and isinstance(b, str) else None
            if n.type == "method_invocation":
                name = raw(n.child_by_field_name("name"))
                args = n.child_by_field_name("arguments")
                args = list(args.named_children) if args else []
                if name in {"create", "of"} and args and raw(n.child_by_field_name("object")) in {"URI", "java.net.URI"}:
                    return evaluate(args[0], values, depth)
                options = helpers.get(name, [])
                if depth == 0 and len(options) == 1:
                    params, expression = options[0]
                    if len(params) == len(args):
                        bound = {p: evaluate(a, values, 1) for p, a in zip(params, args)}
                        return evaluate(expression, bound, 1)
                return "{*}"
            return "{*}"
        receivers = set(re.findall(r"\b(?:RestTemplate|WebClient|HttpClient)\s+(\w+)", text))
        result = []
        for method in methods:
            caller = self._http_caller(builder, file, method.start_point.row + 1)
            if not caller:
                continue
            values = {}
            def flow(n):
                # Unknown runtime conditions require a join, never last-branch wins.
                if n.type == "if_statement":
                    before = dict(values)
                    consequence = n.child_by_field_name("consequence")
                    alternative = n.child_by_field_name("alternative")
                    if consequence:
                        yield from flow(consequence)
                    left = dict(values)
                    values.clear(); values.update(before)
                    if alternative:
                        yield from flow(alternative)
                    right = dict(values)
                    values.clear()
                    values.update({k: left.get(k) if left.get(k) == right.get(k) else None
                                   for k in left.keys() | right.keys()})
                    return
                yield n
                for child in n.named_children:
                    yield from flow(child)
            for n in flow(method):
                if n.type == "variable_declarator":
                    values[raw(n.child_by_field_name("name"))] = evaluate(n.child_by_field_name("value"), values)
                elif n.type == "assignment_expression":
                    values[raw(n.child_by_field_name("left"))] = evaluate(n.child_by_field_name("right"), values)
                if n.type != "method_invocation":
                    continue
                name, obj = raw(n.child_by_field_name("name")), raw(n.child_by_field_name("object"))
                args = n.child_by_field_name("arguments")
                args = list(args.named_children) if args else []
                verb = None
                url = None
                if obj in receivers and args:
                    if name == "exchange" and len(args) > 1:
                        found = re.fullmatch(r"(?:\w+\.)*HttpMethod\.(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)", raw(args[1]))
                        verb = found.group(1) if found else None
                    else:
                        found = re.fullmatch(r"(get|post|put|delete|patch|head|options)(?:ForObject|ForEntity)?", name)
                        verb = found.group(1).upper() if found else None
                    url = evaluate(args[0], values)
                if name == "uri" and args and any(re.match(r"\b" + re.escape(r) + r"\.", obj) for r in receivers):
                    found = re.search(r"\.(get|post|put|delete|patch|head|options)\(\)", obj)
                    verb = found.group(1).upper() if found else None
                    url = evaluate(args[0], values)
                if name == "uri" and args and "HttpRequest.newBuilder(" in obj:
                    parent = n
                    while parent.parent and parent.parent.type == "method_invocation":
                        parent = parent.parent
                    chain = raw(parent)
                    found = re.search(r"\.(GET|POST|PUT|DELETE|HEAD)\(", chain)
                    # A URI builder is only a request if passed to send/sendAsync.
                    declaration = parent.parent
                    request_name = raw(declaration.child_by_field_name("name")) if declaration and declaration.type == "variable_declarator" else None
                    if found and request_name and re.search(r"\b(?:" + "|".join(map(re.escape, receivers)) + r")\.send(?:Async)?\(\s*" + re.escape(request_name) + r"\b", raw(method)):
                        verb, url = found.group(1), evaluate(args[0], values)
                if verb and isinstance(url, str) and url.startswith(("http://", "https://")):
                    result.append((caller, url, verb, file, n.start_point.row + 1,
                                   "helper" if any(re.search(r"\b" + re.escape(h) + r"\(", raw(method))
                                                   for h in helpers if h != raw(method.child_by_field_name("name"))) else "literal_host"))
        return result

    def _python_http_requests(self, builder, file, text, environment):
        """Resolve static URL dataflow, including one imported helper module.

        This is a small AST evaluator, never Python execution. Unknown values
        become path placeholders; an unknown host is rejected by the resolver.
        Only syntactically imported HTTP clients are recognized.
        """
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return []
        result, modules, imports = [], {file: tree}, {}
        def name(n):
            return ast.unparse(n) if n is not None else ""
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = (node.module or "").replace(".", "/") + ".py"
                possible = [module, str(Path(file).parent / module).replace("\\", "/")]
                local = next((p for p in possible if p in builder.raw_file_lines), None)
                if local:
                    try:
                        modules[local] = ast.parse("\n".join(x.rstrip("\r\n") for x in builder.raw_file_lines[local]))
                        for alias in node.names:
                            imports[alias.asname or alias.name] = (local, alias.name)
                    except SyntaxError:
                        pass
        client_aliases = {}
        for module, parsed in modules.items():
            aliases = {}
            for n in ast.walk(parsed):
                if isinstance(n, ast.Import):
                    for alias in n.names:
                        if alias.name in {"requests", "httpx", "urllib.request"}:
                            aliases[alias.asname or alias.name] = alias.name
                if isinstance(n, ast.ImportFrom) and n.module in {"requests", "httpx", "urllib.request"}:
                    for alias in n.names:
                        aliases[alias.asname or alias.name] = n.module + "." + alias.name
            client_aliases[module] = aliases
        definitions = {(m, n.name): n for m, parsed in modules.items()
                       for n in parsed.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        referenced_methods = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        globals_ = {}
        active = set()
        caller = None
        def evaluate(n, values, module=file, depth=0, emit=False, evidence=None):
            if n is None:
                return "{*}"
            if isinstance(n, ast.Constant):
                return n.value if isinstance(n.value, (str, int)) else "{*}"
            key = name(n)
            if key in values:
                return values[key]
            if isinstance(n, ast.Name):
                return globals_.get(n.id, "{*}")
            if isinstance(n, ast.Attribute):
                obj = evaluate(n.value, values, module, depth)
                return obj.get(n.attr, "{*}") if isinstance(obj, dict) else "{*}"
            if isinstance(n, ast.Subscript):
                if name(n.value) in {"os.environ", "environ"}:
                    return environment.get(evaluate(n.slice, values), "{*}")
                return globals_.get(key, "{*}")
            if isinstance(n, ast.JoinedStr):
                return "".join(str(evaluate(v.value if isinstance(v, ast.FormattedValue) else v, values, module, depth)) for v in n.values)
            if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
                return str(evaluate(n.left, values, module, depth)) + str(evaluate(n.right, values, module, depth))
            if not isinstance(n, ast.Call):
                return "{*}"
            callee = name(n.func)
            args = [evaluate(a, values, module, depth) for a in n.args]
            kwargs = {k.arg: evaluate(k.value, values, module, depth) for k in n.keywords if k.arg}
            if callee in {"os.getenv", "os.environ.get", "environ.get"}:
                return environment.get(args[0], "{*}") if args else "{*}"
            if isinstance(n.func, ast.Attribute) and n.func.attr == "format":
                template = evaluate(n.func.value, values, module, depth)
                if isinstance(template, str):
                    try:
                        return template.format(*args, **kwargs)
                    except (ValueError, IndexError, KeyError):
                        return "{*}"
            aliases = client_aliases[module]
            head, _, tail = callee.partition(".")
            canonical = aliases.get(head, head) + ("." + tail if tail else "")
            action = canonical.rsplit(".", 1)[-1]
            if canonical.startswith(("requests.", "httpx.", "urllib.request.")):
                verb = action.upper() if action in {"get", "post", "put", "patch", "delete", "head", "options"} else "GET" if action == "urlopen" else None
                if action == "request":
                    verb = kwargs.get("method", args[0] if args else None)
                    url = kwargs.get("url", args[1] if len(args) > 1 else None)
                else:
                    url = kwargs.get("url", args[0] if args else None)
                if emit and caller and verb and isinstance(url, str) and url.startswith(("http://", "https://")):
                    result.append((caller, url, str(verb).upper(), module, n.lineno,
                                   "helper" if module != file else "env_via_config" if environment and ("config" in text or "environ" in text or "getenv" in text) else "literal_host"))
                return "{*}"
            target = imports.get(callee, (module, callee))
            definition = definitions.get(target)
            # One helper-module boundary; constructors merely carry data.
            if definition is not None and depth < 2 and target not in active:
                active.add(target)
                try:
                    if isinstance(definition, ast.ClassDef):
                        obj = {"__class__": target}
                        init = next((x for x in definition.body if isinstance(x, ast.FunctionDef) and x.name == "__init__"), None)
                        if init:
                            bound = dict(zip([p.arg for p in init.args.args][1:], args))
                            bound.update(kwargs);bound["self"] = obj
                            for statement in ast.walk(init):
                                if isinstance(statement, ast.Assign):
                                    value = evaluate(statement.value, bound, target[0], depth + 1)
                                    for dest in statement.targets:
                                        if isinstance(dest, ast.Attribute) and name(dest.value) == "self":
                                            obj[dest.attr] = value
                        if emit:
                            for method in definition.body:
                                if isinstance(method, ast.FunctionDef) and method.name in referenced_methods and method.name != "__init__":
                                    scan(method, {"self": obj}, target[0], depth + 1, evidence or n.lineno)
                        return obj
                    bound = dict(zip([p.arg for p in definition.args.args], args));bound.update(kwargs)
                    if emit:
                        scan(definition, bound, target[0], depth + 1, evidence or n.lineno)
                    returns = [r for r in ast.walk(definition) if isinstance(r, ast.Return)]
                    return evaluate(returns[0].value, bound, target[0], depth + 1) if len(returns) == 1 else "{*}"
                finally:
                    active.remove(target)
            return "{*}"
        # Configuration initializers often occur below nested Flask handlers.
        # Collect only unique, statically resolved global/config assignments.
        candidates = {}
        for _ in range(3):
            for statement in ast.walk(tree):
                if isinstance(statement, ast.Assign):
                    for dest in statement.targets:
                        key = name(dest)
                        if isinstance(dest, ast.Subscript) or isinstance(dest, ast.Name) and statement in tree.body:
                            value = evaluate(statement.value, globals_)
                            if isinstance(value, str) and "{*}" not in value:
                                candidates.setdefault(key, set()).add(value)
            for key, choices in candidates.items():
                if len(choices) == 1:
                    globals_[key] = next(iter(choices))
                else:
                    globals_.pop(key, None)
        def scan(function, values, module, depth=0, evidence=None):
            # Walk statements in source order, excluding nested functions/classes.
            def nodes(n):
                for child in ast.iter_child_nodes(n):
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        continue
                    yield child
                    yield from nodes(child)
            for n in nodes(function):
                if isinstance(n, ast.Assign):
                    value = evaluate(n.value, values, module, depth)
                    for dest in n.targets:
                        values[name(dest)] = value
                if isinstance(n, ast.Call):
                    evaluate(n, values, module, depth, True, evidence)
        for function in ast.walk(tree):
            if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                caller = self._http_caller(builder, file, function.lineno)
                scan(function, dict(globals_), file)
        return result

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

            sim_matrix = cosine_similarity(self.tfidf_matrix)
            links_added = 0
            n = len(indexed_nodes)
            for i in range(n):
                for j in range(i + 1, min(n, i + 30)):
                    score = float(sim_matrix[i, j])
                    if score >= similarity_threshold:
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
        if self.config.resolve_java_dispatch:
            # Only opt-in exports gain a sidecar; legacy exports stay unchanged.
            config_path = Path(output_path).with_suffix(".build_config.json")
            config_path.write_text(json.dumps(asdict(self.config), indent=2), encoding="utf-8")
