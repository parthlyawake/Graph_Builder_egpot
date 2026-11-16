"""Blinded reviewer packets from complete *source declaration* scopes.

No graph predictions are consulted. Cartesian service x RPC targets includes
systematic cross-service negatives. Reviewers must inspect source separately;
packets alone are NOT human labels, recall, or publication certification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

THRIFT = ("6ecb09706140f8730b5385c08f1386c654c3c526",
          "socialNetwork/social_network.thrift")
PROTO = ("38e7348eb289eb5b87c0c6e8cb19ced0449dc389",
         "protos/demo.proto")

def read_revision(repo: Path, revision: str) -> None:
    got = subprocess.check_output(["git","-C",str(repo),"rev-parse","HEAD"],text=True).strip()
    if got != revision:
        raise ValueError("Pinned source mismatch: " + got)

def parse_contracts(text: str, protocol: str) -> dict[str,list[tuple[str,int]]]:
    services:dict[str,list[tuple[str,int]]] = {}
    current = None
    for n, raw in enumerate(text.splitlines(),1):
        line = raw.split("//",1)[0].strip()
        if not line:
            continue
        opening = re.fullmatch(r"service\s+(\w+)\s*(?:extends\s+[\w.]+\s*)?\{\s*",line)
        if opening:
            if current:
                raise ValueError("Nested service; cannot attest complete scope")
            current = opening.group(1)
            if current in services:
                raise ValueError("Duplicate service declaration")
            services[current] = []
            continue
        if current is None:
            continue
        if line=="}":
            current = None
            continue
        if protocol == "thrift":
            match=re.match(r"^(?:oneway\s+)?[\w.<>, ]+?\s+(\w+)\s*\(",line)
            if "(" in line and not (match or line.startswith((")", "throws ")) or re.match(r"^\d+\s*:",line)):
                raise ValueError(f"Unrecognized Thrift declaration at {n}: {line}")
        else:
            match=re.match(r"^rpc\s+(\w+)\s*\(",line)
            if "rpc" in line and not match:
                raise ValueError(f"Unrecognized Protobuf RPC at {n}")
        if match:
            services[current].append((match.group(1),n))
    if current:
        raise ValueError("Unclosed contract service")
    if not services or not all(services.values()):
        raise ValueError("Empty service / unsupported parser")
    return services

def generate(repo:Path, protocol:str, output:Path):
    revision, relative = THRIFT if protocol=="thrift" else PROTO
    read_revision(repo, revision)
    text=(repo/relative).read_text(encoding="utf-8")
    services=parse_contracts(text,protocol)
    service_ids = {
        s:("contract::thrift::social_network."+s if protocol=="thrift" else "contract::"+s)
        for s in services
    }
    targets = sorted({
        service_ids[s]+"."+method
        for s,methods in services.items()
        for method,_ in methods
    })
    # Full Cartesian candidate universe, not selected builder successes.
    pairs=[
        {"source":service_ids[s],"relation":"DEFINES_RPC","target":target}
        for s in sorted(services)
        for target in targets
    ]
    universe={
        "source_revision":revision,
        "complete_scopes_attested":"automatic_full_file_source_declaration_enumeration_ONLY",
        "candidate_edges":pairs,
    }
    from bench.annotation_review import review_universe_sha256
    digest=review_universe_sha256(universe)
    output.mkdir(parents=True,exist_ok=True)
    (output/"candidate_universe.json").write_text(
        json.dumps(universe,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    for name in ("A","B"):
        # These are BLANK templates; never forge votes or reviewer identities.
        template={
            "reviewer_id":"",
            "source_revision":revision,
            "candidate_universe_sha256":digest,
            "complete_scopes_reviewed":False,
            "votes":[{**row,"judgment":"UNREVIEWED"} for row in pairs],
        }
        (output/f"reviewer_{name}_BLANK.json").write_text(
            json.dumps(template,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    manifest={
        "revision":revision,"protocol":protocol,
        "source_file":relative,
        "source_sha256":hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "service_count":len(services),
        "declared_method_count":len(targets),
        "blinded_candidate_count":len(pairs),
        "universe_sha256":digest,
        "scope":"all service-to-declared-RPC candidate triples in one source file",
        "status":"AWAITING TWO ACTUAL HUMAN REVIEWERS; zero labels provided",
        "reviewer_instructions":[
            "Never inspect graph predictions or generated measured results while labeling.",
            "Inspect the pinned source file and judge every triple positive/negative/uncertain.",
            "Replace empty reviewer_id with a real distinct reviewer identifier; attest complete_scopes_reviewed only after exhaustive work.",
            "After two completed reviews, compare via bench/annotation_review.py and adjudicate all disputed/uncertain cases.",
            "This source-only candidate set does not establish complete Ldep/Lflow/HTTP/AMQP accuracy or external trust."
        ]
    }
    (output/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print("BLINDED_PACKET",json.dumps(manifest,sort_keys=True))

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--repo",required=True,type=Path)
    p.add_argument("--protocol",required=True,choices=["thrift","proto"])
    p.add_argument("--output-dir",required=True,type=Path)
    args=p.parse_args()
    generate(args.repo,args.protocol,args.output_dir)

if __name__=="__main__":
    main()
