"""Exhaustive *automatic* protocol-declaration censuses on pinned source files.

This is an independent, deliberately narrow lexical source oracle, NOT blinded
human adjudication, implementation coverage, or runtime producer/consumer proof.
Count all declarations in one complete file rather than selecting successes.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from graft_ckg import CKGBuilder

THRIFT_REV = "6ecb09706140f8730b5385c08f1386c654c3c526"
THRIFT_FILE = "socialNetwork/social_network.thrift"
TRAIN_REV = "313886e99befb94be6cd45f085c98e0019f59829"
TRAIN_FILE = "ts-order-service/src/main/java/order/controller/OrderController.java"
TRAIN_PREFIX = "/api/v1/orderservice"

def check_revision(repo: Path, expected: str) -> None:
    revision = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != expected:
        raise ValueError(f"Expected source {expected}, got {revision}")

def score(expected: set, actual: set) -> dict:
    tp, fp, fn = expected & actual, actual - expected, expected - actual
    p = len(tp) / len(actual) if actual else None
    r = len(tp) / len(expected) if expected else None
    f = 2*p*r/(p+r) if p is not None and r is not None and p+r else (
        0.0 if p is not None and r is not None else None)
    return {
        "tp": len(tp), "fp": len(fp), "fn": len(fn),
        "precision": p, "recall": r, "f1": f,
        "missing": sorted(map(list, fn)), "unexpected": sorted(map(list, fp))
    }

def thrift_oracle(source: str) -> set[tuple[str,str,str]]:
    """Exhaustive method declaration lines in a single service-based IDL file.

    Refuse unsupported block structure instead of silently treating a partial
    parse as a complete oracle.
    """
    expected = set()
    service = None
    opened = 0
    for raw in source.splitlines():
        line = raw.split("//", 1)[0].strip()
        if service is None:
            m = re.fullmatch(r"service\s+(\w+)\s*(?:extends\s+[\w.]+\s*)?\{\s*", line)
            if m:
                service, opened = m.group(1), 1
            continue
        if line == "}":
            opened -= 1
            if opened == 0:
                service = None
            continue
        if "{" in line or "}" in line:
            raise ValueError("Nested service declaration unsupported: " + line)
        if not line or line.startswith(("throws ", "#")):
            continue
        m = re.match(r"^(?:oneway\s+)?[\w.<>, ]+?\s+(\w+)\s*\(", line)
        if m:
            name = m.group(1)
            u = f"contract::thrift::social_network.{service}"
            expected.add((u, "DEFINES_RPC", f"{u}.{name}"))
        elif "(" in line and not (re.match(r"^\d+\s*:", line) or line.startswith((")", "throws "))):
            raise ValueError("Unrecognized IDL method line: " + line)
    if service is not None:
        raise ValueError("Unclosed service block")
    if not expected:
        raise ValueError("No IDL method declarations identified")
    return expected

def proto_oracle(source: str) -> set[tuple[str,str,str]]:
    """Entire source Protobuf service->RPC declaration set, not runtime bindings."""
    result=set()
    service=None
    for line_no,raw in enumerate(source.splitlines(),1):
        line=raw.split("//",1)[0].strip()
        if service is None:
            match=re.fullmatch(r"service\\s+(\\w+)\\s*\\{\\s*",line)
            if match:
                service=match.group(1)
            continue
        if line=="}":
            service=None
            continue
        rpc=re.match(r"^rpc\\s+(\\w+)\\s*\\(",line)
        if rpc:
            parent="contract::"+service
            result.add((parent,"DEFINES_RPC",parent+"."+rpc.group(1)))
        elif line.startswith("rpc"):
            raise ValueError(f"Unsupported rpc declaration at line {line_no}")
    if service is not None or not result:
        raise ValueError("Unclosed/empty proto scope")
    return result


def inspect_proto(repo: Path) -> dict:
    revision="38e7348eb289eb5b87c0c6e8cb19ced0449dc389"
    relative="protos/demo.proto"
    check_revision(repo,revision)
    expected=proto_oracle((repo/relative).read_text(encoding="utf-8"))
    sources={x[0] for x in expected}
    with contextlib.redirect_stdout(io.StringIO()):
        builder=CKGBuilder(str(repo))
        builder.build()
    actual={(str(u),"DEFINES_RPC",str(v)) for u,v,d in builder.graph.edges(data=True)
            if d.get("relation")=="DEFINES_RPC" and str(u) in sources}
    return {
        "system":"Online Boutique","protocol":"Protobuf",
        "revision":revision,"complete_source_file":relative,
        "measured_relation":"service -> RPC declarations ONLY",
        "expected_count":len(expected),"predicted_count":len(actual),
        "score":score(expected,actual),
        "evidence_status":"automatic_lexical_source_census_not_human_adjudicated",
        "caveats":["Graph service names follow the repo's unqualified canonical RPC convention",
                   "Not all consumer/producer bindings are measured"]
    }

def spring_oracle(source: str) -> set[tuple[str,str,str]]:
    """Entire Spring controller's literal route annotations and Java handlers."""
    route = re.compile(r'@(Get|Post|Put|Delete|Patch)Mapping\s*\(\s*(?:path|value)\s*=\s*"([^"]+)"\s*\)')
    method = re.compile(r"\bpublic\s+(?:[\w<>?,]+\s+)+?(\w+)\s*\(")
    lines = source.splitlines()
    records = set()
    for i, line in enumerate(lines):
        m = route.search(line)
        if not m:
            continue
        name = None
        for candidate in lines[i+1:i+9]:
            v = method.search(candidate)
            if v:
                name = v.group(1)
                break
        if not name:
            raise ValueError(f"Cannot independently identify handler after line {i+1}")
        route_path = TRAIN_PREFIX + m.group(2)
        item = (m.group(1).upper(), route_path, name)
        if item in records:
            raise ValueError("Duplicate declared mapping " + repr(item))
        records.add(item)
    if not records:
        raise ValueError("No Spring routes found")
    return records

def inspect_thrift(repo: Path) -> dict:
    check_revision(repo, THRIFT_REV)
    source = (repo / THRIFT_FILE).read_text(encoding="utf-8")
    expected = thrift_oracle(source)
    with contextlib.redirect_stdout(io.StringIO()):
        builder = CKGBuilder(str(repo))
        builder.build()
    actual = {
        (str(u), "DEFINES_RPC", str(v))
        for u,v,data in builder.graph.edges(data=True)
        if data.get("relation") == "DEFINES_RPC"
        and str(u).startswith("contract::thrift::social_network.")
    }
    return {
        "system": "DeathStarBench", "protocol": "Thrift", "revision": THRIFT_REV,
        "complete_source_file": THRIFT_FILE,
        "measured_relation": "service -> RPC declaration ONLY",
        "expected_count": len(expected), "predicted_count": len(actual),
        "score": score(expected,actual),
        "evidence_status": "automatic_lexical_source_census_not_human_adjudicated",
        "caveats": ["The source oracle is independent code, not a human reviewer",
                    "Does not measure C++ client stub binding or runtime implementation"]
    }

def inspect_train(repo: Path) -> dict:
    check_revision(repo, TRAIN_REV)
    source = (repo / TRAIN_FILE).read_text(encoding="utf-8")
    if not re.search(r'@RequestMapping\s*\(\s*"/api/v1/orderservice"\s*\)', source):
        raise ValueError("Missing independently inspected class route prefix")
    expected = spring_oracle(source)
    with contextlib.redirect_stdout(io.StringIO()):
        builder = CKGBuilder(str(repo))
        builder.build()
    actual = set()
    for (method,path), handlers in builder.http_endpoints.items():
        if not path.startswith(TRAIN_PREFIX):
            continue
        for node in handlers:
            if TRAIN_FILE in str(node):
                # Exact source handler identity rather than path coincidence
                name = str(builder.graph.nodes[node].get("name","")) if node in builder.graph else ""
                actual.add((method, path, name))
    return {
        "system": "Train-Ticket", "protocol": "HTTP Spring annotations",
        "revision": TRAIN_REV, "complete_source_file": TRAIN_FILE,
        "measured_relation": "route registration ONLY, not client-to-route matching",
        "expected_count": len(expected), "predicted_count": len(actual),
        "score": score(expected, actual),
        "evidence_status": "automatic_lexical_source_census_not_human_adjudicated",
        "caveats": ["Does not establish a real HTTP caller or the destination host",
                    "One controller, not the entire Train-Ticket system"]
    }

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol", choices=["thrift","spring","proto"], required=True)
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    report = {"thrift":inspect_thrift,"spring":inspect_train,"proto":inspect_proto}[args.protocol](args.repo)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("COMPLETE_FILE_DECLARATION_CENSUS", json.dumps(report,sort_keys=True))
    return 0 if report["score"]["fp"]==0 and report["score"]["fn"]==0 else 2

if __name__ == "__main__":
    raise SystemExit(main())
