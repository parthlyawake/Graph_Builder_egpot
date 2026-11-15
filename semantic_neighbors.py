"""Bounded-memory semantic adjacency for L2-normalized sparse TF-IDF vectors.

Approximate candidate retrieval with exact cosine scoring; this deliberately
does not claim exhaustive nearest neighbors. No NxN dense similarity matrix.
"""
from collections import Counter, defaultdict


def sparse_semantic_pairs(matrix, *, threshold=0.70, max_neighbors=12,
                          max_candidates=512, max_terms=12, max_postings=1500):
    """Yield unique (row_i, row_j, cosine) with bounded candidate expansion."""
    if max_neighbors < 1 or max_candidates < 1 or max_terms < 1:
        raise ValueError("candidate and neighbor limits must be positive")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")
    x = matrix.tocsr()
    count = x.shape[0]
    if count < 2:
        return
    chosen = []
    postings = defaultdict(list)
    for i in range(count):
        start, end = x.indptr[i], x.indptr[i + 1]
        cols = x.indices[start:end]
        weights = x.data[start:end]
        top = sorted(range(len(cols)), key=lambda k: (-weights[k], cols[k]))[:max_terms]
        terms = [(int(cols[k]), float(weights[k])) for k in top]
        chosen.append(terms)
        for col, _ in terms:
            postings[col].append(i)

    for i in range(count):
        evidence = Counter()
        for col, weight in chosen[i]:
            ids = postings[col]
            if len(ids) > max_postings:
                continue
            for candidate in ids:
                if candidate > i:
                    evidence[candidate] += weight
        if not evidence:
            continue
        candidates = [j for j, _ in sorted(evidence.items(),
                                           key=lambda item: (-item[1], item[0]))[:max_candidates]]
        similarities = (x[candidates] @ x.getrow(i).T).toarray().ravel()
        hits = sorted(((int(j), float(s)) for j, s in zip(candidates, similarities)
                       if float(s) >= threshold), key=lambda it: (-it[1], it[0]))
        for j, score in hits[:max_neighbors]:
            yield i, j, min(1.0, max(0.0, score))
