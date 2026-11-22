# Slim EG-POT integration

This branch omits three DataHub GraphML snapshots, each about 840 MB. The SHA-256 values below identify the original files.

| Omitted file | Original bytes | SHA-256 |
| --- | ---: | --- |
| `bench/results/datahub_graph.graphml` | 839,568,948 | `6332b2c84b5083067d2a72eac3a0f41459f771b791319a5cc7d98baa7f124ef2` |
| `bench/results/datahub_graph_v2.graphml` | 848,540,156 | `71067cb3598e40b2be00c3a4f8b3f3557f03172a3dcd9b9a462cba59894dd162` |
| `bench/results/datahub_graph_v3.graphml` | 848,501,191 | `041015fba8ab3baa7cc883955fcc700e344839b50d72359e072b2bcf43ebfeb0` |

Rebuild recipes and builder pins are recorded in [the v1 coverage mapper](../map_datahub_coverage.py), [the v1 coverage report](datahub_coverage_report.json), [the v2 build script](../build_datahub_v2.py), [the v2 coverage report](datahub_coverage_v2.json), [the v3 build script](../build_datahub_v3.py), and [the v3 coverage report](datahub_coverage_v3.json).

History was rewritten for this copy. [The commit map](slim_commit_map.txt) gives the original → slim mapping. Tags use the `slim-` prefix.
