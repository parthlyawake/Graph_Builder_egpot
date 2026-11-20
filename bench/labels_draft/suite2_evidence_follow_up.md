# DataHub Suite 2 v3 readiness review

This review uses only the [committed source evidence](suite2_source_evidence.md) at `34afe6ce641f3888bbc9c4195ad6430984ba2f5d`. That record confirms declaration IDs and audits direct consumer bindings for blast radius. It supplies source-interface hops for chains and no asserted dependency path for lookalikes. Graph reachability, traversal eligibility, and stored clue text are outside what it verifies.

## Blast radius

A source consumer is a distinct sending scope per contract, keyed by its cited file and declaration. For eager queries this is the cited hook scope. For lazy queries and mutations it is the cited sending callback or function. Repeated calls in one scope count once. A setup scope with a separate sender, an operation document, and cache-only or mock references are omitted. The v3 count credits evidence of a direct binding at the sending scope.

| ID | Contract | Source consumers | Direct at right node | Unrepresentable | At least 3 direct | Unrepresentable consumers and reasons |
|---|---|---:|---:|---:|---|---|
| C01 | `Query.getRootGlossaryNodes` | 5 | 5 | 0 | Yes | — |
| C02 | `Query.getRootGlossaryTerms` | 5 | 5 | 0 | Yes | — |
| C03 | `Query.listGlobalViews` | 5 | 5 | 0 | Yes | — |
| C04 | `Query.listPosts` | 6 | 6 | 0 | Yes | — |
| C05 | `Query.listRecommendations` | 6 | 6 | 0 | Yes | — |
| C06 | `Query.searchDocuments` | 9 | 4 | 5 | Yes | Missing direct bindings for `useLoadDocumentTree.checkForChildren`, `.loadMissingSourceSectionRoots`, `.loadRootPage`, `.loadChildren`, and `.loadMoreChildren`. The outer lazy-hook setup is also unbound. |
| C07 | `Query.listDataProductAssets` | 8 | 5 | 3 | Yes | Missing direct bindings for `OutputPortsSection.loadMore` and `generateUseDownloadListDataProductAssets.refetch`. The edge for `generateUseListDataProductAssetsCount.useListDataProductAssetsCount` lands on the enclosing factory, and the returned named function has no mapped node. The download factory's lazy-hook setup is also unbound. |
| C08 | `Mutation.updateDescription` | 9 | 8 | 1 | Yes | Python `update_description` in Agent Context is outside the frozen roots. |
| C09 | `Mutation.batchSetDataProduct` | 6 | 6 | 0 | Yes | — |
| C10 | `Mutation.batchUpdateDeprecation` | 4 | 4 | 0 | Yes | The flagged `TagActionsColumn` gap is for the setup owner. The evidence records the distinct `handleUndeprecate` sending node and does not flag its direct binding. |
| **Total** | | **63** | **54** | **9** | **10 of 10** | **7 missing bindings, 1 outside the frozen roots, 1 wrong enclosing function.** |

All ten cases retain three or more direct consumers in at least two cited files. Seven cover the complete set of source consumers. C06–C08 retain a graph-covered subset. [Consumer-level evidence](suite2_source_evidence.md#c-blast-radius)

## Lookalikes and versions

The evidence uses the first declaration as the start for every pair. All twelve starts and both declarations in each pair have v3 IDs. The table distinguishes a cue visible in those IDs from behavior documented in source. An eligible path from the start to the alternative is unverified for every pair, so the file cannot identify any pair as policy-blocked.

| ID | Start declaration | Alternative declaration | Both IDs and start | Separating clue |
|---|---|---|---|---|
| B01 | `Query.autoComplete` | `Query.autoCompleteForMultiple` | Yes | IDs signal multiple. Single asset type versus a set of types comes from SDL. |
| B02 | `Query.search` | `Query.searchAcrossEntities` | Yes | IDs signal cross-entity search. The single-type restriction comes from SDL. |
| B03 | `Query.browse` | `Query.browsePaths` | Yes | IDs signal paths. Browsing under a supplied path versus returning paths for a known entity comes from SDL. |
| B04 | `Query.getRootGlossaryNodes` | `Query.getRootGlossaryTerms` | Yes | IDs distinguish nodes from terms. Folders versus vocabulary entries is the source interpretation. |
| B05 | `Query.listGlobalViews` | `Query.listMyViews` | Yes | IDs distinguish global from personal. Ownership by the signed-in user comes from SDL. |
| B06 | `Mutation.addOwner` | `Mutation.batchAddOwners` | Yes | IDs signal batch. The number of assets affected comes from SDL. |
| B07 | `Mutation.setDomain` | `Mutation.batchSetDomain` | Yes | IDs signal batch. Single-asset argument versus batch input comes from SDL. |
| B08 | `Mutation.updateDeprecation` | `Mutation.batchUpdateDeprecation` | Yes | IDs signal batch. The asset scope comes from SDL. |
| B09 | `Mutation.createPost` | `Mutation.updatePost` | Yes | Create versus edit is visible in the IDs and corroborated by SDL. |
| B10 | `Query.aggregateAcrossEntities` | `Query.scrollAcrossEntities` | Yes | IDs distinguish aggregation from scrolling. Summary versus cursor-based results comes from SDL. |
| B11 | `Mutation.createGlossaryTerm` | `Mutation.createGlossaryNode` | Yes | IDs distinguish terms from nodes. Vocabulary entry versus folder is the source interpretation. |
| B12 | `GET /openapi/v2/entity/{entityName}` | `GET /openapi/v3/entity/{entityName}` | Yes | Version is visible in both route IDs. The response model difference comes from the Java declarations. |

The file establishes the source clue for every pair. Storage and retriever visibility of the full clue remain unverified, as does reachability of the alternative. Even for B12, the shared inherited handler is a source fact and the file records no graph path through it. [Pair-level citations and IDs](suite2_source_evidence.md#b-lookalikes-and-versions)

## Chains

Hop 1 connects the caller to contract 1, hop 2 connects contract 1 to handler 1, hop 3 connects handler 1 to contract 2, and hop 4 connects contract 2 to handler 2. The table lists hops broken by missing declarations. Connections whose endpoints both have IDs remain unverified.

| ID | Chain | Hops blocked by missing v3 nodes | Builder work needed |
|---|---|---|---|
| A01 | Python SSO CLI → Play → GMS GraphQL HTTP servlet | 1, 2, 3, 4 | Model Play's POST route and bind the caller and proxy to it. Include the GraphQL servlet module, extract its POST endpoint and handler, and resolve the proxy's compatibility rewrite and outgoing dispatch. |
| A02 | React tracking client → Play → OpenAPI tracking | 1, 2 | Extract POST `/openapi/*path` from Play routes and bind the browser tracking POST and proxy to it. Verify the forwarding and handler edges at the existing tracking endpoint. |
| A03 | Java Rest.li SDK → platform resource → Kafka listener | 1, 3, 4 | Include the Java client and bind its typed Rest.li action request. Model the configured platform event topic and producer dispatch inside the resource callback. Include the listener module and bind its subscription under the documented Kafka and startup conditions. Hop 2 needs an edge check. |
| A04 | Python search results → Play → Rest.li entity search | 1, 2 | Extract and bind the Play POST route. Resolve the proxy rewrite and SDK helpers while preserving the upstream `search` action. |
| A05 | Python aspect counts → Play → Rest.li aspect count | 1, 2 | Extract and bind the Play POST route. Resolve the proxy rewrite and SDK helpers while preserving the upstream `getCount` action. |
| A06 | Python usage emitter → Play → Rest.li usage ingest | 1, 2 | Extract and bind the Play POST route. Resolve the emitter helper's POST and the upstream `usageStats` `batchIngest` action. |
| A07 | Python list-runs CLI → Play → Rest.li list runs | 1, 2 | Extract and bind the Play POST route. Preserve the `list` action on the forwarded `/runs` path. |
| A08 | Python show-run CLI → Play → Rest.li describe run | 1, 2 | Extract and bind the Play POST route. Preserve the `describe` action on the forwarded `/runs` path. |
| A09 | Python rollback CLI → Play → Rest.li rollback | 1, 2 | Extract and bind the Play POST route. Follow the CLI POST helper and preserve the `rollback` action on `/runs`. |
| A10 | Python MCE emitter → Play → Rest.li entity ingest | 1, 2 | Extract and bind the Play POST route. Resolve the emitter helper's POST and preserve the upstream `ingest` action on `/entities`. |
| A11 | Python registry CLI → Play → Rest.li registry deletion | 1, 2 | Extract and bind the Play POST route. Follow the CLI POST helper and preserve the upstream `deleteAll` action on `/entities`. |
| A12 | Python entity batch client → Play → OpenAPI v2 batch | 1, 2 | Extract and bind the Play POST route. Resolve the proxy rewrite to the existing verb-specific OpenAPI v2 batch route and verify the upstream handler edge. |

For A04–A12, model the documented self-hosted proxy condition. Direct GMS configurations bypass Play. [Chain declarations and dispatch citations](suite2_source_evidence.md#a-chains)

## Recommendations

- **Blast radius:** Use **7 of 10** as-is for complete source-consumer scoring. **10 of 10** clear the three-direct-consumer threshold if a graph-covered subset is evaluated separately.
- **Lookalikes and versions:** **12 of 12** are ID-ready. **0 of 12** are confirmed traversal-ready by this evidence alone. Verify eligible paths and clue visibility before scoring.
- **Chains:** **0 of 12** are evaluable as full chains in v3. Each has a missing declaration on the specified path.
