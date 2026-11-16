"""Independent annotator agreement for a pre-registered finite edge universe.

This tool DOES NOT authenticate humans or prove the candidate universe is
exhaustive. Never self-generate reviewer votes from graph predictions.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path


def _key(row):
    if not isinstance(row, dict) or any(not isinstance(row.get(k), str) or not row.get(k)
                                         for k in ("source", "relation", "target")):
        raise ValueError("each candidate/review vote needs exact source relation target strings")
    return (row["source"], row["relation"], row["target"])


def review_universe_sha256(universe):
    if not isinstance(universe, dict) or not isinstance(universe.get("source_revision"), str):
        raise ValueError("source_revision is required")
    if not universe.get("complete_scopes_attested"):
        raise ValueError("a documented complete-scope attestation is required")
    edges = universe.get("candidate_edges")
    if not isinstance(edges, list) or not edges:
        raise ValueError("candidate_edges cannot be empty")
    keys = [_key(row) for row in edges]
    if len(keys) != len(set(keys)):
        raise ValueError("candidate universe contains duplicate exact edges")
    return sha256(json.dumps({
        "source_revision": universe["source_revision"],
        "complete_scopes_attested": universe["complete_scopes_attested"],
        "candidate_edges": sorted(keys),
    },sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest()


def compare_two_reviews(universe, first, second):
    digest = review_universe_sha256(universe)
    target = {_key(row) for row in universe["candidate_edges"]}
    reviewers = (first, second)
    identities = [r.get("reviewer_id") if isinstance(r, dict) else None for r in reviewers]
    if not all(isinstance(x, str) and x.strip() for x in identities) or identities[0] == identities[1]:
        raise ValueError("two distinct explicit reviewer IDs are mandatory")
    matrices=[]
    for review in reviewers:
        if (review.get("candidate_universe_sha256") != digest or
                review.get("source_revision") != universe["source_revision"] or
                review.get("complete_scopes_reviewed") is not True):
            raise ValueError("review must match the exact pinned universe and attest full scope")
        votes=review.get("votes")
        if not isinstance(votes, list):
            raise ValueError("votes must be a list")
        matrix={}
        for row in votes:
            key=_key(row)
            value=row.get("judgment")
            if value not in ("positive", "negative", "uncertain"):
                raise ValueError("vote must be positive, negative or uncertain")
            if key in matrix:
                raise ValueError("duplicate vote")
            matrix[key]=value
        if set(matrix) != target:
            raise ValueError("every enumerated candidate must have a vote")
        matrices.append(matrix)
    a,b=matrices
    agreeing=[key for key in target if a[key]==b[key] and a[key] != "uncertain"]
    disputed=[key for key in target if a[key]!=b[key] or "uncertain" in (a[key],b[key])]
    n=len(target)
    observed=len(agreeing)/n
    positive_a=sum(v=="positive" for v in a.values())/n
    positive_b=sum(v=="positive" for v in b.values())/n
    negative_a=sum(v=="negative" for v in a.values())/n
    negative_b=sum(v=="negative" for v in b.values())/n
    chance=positive_a*positive_b+negative_a*negative_b
    kappa=(observed-chance)/(1-chance) if chance<1 else None
    return {
        "source_revision":universe["source_revision"],
        "candidate_universe_sha256":digest,
        "reviewer_ids":identities,
        "candidate_count":n,
        "agreed_binary_count":len(agreeing),
        "disagreements_or_uncertain":[{"source":k[0],"relation":k[1],"target":k[2],
                                      "review_1":a[k],"review_2":b[k]}
                                     for k in sorted(disputed)],
        "observed_binary_agreement":observed,
        "cohen_kappa_with_uncertain_penalized":kappa,
        "status":"claimed_distinct_reviewers; authenticity_and_universe_completeness_not_verified",
        "publication_ready":False,
        "note":"A third-party human must adjudicate disagreements, authenticate reviewers and certify exhaustive source scope."
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--universe",required=True)
    ap.add_argument("--review-a",required=True)
    ap.add_argument("--review-b",required=True)
    ap.add_argument("--output",required=True)
    args=ap.parse_args()
    data=[json.loads(Path(x).read_text(encoding="utf-8"))
          for x in (args.universe,args.review_a,args.review_b)]
    report=compare_two_reviews(*data)
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"agreed_binary_count":report["agreed_binary_count"],
                      "disagreements":len(report["disagreements_or_uncertain"]),
                      "publication_ready":report["publication_ready"]},sort_keys=True))


if __name__=="__main__":
    main()
