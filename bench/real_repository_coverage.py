#!/usr/bin/env python3
"""Reproducible, application-agnostic source coverage audit for real repositories.

This is a grammar audit, not a graph accuracy benchmark. It reports complete
file counts and parse diagnostics for the checked-out scope. A separate
--build-graph option evaluates construction, never asserted by parse success.
"""
from __future__ import annotations

import argparse
import ast
import importlib
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
import sys

# Executed as `python bench/real_repository_coverage.py` in CI.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from language_adapters import KNOWN_UNSUPPORTED, parser_available, spec_for
from extended_language_adapters import GRAMMAR_MODULES

SKIP_DIRS = frozenset({
    ".git", "node_modules", "vendor", ".venv", "venv", "dist",
    "build", "target", "__pycache__", ".gradle",
})
SCHEMAS = frozenset({".thrift", ".pdl", ".avsc", ".proto"})


def run_audit(root: Path, *, max_bytes=5_000_000, build_graph=False):
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Audit root is not a directory: {root}")
    languages = defaultdict(lambda: Counter())
    unsupported = Counter()
    schema = defaultdict(Counter)
    failures = []
    total_files = 0
    ignored_files = 0
    parser_cache = {}
    grammar_recovery = []

    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            file = Path(base, name)
            rel_path = file.relative_to(root).as_posix()
            ext = file.suffix.lower()
            spec = spec_for(rel_path)
            schema_ext = ext in SCHEMAS
            if spec is None and not schema_ext:
                if ext in KNOWN_UNSUPPORTED:
                    unsupported[ext] += 1
                continue
            total_files += 1
            counts = schema[ext] if schema_ext else languages[spec.name]
            counts["discovered"] += 1
            try:
                if file.is_symlink():
                    raise ValueError("source symlinks are not audited")
                size = file.stat().st_size
                if size > max_bytes:
                    ignored_files += 1
                    raise ValueError(f"source size {size} exceeds --max-bytes {max_bytes}")
                raw = file.read_bytes()
                if schema_ext:
                    if ext == ".avsc":
                        json.loads(raw)
                    elif ext == ".proto":
                        from proto_parser import ProtoParser
                        text = raw.decode("utf-8")
                        ProtoParser.validate_structure(text)
                        ProtoParser.parse_text(text)
                    else:
                        text = raw.decode("utf-8")
                        if not re.search(r"\b(service|struct|enum|exception|union)\b", text) and ext == ".thrift":
                            raise ValueError("no supported Thrift declarations")
                        if not re.search(r"\b(record|enum|typeref|fixed|union)\b", text) and ext == ".pdl":
                            raise ValueError("no supported PDL declarations")
                elif spec.parser == "ast":
                    ast.parse(raw, filename=rel_path)
                else:
                    if not parser_available(spec):
                        raise RuntimeError(f"missing grammar: {spec.package}")
                    # .ts and .tsx require different grammars. Cache by the
                    # actual extension rather than the language's first suffix.
                    key = ext if spec.parser == "tree_sitter" else spec.name
                    parser = parser_cache.get(key)
                    if parser is None:
                        if spec.parser == "tree_sitter_legacy":
                            from tree_sitter import Language, Parser
                            grammar = importlib.import_module(GRAMMAR_MODULES[spec.name])
                            parser = Parser(Language(grammar.language()))
                        else:
                            from polyglot import TreeSitterExtractor
                            parser = TreeSitterExtractor(ext)
                        parser_cache[key] = parser
                    if spec.parser == "tree_sitter":
                        tree, grammar_used = parser.parse_source(raw)
                        if grammar_used != ext.lstrip("."):
                            grammar_recovery.append({
                                "file": rel_path,
                                "extension": ext,
                                "selected_grammar": grammar_used,
                            })
                    else:
                        tree = parser.parse(raw)
                    if tree.root_node.has_error:
                        counts["partial"] += 1
                        # Diagnostics point to parser-error syntax, not merely
                        # the file name, for repeatable root-cause analysis.
                        stack = [tree.root_node]
                        first_error = None
                        while stack:
                            item = stack.pop()
                            if item.type == "ERROR" or item.is_missing:
                                first_error = item
                                break
                            stack.extend(reversed(item.children))
                        diagnostic = {
                            "path": rel_path, "language": spec.name,
                            "reason": "tree-sitter syntax error",
                        }
                        if first_error is not None:
                            diagnostic.update({
                                "error_line": first_error.start_point.row + 1,
                                "error_column": first_error.start_point.column + 1,
                                "error_kind": first_error.type,
                                "source_excerpt": raw[first_error.start_byte:
                                                      min(first_error.start_byte + 150, len(raw))]
                                                  .decode("utf-8", "replace"),
                            })
                        failures.append(diagnostic)
                        continue
                counts["parsed"] += 1
            except Exception as exc:
                counts["failed"] += 1
                failures.append({"path": rel_path,
                                 "language": ext if schema_ext else spec.name,
                                 "reason": str(exc)[:300]})

    report = {
        "root": str(root),
        "audit_type": "grammar_and_schema_syntax_not_graph_accuracy",
        "schema_validation_note": (
            "Protobuf fallback checks structural balance, not complete grammar validation."
        ),
        "discovered_source_and_schema_files": total_files,
        "checked_scopes": [str(root)],
        "languages": {k: dict(v) for k, v in sorted(languages.items())},
        "schemas": {k: dict(v) for k, v in sorted(schema.items())},
        "unsupported_extensions": dict(sorted(unsupported.items())),
        "oversized_or_symlink_files": ignored_files,
        "parse_issue_count": len(failures),
        "grammar_recoveries": grammar_recovery[:300],
        "grammar_recovery_count": len(grammar_recovery),
        "issues": failures[:300],
        "source_coverage_complete": not failures and not unsupported and total_files > 0,
    }
    if build_graph:
        from graft_ckg import CKGBuilder
        builder = CKGBuilder(str(root))
        graph = builder.build()
        report["graph"] = {
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "relations": dict(Counter(d.get("relation", "unknown")
                                      for _, _, d in graph.edges(data=True))),
            "thrift_bindings": getattr(builder, "thrift_bindings", {}),
            "language_report": builder.get_language_report(),
            "source_coverage_complete": builder.get_language_report()["full_source_coverage"],
        }
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--expect-languages", default="")
    p.add_argument("--expect-schema", default="")
    p.add_argument("--max-bytes", type=int, default=5_000_000)
    p.add_argument("--build-graph", action="store_true")
    p.add_argument("--fail-on-incomplete", action="store_true")
    args = p.parse_args()

    report = run_audit(Path(args.root), max_bytes=args.max_bytes,
                       build_graph=args.build_graph)
    expected_langs = [s.strip() for s in args.expect_languages.split(",") if s.strip()]
    expected_schema = [s.strip() for s in args.expect_schema.split(",") if s.strip()]
    missing = [
        "language:" + lang for lang in expected_langs
        if report["languages"].get(lang, {}).get("parsed", 0) == 0
    ] + [
        "schema:" + ext for ext in expected_schema
        if report["schemas"].get("." + ext.lstrip("."), {}).get("parsed", 0) == 0
    ]
    report["missing_expected_capabilities"] = missing
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "scope": str(args.root),
        "supported_file_count": report["discovered_source_and_schema_files"],
        "languages": report["languages"],
        "schemas": report["schemas"],
        "parse_issue_count": report["parse_issue_count"],
        "unsupported_extensions": report["unsupported_extensions"],
        "missing_expected": missing,
        "issues_sample": report["issues"][:20],
        "full_coverage": report["source_coverage_complete"],
    }, indent=2))
    graph_incomplete = args.build_graph and not report["graph"]["source_coverage_complete"]
    if missing or (args.fail_on_incomplete and
                   (not report["source_coverage_complete"] or graph_incomplete)):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
