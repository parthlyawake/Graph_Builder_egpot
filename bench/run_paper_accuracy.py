"""Publication-gated source/edge audit: exact triple matching and closed scopes."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import platform
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from graft_ckg import CKGBuilder
from bench.verify_graph_accuracy import evaluate


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--repo",required=True)
    p.add_argument("--labels",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    builder=CKGBuilder(args.repo)
    builder.build()
    labels=json.loads(Path(args.labels).read_text(encoding="utf-8"))
    result=evaluate(builder.graph,labels,source_root=args.repo)
    result["dataset"]=labels.get("dataset")
    result["source_revision"]=labels.get("source_revision")
    result["graph_nodes"]=builder.graph.number_of_nodes()
    result["graph_edges"]=builder.graph.number_of_edges()
    result["python"]=sys.version
    result["platform"]=platform.platform()
    result["interpretation"]="Precision/F1 valid ONLY for the explicitly closed scopes. The independent-review status is not established by a passing graph check."
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"passed":result["passed"],"publication_ready":result["publication_ready"],
                      "sampled_edges":result["sampled_edges"],
                      "closed_scopes":result["closed_scopes"]},indent=2))
    if not result["passed"]:
        raise SystemExit("Source-grounded closed-scope evaluation failed")


if __name__=="__main__":main()
