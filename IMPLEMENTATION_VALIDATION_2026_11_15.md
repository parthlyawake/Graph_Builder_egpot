# Graph Builder Implementation and Validation — 2026-11-15

## Scope

This implementation targets the five workstreams identified for the SCKG builder:
1. Single-repository incremental source-file updates without dropping unrelated edges.
2. Multi-repository cached composition without reparsing unchanged repositories.
3. Scalable sparse semantic candidate retrieval without dense N×N similarity matrices.
4. Overload identity, repeat-build state resets, and workspace ignore patterns.
5. Expanded Protobuf, OpenAPI, GraphQL schema, operation, and explicit Java DataFetcher bindings.

The implementation uses **bounded semantic candidates** and **workspace recomposition**.
It does not claim exact semantic nearest-neighbor recall or constant-time workspace updates.

## Key implementation files

- `incremental_builder.py`: preserve source registries and reconstruct derived relationships; protocol/schema changes use full-rebuild fallback.
- `workspace_incremental.py`: update affected repository builder, recompose workspace-level contracts and graph bindings.
- `semantic_neighbors.py`: bounded candidate retrieval and sparse cosine scoring.
- `polyglot.py`: signature-aware disambiguation of Java/C# overloaded definitions.
- `graft_ckg.py`: consistent repeat builds, config ignore handling, single-repository contract indexing.
- `proto_parser.py`: map-key/value fields, oneof members, and nested message field isolation.
- `graphql_ast_support.py`, `graphql_links.py`, `graphql_java_bindings.py`: standards-based schema and operation AST extraction, operation-to-schema links, explicit uniquely resolved Java DataFetcher-to-field links.
- `standalone_contract_specs.py`: OpenAPI/GraphQL contract indexing for standalone builds.
- `tests/test_builder_completion.py`: new regression cases.

## Triple full suite verification

GitHub Actions: [Graph Builder Integration](https://github.com/SNK0-0/SCKG_Build/actions/runs/43633826832).

Three independent `pytest -q tests` processes completed:
- Verification 1: **170 passed, 3 skipped** (2.50 s)
- Verification 2: **170 passed, 3 skipped** (1.87 s)
- Verification 3: **170 passed, 3 skipped** (2.12 s)

The 3 skipped tests remain outside this coverage; inspect the CI log for their reasons.
A passing regression suite is not proof of exhaustive program-analysis accuracy.

## Independent pinned DataHub source-subtree check

Upstream: [datahub-project/datahub](https://github.com/datahub-project/datahub)
at commit `051fb78fe6a6395043d272218b035cb00fe27321`.

Tested subtree: `datahub-actions/src` (88 parsed Python files).
The test copies it into a temporary directory, appends a Python function to
`datahub_actions/action/action_stats.py`, times incremental construction,
then compares the exact node set and every typed edge multiplicity to a fresh
full build. The original upstream files are not modified.

| Trial | Nodes after edit | Edges after edit | Initial build (s) | Incremental edit (s) | Fresh post-edit build (s) | Exact graph equivalent |
| --- | ---: | ---: | ---: | ---: | ---: | :---: |
| 1 | 3,299 | 7,662 | 0.234393 | 0.056376 | 0.227250 | Yes |
| 2 | 3,299 | 7,662 | 0.249133 | 0.112420 | 0.221723 | Yes |
| 3 | 3,299 | 7,662 | 0.241412 | 0.061729 | 0.218111 | Yes |

Mean incremental time: **0.076842 s**. Mean fresh post-edit time:
**0.222361 s**. Ratio of means: **2.89× faster** on this small, pinned subtree,
not on the full DataHub repository. No claim of general speedup is implied.

Original JSON artifact: [CI datahub-graph-smoke](https://github.com/SNK0-0/SCKG_Build/actions/runs/43633826832)
(artifact ID: `14129435576`).

## Reproduction

```bash
pip install -r requirements.txt
python -m pytest -q tests
python bench/smoke_datahub_graph.py \
  --repo /path/to/datahub/datahub-actions/src \
  --repetitions 3 \
  --output bench/results/datahub_smoke.json
```

## Known limitations

- The GraphQL operation parser links **literal document root fields** to schema contracts.
  Java resolver edges require an explicit, unambiguous `.dataFetcher("field", new Resolver(...))`
  expression; inferred resolver names and dynamic wiring are not treated as confirmed.
- The Protobuf parser covers common schema forms, including map and oneof fields,
  but is not a complete implementation of the full Protobuf grammar or compiler.
- Cross-service links with unresolved hosts are candidates, not confirmed edges.
- The workspace incremental path reuses per-repository graph objects, but
  recomposes cross-repository edges and semantic indexes. It is not an O(delta)
  workspace updater.
- Semantic edges are built from bounded sparse candidates, not exhaustive
  all-pairs nearest neighbors. This trades recall for tractable indexing.
- Full multi-language/full-DataHub accuracy, runtime coverage, and retrieval
  quality are separate research evaluations and remain to be established.
