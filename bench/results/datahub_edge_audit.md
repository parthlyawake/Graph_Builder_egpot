# DataHub builder v2 edge audit

Source and graph inspection only. No retrieval ran on a labeled query.

## Build time and scope

Successful measured builds took 13,679.22 s (v1) and 358.05 s (v2). Both used the same nine roots, production allowlist, nonproduction path, filename, and generated-header filters, and the same source-parser fallback.

Generated-file globs were `*.generated.*`, `*.min.js`, and `tests.graphql`. The excluded directory names are recorded in both build reports.

| Root | Production directory | v1 D/P/partial/F | v2 D/P/partial/F | v1 child nodes | v2 child nodes |
| --- | --- | --- | --- | --- | --- |
| frontend | datahub-frontend/app | 61/61/0/0 | 61/61/0/0 | 3,755 | 3,755 |
| graphql | datahub-graphql-core/src/main/java | 644/644/0/0 | 644/644/0/0 | 38,247 | 38,247 |
| graphql-idl | datahub-graphql-core/src/main/resources | 0/0/0/0 | 0/0/0/0 | 0 | 0 |
| ingestion | metadata-ingestion/src | 1627/1627/0/0 | 1627/1627/0/0 | 177,855 | 177,855 |
| openapi | metadata-service/openapi-servlet/src/main/java | 82/82/0/0 | 82/82/0/0 | 8,018 | 8,018 |
| openapi-idl | metadata-service/openapi-servlet/src/main/resources | 0/0/0/0 | 0/0/0/0 | 0 | 0 |
| restli | metadata-service/restli-servlet-impl/src/main/java | 15/15/0/0 | 15/15/0/0 | 2,150 | 2,150 |
| restli-idl | metadata-service/restli-api/src/main/idl | 0/0/0/0 | 0/0/0/0 | 0 | 0 |
| web | datahub-web-react/src | 3508/3128/380/0 | 3508/3128/380/0 | 78,628 | 80,691 |

Child counts come from child-owned nodes plus endpoints of namespaced child edges. Workspace-only inherited endpoints are excluded. Reconstructed counts agree with the available child build logs.

The v1 process was observed spending CPU in the per-call scan over all call-site evidence and in full node scans for Python route functions and HTTP caller lookup. The ingestion child alone resolved 102,416 call sites. V2 indexes call-site evidence once and builds per-file HTTP name and line indexes. It also uses constant-time node counts to audit source extraction. See `graft_ckg.py:584–603,1387–1404`, `http_extended.py:37–74`, and `graph_builder_http.py:132–145`. Both timings cover individual successful build invocations. The abandoned v1 attempt is outside its reported timer. The successful worker continued across the network disconnect and exported without a restart. No cached graph was reused. The logs and code explain the dominant work; they do not identify each optimization’s individual share.

## Graph diff

The graphs differ beyond the directly tagged new edges. Callback scoping changes ordinary source nodes and edges. The workspace semantic pass also changes similarity edges. Exported edge keys shift for many otherwise identical edges. Each comparison includes all serialized attributes and preserves multiedge multiplicity.

| Node type | Removed | Added | Retained ID with changed attributes |
| --- | --- | --- | --- |
| argument_expression | 56 | 267 | 0 |
| callsite | 60 | 402 | 0 |
| external_func | 119 | 7 | 2 |
| file | 0 | 10 | 0 |
| function | 10 | 793 | 0 |
| http_endpoint | 0 | 74 | 0 |
| return | 486 | 488 | 0 |
| variable | 466 | 1305 | 8 |

| Relation | Removed (attributes) | Added (attributes) | Removed (with key) | Added (with key) |
| --- | --- | --- | --- | --- |
| CALLS | 2120 | 2919 | 30334 | 31133 |
| CONSUMES | 0 | 835 | 0 | 835 |
| CONTAINS | 70 | 1243 | 10195 | 11368 |
| DECLARES | 0 | 0 | 6053 | 6053 |
| DEFINES | 571 | 621 | 13540 | 13590 |
| EVALUATES | 56 | 267 | 56 | 267 |
| EXTENDS | 0 | 0 | 227 | 227 |
| FLOWS_TO | 268 | 643 | 5790 | 6165 |
| IMPLEMENTS | 0 | 680 | 0 | 680 |
| IMPORTS | 0 | 0 | 30120 | 30120 |
| INVOKES | 49 | 313 | 49 | 313 |
| MUTATES | 26 | 26 | 847 | 847 |
| PASSES_ARG | 6 | 745 | 11455 | 12194 |
| POLYMORPHIC_CALL | 0 | 6 | 8 | 14 |
| PRODUCES | 0 | 26 | 0 | 26 |
| RETURNS | 486 | 488 | 11148 | 11150 |
| SEMANTIC_SIMILAR | 93373 | 100430 | 104692 | 111749 |
| USES | 2353 | 2543 | 47278 | 47468 |
| USES_OPERATION | 0 | 688 | 0 | 688 |

## Precision sample

For each rule, 30 edges were drawn from its combined relation population, sorted by source, destination and key, using a fresh `random.Random(0)`. Verdicts concern the sampled edges. The JSON contains all sample IDs, source excerpts and verdicts.

| Rule | Population | Sampled | Correct | Incorrect | Unverifiable |
| --- | --- | --- | --- | --- | --- |
| apollo | 1374 | 30 | 30 | 0 | 0 |
| java_graphql | 611 | 30 | 30 | 0 | 0 |
| openapi | 126 | 30 | 9 | 21 | 0 |
| restli | 92 | 30 | 30 | 0 | 0 |

### Incorrect sampled edges

| Sample | Caller | Target | Source citation | Reason |
| --- | --- | --- | --- | --- |
| 2 | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations._get_view_definitions` | `GET /{entityName}/{entityUrn:urn:li:.+}/{aspectName}` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:875` | Dremio SQL or job API on the Dremio host. The unprefixed DataHub template accepts those otherwise unrelated path segments. |
| 3 | `ingestion/datahub/ingestion/source/snowplow/services/iglu_client.py:IgluClient.validate_schema` | `POST /{entityName}/{entityUrn:urn:li:.+}/{aspectName}` | `ingestion/datahub/ingestion/source/snowplow/services/iglu_client.py:355` | Iglu schema registry validation on the configured Iglu host. The unprefixed DataHub template accepts those otherwise unrelated path segments. |
| 5 | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations._supports_array_queried_datasets` | `POST /{entityName}` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:1245` | Dremio SQL or job API on the Dremio host. The unprefixed DataHub template accepts those otherwise unrelated path segments. |
| 7 | `ingestion/datahub/ingestion/source/aws/glue.py:GlueSourceConfig.lakeformation_client` | `GET /{entityName}/{entityUrn:urn:li:.+}/{aspectName}` | `ingestion/datahub/ingestion/source/aws/glue.py:650` | AWS SDK/control-plane session and credentials, with no DataHub resource dispatch. The unprefixed DataHub template accepts those otherwise unrelated path segments. |
| 8 | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations.extract_all_queries` | `POST /{entityName}/{entityUrn:urn:li:.+}/{aspectName}` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:1294` | Dremio SQL or job API on the Dremio host. The unprefixed DataHub template accepts those otherwise unrelated path segments. |
| 9 | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations.execute_query_iter` | `POST /{entityName}/{entityUrn:urn:li:.+}/{aspectName}` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:650` | Dremio SQL or job API on the Dremio host. The unprefixed DataHub template accepts those otherwise unrelated path segments. |
| 10 | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations._get_view_definitions` | `POST /{entityName}/{entityUrn:urn:li:.+}/{aspectName}` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:875` | Dremio SQL or job API on the Dremio host. The unprefixed DataHub template accepts those otherwise unrelated path segments. |
| 13 | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations._fetch_results_iter` | `GET /{entityName}/{entityUrn:urn:li:.+}/{aspectName}` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:605` | Dremio SQL or job API on the Dremio host. The unprefixed DataHub template accepts those otherwise unrelated path segments. |
| 14 | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations.execute_query_iter` | `POST /{entityName}` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:639` | Dremio SQL or job API on the Dremio host. The unprefixed DataHub template accepts those otherwise unrelated path segments. |
| 15 | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations._get_all_tables_partitioned_by_container` | `POST /{entityName}/{entityUrn:urn:li:.+}/{aspectName}` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:1031` | Dremio SQL or job API on the Dremio host. The unprefixed DataHub template accepts those otherwise unrelated path segments. |
| 16 | `ingestion/datahub/ingestion/source/informatica/client.py:InformaticaClient.list_mappings` | `GET /{entityName}/{entityUrn:urn:li:.+}/{aspectName}` | `ingestion/datahub/ingestion/source/informatica/client.py:420` | Informatica v2 mapping endpoint on the configured Informatica host. The unprefixed DataHub template accepts those otherwise unrelated path segments. |
| 17 | `ingestion/datahub/ingestion/source/aws/aws_common.py:AwsConnectionConfig.get_session` | `GET /{entityName}/{entityUrn:urn:li:.+}/{aspectName}` | `ingestion/datahub/ingestion/source/aws/aws_common.py:432` | AWS SDK/control-plane session and credentials, with no DataHub resource dispatch. The unprefixed DataHub template accepts those otherwise unrelated path segments. |
| 18 | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations.extract_all_queries` | `POST /{entityName}` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:1294` | Dremio SQL or job API on the Dremio host. The unprefixed DataHub template accepts those otherwise unrelated path segments. |
| 20 | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations._fetch_all_results` | `GET /{entityName}/{entityUrn:urn:li:.+}/{aspectName}` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:587` | Dremio SQL or job API on the Dremio host. The unprefixed DataHub template accepts those otherwise unrelated path segments. |
| 22 | `ingestion/datahub/ingestion/source/sigma/sigma_api.py:SigmaAPI.get_workbook_schema` | `GET /{entityName}/{entityUrn:urn:li:.+}/{aspectName}` | `ingestion/datahub/ingestion/source/sigma/sigma_api.py:1401` | Sigma workbook or dataset API on the configured Sigma host. The unprefixed DataHub template accepts those otherwise unrelated path segments. |
| 24 | `ingestion/datahub/ingestion/source/qlik_sense/qlik_onprem_api.py:QlikOnPremAPI._read_or_skip_app` | `GET /{entityName}/{entityUrn:urn:li:.+}/{aspectName}` | `ingestion/datahub/ingestion/source/qlik_sense/qlik_onprem_api.py:419` | Qlik app/object API on the configured Qlik host. The unprefixed DataHub template accepts those otherwise unrelated path segments. |
| 25 | `ingestion/datahub/ingestion/source/aws/glue.py:GlueSourceConfig.glue_client` | `GET /{entityName}/{entityUrn:urn:li:.+}/{aspectName}` | `ingestion/datahub/ingestion/source/aws/glue.py:642` | AWS SDK/control-plane session and credentials, with no DataHub resource dispatch. The unprefixed DataHub template accepts those otherwise unrelated path segments. |
| 26 | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations.get_all_tables_and_columns` | `POST /{entityName}/{entityUrn:urn:li:.+}/{aspectName}` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:931` | Dremio SQL or job API on the Dremio host. The unprefixed DataHub template accepts those otherwise unrelated path segments. |
| 27 | `ingestion/datahub/ingestion/source/sigma/sigma_api.py:SigmaAPI.get_dataset_sources` | `GET /{entityName}/{entityUrn:urn:li:.+}/{aspectName}` | `ingestion/datahub/ingestion/source/sigma/sigma_api.py:2224` | Sigma workbook or dataset API on the configured Sigma host. The unprefixed DataHub template accepts those otherwise unrelated path segments. |
| 28 | `ingestion/datahub/ingestion/source/qlik_sense/qlik_onprem_api.py:QlikOnPremAPI._app_fingerprint` | `GET /{entityName}/{entityUrn:urn:li:.+}/{aspectName}` | `ingestion/datahub/ingestion/source/qlik_sense/qlik_onprem_api.py:436` | Qlik app/object API on the configured Qlik host. The unprefixed DataHub template accepts those otherwise unrelated path segments. |
| 30 | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations._fetch_results_iter` | `POST /{entityName}/{entityUrn:urn:li:.+}/{aspectName}` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:600` | Dremio SQL or job API on the Dremio host. The unprefixed DataHub template accepts those otherwise unrelated path segments. |

## All 100 OpenAPI suffix `CONSUMES` edges

A shared suffix here is any nonempty common terminal path segment sequence containing a literal segment, after normalizing parameter names and comparing equal verbs. The table distinguishes shared terminal segments from identical complete paths. The compatible-template flags additionally compare the entire path using the builder’s permissive parameter rule. They identify possible overlaps, including all-template routes. These flags give no precision verdict for unsampled edges.

The false edges arise because URL extraction sets aside the host and the matcher accepts any nonempty segment for a brace-delimited parameter, including parameters with Spring regex constraints. See `python_contract_requests.py:_route`, `restli_bindings.py:route_matches`, and `openapi_client_bindings.py:bind_openapi_clients`. The audit found 88 edges targeting the three unprefixed all-template routes.

### `GET /openapi/v1/registry/models/entity/specifications` (1 edges)

Contract ID `http::openapi/GET:/openapi/v1/registry/models/entity/specifications`.

| Common terminal suffix | Other routes with the same verb |
| --- | --- |
| `/specifications` | `GET /openapi/v1/registry/lineage/specifications`, `GET /openapi/v1/registry/models/aspect/specifications`, `GET /openapi/v1/registry/models/event/specifications` |

| Caller | Source citation |
| --- | --- |
| `ingestion/datahub/ingestion/graph/client.py:DataHubGraph.get_entity_aspect_specs` | `ingestion/datahub/ingestion/graph/client.py:588` |

### `GET /{entityName}/{entityUrn:urn:li:.+}/{aspectName}` (59 edges)

Contract ID `http::openapi/GET:/{entityName}/{entityUrn:urn:li:.+}/{aspectName}`.

Other signatures with compatible complete templates

`GET /openapi/v1/system-info`

| Caller | Source citation |
| --- | --- |
| `ingestion/datahub/ingestion/graph/openapi.py:OpenApiAPI.get_related_entities` | `ingestion/datahub/ingestion/graph/openapi.py:210` |
| `ingestion/datahub/ingestion/source/aws/aws_common.py:AwsConnectionConfig.get_credentials` | `ingestion/datahub/ingestion/source/aws/aws_common.py:489` |
| `ingestion/datahub/ingestion/source/aws/aws_common.py:AwsConnectionConfig.get_dynamodb_client` | `ingestion/datahub/ingestion/source/aws/aws_common.py:596` |
| `ingestion/datahub/ingestion/source/aws/aws_common.py:AwsConnectionConfig.get_glue_client` | `ingestion/datahub/ingestion/source/aws/aws_common.py:592` |
| `ingestion/datahub/ingestion/source/aws/aws_common.py:AwsConnectionConfig.get_lakeformation_client` | `ingestion/datahub/ingestion/source/aws/aws_common.py:604` |
| `ingestion/datahub/ingestion/source/aws/aws_common.py:AwsConnectionConfig.get_rds_client` | `ingestion/datahub/ingestion/source/aws/aws_common.py:608` |
| `ingestion/datahub/ingestion/source/aws/aws_common.py:AwsConnectionConfig.get_s3_client` | `ingestion/datahub/ingestion/source/aws/aws_common.py:541` |
| `ingestion/datahub/ingestion/source/aws/aws_common.py:AwsConnectionConfig.get_s3_resource` | `ingestion/datahub/ingestion/source/aws/aws_common.py:574` |
| `ingestion/datahub/ingestion/source/aws/aws_common.py:AwsConnectionConfig.get_sagemaker_client` | `ingestion/datahub/ingestion/source/aws/aws_common.py:601` |
| `ingestion/datahub/ingestion/source/aws/aws_common.py:AwsConnectionConfig.get_session` | `ingestion/datahub/ingestion/source/aws/aws_common.py:432` |
| `ingestion/datahub/ingestion/source/aws/aws_common.py:AwsConnectionConfig.get_sts_client` | `ingestion/datahub/ingestion/source/aws/aws_common.py:612` |
| `ingestion/datahub/ingestion/source/aws/aws_common.py:detect_aws_environment` | `ingestion/datahub/ingestion/source/aws/aws_common.py:164` |
| `ingestion/datahub/ingestion/source/aws/aws_common.py:get_current_identity` | `ingestion/datahub/ingestion/source/aws/aws_common.py:215` |
| `ingestion/datahub/ingestion/source/aws/aws_common.py:is_running_on_ec2` | `ingestion/datahub/ingestion/source/aws/aws_common.py:127` |
| `ingestion/datahub/ingestion/source/aws/glue.py:GlueSourceConfig.glue_client` | `ingestion/datahub/ingestion/source/aws/glue.py:642` |
| `ingestion/datahub/ingestion/source/aws/glue.py:GlueSourceConfig.lakeformation_client` | `ingestion/datahub/ingestion/source/aws/glue.py:650` |
| `ingestion/datahub/ingestion/source/aws/glue.py:GlueSourceConfig.s3_client` | `ingestion/datahub/ingestion/source/aws/glue.py:646` |
| `ingestion/datahub/ingestion/source/aws/sagemaker_processors/common.py:SagemakerSourceConfig.sagemaker_client` | `ingestion/datahub/ingestion/source/aws/sagemaker_processors/common.py:33` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations._fetch_all_results` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:587` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations._fetch_results_iter` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:605` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations._get_all_tables_global_chunked` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:1102` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations._get_all_tables_partitioned_by_container` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:1031` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations._get_queries_chunked` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:1321` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations._get_view_definitions` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:875` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations._supports_array_queried_datasets` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:1245` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations.execute_query` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:573` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations.execute_query_iter` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:656` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations.extract_all_queries` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:1294` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations.get_all_tables_and_columns` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:931` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations.get_job_result` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:678` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations.get_view_parents` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:1217` |
| `ingestion/datahub/ingestion/source/dynamodb/dynamodb.py:DynamoDBConfig.dynamodb_client` | `ingestion/datahub/ingestion/source/dynamodb/dynamodb.py:195` |
| `ingestion/datahub/ingestion/source/hightouch/hightouch_api.py:HightouchAPIClient.get_sync_runs` | `ingestion/datahub/ingestion/source/hightouch/hightouch_api.py:135` |
| `ingestion/datahub/ingestion/source/informatica/client.py:InformaticaClient.list_connections` | `ingestion/datahub/ingestion/source/informatica/client.py:435` |
| `ingestion/datahub/ingestion/source/informatica/client.py:InformaticaClient.list_mappings` | `ingestion/datahub/ingestion/source/informatica/client.py:420` |
| `ingestion/datahub/ingestion/source/microstrategy/client.py:MicroStrategyClient.list_model_tables` | `ingestion/datahub/ingestion/source/microstrategy/client.py:455` |
| `ingestion/datahub/ingestion/source/omni/omni_api.py:OmniClient.get_dashboard_document` | `ingestion/datahub/ingestion/source/omni/omni_api.py:183` |
| `ingestion/datahub/ingestion/source/qlik_sense/qlik_onprem_api.py:QlikOnPremAPI._app_fingerprint` | `ingestion/datahub/ingestion/source/qlik_sense/qlik_onprem_api.py:436` |
| `ingestion/datahub/ingestion/source/qlik_sense/qlik_onprem_api.py:QlikOnPremAPI._load_item` | `ingestion/datahub/ingestion/source/qlik_sense/qlik_onprem_api.py:314` |
| `ingestion/datahub/ingestion/source/qlik_sense/qlik_onprem_api.py:QlikOnPremAPI._read_or_skip_app` | `ingestion/datahub/ingestion/source/qlik_sense/qlik_onprem_api.py:419` |
| `ingestion/datahub/ingestion/source/quicksight/quicksight_config.py:QuickSightSourceConfig.get_quicksight_client` | `ingestion/datahub/ingestion/source/quicksight/quicksight_config.py:217` |
| `ingestion/datahub/ingestion/source/sigma/sigma_api.py:SigmaAPI._assemble_data_model` | `ingestion/datahub/ingestion/source/sigma/sigma_api.py:1992` |
| `ingestion/datahub/ingestion/source/sigma/sigma_api.py:SigmaAPI._dataset_sources_gone_for` | `ingestion/datahub/ingestion/source/sigma/sigma_api.py:2120` |
| `ingestion/datahub/ingestion/source/sigma/sigma_api.py:SigmaAPI._get_data_model_columns` | `ingestion/datahub/ingestion/source/sigma/sigma_api.py:1823` |
| `ingestion/datahub/ingestion/source/sigma/sigma_api.py:SigmaAPI._get_data_model_elements` | `ingestion/datahub/ingestion/source/sigma/sigma_api.py:1813` |
| `ingestion/datahub/ingestion/source/sigma/sigma_api.py:SigmaAPI._get_data_model_lineage_entries` | `ingestion/datahub/ingestion/source/sigma/sigma_api.py:1863` |
| `ingestion/datahub/ingestion/source/sigma/sigma_api.py:SigmaAPI.get_connection_path` | `ingestion/datahub/ingestion/source/sigma/sigma_api.py:2381` |
| `ingestion/datahub/ingestion/source/sigma/sigma_api.py:SigmaAPI.get_data_model_by_url_id` | `ingestion/datahub/ingestion/source/sigma/sigma_api.py:2745` |
| `ingestion/datahub/ingestion/source/sigma/sigma_api.py:SigmaAPI.get_data_model_spec` | `ingestion/datahub/ingestion/source/sigma/sigma_api.py:2649` |
| `ingestion/datahub/ingestion/source/sigma/sigma_api.py:SigmaAPI.get_data_models` | `ingestion/datahub/ingestion/source/sigma/sigma_api.py:2815` |
| `ingestion/datahub/ingestion/source/sigma/sigma_api.py:SigmaAPI.get_dataset_sources` | `ingestion/datahub/ingestion/source/sigma/sigma_api.py:2224` |
| `ingestion/datahub/ingestion/source/sigma/sigma_api.py:SigmaAPI.get_sigma_workbooks` | `ingestion/datahub/ingestion/source/sigma/sigma_api.py:2916` |
| `ingestion/datahub/ingestion/source/sigma/sigma_api.py:SigmaAPI.get_workbook_column_formulas` | `ingestion/datahub/ingestion/source/sigma/sigma_api.py:1371` |
| `ingestion/datahub/ingestion/source/sigma/sigma_api.py:SigmaAPI.get_workbook_lineage` | `ingestion/datahub/ingestion/source/sigma/sigma_api.py:2569` |
| `ingestion/datahub/ingestion/source/sigma/sigma_api.py:SigmaAPI.get_workbook_lineage_entries` | `ingestion/datahub/ingestion/source/sigma/sigma_api.py:1947` |
| `ingestion/datahub/ingestion/source/sigma/sigma_api.py:SigmaAPI.get_workbook_pages` | `ingestion/datahub/ingestion/source/sigma/sigma_api.py:1509` |
| `ingestion/datahub/ingestion/source/sigma/sigma_api.py:SigmaAPI.get_workbook_schema` | `ingestion/datahub/ingestion/source/sigma/sigma_api.py:1401` |
| `ingestion/datahub/ingestion/source/superset.py:SupersetSource.__init__` | `ingestion/datahub/ingestion/source/superset.py:443` |
| `ingestion/datahub/ingestion/source/superset.py:SupersetSource.login` | `ingestion/datahub/ingestion/source/superset.py:497` |

### `POST /openapi/v1/trace/write/{traceId}` (6 edges)

Contract ID `http::openapi/POST:/openapi/v1/trace/write/{traceId}`.

| Caller | Source citation |
| --- | --- |
| `ingestion/datahub/emitter/rest_emitter.py:DataHubRestEmitter._await_status` | `ingestion/datahub/emitter/rest_emitter.py:1322` |
| `ingestion/datahub/emitter/rest_emitter.py:DataHubRestEmitter._emit_openapi_mcps` | `ingestion/datahub/emitter/rest_emitter.py:1102` |
| `ingestion/datahub/emitter/rest_emitter.py:DataHubRestEmitter.emit` | `ingestion/datahub/emitter/rest_emitter.py:834` |
| `ingestion/datahub/emitter/rest_emitter.py:DataHubRestEmitter.emit_mcp` | `ingestion/datahub/emitter/rest_emitter.py:982` |
| `ingestion/datahub/emitter/rest_emitter.py:DataHubRestEmitter.emit_mcps` | `ingestion/datahub/emitter/rest_emitter.py:1004` |
| `ingestion/datahub/emitter/rest_emitter.py:DataHubRestEmitter.get_trace_status` | `ingestion/datahub/emitter/rest_emitter.py:1400` |

### `POST /openapi/v2/entity/batch/{entityName}` (1 edges)

Contract ID `http::openapi/POST:/openapi/v2/entity/batch/{entityName}`.

| Caller | Source citation |
| --- | --- |
| `ingestion/datahub/ingestion/graph/openapi.py:OpenApiAPI.get_entities_v2` | `ingestion/datahub/ingestion/graph/openapi.py:628` |

### `POST /openapi/v3/entity/scroll` (1 edges)

Contract ID `http::openapi/POST:/openapi/v3/entity/scroll`.

| Common terminal suffix | Other routes with the same verb |
| --- | --- |
| `/scroll` | `POST /openapi/v2/relationship/scroll`, `POST /openapi/v3/lineage/scroll`, `POST /openapi/v3/relationship/scroll`, `POST /scroll` |

Other signatures with compatible complete templates

`POST /openapi/v3/entity/{entityName}`

| Caller | Source citation |
| --- | --- |
| `ingestion/datahub/ingestion/graph/openapi.py:OpenApiAPI.scroll_entities` | `ingestion/datahub/ingestion/graph/openapi.py:321` |

### `POST /openapi/v3/entity/{entityName}/batchGet` (1 edges)

Contract ID `http::openapi/POST:/openapi/v3/entity/{entityName}/batchGet`.

| Common terminal suffix | Other routes with the same verb |
| --- | --- |
| `/batchGet` | `POST /openapi/v3/entity/generic/batchGet` |

Other signatures with compatible complete templates

`POST /openapi/v3/entity/generic/batchGet`

| Caller | Source citation |
| --- | --- |
| `ingestion/datahub/ingestion/graph/openapi.py:OpenApiAPI.get_entities` | `ingestion/datahub/ingestion/graph/openapi.py:685` |

### `POST /openapi/v3/lineage/scroll` (1 edges)

Contract ID `http::openapi/POST:/openapi/v3/lineage/scroll`.

| Common terminal suffix | Other routes with the same verb |
| --- | --- |
| `/scroll` | `POST /openapi/v2/relationship/scroll`, `POST /openapi/v3/entity/scroll`, `POST /openapi/v3/relationship/scroll`, `POST /scroll` |

| Caller | Source citation |
| --- | --- |
| `ingestion/datahub/ingestion/graph/openapi.py:OpenApiAPI.scroll_lineage` | `ingestion/datahub/ingestion/graph/openapi.py:485` |

### `POST /openapi/v3/relationship/scroll` (1 edges)

Contract ID `http::openapi/POST:/openapi/v3/relationship/scroll`.

| Common terminal suffix | Other routes with the same verb |
| --- | --- |
| `/relationship/scroll` | `POST /openapi/v2/relationship/scroll` |
| `/scroll` | `POST /openapi/v3/entity/scroll`, `POST /openapi/v3/lineage/scroll`, `POST /scroll` |

| Caller | Source citation |
| --- | --- |
| `ingestion/datahub/ingestion/graph/openapi.py:OpenApiAPI.scroll_relationships` | `ingestion/datahub/ingestion/graph/openapi.py:395` |

### `POST /{entityName}` (13 edges)

Contract ID `http::openapi/POST:/{entityName}`.

Other signatures with compatible complete templates

`POST /scroll`

| Caller | Source citation |
| --- | --- |
| `ingestion/datahub/cli/cli_utils.py:generate_access_token` | `ingestion/datahub/cli/cli_utils.py:412` |
| `ingestion/datahub/cli/cli_utils.py:get_frontend_session_login_as` | `ingestion/datahub/cli/cli_utils.py:374` |
| `ingestion/datahub/ingestion/graph/client.py:DataHubGraph._create_user_with_token` | `ingestion/datahub/ingestion/graph/client.py:2607` |
| `ingestion/datahub/ingestion/graph/client.py:DataHubGraph.create_native_user` | `ingestion/datahub/ingestion/graph/client.py:2712` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations._get_all_tables_global_chunked` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:1102` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations._get_all_tables_partitioned_by_container` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:1031` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations._get_queries_chunked` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:1321` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations._get_view_definitions` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:875` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations._supports_array_queried_datasets` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:1245` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations.execute_query` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:559` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations.execute_query_iter` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:639` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations.extract_all_queries` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:1294` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations.get_all_tables_and_columns` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:931` |

### `POST /{entityName}/{entityUrn:urn:li:.+}/{aspectName}` (16 edges)

Contract ID `http::openapi/POST:/{entityName}/{entityUrn:urn:li:.+}/{aspectName}`.

Other signatures with compatible complete templates

`POST /openapi/entities/v1/`

| Caller | Source citation |
| --- | --- |
| `ingestion/datahub/cli/sso_cli.py:_warn_about_existing_cli_tokens` | `ingestion/datahub/cli/sso_cli.py:48` |
| `ingestion/datahub/cli/sso_cli.py:browser_sso_login` | `ingestion/datahub/cli/sso_cli.py:172` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations._fetch_all_results` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:587` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations._fetch_results_iter` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:600` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations._get_all_tables_global_chunked` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:1102` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations._get_all_tables_partitioned_by_container` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:1031` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations._get_queries_chunked` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:1321` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations._get_view_definitions` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:875` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations._supports_array_queried_datasets` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:1245` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations._wait_for_job` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:546` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations.cancel_query` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:664` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations.execute_query` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:570` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations.execute_query_iter` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:650` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations.extract_all_queries` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:1294` |
| `ingestion/datahub/ingestion/source/dremio/dremio_api.py:DremioAPIOperations.get_all_tables_and_columns` | `ingestion/datahub/ingestion/source/dremio/dremio_api.py:931` |
| `ingestion/datahub/ingestion/source/snowplow/services/iglu_client.py:IgluClient.validate_schema` | `ingestion/datahub/ingestion/source/snowplow/services/iglu_client.py:355` |

## Required edges and graph distances

All 52 required edges were verified after independent ID mapping from the pinned source path, line and declaration name. Query labels contain source-declared path order and no graph edge fields.

A budget of 40 covers 0.01273% of the v2 graph. Hops use the raw undirected graph, degree counts incoming and outgoing parallel edges, and two-hop counts include the start.

### Python → OpenAPI

| Link | Contract hops | Handler hops | Gold depth | Start degree | Contract degree | Within two hops |
| --- | --- | --- | --- | --- | --- | --- |
| DH15 | 1 | 2 | 2 | 42 | 3 | 441 |
| DH16 | 1 | 2 | 2 | 75 | 3 | 709 |
| DH17 | 1 | 2 | 2 | 38 | 3 | 74 |
| DH18 | 1 | 1 | 1 | 59 | 3 | 1873 |
| DH19 | 1 | 2 | 2 | 54 | 3 | 2550 |

### Python → Rest.li

| Link | Contract hops | Handler hops | Gold depth | Start degree | Contract degree | Within two hops |
| --- | --- | --- | --- | --- | --- | --- |
| DH20 | 1 | 2 | 2 | 92 | 21 | 1297 |
| DH21 | 1 | 2 | 2 | 46 | 8 | 2219 |
| DH22 | 1 | 2 | 2 | 33 | 4 | 2122 |
| DH23 | 1 | 2 | 2 | 30 | 11 | 912 |
| DH24 | 1 | 1 | 1 | 29 | 4 | 694 |
| DH25 | 1 | 2 | 2 | 15 | 5 | 1458 |
| DH26 | 1 | 2 | 2 | 97 | 5 | 3544 |

### React → GraphQL

| Link | Contract hops | Handler hops | Gold depth | Start degree | Contract degree | Within two hops |
| --- | --- | --- | --- | --- | --- | --- |
| DH01 | 1 | 2 | 2 | 62 | 6 | 1694 |
| DH02 | 1 | 2 | 2 | 25 | 6 | 1488 |
| DH03 | 1 | 2 | 2 | 83 | 6 | 2555 |
| DH04 | 1 | 2 | 2 | 51 | 6 | 1438 |
| DH05 | 1 | 2 | 2 | 31 | 6 | 1663 |
| DH06 | 1 | 2 | 2 | 93 | 8 | 2501 |
| DH07 | 1 | 2 | 2 | 27 | 6 | 1544 |
| DH08 | 1 | 2 | 2 | 19 | 5 | 56 |
| DH09 | 1 | 2 | 2 | 210 | 11 | 3157 |
| DH10 | 1 | 2 | 2 | 36 | 6 | 1697 |
| DH11 | 1 | 2 | 2 | 42 | 8 | 1326 |
| DH12 | 1 | 2 | 2 | 33 | 8 | 1463 |
| DH13 | 1 | 2 | 2 | 22 | 6 | 623 |
| DH14 | 1 | 2 | 2 | 20 | 6 | 1519 |
