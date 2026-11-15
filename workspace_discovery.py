"""Discover independent application modules for multi-service graph composition.

Based on build manifests and declared service identities, not repository names.
The generated manifest is an auditable input to WorkspaceCKGBuilder.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml

SKIP = {".git", ".gradle", "node_modules", "vendor", "target", "build",
        "dist", "__pycache__", ".venv", "testdata", "fixtures"}


def _spring_name(root):
    names = set()
    resource = root / "src" / "main" / "resources"
    for name in ("application.yml", "application.yaml", "bootstrap.yml", "bootstrap.yaml"):
        path = resource / name
        if not path.is_file():
            continue
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(value, dict):
            continue
        spring = value.get("spring", {})
        if isinstance(spring, dict):
            app = spring.get("application", {})
            if isinstance(app, dict) and isinstance(app.get("name"), str):
                if re.fullmatch(r"[A-Za-z0-9_.-]+", app["name"]):
                    names.add(app["name"])
    props = resource / "application.properties"
    if props.is_file():
        for line in props.read_text(encoding="utf-8").splitlines():
            match = re.fullmatch(r"\s*spring\.application\.name\s*=\s*([A-Za-z0-9_.-]+)\s*", line)
            if match:
                names.add(match[1])
    return next(iter(names)) if len(names) == 1 else None


def _module_marker(path):
    java = (path.joinpath("src", "main").is_dir() and
            any((path / n).is_file() for n in
                ("pom.xml", "build.gradle", "build.gradle.kts")))
    manifest = any((path / n).is_file() for n in ("go.mod", "package.json"))
    # Pre-module Go projects can use dep/glide/Godeps or a Makefile instead
    # of go.mod. An actual Go source file plus a build manifest is required.
    old_go = ((path / "Makefile").is_file() and
              any(path.glob("*.go")))
    return java or manifest or old_go


def discover_modules(root):
    root = Path(root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(str(root))
    modules = []
    occupied = set()
    import os
    for base, directories, _ in os.walk(root):
        directories[:] = sorted(d for d in directories if d not in SKIP)
        path = Path(base)
        if not _module_marker(path):
            continue
        rel = path.relative_to(root).as_posix()
        declared = _spring_name(path)
        name = declared or path.name
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            continue
        modules.append({"id": name, "path": "." if rel == "." else rel,
                        "identity_source": "spring.application.name" if declared
                        else "build_manifest_directory"})
        occupied.add(path)
        directories[:] = []  # A discovered build root owns its nested packages.
    # Duplicate declared service names make ownership ambiguous. Fail rather
    # than merge different service sources into one namespace.
    names = [m["id"] for m in modules]
    if len(names) != len(set(names)):
        raise ValueError("duplicate service identities in discovered source modules")
    return modules


def workspace_manifest(root, *, name="discovered-workspace"):
    root = Path(root).resolve()
    modules = discover_modules(root)
    return {
        "name": name, "version": "1.0",
        "repositories": [{"id": x["id"], "path": x["path"]} for x in modules],
        "discovery_evidence": modules,
        "strict_http_source_evidence": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--build-graph", action="store_true")
    parser.add_argument("--require-cross-service-http", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    manifest = workspace_manifest(root)
    if not manifest["repositories"]:
        raise SystemExit("No independent source modules found")
    output = Path(args.manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    result = {"root": str(root), "service_count": len(manifest["repositories"]),
              "services": manifest["discovery_evidence"],
              "scope": "build-manifest discovered independent modules"}
    if args.build_graph:
        from multi_repo import WorkspaceConfig, WorkspaceCKGBuilder
        builder = WorkspaceCKGBuilder(WorkspaceConfig.from_dict(manifest, str(root)))
        builder.build()
        verified = builder.verify_graph()
        result["graph"] = verified
        if args.require_cross_service_http and verified["http_calls_edges"] < 1:
            result["error"] = "No HTTP_CALLS found; cross-service traversal unsupported"
    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"service_count": result["service_count"],
                      "total_nodes": result.get("graph", {}).get("total_nodes"),
                      "total_edges": result.get("graph", {}).get("total_edges"),
                      "http_calls": result.get("graph", {}).get("http_calls_edges"),
                      "source_coverage": result.get("graph", {}).get("source_coverage_complete")},
                     indent=2))
    if result.get("error"):
        raise SystemExit(result["error"])


if __name__ == "__main__":
    main()
