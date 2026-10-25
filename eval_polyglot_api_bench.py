"""Measure static TypeScript-to-Python API-link recovery against labelled truth.

The benchmark deliberately evaluates graph edges rather than issue-resolution:
each labelled positive is a (frontend function, backend handler) HTTP_CALLS
edge, while labelled negatives must have no HTTP_CALLS edge. Pass
--baseline-root with an upstream checkout for a controlled before/after run.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path


def load_builder(source_root: Path, label: str):
    """Import a graph builder from a source tree without changing its files."""
    source_root = source_root.resolve()
    module_path = source_root / "graft_ckg.py"
    if not module_path.is_file():
        raise FileNotFoundError(f"No graft_ckg.py at {source_root}")
    sys.path.insert(0, str(source_root))
    try:
        specification = importlib.util.spec_from_file_location(
            f"graft_ckg_{label}", module_path
        )
        module = importlib.util.module_from_spec(specification)
        assert specification.loader is not None
        specification.loader.exec_module(module)
        return module.CKGBuilder
    finally:
        sys.path.pop(0)


def evaluate(builder_class, fixture_root: Path, truth: dict) -> dict:
    started = time.perf_counter()
    builder = builder_class(fixture_root)
    graph = builder.build()
    elapsed_seconds = time.perf_counter() - started

    actual = {
        source: target
        for source, target, data in graph.edges(data=True)
        if data.get("relation") == "HTTP_CALLS"
    }
    expected = truth["expected_http_edges"]
    expected_pairs = set(expected.items())
    actual_pairs = set(actual.items())
    true_positives = len(expected_pairs & actual_pairs)
    false_positives = len(actual_pairs - expected_pairs)
    false_negatives = len(expected_pairs - actual_pairs)
    precision = true_positives / (true_positives + false_positives) if actual_pairs else 0.0
    recall = true_positives / len(expected_pairs) if expected_pairs else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    negative_violations = [
        source for source in truth["expected_no_http_edge"] if source in actual
    ]

    return {
        "graph_nodes": graph.number_of_nodes(),
        "graph_edges": graph.number_of_edges(),
        "build_seconds": round(elapsed_seconds, 4),
        "positive_cases": len(expected_pairs),
        "negative_cases": len(truth["expected_no_http_edge"]),
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "negative_cases_passed": len(truth["expected_no_http_edge"]) - len(negative_violations),
        "negative_violations": negative_violations,
        "actual_http_edges": actual,
    }


def print_result(label: str, result: dict) -> None:
    print(f"\n{label}")
    print(f"  Graph: {result['graph_nodes']} nodes, {result['graph_edges']} edges")
    print(f"  Build time: {result['build_seconds']:.4f}s")
    print(
        "  API links: "
        f"P={result['precision']:.1%}, R={result['recall']:.1%}, F1={result['f1']:.1%} "
        f"({result['true_positives']} TP, {result['false_positives']} FP, "
        f"{result['false_negatives']} FN)"
    )
    print(
        f"  Negative cases: {result['negative_cases_passed']}/{result['negative_cases']} passed"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).parent
    parser.add_argument("--fixture", type=Path, default=root / "benchmarks" / "polyglot_api")
    parser.add_argument("--baseline-root", type=Path, help="Upstream source checkout to compare.")
    parser.add_argument("--json-out", type=Path, help="Optional path for machine-readable results.")
    args = parser.parse_args()

    fixture = args.fixture.resolve()
    truth = json.loads((fixture / "ground_truth.json").read_text(encoding="utf-8"))
    results = {"current": evaluate(load_builder(root, "current"), fixture, truth)}
    if args.baseline_root:
        results["baseline"] = evaluate(
            load_builder(args.baseline_root, "baseline"), fixture, truth
        )

    for label in ("baseline", "current"):
        if label in results:
            print_result(label.title(), results[label])
    if args.json_out:
        args.json_out.write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
