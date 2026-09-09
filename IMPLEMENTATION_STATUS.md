# Implementation status

Audited against upstream commit `1c566173e06d7e9a43cdfb247d15ba4c2acceda3`.

## Completed correctness fixes

- Relative Python imports are normalized before call resolution.
- Import aliases are resolved before any global name fallback.
- `self.method()` and `super().method()` follow explicitly declared base classes.
- GraphML/GEXF export creates its output directory automatically.
- Regression tests cover Python inheritance, JavaScript inheritance/imports, and
  TypeScript imports, JavaScript return/mutation flow, and literal local API
  links.

The stricter resolver may report fewer internal call bindings than the previous
implementation. This is intentional: ambiguous name matches are now left
unresolved rather than linked to an unrelated function.

## First polyglot slice

JavaScript, JSX, TypeScript, and TSX are parsed with Tree-sitter and emitted
into the same NetworkX graph schema as Python. The supported common vocabulary
is `CONTAINS`, `IMPORTS`, `EXTENDS`, `CALLS`, `PASSES_ARG`, `DEFINES`, `USES`,
`MUTATES`, `RETURNS`, `FLOWS_TO`, and `HTTP_CALLS`. Relative ES-module imports,
destructured/aliased CommonJS `require()` imports, TypeScript `paths` aliases,
and local workspace package entrypoints are resolved. Literal JS/TS `fetch()`
or Axios calls are linked to literal Flask-style Python handlers when their
HTTP method and path agree. `examples/mixed_service` plus `eval_polyglot.py`
is a frozen, reproducible end-to-end check for those bindings.

## Remaining limits

- JavaScript/TypeScript resolve local alias and workspace configuration only.
  External `node_modules`, package-manager workspaces, wildcard/conditional
  exports, and non-relative CommonJS packages are intentionally left external.
- JavaScript/TypeScript flow covers parameters, local definitions/uses,
  assignments/updates, and direct returns. Closure, alias, object-property,
  and inter-procedural flow remain future work.
- API linking is intentionally limited to literal paths and methods. Dynamic
  URLs, templates, router composition, proxies, authentication middleware, and
  runtime route registration are not inferred.
- The bundled retrieval evaluation uses a generated toy repository. It is not a
  real-repository benchmark and should not be presented as one.
- Semantic links use TF-IDF over Python docstrings. They are lexical similarity,
  not neural embeddings or language-model reasoning.

## Next priority order

1. Build a frozen, independently labelled real-repository evaluation set.
2. Expand API linking to configurable router frameworks and route prefixes.
3. Add external package and conditional-export resolution where project policy
   allows dependency traversal.
4. Add a third language through the same adapter contract.
