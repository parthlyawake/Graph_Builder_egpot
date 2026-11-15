# Real-repository polyglot compatibility audit

Date: 2026-11-15. This report distinguishes *parser availability*, *source
syntax extraction*, *graph construction*, *semantic edge correctness*, and
*runtime behavior*. These are **not** interchangeable. A green audit job may
still contain logged partial parses: the audit deliberately reports the gaps
instead of claiming perfect coverage.

## Scope and reproducibility

All upstream checks are pinned to Git commit SHAs in
`.github/workflows/real-polyglot-coverage.yml` and independently persisted as
per-job JSON artifacts. The CI workflow excludes normal vendor and build
directories, uses sparse checkouts for several large repos and does not assert
that a sampled source subtree represents the full upstream repository.
Do not report the numbers below as a full-repository accuracy benchmark.

| System | Audited scope | Grammar files | Parsed cleanly | Partial | Contract files |
| --- | --- | ---: | ---: | ---: | --- |
| Istio Bookinfo | Complete `samples/bookinfo` application source within Istio | 10 | 10 | 0 | None |
| Fudan Train-Ticket | Selected representative service paths | 46 | 46 | 0 | None |
| DeathStarBench | `socialNetwork`, `mediaMicroservices`, `hotelReservation`, ignoring vendored/build directories | 531 | 466 | 65 | 2 Thrift parsed |
| DataHub | Sparse representative Java, Python, Scala, TS/TSX, PDL and Avro subtrees | 4,429 | 4,008 | 421 | 36 PDL + 11 Avro parsed |
| Sock Shop | Eight separate archived service source repositories, each audited as its own pinned checkout | See CI artifacts | All selected jobs passed grammar checks | See per-service artifacts | Deployment audited separately |

**Counts:** DeathStarBench overall 533 scanned = 531 language files + 2
Thrift contracts; DataHub 4476 scanned = 4429 language files + 47
PDL/Avro contracts. The signed code revisions are in the CI workflow.

A second CI job builds an actual Bookinfo graph with `--build-graph`.
Other upstream jobs currently check grammar/schemas without independently
asserting precision/recall of graph edges, connected cross-service workflows,
or remediation/root-cause accuracy.

## Implemented reusable capabilities

- **Language AST**: Python, JavaScript/JSX, TypeScript/TSX, Go, Java,
  C#, Kotlin, Ruby, Lua, C, C++, Scala. Ruby/Lua/C/C++/Scala extract
  syntax, source-located declarations, imports, and call candidates.
  This is not feature parity with the deeper Python and Java adapters.
- **Static local imports**: Ruby `require_relative`, Lua `require`,
  and quoted C/C++ `#include` bind to a local file only when the path
  has a unique indexed resolution. Ambiguous basenames never bind.
- **Service and schema contracts**: gRPC/protobuf and HTTP
  support existing in the builder; new Thrift IDL declarations, RPC signatures
  and typed fields, Pegasus PDL record schemas, and nested Avro record schemas.
- **Message edges**: AMQP/RabbitMQ producer-consumer contracts in selected
  Python/Java/JS/Go literal client forms, and Kafka producer/consumer
  constructs. Unknown routing keys, exchanges, bindings, and runtime topics
  remain uncertain; they must not become asserted cross-service links.
- **Ruby HTTP**: WEBrick literal `mount_proc` paths and prefix matching
  are represented without asserting host-ambiguous cross-service calls.
- **TSX**: use the JSX-aware grammar. The audit runner caches TypeScript
  and TSX parsers separately.

There are **no repository-name conditionals** in the above production parser
and protocol features. Repository names and pinned commits occur only in CI
fixtures and this verification report.

## Verified gaps — not covered by a green CI status

### DeathStarBench

C and C++ syntax audit: 14 C files, 11 clean and 3 partial; 185 C++
files, 123 clean and 62 partial. The 65 issues include generated
Thrift C++ pointer-to-member declarations/calls such as
`(processor->*(pfn->second))(...)` and some Lua bridge macro
concatenations. Go (53/53), Lua (183/183), Python (65/65), and
JavaScript (31/31) parse cleanly in the checked scopes.
Both Thrift IDLs parse, but complete Thrift client-to-server call binding
and generated C++ dispatch precision/recall are **not verified**.

### DataHub

In the checked out subtrees: Java 65/65; Python 89/89; Scala 4/4;
JavaScript 3/3; TypeScript/TSX 3847/4268 (421 partial).
All 36 PDL and 11 Avro schemas parse.
The 421 remaining TS/TSX parser issues include styled-components
tagged-template interpolation and nested template constructs. The graph
builder must retain `partial` diagnostics; syntax recovery cannot be
represented as full, lossless parsing. Real cross-language Kafka,
GraphQL operation binding and schema links have not been independently
precision/recall graded in the full DataHub project.

### Train-Ticket and Sock Shop

Train-Ticket's audited 46-file sample is not the full set of services.
The complete Spring Cloud REST/discovery graph (including dynamic
configuration and requests) must be assessed separately. The archived
Sock Shop deployment repository is not an authoritative code source for
its services; the CI separately checks eight service repositories.
Although literal AMQP client forms are covered by unit tests, complete
RabbitMQ delivery topology requires exchange-to-queue bindings and
deployment/runtime configuration, not merely source-level API calls.

### General limits

All repository-wide claims require pinned complete source, unbiased
relation labels, edge precision/recall, incremental equivalence,
latency/memory metrics, and an end-to-end remediation acceptance test.
Dynamic reflection, runtime-generated URLs, proxies, message broker
bindings, generated source syntax rejected by the current Tree-sitter
grammar, and missing native compiler context require external evidence
or a compiler-backed fallback. None should be silently guessed.

## Reproduce

    python -m pytest -q tests/test_extended_schema_and_languages.py
    python -m pytest -q tests/test_message_contracts_extended.py
    python -m pytest -q tests/test_tsx_grammar_support.py
    python -m pytest -q tests/test_real_repository_audit.py
    python -m pytest -q tests/test_ruby_webrick_http.py
    python -m pytest -q tests/test_local_language_imports.py
    python -m pytest -q tests

    python bench/real_repository_coverage.py \
      --root /path/to/checked/out/service \
      --output bench/results/external_coverage.json --build-graph

Use `--fail-on-incomplete` when a zero-partial, zero-unsupported
source-syntax audit is a strict release requirement. Note that this
flag evaluates parser coverage, **not** graph edge correctness.

## Source of truth

- Production: `Graph_Builder/krishna`, never the older `SCKG_Build`.
- CI: `Graph Builder Integration` and `Real Polyglot Repository Coverage`.
- Original baseline: seven language adapters; these improvements widen the
  registry to twelve, but **do not establish complete support** for the five
  applications or their full runtime communications.
