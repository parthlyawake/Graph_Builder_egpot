"""Select source declarations independently, then compare them to a saved CKG.

Sampling is deterministic and does not use the graph to choose declarations.
"""

import argparse
import ast
from collections import defaultdict
import json
from pathlib import Path
import pickle
import random

from tree_sitter import Language, Parser
import tree_sitter_c_sharp
import tree_sitter_go
import tree_sitter_java
import tree_sitter_javascript
import tree_sitter_typescript


GRAMMARS = {
    ".go": tree_sitter_go.language,
    ".java": tree_sitter_java.language,
    ".cs": tree_sitter_c_sharp.language,
    ".js": tree_sitter_javascript.language,
    ".jsx": tree_sitter_javascript.language,
    ".ts": tree_sitter_typescript.language_typescript,
    ".tsx": tree_sitter_typescript.language_tsx,
}
FUNCTION_TYPES = {"function_declaration", "method_declaration", "method_definition"}
EXCLUDED_DIRS = {".git", "node_modules", "vendor", "dist", "build", "generated", "genproto",
                 "gen-py", "gen-go", "gen-cpp", "protos", "__pycache__", "tests", "test",
                 "e2e", "deployment", "assets"}


def source_declarations(repo):
    declarations = []
    for file in sorted(repo.rglob("*")):
        if not file.is_file() or any(part.lower() in EXCLUDED_DIRS for part in file.relative_to(repo).parts[:-1]):
            continue
        relative = file.relative_to(repo).as_posix()
        ext = file.suffix.lower()
        if ext != ".py" and ext not in GRAMMARS:
            continue
        if file.name.endswith((".min.js", ".pb.go", "_test.go", ".generated.ts")):
            continue
        source = file.read_bytes()
        if ext == ".py":
            try:
                root = ast.parse(source, filename=str(file))
            except (SyntaxError, ValueError):
                continue
            for node in ast.walk(root):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("test_"):
                    declarations.append((relative, node.name, node.lineno, ext))
            continue
        parser = Parser(Language(GRAMMARS[ext]()))
        root = parser.parse(source).root_node
        stack = [root]
        while stack:
            node = stack.pop()
            if node.type in FUNCTION_TYPES:
                name = node.child_by_field_name("name")
                if name is not None:
                    spelling = source[name.start_byte:name.end_byte].decode("utf-8", "replace")
                    if not spelling.startswith("test"):
                        declarations.append((relative, spelling, node.start_point.row + 1, ext))
            stack.extend(reversed(node.named_children))
    return declarations


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=20261025)
    parser.add_argument("--count", type=int, default=3)
    args = parser.parse_args()
    repo = args.repo.resolve()
    with args.graph.open("rb") as stream:
        graph = pickle.load(stream)  # Only load graphs generated locally by audit_graph_builder.py.

    candidates = source_declarations(repo)
    by_ext = defaultdict(list)
    for candidate in candidates:
        by_ext[candidate[3]].append(candidate)
    rng = random.Random(args.seed)
    groups = sorted(by_ext, key=lambda ext: (-len(by_ext[ext]), ext))
    selected = []
    for ext in groups:
        selected.append(rng.choice(by_ext[ext]))
        if len(selected) >= args.count:
            break
    if len(selected) < args.count:
        remaining = [candidate for candidate in candidates if candidate not in selected]
        selected.extend(rng.sample(remaining, min(args.count - len(selected), len(remaining))))

    graph_functions = defaultdict(list)
    for node_id, data in graph.nodes(data=True):
        if data.get("type") == "function":
            graph_functions[(data.get("file"), data.get("name"))].append((node_id, data))

    samples = []
    for relative, name, line, ext in selected:
        file = repo / relative
        lines = file.read_text(encoding="utf-8", errors="replace").splitlines()
        matches = graph_functions[(relative, name)]
        match = min(matches, key=lambda pair: abs(pair[1].get("line_no", 0) - line)) if matches else None
        node_id = match[0] if match else None
        edges = []
        if node_id:
            for source, target, data in graph.in_edges(node_id, data=True):
                if data.get("relation") != "SEMANTIC_SIMILAR":
                    edges.append({"direction": "in", "relation": data.get("relation"), "other": source})
            for source, target, data in graph.out_edges(node_id, data=True):
                if data.get("relation") != "SEMANTIC_SIMILAR":
                    edges.append({"direction": "out", "relation": data.get("relation"), "other": target})
        samples.append({
            "source_file": relative, "source_name": name, "source_line": line, "language_extension": ext,
            "source_excerpt": "\n".join(f"{i+1}: {lines[i]}" for i in range(max(0, line-1), min(len(lines), line+11))),
            "graph_node": node_id, "graph_line": match[1].get("line_no") if match else None,
            "edges": sorted(edges, key=lambda edge: (edge["direction"], edge["relation"], edge["other"]))[:60],
        })
    result = {"repo": repo.name, "seed": args.seed, "source_candidates": len(candidates),
              "candidates_by_extension": {key: len(value) for key, value in sorted(by_ext.items())},
              "samples": samples}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"repo": repo.name, "candidates": len(candidates), "samples": [
        {"source": f"{item['source_file']}:{item['source_line']}:{item['source_name']}",
         "node": item["graph_node"], "edges": len(item["edges"])} for item in samples]}, indent=2, default=str))


if __name__ == "__main__":
    main()
