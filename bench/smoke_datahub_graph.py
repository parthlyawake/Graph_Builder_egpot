"""Pinned DataHub source-subtree smoke test for graph generation.

Run: python bench/smoke_datahub_graph.py --repo /path/to/datahub/datahub-actions/src

Creates a temporary copy, injects a small Python function, compares the exact
node set and typed edge multiplicities against a fresh full build, then writes
repeatable metrics. No DataHub files are modified.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import shutil
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from graft_ckg import CKGBuilder


def signature(graph):
    return (
        set(graph.nodes),
        Counter((u, data.get("relation"), v, data.get("layer"))
                for u, v, data in graph.edges(data=True)),
    )


def run_once(repo: Path, edit_file: str):
    with tempfile.TemporaryDirectory(prefix="sckg_datahub_") as temp:
        workspace = Path(temp) / "repo"
        shutil.copytree(repo, workspace)
        source = workspace / edit_file
        if not source.is_file():
            raise FileNotFoundError(source)

        builder = CKGBuilder(str(workspace))
        with contextlib.redirect_stdout(io.StringIO()):
            started = time.perf_counter()
            builder.build()
            full_s = time.perf_counter() - started

        with source.open("a", encoding="utf-8") as handle:
            handle.write(
                "\n\ndef sckg_incremental_probe(value: int) -> int:\n"
                "    return value + 1\n"
            )
        with contextlib.redirect_stdout(io.StringIO()):
            started = time.perf_counter()
            builder.update_files([edit_file])
            incremental_s = time.perf_counter() - started

        refreshed = CKGBuilder(str(workspace))
        with contextlib.redirect_stdout(io.StringIO()):
            started = time.perf_counter()
            refreshed.build()
            fresh_after_s = time.perf_counter() - started

        updated_sig = signature(builder.graph)
        fresh_sig = signature(refreshed.graph)
        if updated_sig != fresh_sig:
            missing_nodes = fresh_sig[0] - updated_sig[0]
            extra_nodes = updated_sig[0] - fresh_sig[0]
            missing_edges = fresh_sig[1] - updated_sig[1]
            extra_edges = updated_sig[1] - fresh_sig[1]
            raise AssertionError(
                f"Incremental graph != fresh graph: missing nodes={len(missing_nodes)}, "
                f"extra nodes={len(extra_nodes)}, missing typed edges="
                f"{sum(missing_edges.values())}, extra typed edges="
                f"{sum(extra_edges.values())}; examples="
                f"{list(missing_edges.items())[:3]}"
            )

        expected = f"{edit_file}:sckg_incremental_probe"
        if expected not in builder.graph:
            raise AssertionError(f"Injected symbol not indexed: {expected}")

        layers = Counter(data.get("layer", "untyped")
                         for _, _, data in refreshed.graph.edges(data=True))
        return {
            "source_files": sum(data.get("type") == "file"
                                for _, data in refreshed.graph.nodes(data=True)),
            "nodes": refreshed.graph.number_of_nodes(),
            "edges": refreshed.graph.number_of_edges(),
            "layers": dict(layers),
            "baseline_build_seconds": round(full_s, 6),
            "incremental_seconds": round(incremental_s, 6),
            "fresh_postedit_seconds": round(fresh_after_s, 6),
            "equivalence": True,
            "injected_symbol": expected,
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--edit-file", default="datahub_actions/action/action_stats.py")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("bench/results/datahub_smoke.json"))
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("--repetitions must be positive")
    if not args.repo.is_dir():
        parser.error(f"Missing source directory: {args.repo}")
    results = [run_once(args.repo, args.edit_file) for _ in range(args.repetitions)]
    report = {"subtree": str(args.repo), "repetitions": args.repetitions,
              "all_equivalent": all(r["equivalence"] for r in results),
              "trials": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
