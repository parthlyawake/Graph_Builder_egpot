# Contracts in GRAFT-CKG

A **contract** is an agreed boundary in code: an interface that a class says it implements, an HTTP route that a client calls, or an RPC defined in a `.proto` file. GRAFT-CKG represents these boundaries as graph nodes and links them to the code on either side. This helps answer: **“If this boundary changes, which files might need attention?”**

The graph is a static index of source code, not a compiler, type checker, API validator, or proof of root cause. An edge means the parser found a supported, explicit relationship. Missing edges can mean the relationship is dynamic or not yet supported.

## The vocabulary

| Graph item | Plain-English meaning | Example |
| --- | --- | --- |
| `interface` node | A declared TypeScript, Go, Java, or C# interface | `Store` |
| `http_endpoint` node | A registered HTTP method and path | `POST /api/orders` |
| `http_callsite` node | A call with a visible path but unresolved host | `POST /orders (host unresolved)` |
| `service_contract` node | A service declared in a protobuf file | `OrderService` |
| `rpc_contract` node | One operation declared by that service | `OrderService.CreateOrder` |
| `DECLARES` edge | An interface contains a method or property signature | `Store → get` |
| `IMPLEMENTS` edge | Code explicitly provides an interface, route, service, or RPC | `POST handler → POST /api/orders` |
| `CONSUMES` edge | Code calls an HTTP or gRPC contract | `submitOrder → POST /api/orders` |
| `EXTENDS` edge | One interface explicitly extends another | `NamedStore → Store` |
| `DEFINES_RPC` edge | A protobuf service declares an RPC | `OrderService → CreateOrder` |
| `HTTP_CALLS` edge | A direct, statically matched client-to-handler dependency | `submitOrder → POST handler` |
| `HTTP_REQUEST` edge | A function makes a dynamic-host HTTP request with a visible path | `shipOrder → POST /ship-order` |
| `POSSIBLE_HTTP_TARGET` edge | A dynamic-host callsite has the same method and path as an indexed route; the host is unverified | `POST /ship-order → route candidate` |

`DECLARES`, `IMPLEMENTS`, `CONSUMES`, and contract `EXTENDS` relationships are in the `Lcontract` layer. `HTTP_CALLS` is in the dependency layer (`Ldep`); it is kept alongside the contract edges for direct traversal.

## Three examples

### 1. TypeScript interface

```ts
interface Store { get(id: string): string }
class MemoryStore implements Store { get(id: string) { return id } }
```

The graph contains `Store` as an `interface`, its `get` signature as a `method`, and `MemoryStore --IMPLEMENTS--> Store`. Interface method and property signatures are linked with `DECLARES`. An `interface ... extends OtherInterface` declaration produces an `EXTENDS` contract edge when the target resolves. A Go `interface` is typed as an interface node, but Go's implicit implementation is **not** inferred.

This records the *explicit declaration*. It does not check that `MemoryStore` truly satisfies every method or that a TypeScript type alias is equivalent to the interface.

### 2. HTTP route

```ts
// app/api/orders/route.ts
export async function POST() { /* ... */ }

// client.ts
fetch('/api/orders', { method: 'POST' })
```

The graph contains a contract node named `POST /api/orders` (`http::POST:/api/orders`). The handler has an `IMPLEMENTS` edge to it; the calling function has a `CONSUMES` edge to it and an `HTTP_CALLS` edge directly to the handler.

Supported static route registrations include Python route decorators, Spring mapping annotations, Express `app`/`router` method registrations, Go `http.HandleFunc`, and Next-style `app/api/.../route.ts`/`.js` exports. The Python and JavaScript/TypeScript client extractors recognize supported literal HTTP calls; Go recognizes literal `http.Get`/`http.Post` and `http.NewRequest` variants. Exact method-and-path matching is used, with a wildcard method for Go `HandleFunc`. A statically visible suffix appended to a dynamic host is kept as an `http_callsite`. A path match to a local endpoint uses `POSSIBLE_HTTP_TARGET`; it is **not** a confirmed `HTTP_CALLS` edge.

### 3. Protobuf/gRPC service

```proto
service OrderService {
  rpc CreateOrder (CreateOrderRequest) returns (CreateOrderReply);
}
```

The `.proto` file produces `contract::OrderService` and `contract::OrderService.CreateOrder`, joined by `DEFINES_RPC`. Recognized Python, Go, and JavaScript server bindings produce `IMPLEMENTS`; recognized client stub calls produce `CONSUMES`. The graph also keeps the request and response type names and a hash of each `.proto` definition.

In a multi-repo workspace, matching protobuf services are unified and differing copies are reported as contract skew. Cross-repo literal HTTP calls can link directly to matching handlers with `HTTP_CALLS`; a shared cross-repo HTTP contract node is **not** currently unified the way protobuf contracts are.

## How to inspect a contract

Run the local viewer from the repository root:

```powershell
python -m pip install -r requirements.txt
python bench/team_demo.py --repo "C:\path\to\your\repo"
```

Open `http://127.0.0.1:8767/`. Search for an interface name, `POST /api/orders`, or an RPC name; select the node and inspect its neighbors. The **Contracts** toggle shows or hides contract-layer edges. The retrieval panel compares methods that may use contract traversal, including R9 and R10, but its ranked files are *candidates*, not measured root-cause accuracy.

For protobuf services/RPCs, the command-line queries are also available:

```powershell
python graft_ckg.py "C:\path\to\your\repo" --who-implements OrderService.CreateOrder
python graft_ckg.py "C:\path\to\your\repo" --who-consumes OrderService.CreateOrder
```

These two CLI queries currently resolve **protobuf/gRPC contract nodes only**. Use graph search and the node inspector for HTTP and interface relationships.
The CLI also exports `repo_graph.graphml` by default; pass `--export "C:\path\to\output.graphml"` to choose its location.

## What remains limited

- Dynamic hosts are not reliably resolved to services. Some Python and Go calls retain a static path suffix as a callsite; URL parameters, router rewrites, runtime registrations, and nonliteral HTTP methods remain unresolved.
- TypeScript structural compatibility and Go implicit interface satisfaction are not inferred. Only explicit TypeScript `implements`/`extends` declarations create those contract edges.
- The protobuf parser covers the service/RPC declaration patterns tested here; it is not a full protobuf compiler or schema-compatibility checker. A differing file hash flags possible skew, not necessarily a breaking change.
- A contract edge says *where to investigate*. It does not show that the endpoint is healthy, the response schema is correct, or a retrieved file is the true root cause.

Implementation lives in [`graft_ckg.py`](graft_ckg.py), [`polyglot.py`](polyglot.py), and [`multi_repo.py`](multi_repo.py). Focused examples are tested in [`tests/test_interface_http_contracts.py`](tests/test_interface_http_contracts.py) and [`tests/test_contract_layer.py`](tests/test_contract_layer.py). For teammate setup and ignore rules, see [`TEAMMATE_GRAPH_GUIDE.md`](TEAMMATE_GRAPH_GUIDE.md).
