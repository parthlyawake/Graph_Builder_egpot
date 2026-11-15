# Traversal handoff: pinned polyglot repositories

## Scope and evidence semantics

The implementation on the krishna branch uses language/protocol extraction
rather than repository-specific paths. The five real repositories below are
pinned CI fixtures, not special cases in the parsers.

Confirmed HTTP_CALLS relationships and typed Thrift CONSUMES/IMPLEMENTS edges
require source evidence. POSSIBLE_HTTP_TARGET edges are conditional candidates,
NOT confirmed runtime calls. Message delivery is traced as PRODUCES_EVENT,
optionally ROUTES_TO, then a broker queue/topic consumed by CONSUMES_EVENT.
PAYLOAD_SCHEMA is a typed declaration, not runtime delivery evidence.

Green CI verifies successful construction and defined minimum coverage gates.
It does not prove exhaustive parsing, 100% edge accuracy or runtime behavior.

## CI jobs and downloadable artifacts

| Job | Artifact | Evidence gate | Caveat |
| --- | --- | --- | --- |
| train_ticket_composed | train-ticket-full-workspace | 45 modules and >=100 confirmed HTTP edges | Does not execute Spring Cloud runtime discovery |
| sockshop_composed | sockshop-composed-graph | 8 repos, >=1 confirmed RabbitMQ delivery, >=3 conditional HTTP links | HTTP edges remain conditional |
| bookinfo_composed | bookinfo-composed-graph | Four modules, >=4 conditional HTTP links | Overrideable service hostnames remain unresolved |
| datahub_graphql_contract | datahub-graphql-contract-graph | >=3,000 SDL fields, >=100 operations and >=1,000 typed selection links | Does not prove the entire DataHub web code parses |
| deathstar_graph | deathstar-source-graph | >=1 Thrift implementation and typed client consumption link | Original C/C++ grammar still reports partial parses |

Pinned run observations on November 15, 2026 (verify against current CI):
- Train-Ticket: 45 services, 19,961 nodes, 61,593 edges, 209 confirmed HTTP links.
- Sock Shop: 8 services, 6,288 nodes, 18,082 edges; 1 confirmed
  producer-to-consumer event path and 3 possible HTTP targets.
- Bookinfo: 3 possible productpage-to-service links, plus 1 possible
  Java reviews-to-Node ratings link; these reflect environment defaults.
- DataHub GraphQL schema/client scope: 4,061 fields, 339 operations,
  12,592 typed operation-to-field CONSUMES links.
- DeathStarBench Social Network: 27 Thrift handler IMPLEMENTS links and
  14 typed client CONSUMES links; 31 original-source C/C++ partial parses.

The exact Git SHA for each upstream fixture is in
.github/workflows/real-polyglot-coverage.yml.

## Loading the exported JSON into traversal

```python
from graph_io import load_graph_json
from traversal import SCKGTraversal

graph = load_graph_json("sockshop_graph.json")
engine = SCKGTraversal(graph)

producers = sorted(
    node for node in graph
    if any(data.get("relation") == "PRODUCES_EVENT"
           for _, _, data in graph.out_edges(node, data=True))
)
for producer in producers:
    for path in engine.event_delivery_paths(producer)["paths"]:
        print(path["producer"], path["queue_or_topic"], path["consumer"])
```

For GraphQL, enumerate nodes with type graphql_operation and follow their
outgoing CONSUMES edges into contract::graphql::Type::field. For Train-Ticket,
follow HTTP_CALLS from a client to the route handler. For DeathStarBench,
find incoming CONSUMES/IMPLEMENTS edges to exact Thrift RPC contract IDs.

## Traversal readiness

**Start scoped traversal tests now**: full Train-Ticket workspace HTTP edges,
verified Sock Shop RabbitMQ delivery, DataHub typed GraphQL operations
within the schema/client sample, and source-grounded Thrift RPC bindings.

**Treat as conditional**: Bookinfo and Sock Shop possible HTTP destinations.
Never mix these with confirmed edges in recall/precision evaluation.

**Not yet proven complete**: every C/C++ symbol in DeathStarBench,
all TSX/TypeScript files in the large DataHub tree, runtime-dependent
service discovery, dynamic target URLs, opaque broker policies, or exhaustive
cross-service edge precision. Partial-parser diagnostics must remain visible.

Reproduce with the Real Polyglot Repository Coverage workflow and download
its corresponding graph JSON and report artifacts. The build report includes
failed gate checks and HTTP abstention reasons. The CLI is
bench/build_workspace.py with --manifest, --report, --graph, --strict-coverage
and protocol-specific minimum counts.
