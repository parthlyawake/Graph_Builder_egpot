"""Compare locally rebuilt graphs with the pinned pre-fix audit snapshots."""

import argparse
import json
from pathlib import Path
import pickle


SYSTEMS = (
    "microservices-demo", "opentelemetry-demo", "retail-store-sample-app",
    "robot-shop", "bookinfo", "train-ticket", "DeathStarBench", "sock-shop",
)


def load_graph(root, system):
    with (root / system / "graph.pkl").open("rb") as stream:
        return pickle.load(stream)  # Only load graphs generated locally by audit_graph_builder.py.


def targets(graph, node, relation):
    return [target for _, target, data in graph.out_edges(node, data=True)
            if data.get("relation") == relation]


def duplicate_http_names(graph):
    old = {data["name"] for _, data in graph.nodes(data=True) if data.get("type") == "endpoint"}
    new = {data["name"] for _, data in graph.nodes(data=True) if data.get("type") == "http_endpoint"}
    return len(old & new)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    before = args.before.resolve()
    after = args.after.resolve()
    result = {"systems": {}, "checks": {}}
    matched = contained = sampled = 0

    for system in SYSTEMS:
        old_graph, graph = load_graph(before, system), load_graph(after, system)
        summary = json.loads((after / system / "summary.json").read_text(encoding="utf-8"))
        sample_set = json.loads((after / system / "samples.json").read_text(encoding="utf-8"))["samples"]
        sampled += len(sample_set)
        matched += sum(bool(item["graph_node"]) for item in sample_set)
        contained += sum(any(edge["relation"] == "CONTAINS" and edge["direction"] == "in"
                             for edge in item["edges"]) for item in sample_set)
        result["systems"][system] = {
            "source_files": summary["parsed_files"],
            "nodes": summary["nodes"], "edges": summary["edges"],
            "build_warnings": len(summary["log_warnings"]),
            "duplicate_http_names_before": duplicate_http_names(old_graph),
            "duplicate_http_names_after": duplicate_http_names(graph),
            "dynamic_http_callsites_after": sum(1 for _, data in graph.nodes(data=True)
                                                if data.get("type") == "http_callsite"),
        }

    result["sample"] = {"declarations": sampled, "matching_nodes": matched,
                        "containment_edges": contained}
    robot = load_graph(after, "robot-shop")
    retail = load_graph(after, "retail-store-sample-app")
    boutique = load_graph(after, "microservices-demo")
    otel = load_graph(after, "opentelemetry-demo")
    deathstar = load_graph(after, "DeathStarBench")
    result["checks"] = {
        "java_system_getenv_external": "external::System.getenv" in targets(
            robot, "shipping/src/main/java/com/instana/robotshop/shipping/Controller.java:Controller.getenv", "CALLS"),
        "java_getenv_no_false_self_call": "shipping/src/main/java/com/instana/robotshop/shipping/Controller.java:Controller.getenv" not in targets(
            robot, "shipping/src/main/java/com/instana/robotshop/shipping/Controller.java:Controller.getenv", "CALLS"),
        "go_catalog_reindex_resolved": "src/catalog/api/catalog.go:CatalogAPI.Reindex" in targets(
            retail, "src/catalog/controller/controller.go:Controller.ReindexProducts", "CALLS"),
        "csharp_ping_declared": "src/cartservice/src/cartstore/ICartStore.cs:ICartStore.Ping" in targets(
            boutique, "src/cartservice/src/cartstore/ICartStore.cs:ICartStore", "DECLARES"),
        "go_anonymous_blob_absent": not any(
            node.startswith("external::func()") for node in targets(
                boutique, "src/productcatalogservice/server.go:main", "CALLS")),
        "otel_ship_order_callsite": any(
            otel.nodes[node]["name"] == "POST /ship-order (host unresolved)"
            for node in targets(otel, "src/checkout/main.go:checkout.shipOrder", "HTTP_REQUEST")),
        "deathstar_movie_write_callsite": any(
            deathstar.nodes[node]["name"] == "POST /wrk2-api/movie-info/write (host unresolved)"
            for node in targets(deathstar, "mediaMicroservices/scripts/write_movie_info.py:upload_movie_info", "HTTP_REQUEST")),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    if (sampled != 24 or matched != sampled or contained != sampled
            or any(data["duplicate_http_names_after"] for data in result["systems"].values())
            or any(data["build_warnings"] for data in result["systems"].values())
            or not all(result["checks"].values())):
        raise SystemExit("Graph audit fix verification failed; see output JSON")
    print(f"Verified {len(SYSTEMS)} builds, {matched}/{sampled} sampled nodes, and all targeted checks")


if __name__ == "__main__":
    main()
