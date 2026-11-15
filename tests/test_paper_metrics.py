import unittest
from bench.paper_metrics import (exact_rank, retrieval_metrics, edge_metrics,
    byte_span_metrics, context_evidence_spans, percentile, time_summary,
    summarize_token_irrelevance)


class ByteTokenizer:
    """Deterministic stand-in for tiktoken for unit testing, one UTF8 byte/token."""
    def encode(self, text, disallowed_special=()):
        return list(text.encode("utf-8"))

    def decode_single_token_bytes(self, token):
        return bytes([token])


class TestPaperMetrics(unittest.TestCase):
    def test_exact_ids_no_substring(self):
        self.assertIsNone(exact_rank(["a/methodExtra", "a/method"], ["method"], 5))
        self.assertEqual(exact_rank(["a/methodExtra", "a/method"], ["a/method"], 5),2)
        with self.assertRaises(ValueError):
            exact_rank(["foo"], [])

    def test_independent_mrr(self):
        a=retrieval_metrics([
            {"ranked_ids":["a","b"],"relevant_ids":["a"]},
            {"ranked_ids":["b","a"],"relevant_ids":["a"]}],2)
        b=retrieval_metrics([
            {"ranked_ids":["b","a"],"relevant_ids":["a"]},
            {"ranked_ids":["b","c"],"relevant_ids":["a"]}],2)
        self.assertAlmostEqual(a["MRR@2"],0.75)
        self.assertAlmostEqual(b["MRR@2"],0.25)
        self.assertAlmostEqual(a["Recall@2"],1.0)
        self.assertAlmostEqual(b["Recall@2"],0.5)

    def test_closed_scopes_exclude_unlabelled(self):
        truth={("a","CALLS","b"),("x","CALLS","z")}
        pred={("a","CALLS","b"),("a","CALLS","wrong"),("x","CALLS","anything")}
        m=edge_metrics(pred,truth,{("a","CALLS")})
        self.assertEqual((m["TP"],m["FP"],m["FN"]),(1,1,0))
        self.assertAlmostEqual(m["precision"],0.5)

    def test_byte_exact(self):
        text="prefix café suffix"
        pos=context_evidence_spans(text,["café"])
        metric=byte_span_metrics(text,pos,ByteTokenizer())
        self.assertEqual(metric["total_tokens"],len(text.encode("utf-8")))
        self.assertEqual(metric["relevant_tokens"],len("café".encode("utf-8")))
        self.assertAlmostEqual(metric["irrelevance_ratio"],
            1-len("café".encode("utf-8"))/len(text.encode("utf-8")))
        with self.assertRaises(ValueError):
            context_evidence_spans("abc abc",["abc"])

    def test_unannotated_not_zero(self):
        with self.assertRaises(ValueError):
            summarize_token_irrelevance([{"irrelevance_ratio":None}])

    def test_percentiles(self):
        self.assertEqual(percentile([0,10],95),9.5)
        self.assertEqual(time_summary([1,2,3])["p50_s"],2)


if __name__ == "__main__":
    unittest.main()
