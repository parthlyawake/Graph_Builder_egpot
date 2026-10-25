"""Build one repository and save graph evidence for a source-to-graph audit.

This deliberately does not call any retrieval or ranking method.
"""

import argparse
from collections import Counter
from contextlib import redirect_stdout
import json
from pathlib import Path
import pickle
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from graft_ckg import CKGBuilder  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    with (output / "build.log").open("w", encoding="utf-8") as log, redirect_stdout(log):
        try:
            builder = CKGBuilder(str(repo))
            graph = builder.build()
        except Exception:
            traceback.print_exc(file=log)
            raise

    with (output / "graph.pkl").open("wb") as stream:
        pickle.dump(graph, stream, protocol=pickle.HIGHEST_PROTOCOL)

    relation_counts = Counter(data.get("relation", "") for _, _, data in graph.edges(data=True))
    type_counts = Counter(data.get("type", "") for _, data in graph.nodes(data=True))
    parsed_files = sorted(builder.raw_file_lines)
    summary = {
        "repository": repo.name,
        "seconds": round(time.perf_counter() - started, 3),
        "total_loc": builder.total_loc,
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "parsed_files": len(parsed_files),
        "node_types": dict(sorted(type_counts.items())),
        "relations": dict(sorted(relation_counts.items())),
        "log_warnings": [line for line in (output / "build.log").read_text(encoding="utf-8").splitlines()
                         if "[!]" in line],
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("repository", "seconds", "nodes", "edges", "parsed_files", "log_warnings")}, indent=2))


if __name__ == "__main__":
    main()
