# DataHub builder v2 coverage

Coverage is measured against the same 26 source-verified links. No retrieval or scoring ran.

## Module pairs

| Module pair | Before full | Before partial | Before absent | After full | After partial | After absent |
| --- | --- | --- | --- | --- | --- | --- |
| Python → OpenAPI | 0 | 5 | 0 | 5 | 0 | 0 |
| Python → Rest.li | 0 | 7 | 0 | 7 | 0 | 0 |
| React → GraphQL | 0 | 14 | 0 | 14 | 0 | 0 |

## Per-link classes

| Link | Before | After | Remaining gap |
| --- | --- | --- | --- |
| DH01 | partly covered | fully covered | — |
| DH02 | partly covered | fully covered | — |
| DH03 | partly covered | fully covered | — |
| DH04 | partly covered | fully covered | — |
| DH05 | partly covered | fully covered | — |
| DH06 | partly covered | fully covered | — |
| DH07 | partly covered | fully covered | — |
| DH08 | partly covered | fully covered | — |
| DH09 | partly covered | fully covered | — |
| DH10 | partly covered | fully covered | — |
| DH11 | partly covered | fully covered | — |
| DH12 | partly covered | fully covered | — |
| DH13 | partly covered | fully covered | — |
| DH14 | partly covered | fully covered | — |
| DH15 | partly covered | fully covered | — |
| DH16 | partly covered | fully covered | — |
| DH17 | partly covered | fully covered | — |
| DH18 | partly covered | fully covered | — |
| DH19 | partly covered | fully covered | — |
| DH20 | partly covered | fully covered | — |
| DH21 | partly covered | fully covered | — |
| DH22 | partly covered | fully covered | — |
| DH23 | partly covered | fully covered | — |
| DH24 | partly covered | fully covered | — |
| DH25 | partly covered | fully covered | — |
| DH26 | partly covered | fully covered | — |

## Repo-wide additions

| Rule | Counted additions | Count |
| --- | --- | --- |
| apollo | callback_contains_edges | 783 |
| apollo | callback_nodes | 783 |
| apollo | consumes_edges | 686 |
| apollo | operation_edges | 688 |
| graphql_java | implements_edges | 611 |
| openapi | consumes_edges | 100 |
| openapi | implements_edges | 26 |
| openapi | inherited_contract_nodes | 26 |
| openapi | produces_edges | 26 |
| restli | consumes_edges | 49 |
| restli | contains_edges | 48 |
| restli | contract_nodes | 48 |
| restli | defines_edges | 48 |
| restli | idl_file_nodes | 10 |
| restli | implements_edges | 43 |

Callback counts include new function nodes and their containment edges. The graph also reflects the normal extraction of callback bodies under their new function scopes.

## Existing source fixture identity

The frozen v1 and enabled v2 builds had identical digests over attributed nodes and keyed edges.

| Fixture | Nodes | Edges | Graph digest |
| --- | --- | --- | --- |
| multi_repo_system | 85 | 171 | 8594e363312bb408b171960877788d81bde5f5d7d892c981a114e9a61dbc1f63 |
| polyglot_api | 72 | 95 | b1972f3f172972dc31b1c0e5889ac76cf0d4b8fa49da246198c2eadc0b73fbc6 |
| polyglot_system | 65 | 101 | 8867cca22c4c89955060b44211b4c181934fdecbabece530a3617330d0fac776 |

## Build verification

GraphML SHA-256 `71067cb3598e40b2be00c3a4f8b3f3557f03172a3dcd9b9a462cba59894dd162` (848,540,156 bytes).

Scoped and full builds agreed on the coverage classes. Scoped build 26.17 s. Full build 358.05 s, peak working set 2.92 GiB.

Nodes 312,070 → 314,219. Edges 1,019,825 → 1,032,920. SEMANTIC_SIMILAR 105,546 → 112,603.

## Export and baseline checks

- The scoped reference used 575 files. All 26 links are fully covered in both builds.
- The React child graph gained 2,063 nodes and 3,715 edges during callback extraction, including callback-body edges. The rule table gives the directly recorded additions.
- The GraphML SHA-256, node types, relation and layer counts, and all 52 required directed edges verified after export.
- The full workspace build loaded code at `0548aacc2613e69ef44f21e8de259aed4ff8b645`. The validated builder revision `fb55db870727cbba3fa32208aa1db9213b83b5a0` restores the configuration-free standalone GraphQL entry point. The configured v2 workspace binding is identical across those two revisions.
- The full test suite finished with 704 passed, 3 skipped, 2 failed, and 4 errors. The LSP and CRLF failures and the four missing trace-fixture errors match the baseline.
- Child semantic edges grew from 1,020 to 1,022. Workspace semantic edges grew from 104,526 to 111,581.
