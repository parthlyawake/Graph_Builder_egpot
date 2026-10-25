"""Run the graph explorer against any local repository (no upload required).

Example: python bench/team_demo.py --repo C:\\path\\to\\project --port 8767
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from graft_ckg import CKGBuilder  # noqa: E402
from hybrid_retrieval import CONFIGS, HybridRetriever  # noqa: E402

DEFAULT_EXCLUDES = (
    ".next/*", ".vinext/*", ".wrangler/*", ".vercel/*", ".openai/*",
    ".tmp/*", ".output/*", "coverage/*", "out/*", "outputs/*",
)


def build_payload(repo: Path, excludes: list[str]):
    builder = CKGBuilder(str(repo))
    # build() calls this; make the added patterns part of the loader.
    original_loader = builder._load_ignore_patterns

    def load_ignores():
        original_loader()
        builder.ignore_patterns.extend(DEFAULT_EXCLUDES)
        builder.ignore_patterns.extend(excludes)

    builder._load_ignore_patterns = load_ignores
    with contextlib.redirect_stdout(io.StringIO()) as build_log:
        builder.build()
    del builder._load_ignore_patterns
    graph = builder.graph
    payload = {
        "source": repo.name,
        "counts": {
            "files": sum(d.get("type") == "file" for _, d in graph.nodes(data=True)),
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "loc": builder.total_loc,
        },
        "nodes": [
            {"id": str(node_id), "name": str(data.get("name") or node_id),
             "type": str(data.get("type") or "unknown"),
             "layer": str(data.get("layer") or ""),
             "file": str(data.get("file") or ""),
             "line": int(data.get("line_no") or 0)}
            for node_id, data in graph.nodes(data=True)
        ],
        "edges": [
            {"source": str(u), "target": str(v),
             "relation": str(data.get("relation") or ""),
             "layer": str(data.get("layer") or "")}
            for u, v, data in graph.edges(data=True)
        ],
    }
    return builder, payload, build_log.getvalue()


def create_handler(payload, retriever):
    graph_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    page_bytes = (ROOT / "viewer" / "index.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, body, content_type="application/json; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/":
                self.reply(200, page_bytes, "text/html; charset=utf-8")
            elif self.path == "/api/graph":
                self.reply(200, graph_bytes)
            elif self.path == "/api/health":
                self.reply(200, b'{"ok":true}')
            else:
                self.reply(404, b'{"error":"Not found"}')

        def do_POST(self):
            if self.path != "/api/retrieve":
                self.reply(404, b'{"error":"Not found"}')
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 8192:
                    raise ValueError("Request is empty or too large")
                request = json.loads(self.rfile.read(size))
                query = str(request.get("query", "")).strip()
                if not 2 <= len(query) <= 500:
                    raise ValueError("Query must be 2–500 characters")
                requested = request.get("method", "all")
                if requested != "all" and requested not in CONFIGS:
                    raise ValueError("Unknown retrieval method")
                chosen = list(CONFIGS) if requested == "all" else [requested]
                results = []
                for method in chosen:
                    start = time.perf_counter()
                    response = retriever.retrieve(query, method, top_k=12, token_budget=2048)
                    matches = response["top_matches"]
                    results.append({
                        "id": method, "title": CONFIGS[method].title,
                        "effective_config": response["effective_config"],
                        "top_matches": matches,
                        "file_hits": list(dict.fromkeys(hit["file"] for hit in matches if hit["file"])),
                        "query_seconds": round(time.perf_counter() - start, 3),
                    })
                self.reply(200, json.dumps({"query": query, "methods": results}).encode("utf-8"))
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self.reply(400, json.dumps({"error": str(exc)}).encode("utf-8"))
            except Exception as exc:
                self.reply(500, json.dumps({"error": f"Retrieval failed: {type(exc).__name__}"}).encode("utf-8"))

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Local GRAFT-CKG graph explorer for any repository")
    parser.add_argument("--repo", type=Path, required=True, help="Local repository directory to index")
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--exclude", action="append", default=[], help="Additional .ckgignore-style glob")
    args = parser.parse_args()
    repo = args.repo.resolve()
    if not repo.is_dir():
        parser.error(f"Repository directory does not exist: {repo}")
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    builder, payload, log = build_payload(repo, args.exclude)
    print(log, end="")
    print(f"Index ready: {payload['counts']['files']} files, {payload['counts']['nodes']} nodes, {payload['counts']['edges']} edges")
    retriever = HybridRetriever(builder, include_documents=False)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), create_handler(payload, retriever))
    print(f"Open http://127.0.0.1:{args.port}/ (local computer only)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
