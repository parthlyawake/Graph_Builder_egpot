"""Source-pinned Train-Ticket REST route probe, separate from closed-scope P/R."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
from pathlib import Path

from graft_ckg import CKGBuilder

SRC = "ts-order-service/src/main/java/order/controller/OrderController.java"
PREFIX = "/api/v1/orderservice"
CASES = (
    ("home", "GET", "/welcome", '@GetMapping(path = "/welcome")'),
    ("createNewOrder", "POST", "/order", '@PostMapping(path = "/order")'),
    ("getOrderPrice", "GET", "/order/price/{orderId}", '@GetMapping(path = "/order/price/{orderId}")'),
)


def inspect(root: Path) -> dict:
    source = (root / SRC)
    text = source.read_text(encoding="utf-8")
    if not ('@RestController' in text and '@RequestMapping("/api/v1/orderservice")' in text):
        raise ValueError("Source controller/prefix differs from pinned annotation")
    with contextlib.redirect_stdout(io.StringIO()):
        builder = CKGBuilder(str(root))
        builder.build()
    facts = []
    for name, method, suffix, decorator in CASES:
        if decorator not in text or f" {name}(" not in text:
            raise ValueError("Unverifiable source endpoint annotation: " + name)
        nodes = [nid for nid, data in builder.graph.nodes(data=True)
                 if data.get("type") in {"method","function"}
                 and data.get("name") == name and SRC in str(data.get("file",""))]
        full_path = PREFIX + suffix
        registry = builder.http_endpoints.get((method, full_path), [])
        candidate_edges = [
            (u,v,d.get("relation")) for u,v,d in builder.graph.edges(data=True)
            if any(n in (u,v) for n in nodes) and d.get("layer") == "Lcontract"
        ]
        facts.append({
            "handler": name, "expected_method": method, "source_path": full_path,
            "source_annotation_verified": True, "code_nodes":nodes,
            "registered_handler_ids":registry, "nearby_contract_edge_count":len(candidate_edges),
            "registered_exact_route": bool(registry),
            "notes":"A registered route is a graph claim; source existence alone does not establish cross-service client binding."
        })
    return {"repo":"FudanSELab/train-ticket","sha":"313886e99befb94be6cd45f085c98e0019f59829",
            "source_file":SRC,"scope":"three exact Java Spring route declarations, not whole service",
            "handler_nodes_found":sum(bool(x["code_nodes"]) for x in facts),
            "route_registrations_found":sum(x["registered_exact_route"] for x in facts),
            "cases":facts,"human_review_status":"pending independent reviewers"}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--repo",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    result=inspect(Path(args.repo))
    output=Path(args.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"source_anchors":len(result["cases"]),
                      "handler_nodes_found":result["handler_nodes_found"],
                      "route_registrations_found":result["route_registrations_found"]}, indent=2))


if __name__=="__main__":
    main()
