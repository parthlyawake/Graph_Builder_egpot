"""Strict, reproducible evaluation metrics for GRAFT-CKG.

This module deliberately does not infer relevance from keywords or symbol substrings.
A label identifies an *exact* canonical node ID and optional source-evidence
byte spans in a rendered context. Missing annotations are not assumed irrelevant
in real repositories; publish irrelevance only for completely annotated queries.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence
import math


def exact_rank(ranked_ids: Sequence[str], relevant_ids: Iterable[str], k: int = 5) -> int | None:
    """First relevant rank. No fuzzy, substring or basename matches."""
    relevant = set(relevant_ids)
    if not relevant:
        raise ValueError("Query needs at least one relevant canonical node ID")
    return next((i for i, node in enumerate(ranked_ids[:k], 1) if node in relevant), None)


def retrieval_metrics(rows: Sequence[Mapping[str, Any]], k: int = 5) -> dict:
    """Micro-averaged ranks and macro-averaged per-query exact-ID recall."""
    if k < 1 or not rows:
        raise ValueError("k must be positive and rows must not be empty")
    ranks, recalls = [], []
    for row in rows:
        ranked = list(row["ranked_ids"])[:k]
        targets = set(row["relevant_ids"])
        rank = exact_rank(ranked, targets, k)
        ranks.append(rank)
        recalls.append(len(targets.intersection(ranked)) / len(targets))
    n = len(ranks)
    return {
        f"MRR@{k}": sum(1.0/r for r in ranks if r is not None)/n,
        "Hits@1": sum(r == 1 for r in ranks)/n,
        f"Hits@{k}": sum(r is not None for r in ranks)/n,
        f"Recall@{k}": sum(recalls)/n,
        "n_queries": n,
    }


def edge_metrics(predicted: Iterable[tuple[str, str, str]],
                 labelled: Iterable[tuple[str, str, str]],
                 closed_sources: Iterable[tuple[str, str]]) -> dict:
    """Evaluate only exhaustively annotated (source, relation) scopes.

    Other predictions are outside the evaluable universe, never false positives.
    A missing positive is a false negative even when the graph has no source.
    """
    scopes = set(closed_sources)
    if not scopes:
        raise ValueError("At least one independently audited closed scope required")
    gold = {e for e in labelled if (e[0], e[1]) in scopes}
    pred = {e for e in predicted if (e[0], e[1]) in scopes}
    tp, fp, fn = len(gold & pred), len(pred-gold), len(gold-pred)
    p = tp/(tp+fp) if tp+fp else None
    r = tp/(tp+fn) if tp+fn else None
    f = 2*p*r/(p+r) if p is not None and r is not None and p+r else None
    return {"TP":tp,"FP":fp,"FN":fn,"precision":p,"recall":r,"f1":f,
            "scopes":len(scopes)}


def _token_ranges(text: str, tokenizer: Any) -> list[tuple[int,int]]:
    """One UTF-8 byte interval per token, using tiktoken's exact token bytes."""
    offset, ranges = 0, []
    for token in tokenizer.encode(text, disallowed_special=()):
        n = len(tokenizer.decode_single_token_bytes(token))
        ranges.append((offset, offset+n))
        offset += n
    if offset != len(text.encode("utf-8")):
        raise ValueError("Tokenizer does not provide byte-exact reconstruction")
    return ranges


def byte_span_metrics(text: str, relevant_byte_spans: Sequence[tuple[int,int]],
                      tokenizer: Any) -> dict:
    """Count genuinely annotated relevant tokens within the *actual* context.

    A token counts as relevant iff all its UTF-8 bytes are inside a labeled span.
    Tokens crossing annotation boundaries are conservatively marked irrelevant.
    This is a measure of evidence-token irrelevance, not a semantic oracle.
    """
    encoded_length = len(text.encode("utf-8"))
    spans = sorted((int(a),int(b)) for a,b in relevant_byte_spans)
    if any(a<0 or b<=a or b>encoded_length for a,b in spans):
        raise ValueError("Invalid annotated byte span")
    if any(spans[i][1]>spans[i+1][0] for i in range(len(spans)-1)):
        raise ValueError("Overlapping annotated spans")
    total = relevant = 0
    i = 0
    for start,end in _token_ranges(text,tokenizer):
        total += 1
        while i<len(spans) and spans[i][1] <= start:
            i+=1
        if i<len(spans) and spans[i][0]<=start and end<=spans[i][1]:
            relevant+=1
    return {"total_tokens":total,"relevant_tokens":relevant,
            "irrelevant_tokens":total-relevant,
            "irrelevance_ratio":(total-relevant)/total if total else None}


def context_evidence_spans(context: str, evidence: Sequence[str]) -> list[tuple[int,int]]:
    """Locate independently annotated evidence strings uniquely in a context.

    Exact evidence MUST appear exactly once; otherwise refuse a numeric score
    rather than guessing which occurrence is relevant.
    """
    spans=[]
    for excerpt in evidence:
        if not excerpt:
            raise ValueError("Empty evidence excerpt")
        position=context.find(excerpt)
        if position<0 or context.find(excerpt,position+1)>=0:
            raise ValueError("Missing or ambiguous annotated evidence: "+repr(excerpt[:60]))
        a=len(context[:position].encode("utf-8"))
        b=a+len(excerpt.encode("utf-8"))
        spans.append((a,b))
    return sorted(spans)


def summarize_token_irrelevance(rows: Sequence[Mapping[str,Any]]) -> dict:
    """Aggregate only fully annotated, nonempty contexts."""
    if not rows:
        return {"n":0,"irrelevance_ratio":None}
    for r in rows:
        if r.get("irrelevance_ratio") is None:
            raise ValueError("Unscored token context: missing annotation")
    total=sum(r["total_tokens"] for r in rows)
    irrelevant=sum(r["irrelevant_tokens"] for r in rows)
    return {"n":len(rows),"total_tokens":total,"irrelevant_tokens":irrelevant,
            "irrelevance_ratio":irrelevant/total if total else None}


def percentile(values: Sequence[float], p: float) -> float | None:
    if not values:
        return None
    if not 0 <= p <= 100:
        raise ValueError("p must be 0..100")
    ordered=sorted(values)
    pos=(len(ordered)-1)*p/100
    lo=math.floor(pos); hi=math.ceil(pos)
    return ordered[lo]+(ordered[hi]-ordered[lo])*(pos-lo)


def time_summary(values: Sequence[float]) -> dict:
    return {"n":len(values),"p50_s":percentile(values,50),
            "p95_s":percentile(values,95),"min_s":min(values) if values else None,
            "max_s":max(values) if values else None}
