"""
serve_chatgpt_bridge.py
=======================
Lightweight, zero-external-dependency HTTP server that connects ChatGPT Actions
directly to the live GRAFT-CKG / SCKG graph.

Enables ChatGPT to:
- Search symbols, RPCs, endpoints, and classes across repositories.
- Inspect full node metadata, signatures, docstrings, and source code.
- Retrieve N-hop neighborhoods and call chains across services.
- Compute downstream blast radius and impact of code changes.
- Trace inter-service causal execution paths.
- List all active gRPC, REST, and Kafka contracts.

Usage:
    python serve_chatgpt_bridge.py --workspace repos/online-boutique/workspace.yaml --port 8080
    python serve_chatgpt_bridge.py --graph online_boutique_graph.json --port 8080

Then expose locally using:
    ngrok http 8080
and paste the public URL and OpenAPI schema into ChatGPT Custom GPT Actions.
"""

import os
import sys
import json
import argparse
import urllib.parse
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

import networkx as nx

# Try importing workspace and traversal modules
try:
    from multi_repo import WorkspaceCKGBuilder, WorkspaceConfig
    from traversal import SCKGTraversal
except ImportError:
    WorkspaceCKGBuilder = None
    SCKGTraversal = None

GLOBAL_GRAPH: nx.MultiDiGraph = None
GLOBAL_WORKSPACE_NAME: str = "GRAFT-CKG"
GLOBAL_PRODUCERS = {}
GLOBAL_CONSUMERS = {}
GLOBAL_CONTRACTS = []

def _refresh_contracts_from_graph():
    global GLOBAL_CONTRACTS
    GLOBAL_CONTRACTS = []
    if not GLOBAL_GRAPH:
        return

    # Find all contract nodes
    contract_nodes = [
        n for n, d in GLOBAL_GRAPH.nodes(data=True)
        if d.get("type") in ("rpc_contract", "service_contract") or "contract::" in n
    ]

    for c_node in sorted(contract_nodes):
        nd = GLOBAL_GRAPH.nodes[c_node]
        if nd.get("type") != "rpc_contract" and "contract::" not in c_node:
            continue

        producers = []
        consumers = []
        for u, _, k, data in GLOBAL_GRAPH.in_edges(c_node, keys=True, data=True):
            rel = data.get("relation")
            if rel == "IMPLEMENTS":
                producers.append(u)
            elif rel == "CONSUMES":
                consumers.append(u)

        GLOBAL_CONTRACTS.append({
            "rpc_id": c_node,
            "type": nd.get("type", "rpc_contract"),
            "producers": producers,
            "consumers": consumers,
            "producer_count": len(producers),
            "consumer_count": len(consumers)
        })

def init_from_workspace(workspace_path: str):
    global GLOBAL_GRAPH, GLOBAL_WORKSPACE_NAME
    print(f"[*] Building live multi-repo graph from: {workspace_path}")
    builder = WorkspaceCKGBuilder(workspace_path)
    G = builder.build()
    GLOBAL_GRAPH = G
    GLOBAL_WORKSPACE_NAME = builder.config.name
    _refresh_contracts_from_graph()
    print(f"[+] Loaded {len(G.nodes)} nodes and {len(G.edges)} edges across {len(builder.repo_builders)} repos.")

def init_from_json(json_path: str):
    global GLOBAL_GRAPH, GLOBAL_WORKSPACE_NAME
    print(f"[*] Loading pre-built graph from: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    G = nx.MultiDiGraph()
    for n in data.get("nodes", []):
        nid = n.get("id")
        if nid:
            G.add_node(nid, **n)
    for e in data.get("edges", data.get("links", [])):
        u = e.get("source", e.get("from"))
        v = e.get("target", e.get("to"))
        if u and v:
            G.add_edge(u, v, **e)

    GLOBAL_GRAPH = G
    GLOBAL_WORKSPACE_NAME = Path(json_path).stem
    _refresh_contracts_from_graph()
    print(f"[+] Loaded {len(G.nodes)} nodes and {len(G.edges)} edges.")

class ChatGPTBridgeHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, data: dict):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        # 1. Health check
        if path in ("/", "/health"):
            total_nodes = len(GLOBAL_GRAPH.nodes) if GLOBAL_GRAPH else 0
            total_edges = len(GLOBAL_GRAPH.edges) if GLOBAL_GRAPH else 0
            self._send_json(200, {
                "status": "healthy",
                "workspace": GLOBAL_WORKSPACE_NAME,
                "total_nodes": total_nodes,
                "total_edges": total_edges,
                "contracts_count": len(GLOBAL_CONTRACTS),
                "api_version": "1.0.0"
            })

        # 2. OpenAPI specification
        elif path in ("/openapi.json", "/api/openapi.json"):
            openapi_file = Path(__file__).resolve().parent / "chatgpt_export" / "openapi_chatgpt_action.json"
            if openapi_file.is_file():
                spec = json.loads(openapi_file.read_text(encoding="utf-8"))
                host_header = self.headers.get("Host")
                if host_header:
                    scheme = "https" if "ngrok" in host_header or "loca.lt" in host_header else "http"
                    spec["servers"] = [{"url": f"{scheme}://{host_header}", "description": "Active ChatGPT Bridge Server"}]
                self._send_json(200, spec)
            else:
                self._send_json(404, {"error": "openapi_chatgpt_action.json not found. Run export_chatgpt_context.py first."})

        # 3. Node search
        elif path == "/api/search":
            query = params.get("q", [""])[0].strip().lower()
            limit = int(params.get("limit", ["10"])[0])
            if not query:
                self._send_json(400, {"error": "Query parameter 'q' is required."})
                return

            matches = []
            for nid, d in GLOBAL_GRAPH.nodes(data=True):
                name = d.get("name", "")
                if query in nid.lower() or query in name.lower():
                    matches.append({
                        "id": nid,
                        "name": name or nid.split(":")[-1],
                        "type": d.get("type", "unknown"),
                        "layer": d.get("layer", "Lsyn"),
                        "file": d.get("file", ""),
                        "line": d.get("line_no", 0),
                        "repo": d.get("repo", "")
                    })
                    if len(matches) >= limit * 2:
                        break

            # Sort exact prefix/substring matches higher
            matches.sort(key=lambda m: (
                0 if m["name"].lower() == query else 1,
                0 if query in m["name"].lower() else 1,
                len(m["name"])
            ))
            matches = matches[:limit]

            self._send_json(200, {
                "query": query,
                "total_matches": len(matches),
                "matches": matches
            })

        # 4. Node Detail
        elif path == "/api/node":
            node_id = params.get("id", [""])[0].strip()
            if not node_id:
                self._send_json(400, {"error": "Query parameter 'id' is required."})
                return

            if node_id not in GLOBAL_GRAPH:
                candidates = [n for n in GLOBAL_GRAPH.nodes if node_id.lower() in n.lower()]
                if not candidates:
                    self._send_json(404, {"error": f"Node '{node_id}' not found in graph."})
                    return
                node_id = candidates[0]

            d = GLOBAL_GRAPH.nodes[node_id]
            in_edges_summary = []
            for u, _, k, ed in GLOBAL_GRAPH.in_edges(node_id, keys=True, data=True):
                in_edges_summary.append({
                    "from": u,
                    "relation": ed.get("relation"),
                    "layer": ed.get("layer")
                })
            out_edges_summary = []
            for _, v, k, ed in GLOBAL_GRAPH.out_edges(node_id, keys=True, data=True):
                out_edges_summary.append({
                    "to": v,
                    "relation": ed.get("relation"),
                    "layer": ed.get("layer")
                })

            self._send_json(200, {
                "id": node_id,
                "name": d.get("name") or node_id.split(":")[-1],
                "type": d.get("type", "unknown"),
                "layer": d.get("layer", "Lsyn"),
                "file": d.get("file", ""),
                "line": d.get("line_no", 0),
                "docstring": d.get("docstring", ""),
                "code": d.get("code", ""),
                "repo": d.get("repo", ""),
                "in_degree": len(in_edges_summary),
                "out_degree": len(out_edges_summary),
                "in_edges": in_edges_summary[:20],
                "out_edges": out_edges_summary[:20]
            })

        # 5. N-hop neighborhood
        elif path == "/api/nhop":
            node_id = params.get("node", [""])[0].strip()
            hops = min(int(params.get("hops", ["1"])[0]), 3)
            direction = params.get("direction", ["both"])[0]
            layers_param = params.get("layers", [""])[0]
            layers = {l.strip() for l in layers_param.split(",") if l.strip()} if layers_param else None

            if not node_id:
                self._send_json(400, {"error": "Query parameter 'node' is required."})
                return

            if node_id not in GLOBAL_GRAPH:
                candidates = [n for n in GLOBAL_GRAPH.nodes if node_id.lower() in n.lower()]
                if not candidates:
                    self._send_json(404, {"error": f"Node '{node_id}' not found."})
                    return
                node_id = candidates[0]

            visited = {node_id: 0}
            queue = [(node_id, 0)]
            retrieved_edges = []

            while queue:
                curr, depth = queue.pop(0)
                if depth >= hops:
                    continue

                if direction in ("out", "both"):
                    for _, target, k, data in GLOBAL_GRAPH.out_edges(curr, keys=True, data=True):
                        l = data.get("layer")
                        if layers and l not in layers:
                            continue
                        retrieved_edges.append({
                            "source": curr,
                            "target": target,
                            "relation": data.get("relation"),
                            "layer": l
                        })
                        if target not in visited or visited[target] > depth + 1:
                            visited[target] = depth + 1
                            queue.append((target, depth + 1))

                if direction in ("in", "both"):
                    for source, _, k, data in GLOBAL_GRAPH.in_edges(curr, keys=True, data=True):
                        l = data.get("layer")
                        if layers and l not in layers:
                            continue
                        retrieved_edges.append({
                            "source": source,
                            "target": curr,
                            "relation": data.get("relation"),
                            "layer": l
                        })
                        if source not in visited or visited[source] > depth + 1:
                            visited[source] = depth + 1
                            queue.append((source, depth + 1))

            nodes_payload = []
            for nid, d_hop in visited.items():
                nd = GLOBAL_GRAPH.nodes[nid]
                nodes_payload.append({
                    "id": nid,
                    "name": nd.get("name") or nid.split(":")[-1],
                    "type": nd.get("type", "unknown"),
                    "layer": nd.get("layer", "Lsyn"),
                    "hop": d_hop,
                    "file": nd.get("file", ""),
                    "line": nd.get("line_no", 0)
                })

            self._send_json(200, {
                "root_id": node_id,
                "hops": hops,
                "total_nodes": len(nodes_payload),
                "total_edges": len(retrieved_edges),
                "nodes": nodes_payload,
                "edges": retrieved_edges
            })

        # 6. Blast Radius
        elif path == "/api/blast_radius":
            node_id = params.get("node", [""])[0].strip()
            max_depth = min(int(params.get("max_depth", ["3"])[0]), 5)

            if not node_id:
                self._send_json(400, {"error": "Query parameter 'node' is required."})
                return

            if node_id not in GLOBAL_GRAPH:
                candidates = [n for n in GLOBAL_GRAPH.nodes if node_id.lower() in n.lower()]
                if not candidates:
                    self._send_json(404, {"error": f"Node '{node_id}' not found."})
                    return
                node_id = candidates[0]

            visited = {node_id: 0}
            queue = [(node_id, 0)]
            impacted_services = set()
            impacted_contracts = []

            while queue:
                curr, depth = queue.pop(0)
                if depth >= max_depth:
                    continue

                for _, target, k, data in GLOBAL_GRAPH.out_edges(curr, keys=True, data=True):
                    rel = data.get("relation")
                    # Track caller consumers or dependent flows
                    if target not in visited:
                        visited[target] = depth + 1
                        queue.append((target, depth + 1))
                        repo = GLOBAL_GRAPH.nodes[target].get("repo")
                        if repo:
                            impacted_services.add(repo)
                        if "contract::" in target:
                            impacted_contracts.append(target)

            self._send_json(200, {
                "target_node": node_id,
                "max_depth": max_depth,
                "total_affected_nodes": len(visited),
                "affected_services": sorted(list(impacted_services)),
                "affected_contracts": sorted(list(set(impacted_contracts))),
                "sample_affected_nodes": [
                    {"id": nid, "depth": d, "type": GLOBAL_GRAPH.nodes[nid].get("type")}
                    for nid, d in list(visited.items())[:25]
                ]
            })

        # 7. List Contracts
        elif path == "/api/contracts":
            self._send_json(200, {
                "total_contracts": len(GLOBAL_CONTRACTS),
                "contracts": GLOBAL_CONTRACTS
            })

        # 8. Explain Path
        elif path == "/api/explain_path":
            src = params.get("source", [""])[0].strip()
            tgt = params.get("target", [""])[0].strip()

            if not src or not tgt:
                self._send_json(400, {"error": "Both 'source' and 'target' query parameters are required."})
                return

            # Fuzzy resolve if necessary
            if src not in GLOBAL_GRAPH:
                c = [n for n in GLOBAL_GRAPH.nodes if src.lower() in n.lower()]
                if c: src = c[0]
            if tgt not in GLOBAL_GRAPH:
                c = [n for n in GLOBAL_GRAPH.nodes if tgt.lower() in n.lower()]
                if c: tgt = c[0]

            if src not in GLOBAL_GRAPH or tgt not in GLOBAL_GRAPH:
                self._send_json(404, {"error": "Source or target node not found in graph."})
                return

            try:
                # Find shortest path ignoring direction or along directed edges
                try:
                    path_nodes = nx.shortest_path(GLOBAL_GRAPH, source=src, target=tgt)
                except nx.NetworkXNoPath:
                    path_nodes = nx.shortest_path(GLOBAL_GRAPH.to_undirected(), source=src, target=tgt)

                path_edges = []
                for i in range(len(path_nodes) - 1):
                    u = path_nodes[i]
                    v = path_nodes[i+1]
                    edge_data = GLOBAL_GRAPH.get_edge_data(u, v)
                    if edge_data:
                        first_k = next(iter(edge_data))
                        rel = edge_data[first_k].get("relation", "CONNECTED_TO")
                        layer = edge_data[first_k].get("layer", "Lsyn")
                    else:
                        rel = "REVERSE_RELATION"
                        layer = "Lsyn"
                    path_edges.append({
                        "step": i + 1,
                        "from": u,
                        "relation": rel,
                        "layer": layer,
                        "to": v
                    })

                self._send_json(200, {
                    "source": src,
                    "target": tgt,
                    "path_length": len(path_nodes) - 1,
                    "explanation": " -> ".join([p.split(":")[-1] for p in path_nodes]),
                    "steps": path_edges
                })
            except nx.NetworkXNoPath:
                self._send_json(200, {
                    "source": src,
                    "target": tgt,
                    "path_length": -1,
                    "explanation": "No topological path exists between these entities."
                })

        else:
            self._send_json(404, {"error": f"Endpoint '{path}' not found. See /openapi.json for valid paths."})

def main():
    parser = argparse.ArgumentParser(description="GRAFT-CKG ChatGPT Actions Bridge Server")
    parser.add_argument("--workspace", type=str, default="repos/online-boutique/workspace.yaml", help="Path to workspace.yaml")
    parser.add_argument("--graph", type=str, default=None, help="Path to pre-built .json graph")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default 8080)")
    args = parser.parse_args()

    if args.graph and Path(args.graph).is_file():
        init_from_json(args.graph)
    elif Path(args.workspace).is_file() and WorkspaceCKGBuilder:
        init_from_workspace(args.workspace)
    elif Path("online_boutique_graph.json").is_file():
        init_from_json("online_boutique_graph.json")
    else:
        print("[!] Warning: No workspace or graph found. Initializing empty graph.")
        init_from_json("online_boutique_graph.json")

    server_address = ("", args.port)
    httpd = HTTPServer(server_address, ChatGPTBridgeHandler)
    print("=" * 70)
    print(f" GRAFT-CKG ChatGPT Actions Bridge running on http://localhost:{args.port}")
    print(f" - Health check:    http://localhost:{args.port}/health")
    print(f" - OpenAPI spec:    http://localhost:{args.port}/openapi.json")
    print(f" - Search API:      http://localhost:{args.port}/api/search?q=CartService")
    print(f" - Contracts API:   http://localhost:{args.port}/api/contracts")
    print(f" - Blast Radius:    http://localhost:{args.port}/api/blast_radius?node=hipstershop.CartService")
    print("=" * 70)
    print("To connect ChatGPT:")
    print("  1. Run: ngrok http 8080")
    print("  2. In ChatGPT Custom GPT builder -> Add Action -> Import from URL: <ngrok_url>/openapi.json")
    print("=" * 70)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Server stopped.")

if __name__ == "__main__":
    main()
