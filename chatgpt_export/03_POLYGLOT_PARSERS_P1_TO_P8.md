# Polyglot Architecture & AST Extractors (P1 to P8 Enhancements)

GRAFT-CKG supports 7 programming languages and 3 contract description specifications with deep syntax and semantic extraction:

## Supported Languages & Grammars
1. **Go** (`tree-sitter-go`): Package declarations, struct receiver functions, interface definitions, goroutines, gRPC client calls, `http.HandleFunc` route registration.
2. **Python** (`ast` + `tree-sitter-python`): Class definitions, method implementations, decorators, dynamic import tracking, gRPC `add_*Servicer_to_server`, Flask/FastAPI routes.
3. **JavaScript / TypeScript** (`tree-sitter-javascript`, `tree-sitter-typescript`): CommonJS `require()` and ES6 `import`, class hierarchies, arrow functions, Express/Fastify routes, dynamic `grpc.loadPackageDefinition()`.
4. **Java** (`tree-sitter-java`): Spring Boot `@RestController`, `@GetMapping`, `@PostMapping`, gRPC `*ImplBase` inheritance, method signatures, package-level isolation.
5. **C#** (`tree-sitter-c-sharp`): ASP.NET Core MVC `[Route]`, `[HttpGet]`, `[HttpPost]`, constructor Dependency Injection (DI) gRPC client resolution, `using` namespace directives.
6. **Kotlin** (`tree-sitter-kotlin`): Spring REST controllers, Kafka `@KafkaListener` event handlers, Coroutine gRPC servicers (`*CoroutineImplBase`).
7. **Protobuf 3** (`proto_parser.py` AST): Recursive syntax tree extracting services, rpc methods, request/response streaming, options, nested messages, typed fields, and package declarations.

## Architectural Enhancements (P1 to P8)
- **P1: Protobuf AST Engine (`proto_parser.py`)**: Replaces brittle regex with complete AST parser capturing streaming RPCs and options.
- **P2: Full C# ASP.NET & DI Extractor (`polyglot.py`)**: Parity with Java extractor; parses ASP.NET route attributes and constructor DI.
- **P3: Type-Aware Polymorphic Dispatch (`graft_ckg.py`)**: Uses type signatures and stub definitions (.pyi/.d.ts) to compute exact softmax confidence weights while strictly preserving Theorem 2 ($\sum c_{\text{type}} = 1.0$).
- **P4: Inter-Service Dataflow (`multi_repo.py`)**: Bridges caller arguments to server handler parameters across repo boundaries via contract nodes in $L_{\text{flow}}$.
- **P5: OpenAPI 3.x & GraphQL SDL Parsers (`openapi_graphql_parser.py`)**: Extends contract plane beyond gRPC to RESTful APIs and GraphQL query/mutation schemas.
- **P6: Kotlin Language Extractor (`polyglot.py`)**: Full AST extraction for Kotlin microservices, Spring Boot, and coroutine-based gRPC handlers.
- **P7: LSP Augmentation Engine (`lsp_augmenter.py`)**: Interfaces with language servers (`gopls`, `pyright`, `jdtls`) to elevate ambiguous static call sites to exact $c_{\text{type}} = 1.0$ bindings.
- **P8: Cross-Language Proto Type Identity (`multi_repo.py`)**: Unifies language-specific model classes in Go and Python to canonical proto message entities in $L_{\text{contract}}$.
