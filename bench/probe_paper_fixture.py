"""Diagnostic only: report graph relations for source-audited fixture.

Never treat generated edges as ground truth. Independent annotators must inspect
source files and enumerate all expected/forbidden edges before closing scopes.
"""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from graft_ckg import CKGBuilder

base=ROOT/"benchmarks"/"paper_relations"
b=CKGBuilder(str(base));b.build()
interesting=("CALLS","POLYMORPHIC_CALL","PASSES_ARG","FLOWS_TO",
             "CONSUMES","IMPLEMENTS","HTTP_CALLS")
edges=[]
for u,v,d in b.graph.edges(data=True):
    if d.get("relation") in interesting:
        edges.append({"u":str(u),"r":d.get("relation"),"v":str(v),
                      "layer":d.get("layer"),
                      "flow_kind":d.get("flow_kind"),
                      "c_type":d.get("c_type")})
edges.sort(key=lambda x:(x["r"],x["u"],x["v"]))
report={"nodes":len(b.graph),"edges":b.graph.number_of_edges(),
        "interesting":edges,
        "functions":[{"id":str(n),"name":d.get("name"),
                     "type":d.get("type"),"file":d.get("file"),
                     "param_types":d.get("param_types")}
                     for n,d in b.graph.nodes(data=True)
                     if d.get("type")=="function"]}
out=ROOT/"bench"/"results"/"paper_fixture_probe_ci.json"
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(report,indent=2,default=str)+"\n",encoding="utf-8")
print("Fixture graph nodes",report["nodes"],"edges",report["edges"],
      "relevant edges",len(edges),"output",out)
