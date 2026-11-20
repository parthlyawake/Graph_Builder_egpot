# DataHub v3 OpenAPI audit

One full guarded rebuild used the same nine production roots, allowlist, nonproduction filters and generated-file rules as v2. No retrieval or scoring ran.

Builder `ea3f50e25f22e141495569207a8b16cbbd79e319`. Graph SHA-256 `041015fba8ab3baa7cc883955fcc700e344839b50d72359e072b2bcf43ebfeb0`. 314,219 nodes, 1,032,832 edges, and 848,501,191 bytes. Build 265.93 s, peak 3.02 GiB. Semantic edges 112,603.

## Matching rule

Trusted bases are `self._gms_server`, `self.config.gms_server`, `self.gms_server`. Source-proven local aliases, forwarded helper arguments, and `.rstrip('/')` preserve that provenance. The typed instance session names are `self._session`, `self.session`. Recognized HTTP modules and typed local receivers also require SDK URL provenance. Each same-verb route must match every segment, including at least one literal segment. Constrained parameters require complete regex matches against a known segment; unsupported constraints and unknown dynamic values fail closed. Equal best literal counts are recorded as ambiguous and emit no edge.

## v2 → v3 graph diff

Attribute comparison includes direction and parallel-edge multiplicity. Endpoint/relation identities show the actual removed bindings, separately from the new evidence fields on retained edges.

| Relation | Removed with attributes | Added with attributes | Removed with keys | Added with keys |
| --- | --- | --- | --- | --- |
| CONSUMES | 100 | 12 | 100 | 12 |

## v1 → v2 node attribution

| Cause or directly observed change | Removed nodes |
| --- | --- |
| external symbol with only React-side old graph references | 119 |
| old source artifact inside a newly scoped React callback | 24 |
| same source identity present within a newly scoped React callback | 1054 |

React callback scopes replace the old parent-scoped identities, including function, variable, return, callsite and argument-expression nodes. The removed external stubs had only React-side references in v1. The JSON preserves the ID and source anchor for every removed node and the complete attribute pairs for every retained ID with a change.

| Retained ID | Attribute | Before | After |
| --- | --- | --- | --- |
| `external::expand` | repo | web | ingestion |
| `external::next` | repo | web | ingestion |
| `web/alchemy-components/components/CodeBlock/CodeBlockEditor.tsx:CodeBlockEditor.var::el` | line_no | 69 | 84 |
| `web/app/entityV2/shared/EntitySearchSelect/ActorsSearchSelect.tsx:ActorsSearchSelect.var::entity` | line_no | 196 | 244 |
| `web/app/entityV2/shared/EntitySearchSelect/EntitySearchDropdown.tsx:EntitySearchDropdown.var::typesToSearch` | line_no | 145 | 199 |
| `web/app/homeV2/layout/sidebar/documents/DocumentTree.tsx:DocumentTree.var::next` | line_no | 192 | 222 |
| `web/app/homeV3/modules/hierarchyViewModule/treeView/context/TreeViewContextProvider.tsx:TreeViewContextProvider.var::loadChildren` | line_no | 14 | 50 |
| `web/app/ingestV2/source/usePollSource.ts:usePollSource.var::newSet` | line_no | 36 | 91 |
| `web/app/sharedV2/icons/PlatformIcon.tsx:PlatformIcon.var::img` | line_no | 80 | 112 |
| `web/app/sharedV2/tags/TagSelect.tsx:TagSelect.var::trimmed` | line_no | 105 | 203 |

Eight retained React variable IDs now point to a different declaration line after callback scoping. Two shared external IDs changed first-contributor `repo` metadata from web to ingestion.

## OpenAPI census

| Population | Correct | Incorrect | Unverifiable |
| --- | --- | --- | --- |
| native | 105 | 14 | 0 |
| sdk_consumes | 12 | 0 | 0 |
| spring_inherited_route | 26 | 0 | 0 |

Before the fix, the v2 client census has 88 incorrect, 12 correct, and 0 unverifiable `CONSUMES` edges. V3 records 0 ambiguous requests. Ambiguous requests are not graph edges. The native Spring declarations are retained in both graphs. The JSON includes the full v3 census and the v2 client findings.

### Incorrect surviving native edges

| Handler | Exported route | Source | Reason |
| --- | --- | --- | --- |
| `openapi/io/datahubproject/openapi/controller/GenericEntitiesController.java:GenericEntitiesController.getEntities` | `GET /{entityName}` | `metadata-service/openapi-servlet/src/main/java/io/datahubproject/openapi/controller/GenericEntitiesController.java:216` | Annotation describes an inherited fragment, but the owner is not a registered concrete controller at this URL. |
| `openapi/io/datahubproject/openapi/controller/GenericEntitiesController.java:GenericEntitiesController.getEntity` | `GET /{entityName}/{entityUrn:urn:li:.+}` | `metadata-service/openapi-servlet/src/main/java/io/datahubproject/openapi/controller/GenericEntitiesController.java:386` | Annotation describes an inherited fragment, but the owner is not a registered concrete controller at this URL. |
| `openapi/io/datahubproject/openapi/controller/GenericEntitiesController.java:GenericEntitiesController.headEntity` | `GET /{entityName}/{entityUrn:urn:li:.+}` | `metadata-service/openapi-servlet/src/main/java/io/datahubproject/openapi/controller/GenericEntitiesController.java:430` | Exported verb/path differs from the annotated Spring route. |
| `openapi/io/datahubproject/openapi/controller/GenericEntitiesController.java:GenericEntitiesController.getAspect` | `GET /{entityName}/{entityUrn:urn:li:.+}/{aspectName}` | `metadata-service/openapi-servlet/src/main/java/io/datahubproject/openapi/controller/GenericEntitiesController.java:465` | Annotation describes an inherited fragment, but the owner is not a registered concrete controller at this URL. |
| `openapi/io/datahubproject/openapi/controller/GenericEntitiesController.java:GenericEntitiesController.headAspect` | `GET /{entityName}/{entityUrn:urn:li:.+}/{aspectName}` | `metadata-service/openapi-servlet/src/main/java/io/datahubproject/openapi/controller/GenericEntitiesController.java:530` | Exported verb/path differs from the annotated Spring route. |
| `openapi/io/datahubproject/openapi/controller/GenericEntitiesController.java:GenericEntitiesController.deleteEntity` | `DELETE /{entityName}/{entityUrn:urn:li:.+}` | `metadata-service/openapi-servlet/src/main/java/io/datahubproject/openapi/controller/GenericEntitiesController.java:569` | Annotation describes an inherited fragment, but the owner is not a registered concrete controller at this URL. |
| `openapi/io/datahubproject/openapi/controller/GenericEntitiesController.java:GenericEntitiesController.createEntity` | `POST /{entityName}` | `metadata-service/openapi-servlet/src/main/java/io/datahubproject/openapi/controller/GenericEntitiesController.java:635` | Annotation describes an inherited fragment, but the owner is not a registered concrete controller at this URL. |
| `openapi/io/datahubproject/openapi/controller/GenericEntitiesController.java:GenericEntitiesController.deleteAspect` | `DELETE /{entityName}/{entityUrn:urn:li:.+}/{aspectName}` | `metadata-service/openapi-servlet/src/main/java/io/datahubproject/openapi/controller/GenericEntitiesController.java:677` | Annotation describes an inherited fragment, but the owner is not a registered concrete controller at this URL. |
| `openapi/io/datahubproject/openapi/controller/GenericEntitiesController.java:GenericEntitiesController.createAspect` | `POST /{entityName}/{entityUrn:urn:li:.+}/{aspectName}` | `metadata-service/openapi-servlet/src/main/java/io/datahubproject/openapi/controller/GenericEntitiesController.java:749` | Annotation describes an inherited fragment, but the owner is not a registered concrete controller at this URL. |
| `openapi/io/datahubproject/openapi/controller/GenericEntitiesController.java:GenericEntitiesController.patchAspect` | `PATCH /{entityName}/{entityUrn:urn:li:.+}/{aspectName}` | `metadata-service/openapi-servlet/src/main/java/io/datahubproject/openapi/controller/GenericEntitiesController.java:830` | Annotation describes an inherited fragment, but the owner is not a registered concrete controller at this URL. |
| `openapi/io/datahubproject/openapi/controller/GenericRelationshipController.java:GenericRelationshipController.getRelationshipsByType` | `GET /{relationshipType}` | `metadata-service/openapi-servlet/src/main/java/io/datahubproject/openapi/controller/GenericRelationshipController.java:58` | Annotation describes an inherited fragment, but the owner is not a registered concrete controller at this URL. |
| `openapi/io/datahubproject/openapi/controller/GenericRelationshipController.java:GenericRelationshipController.getRelationshipsByEntity` | `GET /{entityName}/{entityUrn}` | `metadata-service/openapi-servlet/src/main/java/io/datahubproject/openapi/controller/GenericRelationshipController.java:156` | Annotation describes an inherited fragment, but the owner is not a registered concrete controller at this URL. |
| `openapi/io/datahubproject/openapi/controller/GenericRelationshipController.java:GenericRelationshipController.scrollRelationships` | `POST /scroll` | `metadata-service/openapi-servlet/src/main/java/io/datahubproject/openapi/controller/GenericRelationshipController.java:288` | Annotation describes an inherited fragment, but the owner is not a registered concrete controller at this URL. |
| `openapi/io/datahubproject/openapi/v1/relationships/RelationshipsController.java:RelationshipsController.getRelationships` | `GET /openapi/relationships/v1/, ` | `metadata-service/openapi-servlet/src/main/java/io/datahubproject/openapi/v1/relationships/RelationshipsController.java:115` | Exported verb/path differs from the annotated Spring route. |

## Fresh independent source checks

For each rule, sort edges by source, destination and key, exclude its earlier 30 seed-0 edges, and draw with a fresh `random.Random(1)`. The Rest.li pool has only 62 remaining edges and all were reviewed.

| Rule | Eligible pool | Reviewed | Correct | Incorrect | Unverifiable |
| --- | --- | --- | --- | --- | --- |
| apollo | 1344 | 100 | 100 | 0 | 0 |
| java_graphql | 581 | 100 | 100 | 0 | 0 |
| restli | 62 | 62 | 62 | 0 | 0 |

## Coverage and topology

All 52 required edges verified after a fresh declaration-only ID mapping. The query file stayed byte-identical at SHA-256 `69e72fde97c6d7c32fc1809f74b45d960af11ac1566da57059a783af25bde6e0`. The undirected raw graph's budget-40 share is 0.01273%. Degree counts all directed incidences and parallel edges. Two-hop counts include the start.

### Python → OpenAPI

| Link | Coverage | Contract hops | Handler hops | Gold depth | Start degree | Contract degree | Within 2 hops |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DH15 | fully covered | 1 | 2 | 2 | 42 | 3 | 441 |
| DH16 | fully covered | 1 | 2 | 2 | 75 | 3 | 709 |
| DH17 | fully covered | 1 | 2 | 2 | 38 | 3 | 74 |
| DH18 | fully covered | 1 | 1 | 1 | 59 | 3 | 1873 |
| DH19 | fully covered | 1 | 2 | 2 | 54 | 3 | 2550 |

### Python → Rest.li

| Link | Coverage | Contract hops | Handler hops | Gold depth | Start degree | Contract degree | Within 2 hops |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DH20 | fully covered | 1 | 2 | 2 | 92 | 21 | 1297 |
| DH21 | fully covered | 1 | 2 | 2 | 46 | 8 | 2219 |
| DH22 | fully covered | 1 | 2 | 2 | 33 | 4 | 2122 |
| DH23 | fully covered | 1 | 2 | 2 | 30 | 11 | 912 |
| DH24 | fully covered | 1 | 1 | 1 | 29 | 4 | 694 |
| DH25 | fully covered | 1 | 2 | 2 | 15 | 5 | 1458 |
| DH26 | fully covered | 1 | 2 | 2 | 97 | 5 | 3544 |

### React → GraphQL

| Link | Coverage | Contract hops | Handler hops | Gold depth | Start degree | Contract degree | Within 2 hops |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DH01 | fully covered | 1 | 2 | 2 | 62 | 6 | 1694 |
| DH02 | fully covered | 1 | 2 | 2 | 25 | 6 | 1488 |
| DH03 | fully covered | 1 | 2 | 2 | 83 | 6 | 2555 |
| DH04 | fully covered | 1 | 2 | 2 | 51 | 6 | 1438 |
| DH05 | fully covered | 1 | 2 | 2 | 31 | 6 | 1663 |
| DH06 | fully covered | 1 | 2 | 2 | 93 | 8 | 2501 |
| DH07 | fully covered | 1 | 2 | 2 | 27 | 6 | 1544 |
| DH08 | fully covered | 1 | 2 | 2 | 19 | 5 | 56 |
| DH09 | fully covered | 1 | 2 | 2 | 210 | 11 | 3157 |
| DH10 | fully covered | 1 | 2 | 2 | 36 | 6 | 1697 |
| DH11 | fully covered | 1 | 2 | 2 | 42 | 8 | 1326 |
| DH12 | fully covered | 1 | 2 | 2 | 33 | 8 | 1463 |
| DH13 | fully covered | 1 | 2 | 2 | 22 | 6 | 623 |
| DH14 | fully covered | 1 | 2 | 2 | 20 | 6 | 1519 |

## Startup timing only

V3 GraphML load 24.68 s and TF-IDF fit 8.01 s. The earlier v2 observations were 27.00 s and 9.50 s. V3 timing constructed a graph view and fit a scorer under the audit guard. It issued no query or method call.
