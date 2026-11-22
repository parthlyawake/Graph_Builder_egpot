# DataHub source-to-builder coverage audit

This report uses source labels and graph structure only. No retrieval methods or scoring ran.

Pinned source `c2a82c97f0faf73c266d6525aead90557615147f`. Frozen builder `egpot-bench-builder-v1` at `94aae7b8aef08ac2beddcbc7fc37a7e2b2cc69ce` already contains the C++ full-body binder fix used in the DeathStarBench builds.

[Verified source evidence v2](../../../egpot_repos/labels_draft/datahub_source_evidence_v2.md) SHA-256 `c1ff8a532c5cf830952e60b2cb974c1cafd2d8b67d4bf6a063173c7e62fb2cb2`.

GraphML SHA-256 `6332b2c84b5083067d2a72eac3a0f41459f771b791319a5cc7d98baa7f124ef2`. 312,070 nodes and 1,019,825 edges. Build time 13679.22 s. Build process peak working set 2.41 GiB. Budget 40 represents 0.01282% of this graph.

GraphML serialization replaced 30 invalid XML characters with U+FFFD. Non-scalar attributes are serialized as strings.

## Exact scope

| Namespace | Production root |
| --- | --- |
| web | datahub-web-react/src |
| graphql | datahub-graphql-core/src/main/java |
| graphql-idl | datahub-graphql-core/src/main/resources |
| frontend | datahub-frontend/app |
| ingestion | metadata-ingestion/src |
| openapi | metadata-service/openapi-servlet/src/main/java |
| openapi-idl | metadata-service/openapi-servlet/src/main/resources |
| restli | metadata-service/restli-servlet-impl/src/main/java |
| restli-idl | metadata-service/restli-api/src/main/idl |

`exclude_nonproduction=True` applies to every root. Extra basename globs are `*.generated.*, *.min.js, tests.graphql`. Excluded directory components are `.git, .venv, __pycache__, __tests__, bin, build, dist, docs, e2e-test, example, examples, fixtures, generated, genproto, node_modules, obj, perf-test, smoke-test, target, test, testdata, testfixtures, tests, vendor`. Frozen test filename and first-5,000-character generated-header checks also apply. Discovery for workspace SDL and operation scans is scoped to the same allowlist.

## Coverage by module pair

| Pair | fully covered | partly covered | not covered |
| --- | --- | --- | --- |
| React → GraphQL | 0 | 14 | 0 |
| Python → OpenAPI | 0 | 5 | 0 |
| Python → Rest.li | 0 | 7 | 0 |

A fully covered row requires the exact caller, contract and handler method, with caller-to-contract CONSUMES and handler-to-contract IMPLEMENTS. Canonical contract nodes without a file attribute were matched by complete qualified name or verb and path only. The JSON records source-line offsets and ambiguous candidates. Edges were inspected only after node selection.

## All links

| Link | Caller | Contract | Handler | Start → contract | Handler → contract | Start → handler | Coverage / missing |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DH01 | `web/app/domainV2/CreateDomainModal.tsx:CreateDomainModal.onCreateDomain` | `contract::graphql::Mutation::createDomain` | `graphql/com/linkedin/datahub/graphql/resolvers/domain/CreateDomainResolver.java:CreateDomainResolver.get` | — | — | — | partly covered · start-to-contract CONSUMES, handler-to-contract IMPLEMENTS |
| DH02 | `web/app/domainV2/DomainItemMenu.tsx:DomainItemMenu.deleteDomain` | `contract::graphql::Mutation::deleteDomain` | `graphql/com/linkedin/datahub/graphql/resolvers/domain/DeleteDomainResolver.java:DeleteDomainResolver.get` | — | — | — | partly covered · start-to-contract CONSUMES, handler-to-contract IMPLEMENTS |
| DH03 | `web/app/domainV2/DomainsList.tsx:DomainsList` | `contract::graphql::Query::listDomains` | `graphql/com/linkedin/datahub/graphql/resolvers/domain/ListDomainsResolver.java:ListDomainsResolver.get` | — | — | — | partly covered · start-to-contract CONSUMES, handler-to-contract IMPLEMENTS |
| DH04 | `web/app/tags/CreateNewTagModal/CreateNewTagModal.tsx:CreateNewTagModal.onOk` | `contract::graphql::Mutation::createTag` | `graphql/com/linkedin/datahub/graphql/resolvers/tag/CreateTagResolver.java:CreateTagResolver.get` | — | — | — | partly covered · start-to-contract CONSUMES, handler-to-contract IMPLEMENTS |
| DH05 | — | `contract::graphql::Mutation::deleteTag` | `graphql/com/linkedin/datahub/graphql/resolvers/tag/DeleteTagResolver.java:DeleteTagResolver.get` | — | — | — | partly covered · caller, start-to-contract CONSUMES, handler-to-contract IMPLEMENTS |
| DH06 | `web/app/permissions/roles/ManageRoles.tsx:ManageRoles` | `contract::graphql::Query::listRoles` | `graphql/com/linkedin/datahub/graphql/resolvers/role/ListRolesResolver.java:ListRolesResolver.get` | — | — | — | partly covered · start-to-contract CONSUMES, handler-to-contract IMPLEMENTS |
| DH07 | `web/app/permissions/policy/usePolicy.ts:usePolicy.handleDeleteConfirm` | `contract::graphql::Mutation::deletePolicy` | `graphql/com/linkedin/datahub/graphql/resolvers/policy/DeletePolicyResolver.java:DeletePolicyResolver.get` | — | — | — | partly covered · start-to-contract CONSUMES, handler-to-contract IMPLEMENTS |
| DH08 | `web/app/identity/user/UserListV2.hooks.ts:useUserListData` | `contract::graphql::Query::searchUsers` | `graphql/com/linkedin/datahub/graphql/resolvers/user/SearchUsersResolver.java:SearchUsersResolver.get` | — | — | — | partly covered · start-to-contract CONSUMES, handler-to-contract IMPLEMENTS |
| DH09 | `web/app/ingestV2/source/IngestionSourceList.tsx:IngestionSourceList` | `contract::graphql::Query::listIngestionSources` | `graphql/com/linkedin/datahub/graphql/resolvers/ingest/source/ListIngestionSourcesResolver.java:ListIngestionSourcesResolver.get` | — | — | — | partly covered · start-to-contract CONSUMES, handler-to-contract IMPLEMENTS |
| DH10 | — | `contract::graphql::Mutation::deleteIngestionSource` | `graphql/com/linkedin/datahub/graphql/resolvers/ingest/source/DeleteIngestionSourceResolver.java:DeleteIngestionSourceResolver.get` | — | — | — | partly covered · caller, start-to-contract CONSUMES, handler-to-contract IMPLEMENTS |
| DH11 | `web/app/entityV2/view/builder/ViewBuilder.tsx:ViewBuilder.upsertView` | `contract::graphql::Mutation::createView` | `graphql/com/linkedin/datahub/graphql/resolvers/view/CreateViewResolver.java:CreateViewResolver.get` | — | — | — | partly covered · start-to-contract CONSUMES, handler-to-contract IMPLEMENTS |
| DH12 | `web/app/entityV2/view/menu/ViewDropdownMenu.tsx:ViewDropdownMenu.deleteView` | `contract::graphql::Mutation::deleteView` | `graphql/com/linkedin/datahub/graphql/resolvers/view/DeleteViewResolver.java:DeleteViewResolver.get` | — | — | — | partly covered · start-to-contract CONSUMES, handler-to-contract IMPLEMENTS |
| DH13 | `web/app/sharedV2/owners/useOwnershipTypes.ts:useOwnershipTypes` | `contract::graphql::Query::listOwnershipTypes` | `graphql/com/linkedin/datahub/graphql/resolvers/ownership/ListOwnershipTypesResolver.java:ListOwnershipTypesResolver.get` | — | — | — | partly covered · start-to-contract CONSUMES, handler-to-contract IMPLEMENTS |
| DH14 | `web/app/lineageV3/manualLineage/ManageLineageModal.tsx:ManageLineageModal.saveLineageChanges` | `contract::graphql::Mutation::updateLineage` | `graphql/com/linkedin/datahub/graphql/resolvers/lineage/UpdateLineageResolver.java:UpdateLineageResolver.get` | — | — | — | partly covered · start-to-contract CONSUMES, handler-to-contract IMPLEMENTS |
| DH15 | `ingestion/datahub/ingestion/graph/openapi.py:OpenApiAPI.get_entities` | `http::openapi/POST:/openapi/v3/entity/{entityName}/batchGet` | `openapi/io/datahubproject/openapi/v3/controller/EntityController.java:EntityController.getEntityBatch` | — | IMPLEMENTS | — | partly covered · start-to-contract CONSUMES |
| DH16 | `ingestion/datahub/ingestion/graph/openapi.py:OpenApiAPI.scroll_entities` | `http::openapi/POST:/openapi/v3/entity/scroll` | `openapi/io/datahubproject/openapi/v3/controller/EntityController.java:EntityController.scrollEntities` | — | IMPLEMENTS | — | partly covered · start-to-contract CONSUMES |
| DH17 | `ingestion/datahub/ingestion/graph/openapi.py:OpenApiAPI.scroll_relationships` | — | `openapi/io/datahubproject/openapi/controller/GenericRelationshipController.java:GenericRelationshipController.scrollRelationships` | — | — | — | partly covered · contract, start-to-contract CONSUMES, handler-to-contract IMPLEMENTS |
| DH18 | `ingestion/datahub/ingestion/graph/openapi.py:OpenApiAPI.scroll_lineage` | `http::openapi/POST:/openapi/v3/lineage/scroll` | `openapi/io/datahubproject/openapi/v3/controller/LineageController.java:LineageController.scrollLineage` | — | IMPLEMENTS | SEMANTIC_SIMILAR | partly covered · start-to-contract CONSUMES |
| DH19 | `ingestion/datahub/ingestion/graph/client.py:DataHubGraph.get_entity_aspect_specs` | `http::openapi/GET:/openapi/v1/registry/models/entity/specifications` | `openapi/io/datahubproject/openapi/v1/registry/EntityRegistryController.java:EntityRegistryController.getEntitySpecs` | — | IMPLEMENTS | — | partly covered · start-to-contract CONSUMES |
| DH20 | `ingestion/datahub/ingestion/graph/client.py:DataHubGraph.get_aspect` | — | `restli/com/linkedin/metadata/resources/entity/AspectResource.java:AspectResource.get` | — | — | — | partly covered · contract, start-to-contract CONSUMES, handler-to-contract IMPLEMENTS |
| DH21 | `ingestion/datahub/ingestion/graph/client.py:DataHubGraph.get_usage_aspects_from_urn` | — | `restli/com/linkedin/metadata/resources/entity/AspectResource.java:AspectResource.getTimeseriesAspectValues` | — | — | — | partly covered · contract, start-to-contract CONSUMES, handler-to-contract IMPLEMENTS |
| DH22 | `ingestion/datahub/ingestion/graph/client.py:DataHubGraph.list_all_entity_urns` | — | `restli/com/linkedin/metadata/resources/entity/EntityResource.java:EntityResource.listUrns` | — | — | — | partly covered · contract, start-to-contract CONSUMES, handler-to-contract IMPLEMENTS |
| DH23 | `ingestion/datahub/ingestion/graph/client.py:DataHubGraph.get_entity_raw` | — | `restli/com/linkedin/metadata/resources/entity/EntityV2Resource.java:EntityV2Resource.get` | — | — | — | partly covered · contract, start-to-contract CONSUMES, handler-to-contract IMPLEMENTS |
| DH24 | `ingestion/datahub/ingestion/graph/client.py:DataHubGraph.delete_references_to_urn` | — | `restli/com/linkedin/metadata/resources/entity/EntityResource.java:EntityResource.deleteReferencesTo` | — | — | SEMANTIC_SIMILAR | partly covered · contract, start-to-contract CONSUMES, handler-to-contract IMPLEMENTS |
| DH25 | `ingestion/datahub/ingestion/graph/client.py:DataHubGraph._restore_index_call` | — | `restli/com/linkedin/metadata/resources/operations/OperationsResource.java:OperationsResource.restoreIndices` | — | — | — | partly covered · contract, start-to-contract CONSUMES, handler-to-contract IMPLEMENTS |
| DH26 | `ingestion/datahub/emitter/rest_emitter.py:DataHubRestEmitter._emit_restli_mcps` | — | `restli/com/linkedin/metadata/resources/entity/AspectResource.java:AspectResource.ingestProposalBatch` | — | — | — | partly covered · contract, start-to-contract CONSUMES, handler-to-contract IMPLEMENTS |

## GraphQL operation paths

The hook and operation were located independently from the verified operation document and generated-hook name. An external hook symbol, where present, is a fallback symbol without source provenance.

| Link | Generated hook file/name | Exact hook ID | Start → hook / external | External hook ID | Document | Hook → doc / op | Document → operation | Operation | Operation → field | Start → operation | Resolver class → field |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DH01 | `datahub-web-react/src/graphql/domain.generated.ts:useCreateDomainMutation` | — | — / — | external::useCreateDomainMutation | file::datahub-web-react/src/graphql/domain.graphql | — / — | CONTAINS | graphqlop::datahub-web-react/src/graphql/domain.graphql:mutation:createDomain | CONSUMES | — | graphql/com/linkedin/datahub/graphql/resolvers/domain/CreateDomainResolver.java:CreateDomainResolver · IMPLEMENTS |
| DH02 | `datahub-web-react/src/graphql/domain.generated.ts:useDeleteDomainMutation` | — | — / — | external::useDeleteDomainMutation | file::datahub-web-react/src/graphql/domain.graphql | — / — | CONTAINS | graphqlop::datahub-web-react/src/graphql/domain.graphql:mutation:deleteDomain | CONSUMES | — | graphql/com/linkedin/datahub/graphql/resolvers/domain/DeleteDomainResolver.java:DeleteDomainResolver · IMPLEMENTS |
| DH03 | `datahub-web-react/src/graphql/domain.generated.ts:useListDomainsQuery` | — | — / CALLS | external::useListDomainsQuery | file::datahub-web-react/src/graphql/domain.graphql | — / — | CONTAINS | graphqlop::datahub-web-react/src/graphql/domain.graphql:query:listDomains | CONSUMES | — | graphql/com/linkedin/datahub/graphql/resolvers/domain/ListDomainsResolver.java:ListDomainsResolver · IMPLEMENTS |
| DH04 | `datahub-web-react/src/graphql/tag.generated.ts:useCreateTagMutation` | — | — / — | external::useCreateTagMutation | file::datahub-web-react/src/graphql/tag.graphql | — / — | CONTAINS | graphqlop::datahub-web-react/src/graphql/tag.graphql:mutation:createTag | CONSUMES | — | graphql/com/linkedin/datahub/graphql/resolvers/tag/CreateTagResolver.java:CreateTagResolver · IMPLEMENTS |
| DH05 | `datahub-web-react/src/graphql/tag.generated.ts:useDeleteTagMutation` | — | — / — | external::useDeleteTagMutation | file::datahub-web-react/src/graphql/tag.graphql | — / — | CONTAINS | graphqlop::datahub-web-react/src/graphql/tag.graphql:mutation:deleteTag | CONSUMES | — | graphql/com/linkedin/datahub/graphql/resolvers/tag/DeleteTagResolver.java:DeleteTagResolver · IMPLEMENTS |
| DH06 | `datahub-web-react/src/graphql/role.generated.ts:useListRolesQuery` | — | — / CALLS | external::useListRolesQuery | file::datahub-web-react/src/graphql/role.graphql | — / — | CONTAINS | graphqlop::datahub-web-react/src/graphql/role.graphql:query:listRoles | CONSUMES | — | graphql/com/linkedin/datahub/graphql/resolvers/role/ListRolesResolver.java:ListRolesResolver · IMPLEMENTS |
| DH07 | `datahub-web-react/src/graphql/policy.generated.ts:useDeletePolicyMutation` | — | — / — | external::useDeletePolicyMutation | file::datahub-web-react/src/graphql/policy.graphql | — / — | CONTAINS | graphqlop::datahub-web-react/src/graphql/policy.graphql:mutation:deletePolicy | CONSUMES | — | graphql/com/linkedin/datahub/graphql/resolvers/policy/DeletePolicyResolver.java:DeletePolicyResolver · IMPLEMENTS |
| DH08 | `datahub-web-react/src/graphql/user.generated.ts:useSearchUsersQuery` | — | — / CALLS | external::useSearchUsersQuery | file::datahub-web-react/src/graphql/user.graphql | — / — | CONTAINS | graphqlop::datahub-web-react/src/graphql/user.graphql:query:searchUsers | CONSUMES | — | graphql/com/linkedin/datahub/graphql/resolvers/user/SearchUsersResolver.java:SearchUsersResolver · IMPLEMENTS |
| DH09 | `datahub-web-react/src/graphql/ingestion.generated.ts:useListIngestionSourcesQuery` | — | — / CALLS | external::useListIngestionSourcesQuery | file::datahub-web-react/src/graphql/ingestion.graphql | — / — | CONTAINS | graphqlop::datahub-web-react/src/graphql/ingestion.graphql:query:listIngestionSources | CONSUMES | — | graphql/com/linkedin/datahub/graphql/resolvers/ingest/source/ListIngestionSourcesResolver.java:ListIngestionSourcesResolver · IMPLEMENTS |
| DH10 | `datahub-web-react/src/graphql/ingestion.generated.ts:useDeleteIngestionSourceMutation` | — | — / — | external::useDeleteIngestionSourceMutation | file::datahub-web-react/src/graphql/ingestion.graphql | — / — | CONTAINS | graphqlop::datahub-web-react/src/graphql/ingestion.graphql:mutation:deleteIngestionSource | CONSUMES | — | graphql/com/linkedin/datahub/graphql/resolvers/ingest/source/DeleteIngestionSourceResolver.java:DeleteIngestionSourceResolver · IMPLEMENTS |
| DH11 | `datahub-web-react/src/graphql/view.generated.ts:useCreateViewMutation` | — | — / — | external::useCreateViewMutation | file::datahub-web-react/src/graphql/view.graphql | — / — | CONTAINS | graphqlop::datahub-web-react/src/graphql/view.graphql:mutation:createView | CONSUMES | — | graphql/com/linkedin/datahub/graphql/resolvers/view/CreateViewResolver.java:CreateViewResolver · IMPLEMENTS |
| DH12 | `datahub-web-react/src/graphql/view.generated.ts:useDeleteViewMutation` | — | — / — | external::useDeleteViewMutation | file::datahub-web-react/src/graphql/view.graphql | — / — | CONTAINS | graphqlop::datahub-web-react/src/graphql/view.graphql:mutation:deleteView | CONSUMES | — | graphql/com/linkedin/datahub/graphql/resolvers/view/DeleteViewResolver.java:DeleteViewResolver · IMPLEMENTS |
| DH13 | `datahub-web-react/src/graphql/ownership.generated.ts:useListOwnershipTypesQuery` | — | — / CALLS | external::useListOwnershipTypesQuery | file::datahub-web-react/src/graphql/ownership.graphql | — / — | CONTAINS | graphqlop::datahub-web-react/src/graphql/ownership.graphql:query:listOwnershipTypes | CONSUMES | — | graphql/com/linkedin/datahub/graphql/resolvers/ownership/ListOwnershipTypesResolver.java:ListOwnershipTypesResolver · IMPLEMENTS |
| DH14 | `datahub-web-react/src/graphql/mutations.generated.ts:useUpdateLineageMutation` | — | — / — | external::useUpdateLineageMutation | file::datahub-web-react/src/graphql/mutations.graphql | — / — | CONTAINS | graphqlop::datahub-web-react/src/graphql/mutations.graphql:mutation:updateLineage | CONSUMES | — | graphql/com/linkedin/datahub/graphql/resolvers/lineage/UpdateLineageResolver.java:UpdateLineageResolver · IMPLEMENTS |

## Rest.li action identity

| Link | Exact action or resource | Collection candidates | Collapsed |
| --- | --- | --- | --- |
| DH20 | — | [] | no |
| DH21 | — | [] | no |
| DH22 | — | [] | no |
| DH23 | — | [] | no |
| DH24 | — | [] | no |
| DH25 | — | [] | no |
| DH26 | — | [] | no |

## HTTP dispatch and DH17 shared handler

Dispatch checks follow SDK-local call edges, then look for a confirmed HTTP_CALLS to the mapped handler or a CONSUMES to the mapped contract. Tentative HTTP targets are shown separately.

| Link | Found dispatch path |
| --- | --- |
| DH15 | — |
| DH16 | — |
| DH18 | — |

| Route | Contract ID | Handler → contract |
| --- | --- | --- |
| POST /openapi/v2/relationship/scroll | — | — |
| POST /openapi/v3/relationship/scroll | — | — |

Unprefixed route candidates from the same contract-name index:

| Candidate | Source file |
| --- | --- |
| http::openapi/POST:/scroll | metadata-service/openapi-servlet/src/main/java/io/datahubproject/openapi/controller/GenericRelationshipController.java |

## Depth and degree

Depth counts raw undirected GraphML hops. Multigraph degree counts parallel edges. Rows with three independently matched nodes are shown for description even when required edges are missing.

| Link | Coverage | Contract hops | Handler hops | Max depth | Start degree | Contract degree | Within 2 hops including start |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DH01 | partly covered | 4 | 3 | 4 | 58 | 3 | 1604 |
| DH02 | partly covered | 5 | 3 | 5 | 23 | 3 | 1473 |
| DH03 | partly covered | 5 | 4 | 5 | 81 | 3 | 2358 |
| DH04 | partly covered | 6 | 4 | 6 | 44 | 3 | 1367 |
| DH06 | partly covered | 2 | 2 | 2 | 89 | 3 | 2395 |
| DH07 | partly covered | 5 | 3 | 5 | 39 | 3 | 1606 |
| DH08 | partly covered | 7 | 5 | 7 | 17 | 3 | 45 |
| DH09 | partly covered | 4 | 4 | 4 | 231 | 6 | 2945 |
| DH11 | partly covered | 5 | 4 | 5 | 38 | 3 | 1268 |
| DH12 | partly covered | 5 | 3 | 5 | 33 | 3 | 1473 |
| DH13 | partly covered | 2 | 2 | 2 | 20 | 3 | 613 |
| DH14 | partly covered | 5 | 5 | 5 | 18 | 3 | 1459 |
| DH15 | partly covered | 5 | 4 | 5 | 41 | 2 | 438 |
| DH16 | partly covered | 3 | 2 | 3 | 74 | 2 | 708 |
| DH18 | partly covered | 2 | 1 | 2 | 58 | 2 | 1873 |
| DH19 | partly covered | 5 | 4 | 5 | 53 | 2 | 2548 |

## Inventory and semantic growth

| Node type | Count |
| --- | --- |
| variable | 132697 |
| external_func | 42225 |
| return | 37470 |
| function | 27814 |
| symbol_ref | 18806 |
| callsite | 16890 |
| argument_expression | 11496 |
| property | 6085 |
| file | 6083 |
| class | 4790 |
| contract | 4046 |
| type | 1599 |
| interface | 1324 |
| graphql_operation | 342 |
| module | 269 |
| http_endpoint | 123 |
| http_callsite | 11 |

| Node language | Count |
| --- | --- |
| Python | 162348 |
| TypeScript | 68105 |
| Unattributed | 42225 |
| Java | 34841 |
| GraphQL | 4534 |
| Scala | 16 |
| JavaScript | 1 |

| Relation | Layer | Count |
| --- | --- | --- |
| USES | Lflow | 277646 |
| CALLS | Ldep | 146801 |
| FLOWS_TO | Lflow | 124790 |
| SEMANTIC_SIMILAR | Lsem | 105546 |
| DEFINES | Lflow | 80212 |
| IMPORTS | Ldep | 77166 |
| PASSES_ARG | Lflow | 59312 |
| CONTAINS | Lsyn | 57507 |
| RETURNS | Lflow | 37470 |
| INVOKES | Ldep | 15750 |
| CONSUMES | Lcontract | 12610 |
| EVALUATES | Lflow | 11496 |
| DECLARES | Lcontract | 6126 |
| EXTENDS | Ldep | 3704 |
| MUTATES | Lflow | 1979 |
| IMPLEMENTS | Lcontract | 736 |
| POLYMORPHIC_CALL | Ldep | 658 |
| EXTENDS | Lcontract | 180 |
| PRODUCES | Lcontract | 125 |
| HTTP_REQUEST | Lcontract | 11 |

Child graphs contributed 1,020 SEMANTIC_SIMILAR edges. The workspace pass added 104,526. The JSON includes the full node-type × language and relation × source/target-language inventories. No same-scope older DataHub semantic count was available in the source recon evidence, so the growth shown here is the child-to-workspace increment.

## Root causes and bounded recovery

See the per-link missing elements above. The following are source-based proposals only.

- GraphQL operation discovery emits operation → field and document → operation (`graphql_links.py:218–255`). The embedded binder handles literal tags (`graphql_embedded.py:108–146`). The pinned source does not track the near-operation hook files configured in `datahub-web-react/codegen.yml:20–29`. Resolve the generated-hook name back to the checked-in operation from codegen metadata, then emit the UI caller → field CONSUMES with the operation as provenance. 12 rows have independently matched caller, handler and field plus an existing operation → field edge. Those rows are the immediate candidates for fixing the missing start link.
- Java GraphQL binding emits IMPLEMENTS from the resolver class, not its get method (`graphql_java_bindings.py:89–113`). Resolve the unique DataFetcher get declaration in that same class before adding the method edge. 12 of the preceding candidates already have a class-edge binding. These counts are ceilings, not a measured recovery.
- DH05, DH10 map to same-line variables for `useCallback` initializers. The JavaScript adapter recognizes a directly assigned arrow or function expression (`polyglot.py:541–545`). Representing the callback as a named function could recover the missing starts for 2 more rows, alongside both GraphQL binding changes.
- HTTP workspace binding is evidence-gated by URL and server ownership (`graph_builder_http.py:501–572`). Spring method registration uses the class route prefix and a directly annotated method (`polyglot.py:1242–1263`). Propagate a proven SDK base URL through its request wrappers and bind inherited mappings to each concrete route. Keep provisional paths distinct from confirmed HTTP_CALLS or CONSUMES.
- Rest.li restspec JSON does not meet the OpenAPI filename selector (`multi_repo.py:849–854`). Read the restspec collection, verb and action identity, then match annotation registration and the literal action selector. This is the prerequisite for DH20–DH26. A collection-only edge cannot recover an action-specific gold path.
