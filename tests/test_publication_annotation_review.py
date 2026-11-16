"""Source labels remain unapproved until actual independent human review."""
import copy
import pytest
from bench.annotation_review import review_universe_sha256, compare_two_reviews


def example():
    universe={"source_revision":"a"*40,"complete_scopes_attested":[
        {"source":"service.py:handler","relation":"CALLS"}],
        "candidate_edges":[
            {"source":"service.py:handler","relation":"CALLS","target":"service.py:valid"},
            {"source":"service.py:handler","relation":"CALLS","target":"service.py:wrong"},
        ]}
    digest=review_universe_sha256(universe)
    first={"reviewer_id":"reviewer-a","source_revision":"a"*40,
           "candidate_universe_sha256":digest,
           "complete_scopes_reviewed":True,
           "votes":[
               {"source":"service.py:handler","relation":"CALLS","target":"service.py:valid","judgment":"positive"},
               {"source":"service.py:handler","relation":"CALLS","target":"service.py:wrong","judgment":"negative"}]}
    second=copy.deepcopy(first);second["reviewer_id"]="reviewer-b"
    return universe,first,second


def test_paper_gate_never_authenticates_reviewers_by_self_report():
    u,a,b=example()
    report=compare_two_reviews(u,a,b)
    assert report["agreed_binary_count"]==2
    assert report["cohen_kappa_three_category"]==1.0
    assert report["publication_ready"] is False


def test_disagreement_and_uncertainty_require_external_adjudication():
    u,a,b=example()
    b["votes"][1]["judgment"]="uncertain"
    report=compare_two_reviews(u,a,b)
    assert len(report["disagreements_or_uncertain"])==1
    assert report["agreed_binary_count"]==1
    assert report["publication_ready"] is False


def test_review_scope_and_identity_fail_closed():
    u,a,b=example()
    b["reviewer_id"]="reviewer-a"
    with pytest.raises(ValueError, match="distinct"):
        compare_two_reviews(u,a,b)
    u,a,b=example()
    b["candidate_universe_sha256"]="b"*64
    with pytest.raises(ValueError, match="exact pinned universe"):
        compare_two_reviews(u,a,b)
    u,a,b=example()
    b["votes"]=b["votes"][:1]
    with pytest.raises(ValueError,match="every enumerated candidate"):
        compare_two_reviews(u,a,b)
