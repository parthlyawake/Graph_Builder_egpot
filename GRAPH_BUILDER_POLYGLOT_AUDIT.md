# Graph builder audit on the polyglot repository list

**Run date:** 2026-10-25

**Builder revision:** [`3ce1ba2`](https://github.com/SNK0-0/SCKG_Build/commit/3ce1ba2c654305180aad9d8ea4135b1efeebb4df) (`main`)

**Scope:** graph construction, source nodes, containment, calls, and contracts. **No retrieval, ranking, or runtime execution was tested.**

## Verdict

The builder completed on all eight entries in the [polyglot repository list](https://github.com/Vikas-Personal-Research-Org/polygot-repo-list). Across a seeded, language-stratified sample, **24/24 source declarations had matching function nodes and 24/24 had a `CONTAINS` edge**. Those results establish basic node creation for the sampled code; they do not establish that every dependency edge is correct. Manual edge checks found a false Java self-call, a missed Go method binding, duplicate HTTP contract nodes, and missing service links for dynamic URLs. DeathStarBench contains C++/Thrift application code that this builder does not parse, and the listed Sock Shop repository contains deployment assets rather than its service implementations.

**Do not describe these eight builds as full multi-language or cross-service correctness.** The output is useful for graph inspection, but it needs the fixes below before it supports that claim.

## Method

1. Pinned each upstream repository at the commit shown below. Used `samples/bookinfo` for Istio because the list names Bookinfo rather than all of Istio.
2. Built each graph with `CKGBuilder.build()` from `main` and saved a build log, graph snapshot, and summary. No retrieval method was called.
3. Independently parsed source declarations with Python `ast` and tree-sitter, excluding generated/minified and test paths. With seed `20261025`, selected one declaration from each of the three most represented supported language extensions per repository, or all available declarations if fewer than three. The sampling code chose from source files **before** looking up graph nodes.
4. For each selected declaration, compared its source file, name, and line to the graph node; checked its incoming containment edge; then read its body and inspected relevant outgoing/incoming calls and contract edges. Added targeted protocol checks where a random sample did not exercise a contract.

The code and compact evidence are in [`bench/audit_graph_builder.py`](bench/audit_graph_builder.py), [`bench/audit_source_samples.py`](bench/audit_source_samples.py), and [`bench/results/graph_builder_audit/`](bench/results/graph_builder_audit/). Raw graphs and upstream clones are local validation artifacts, not part of the repository.

## Build results

`Source files` counts files read by the builder; `.proto` files are parsed separately. Node and edge totals are raw graph sizes, not accuracy scores. Every build log had zero parser warnings.

| System and pinned revision | Scope | Source files | Nodes | Edges | Sampled node / containment |
| --- | --- | ---: | ---: | ---: | ---: |
| [Online Boutique `38e7348`](https://github.com/GoogleCloudPlatform/microservices-demo/tree/38e7348eb289eb5b87c0c6e8cb19ced0449dc389) | Full clone | 47 | 2,126 | 5,744 | 3/3 · 3/3 |
| [OpenTelemetry Astronomy Shop `5c8d404`](https://github.com/open-telemetry/opentelemetry-demo/tree/5c8d404a85380226ff45a39dcb4159eda9552c56) | Full clone | 207 | 5,585 | 16,631 | 3/3 · 3/3 |
| [AWS Retail Store Sample `d7a380b`](https://github.com/aws-containers/retail-store-sample-app/tree/d7a380b843e0759e58754f74188ea18252a51415) | Full clone | 274 | 5,498 | 13,320 | 3/3 · 3/3 |
| [Stan's Robot Shop `55292e2`](https://github.com/instana/robot-shop/tree/55292e2199f2fb00a165b1f7d3045fe7f8922038) | Full clone | 22 | 766 | 1,605 | 3/3 · 3/3 |
| [Istio Bookinfo `64b84bc`](https://github.com/istio/istio/tree/64b84bc308d5533e26f71ab7241e2c3eb927d67e/samples/bookinfo) | `samples/bookinfo` only | 9 | 345 | 639 | 3/3 · 3/3 |
| [Train-Ticket `313886e`](https://github.com/FudanSELab/train-ticket/tree/313886e99befb94be6cd45f085c98e0019f59829) | Full clone | 716 | 33,707 | 150,267 | 3/3 · 3/3 |
| [DeathStarBench `6ecb097`](https://github.com/delimitrou/DeathStarBench/tree/6ecb09706140f8730b5385c08f1386c654c3c526) | Source-focused extraction of three apps | 131 | 10,336 | 37,371 | 3/3 · 3/3 |
| [Sock Shop `9dff06f`](https://github.com/microservices-demo/microservices-demo/tree/9dff06fae4981921caec6a62393a6ebfce4b3e3f) | Listed umbrella repo | 4 | 31 | 64 | 3/3 · 3/3 |

DeathStarBench's Git tree includes filenames that Windows cannot check out. I used its pinned archive and extracted source/readme files from `hotelReservation`, `mediaMicroservices`, and `socialNetwork`; binary assets and other directories were omitted. Sock Shop's listed repository has only dashboard Python functions among supported source files. Its actual Go, Java, and Node.js services live in separate repositories, so its three sampled functions are dashboard helpers, not shop business logic.

## Source-to-graph manual checks

The full source snippets and graph neighbor lists for each row are in the corresponding `samples.json` evidence file. `PASS` means the stated relationship was observed for that sample; `PARTIAL` or `FAIL` names an observed gap. A sample passing does not prove every edge in the function is correct.

| System | Seeded source declaration | Source-versus-graph observation |
| --- | --- | --- |
| Online Boutique | Go `productcatalogservice.main` | **PARTIAL:** node is under its file; calls to local `initTracing`, `initProfiling`, and `run` resolve. An invoked anonymous function also becomes a long `external::func() { ... }` pseudo-target. |
| Online Boutique | Python `send_confirmation_email` | **PASS:** calls include the gRPC stub and the node `CONSUMES` `EmailService.SendOrderConfirmation`. |
| Online Boutique | C# `ICartStore.Ping` | **PARTIAL:** method signature exists under `ICartStore` via `CONTAINS`; no `DECLARES` contract edge is emitted for this C# interface member. |
| Astronomy Shop | Python `WebsiteUser.index` | **PASS:** class containment and calls to `self.client.get`, tracer, and logging are represented. The HTTP client target remains external. |
| Astronomy Shop | Go `checkout.shipOrder` | **PARTIAL:** call edges include `http.NewRequestWithContext` and `cs.httpClient.Do`; there is no `HTTP_CALLS` edge to the shipping handler because the URL joins a configured address with `"/ship-order"`. |
| Astronomy Shop | TypeScript `SessionIdProcessor.forceFlush` | **PASS:** class containment and `Promise.resolve` call are present. |
| AWS Retail | Java `ShippingAddress.getAddress1` | **PASS:** getter is contained by `ShippingAddress`; the body has no call to resolve. |
| AWS Retail | TypeScript `RedisCheckoutRepository.readClient` | **PASS:** internal `buildClient` call resolves to a method node in the same class. |
| AWS Retail | Go `Controller.ReindexProducts` | **PARTIAL:** `CatalogAPI.IsSearchEnabled` resolves, but `c.api.Reindex()` points to `external::c.api.Reindex` even though `CatalogAPI.Reindex` is a graph node. |
| Robot Shop | Java `Controller.getenv` | **FAIL:** source calls `System.getenv(key)`; graph creates a `CALLS` edge from `Controller.getenv` back to itself instead of the external `System.getenv`. |
| Robot Shop | JavaScript `autoComplete.removeEvent` | **PASS:** calls to `el.detachEvent` and `el.removeEventListener` are represented. |
| Robot Shop | Python `Publisher._publish` | **PASS:** `basic_publish`, JSON encoding, and logger calls appear; `Publisher.publish` calls this method. |
| Bookinfo | Python `metrics` | **PASS:** node implements `GET /metrics` and calls `generate_latest`. |
| Bookinfo | JavaScript `getLocalReviews` | **PASS:** the node is called by `getLocalReviewsSuccessful` and `putLocalReviews`. |
| Bookinfo | Java `LibertyRestEndpoint.getRatings` | **PARTIAL:** Java invocation edges such as `ClientBuilder.newBuilder`, `cb.property`, and `client.target` are present. The service URL is assembled from values, so no HTTP service edge is produced. |
| Train-Ticket | Java `SecurityConfig.corsConfigurer` | **PASS:** class containment and nested `addCorsMappings` containment are present. |
| Train-Ticket | JavaScript `setTodayDatePreserve` | **PASS:** Date construction and date/DOM calls appear. |
| Train-Ticket | Python `GetVoucherHandler.queryOrderByIdAndType` | **PARTIAL:** `urllib.request.urlopen` appears as an external call, but configured order-service URLs have no cross-service HTTP edge. |
| DeathStarBench | Go `RatePlans.Less` | **PASS:** node is contained by `RatePlans`; the body accesses fields without a function call. |
| DeathStarBench | JavaScript `getTime` | **PASS:** incoming calls from timeline functions and outgoing Date/formatting calls appear. |
| DeathStarBench | Python `upload_movie_info` | **PARTIAL:** `session.post` is represented, but `addr + "/wrk2-api/movie-info/write"` does not resolve to a service endpoint. |
| Sock Shop | Python `service_qps_graph` | **PASS for dashboard code:** `service_row` calls it; graph construction calls such as `Graph` and `Target` appear. |
| Sock Shop | Python `service_latency_graph` | **PASS for dashboard code:** `service_row` calls it; graph construction calls appear. |
| Sock Shop | Python `service_row` | **PASS for dashboard code:** calls both dashboard graph helpers. |

## Targeted contract and coverage checks

- **Spring and Flask routes are present.** AWS Retail's `TopologyController.info` implements `GET /topology`; Train-Ticket's `OrderController.getTicketListByDateAndTripId` implements `POST /api/v1/orderservice/order/tickets`; Bookinfo's `metrics` implements `GET /metrics`. These were checked against source annotations/decorators and graph edges.
- **Merged HTTP representations are duplicated.** The same named route appears as both an `endpoint` node (`contract::HTTP.GET./topology`) and an `http_endpoint` node (`http::GET:/topology`) in AWS Retail. There are **44 duplicated route names** in AWS Retail, **9** in Robot Shop, and **262** in Train-Ticket. Handler methods can have two `IMPLEMENTS` edges for one route. This is a confirmed graph-model defect introduced by combining the existing Spring contract representation with the newer HTTP contract representation.
- **Dynamic HTTP calls remain unlinked.** Astronomy Shop's [`shipOrder`](https://github.com/open-telemetry/opentelemetry-demo/blob/5c8d404a85380226ff45a39dcb4159eda9552c56/src/checkout/main.go#L622-L636) creates a POST URL using `shippingSvcAddr`. The graph records the HTTP library calls but no `HTTP_CALLS` or endpoint `CONSUMES` edge. This matches the implementation's static-literal limitation, but limits affected-service analysis.
- **Java false binding.** Robot Shop's [`Controller.getenv`](https://github.com/instana/robot-shop/blob/55292e2199f2fb00a165b1f7d3045fe7f8922038/shipping/src/main/java/com/instana/robotshop/shipping/Controller.java#L34-L38) calls `System.getenv`; the graph points back to `Controller.getenv`. This is an incorrect edge, not an unresolved edge.
- **Go missed binding.** AWS Retail's [`ReindexProducts`](https://github.com/aws-containers/retail-store-sample-app/blob/d7a380b843e0759e58754f74188ea18252a51415/src/catalog/controller/controller.go#L227-L238) calls `c.api.Reindex()`. [`CatalogAPI.Reindex`](https://github.com/aws-containers/retail-store-sample-app/blob/d7a380b843e0759e58754f74188ea18252a51415/src/catalog/api/catalog.go#L64) exists and is a graph node, yet the call remains external.
- **C++/Thrift gap.** DeathStarBench's [`SocialGraphHandler::Follow`](https://github.com/delimitrou/DeathStarBench/blob/6ecb09706140f8730b5385c08f1386c654c3c526/socialNetwork/src/SocialGraphService/SocialGraphHandler.h#L103) has no node because C++ is unsupported. Its Social Network and Media service contracts are Thrift schemas, also unsupported. Python generated Thrift code contributes graph nodes but does not substitute for the C++ implementation graph.
- **Listed Sock Shop target lacks application source.** The [umbrella repository](https://github.com/microservices-demo/microservices-demo/tree/9dff06fae4981921caec6a62393a6ebfce4b3e3f) primarily contains deployment assets. A real Sock Shop service graph requires cloning its component repositories separately.

## Recommended order of fixes

1. **Unify the two HTTP endpoint representations** into one stable node ID and update handlers/consumers to use it. Rebuild the three affected graphs and check for one node and one `IMPLEMENTS` edge per static route.
2. **Fix call resolution errors** using the two concrete regression cases: `System.getenv` must not bind to `Controller.getenv`; `c.api.Reindex()` should resolve to `CatalogAPI.Reindex` when receiver type information is available. Add focused tests.
3. **Improve static HTTP linking** for a literal path appended to a configured base address, while preserving an unresolved result when the host cannot be proven. Measure missing and false links on these pinned repositories.
4. **State language/protocol coverage explicitly.** The builder handles Python, JavaScript, TypeScript, Go, Java, C#, and `.proto` schemas; Astronomy Shop also includes unsupported service languages, and DeathStarBench's central C++/Thrift services are outside this coverage. Expand support only if those systems are intended as end-to-end graph benchmarks.
5. **Use actual Sock Shop component repositories** in a later service-level audit. Keep the current umbrella-repo result as a valid deployment-repo smoke test only.

## Reproduce

With the pinned source trees available, from this repository root on `main`:

```powershell
python bench/audit_graph_builder.py --repo "C:\path\to\microservices-demo" --output "C:\path\to\audit\microservices-demo"
python bench/audit_source_samples.py --repo "C:\path\to\microservices-demo" --graph "C:\path\to\audit\microservices-demo\graph.pkl" --output "C:\path\to\audit\microservices-demo\samples.json" --seed 20261025
```

The saved graph pickle is a local audit artifact; load only files produced by this script. The committed evidence contains JSON summaries and sampled neighbors, not source copies or pickles.
