"""Source-grounded, exact-ID graph verification. No substring matching or assumed precision."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import shutil
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def edge(item):
    if isinstance(item, dict):
        return item["source"], item["relation"], item["target"]
    if isinstance(item, (list, tuple)) and len(item) == 3:
        return tuple(item)
    raise ValueError("Edge requires source, relation, target")


def edges(graph):
    return {(str(u), str(data.get("relation", "")), str(v))
            for u, v, data in graph.edges(data=True)}


def metrics(truth, predicted):
    tp, fp, fn = truth & predicted, predicted - truth, truth - predicted
    precision = len(tp) / len(predicted) if predicted else (1.0 if not truth else 0.0)
    recall = len(tp) / len(truth) if truth else None
    f1 = (2 * precision * recall / (precision + recall)) if recall is not None and precision + recall else (0.0 if recall is not None else None)
    return {"tp": len(tp), "fp": len(fp), "fn": len(fn), "precision": precision,
            "recall": recall, "f1": f1, "missing": sorted(map(list, fn)),
            "unexpected": sorted(map(list, fp))}


def evaluate(graph, labels, source_root=None):
    """Source evidence is checked against real source, not inferred from graph nodes.

    closed_scopes enumerate all expected outgoing edges for each named source
    and relation. Only such declared complete scopes yield valid precision.
    """
    if not isinstance(labels, dict):
        raise ValueError("Expected a label object")
    actual = edges(graph)
    node_labels = labels.get("nodes", [])
    edge_labels = labels.get("edges", [])
    positives = [edge(item) for item in edge_labels]
    if len(set(positives)) != len(positives):
        raise ValueError("Duplicate ground-truth edges")
    truth = set(positives)
    negatives = {edge(item) for item in labels.get("negatives", [])}
    if truth & negatives:
        raise ValueError("Contradictory positive and negative labels")
    evidence = {"verified": 0, "missing": 0, "unavailable": 0, "failures": []}
    for item in node_labels + edge_labels:
        proof = item.get("evidence", {})
        if not source_root or not proof:
            evidence["unavailable"] += 1
            continue
        root = Path(source_root).resolve()
        file = proof.get("file")
        marker = proof.get("contains")
        target = (root / str(file)).resolve() if file else root
        failure = None
        if not file or not isinstance(marker, str) or not marker:
            failure = "missing_file_or_source_marker"
        elif root not in target.parents:
            failure = "path_outside_source_root"
        elif not target.is_file():
            failure = "source_file_unavailable"
        elif marker not in target.read_text(encoding="utf-8", errors="replace"):
            failure = "source_marker_not_found"
        if failure:
            evidence["missing"] += 1
            evidence["failures"].append({
                "label": str(item.get("id") or
                             (item.get("source"), item.get("relation"), item.get("target"))),
                "source_file": file,
                "marker": marker[:120] if isinstance(marker, str) else None,
                "reason": failure,
            })
        else:
            evidence["verified"] += 1
    node_truth = {str(item["id"]) for item in node_labels}
    absent_nodes = sorted(node_truth - set(graph.nodes))
    result = {
        "nodes": {"labelled": len(node_truth), "found": len(node_truth) - len(absent_nodes),
                  "missing": absent_nodes, "recall": (len(node_truth) - len(absent_nodes)) / len(node_truth) if node_truth else None,
                  "precision": None},
        "sampled_edges": {"labelled": len(truth), "found": len(truth & actual),
                          "missing": sorted(map(list, truth - actual)),
                          "recall": len(truth & actual) / len(truth) if truth else None,
                          "precision": None},
        "negative_violations": sorted(map(list, negatives & actual)),
        "source_evidence": evidence,
        "closed_scopes": [],
        "closed_node_scopes": [],
        "by_relation_language": {},
        "status": labels.get("status", "unspecified"),
    }
    for scope in labels.get("closed_node_scopes", []):
        node_type, files = scope["type"], set(scope["files"])
        if not files:
            raise ValueError("Empty closed node scope")
        expected_nodes = {(str(item["id"]),) for item in node_labels
                          if item.get("type") == node_type and item.get("file") in files}
        graph_nodes = {(str(node),) for node, data in graph.nodes(data=True)
                       if data.get("type") == node_type and data.get("file") in files}
        result["closed_node_scopes"].append({
            "type": node_type, "files": sorted(files),
            "language": scope.get("language", "unspecified"),
            **metrics(expected_nodes, graph_nodes)})
    grouped = defaultdict(set)
    for item in edge_labels:
        grouped[(item["relation"], item.get("language", "unspecified"))].add(edge(item))
    for (relation, language), group in sorted(grouped.items()):
        result["by_relation_language"][relation + "|" + language] = {
            "labelled": len(group), "found": len(group & actual),
            "recall": len(group & actual) / len(group), "precision": None}
    for scope in labels.get("closed_scopes", []):
        relation, sources = scope["relation"], set(scope["sources"])
        if not sources:
            raise ValueError("Empty closed scope")
        expected = {e for e in truth if e[1] == relation and e[0] in sources}
        predicted = {e for e in actual if e[1] == relation and e[0] in sources}
        result["closed_scopes"].append({
            "relation": relation, "language": scope.get("language", "unspecified"),
            "source_count": len(sources), **metrics(expected, predicted)})
    result["passed"] = not absent_nodes and not result["sampled_edges"]["missing"] and not result["negative_violations"] and evidence["missing"] == 0 and all(s["fp"] == 0 for s in result["closed_scopes"]) and all(s["fp"] == 0 for s in result["closed_node_scopes"])
    result["publication_ready"] = (result["passed"] and bool(result["closed_scopes"]) and bool(result["closed_node_scopes"])
                                   and evidence["unavailable"] == 0 and evidence["missing"] == 0
                                   and labels.get("status") == "independently_reviewed")
    return result


def evaluate_trace(graph, trace):
    """Observed runtime events establish recall of exercised paths, not static precision."""
    observed = {edge(e) for e in trace.get("observed_edges", [])}
    found = observed & edges(graph)
    return {"observed": len(observed), "matched": len(found),
            "observed_recall": len(found) / len(observed) if observed else None,
            "missing_observed_edges": sorted(map(list, observed - found)),
            "static_precision": None,
            "note": "Unexecuted static edges are not necessarily false positives."}


def signature(graph):
    """Ignore volatile attributes; retain exact IDs, node type and typed edge multiplicity."""
    return {
        "nodes": sorted((str(n), str(d.get("type", "")), str(d.get("file", "")),
                         str(d.get("name", "")), str(d.get("line_no", "")))
                        for n, d in graph.nodes(data=True)),
        "edges": sorted((str(u), str(d.get("relation", "")), str(v), str(d.get("layer", "")))
                        for u, v, d in graph.edges(data=True)),
    }


def evaluate_mutation(repo, spec):
    """Modify only a temporary copy; require exact full/incremental graph agreement."""
    from graft_ckg import CKGBuilder

    relative = Path(spec["file"])
    if relative.is_absolute() or ".." in relative.parts or not spec.get("old"):
        raise ValueError("Unsafe mutation path or missing old text")
    with tempfile.TemporaryDirectory(prefix="ckg_accuracy_") as temp:
        copy = Path(temp) / "repo"
        shutil.copytree(Path(repo).resolve(), copy,
                        ignore=shutil.ignore_patterns(".git", ".venv", "node_modules", "__pycache__", "*.pyc"))
        target = copy / relative
        original = target.read_text(encoding="utf-8")
        if original.count(spec["old"]) != 1:
            raise ValueError("Mutation anchor must occur exactly once")
        with contextlib.redirect_stdout(io.StringIO()):
            incremental = CKGBuilder(str(copy))
            incremental.build()
        before = signature(incremental.graph)
        target.write_text(original.replace(spec["old"], spec["new"], 1), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            incremental.update_files([relative.as_posix()])
            rebuilt = CKGBuilder(str(copy))
            rebuilt.build()
        inc, fresh = signature(incremental.graph), signature(rebuilt.graph)
        before_nodes, after_nodes = {r[0] for r in before["nodes"]}, {r[0] for r in fresh["nodes"]}
        new_nodes, deleted_nodes = after_nodes - before_nodes, before_nodes - after_nodes
        before_edges, after_edges = set(map(tuple, before["edges"])), set(map(tuple, fresh["edges"]))
        new_edges, deleted_edges = after_edges - before_edges, before_edges - after_edges
        checks = {
            "expected_added_nodes": set(spec.get("expected_added_nodes", [])) <= new_nodes,
            "expected_removed_nodes": set(spec.get("expected_removed_nodes", [])) <= deleted_nodes,
            "expected_added_edges": {tuple(e) for e in spec.get("expected_added_edges", [])} <= new_edges,
            "expected_removed_edges": {tuple(e) for e in spec.get("expected_removed_edges", [])} <= deleted_edges,
        }
        return {"incremental_equals_full": inc == fresh, "changed": before != fresh,
                "checks": checks, "passed": inc == fresh and before != fresh and all(checks.values()),
                "added_nodes": sorted(new_nodes), "removed_nodes": sorted(deleted_nodes),
                "added_edges": [list(e) for e in sorted(new_edges)],
                "removed_edges": [list(e) for e in sorted(deleted_edges)]}


def load_graph(args):
    if args.graph_json:
        from networkx.readwrite import json_graph
        return json_graph.node_link_graph(json.loads(Path(args.graph_json).read_text(encoding="utf-8")), edges="links")
    if args.workspace:
        from multi_repo import WorkspaceCKGBuilder
        builder = WorkspaceCKGBuilder(args.workspace)
    else:
        from graft_ckg import CKGBuilder
        builder = CKGBuilder(args.repo)
    with contextlib.redirect_stdout(io.StringIO()):
        builder.build()
    return builder.graph


def main(argv=None):
    parser = argparse.ArgumentParser(description="Independent graph verification against exact source labels")
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--repo")
    inputs.add_argument("--workspace")
    inputs.add_argument("--graph-json")
    parser.add_argument("--labels", required=True)
    parser.add_argument("--source-root")
    parser.add_argument("--trace", help="JSON with observed_edges; provide actual instrumented observations")
    parser.add_argument("--mutation", help="JSON edit spec; requires --repo")
    parser.add_argument("--output")
    parser.add_argument("--fail-on-missing", action="store_true")
    args = parser.parse_args(argv)
    if args.mutation and not args.repo:
        parser.error("--mutation requires --repo")
    graph = load_graph(args)
    labels = json.loads(Path(args.labels).read_text(encoding="utf-8"))
    report = {"graph_nodes": graph.number_of_nodes(), "graph_edges": graph.number_of_edges(),
              "static": evaluate(graph, labels, source_root=args.source_root)}
    if args.trace:
        report["runtime"] = evaluate_trace(graph, json.loads(Path(args.trace).read_text(encoding="utf-8")))
    if args.mutation:
        report["mutation"] = evaluate_mutation(args.repo, json.loads(Path(args.mutation).read_text(encoding="utf-8")))
    output = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    print(output)
    if args.fail_on_missing and (not report["static"]["passed"] or
            ("runtime" in report and report["runtime"]["missing_observed_edges"]) or
            ("mutation" in report and not report["mutation"]["passed"])):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
