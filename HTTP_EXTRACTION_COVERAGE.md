# Cross-repository HTTP source extraction coverage

## Safety and evidence contract

This module statically derives HTTP dependency edges. An asserted cross-repo
`HTTP_CALLS` requires a source-evidenced HTTP method and URL, a resolvable
host ownership identity, a route compatible with the method and *complete*
path components, and exactly one matching handler in that destination
repository. It never treats a same-path match in unrelated services as proof.

When source evidence does not establish the host, branch or destination,
the resolver abstains. A `POSSIBLE_HTTP_TARGET` is explicitly uncertain
and is excluded from the default operational blast radius.

## Covered source idioms

- **Python outbound**: direct Requests/httpx methods, imported aliases,
  instantiated `requests.Session`, `httpx.Client`, `httpx.AsyncClient`,
  `aiohttp.ClientSession`, `urllib3.PoolManager`, `urllib.request.urlopen`
  and `Request` URL objects, including `self.session` assignments
  established in a class initializer.
- **Python inbound**: FastAPI/Flask literal route decorators, FastAPI
  `APIRouter(prefix=...)` and mounted/imported routers, Flask Blueprint
  `url_prefix`, Django literal `path()` and nested `include()` URLconfs.
- **JavaScript and TypeScript outbound**: `fetch`, direct Axios methods,
  `axios.create({baseURL})` instances, `new URL()` expressions, statically
  known `const` concatenations and template substitutions, and known
  deployment-provided environment variables.
- **JavaScript and TypeScript inbound**: Express literal router verbs
  and `app.use(prefix, router)` (including simple imported routers),
  Express chained `app.route(path).get(handler)`, Fastify method helpers
  and literal object-form `fastify.route({method,url,handler})`.
- **Go outbound**: `http.Get`, `http.Post`, `http.NewRequest`,
  `http.NewRequestWithContext`, statically known function-local URL
  concatenation, and known `os.Getenv` values from workspace deployment
  configuration. Unrelated functions and conditional assignments are not
  used as proof.
- **Go inbound**: `http.HandleFunc` (core extractor), Gin and Echo
  literal route methods and `.Group(prefix)`, Chi literal methods and
  `Route(prefix, func(r chi.Router){ ... })`, Gorilla Mux
  `HandleFunc(...).Methods(...)`.
- **Previously existing adapters**: Java/Spring and C#/ASP.NET method
  annotation handling, REST client method inference, route parameter
  representations such as `/users/{id}`, `/users/<id>`, `/users/:id`.

These entries describe implemented source idioms and exercised fixtures,
not exhaustive API coverage or runtime correctness for every application.

## Explicit unknowns

A purely static analyzer cannot identify an HTTP target when the URL,
host, route, middleware mapping, DNS alias or rewrite depends on data that
is not present in the indexed source or supported deployment configuration.
Examples include URLs returned by an opaque runtime helper, remotely
injected environment values, dynamic router registration via reflection,
conditional routing and proxy rewrites. Such cases require traces,
configuration ingestion or human-provided authoritative mappings.

Do not promote unresolved links to confirmed `HTTP_CALLS` merely to improve
graph recall. A false cross-repo link can misdirect the remediation agent.

## Reproduce

Run from the repository root:

    python -m pytest -q tests/test_http_extended_coverage.py
    python -m pytest -q tests/test_http_binding_safety.py
    python -m pytest -q tests/test_sop_review_defects.py
    python -m pytest -q tests

Also inspect GitHub Actions `Graph Builder Integration` on `krishna` for
the full regression suite and pinned-repository graph checks.
