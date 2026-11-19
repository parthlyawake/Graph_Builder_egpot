import pytest

from bench import analyze_dsb_width12 as followup


def row(method, budget, hit, *, seed=0, experiment="main"):
    return {
        "app": "toy", "id": "q", "link_id": "l", "type": "explicit",
        "method": method, "node_budget": budget, "seed": seed, "experiment": experiment,
        "label": {"start_node": "s", "gold_nodes": ["g"], "lookalike_nodes": ["other"]},
        "returned_nodes": ["s", "g" if hit else "other"], "gold_found": ["g"] if hit else [],
        "hit": int(hit), "gold_recall": float(hit), "precision": 0.5 if hit else 0,
        "path_coverage": 1.0 if hit else 0.5, "ordered_path_match": int(hit),
        "nodes_returned": 2, "nodes_to_hit": 2 if hit else None,
        "precision_at_hit": 0.5 if hit else None, "latency_s": 0.1,
    }


def test_toy_aggregation_bootstrap_seed_spread_and_failures():
    rows = [row(method, b, method in followup.WIDE)
            for b in followup.BUDGETS for method in (*followup.WIDE, *followup.REFERENCES)]
    rows.extend(row("egpot_full_tiebreak_w12", b, seed < 5, seed=seed, experiment="seeds")
                for b in (20, 40) for seed in range(6))
    result = followup.summarize_scope(rows, {("toy", "q"): 2}, resamples=40)
    assert result == followup.summarize_scope(rows, {("toy", "q"): 2}, resamples=40)
    assert len(result["main"]) == 21
    assert all(r["depth"] == 2 for r in result["depth"])
    assert all(r["hit"]["difference"] == 1 and r["hit"]["interval_95"] == [1, 1]
               and r["gold_recall"]["interval_95"] == [1, 1]
               and r["analysis_type"] == "post-hoc exploratory" for r in result["paired"])
    spread = result["seed_spread"][0]["metrics"]
    assert spread["hit_count"] == {"min": 0, "median": 1, "max": 1, "defined_seeds": 6}
    assert spread["nodes_to_hit"]["defined_seeds"] == 5
    assert result["misses"] and all(r["returned_lookalike_nodes"] == ["other"] for r in result["misses"])


def test_prediction_c_requires_both_thresholds():
    def stats(method, budget, hits, nodes, precision):
        return {"method": method, "budget": budget, "n": 46,
                "hit_count": hits, "nodes_returned": nodes, "precision": precision}

    result = followup.predictions([
        stats("egpot_full_w12", 40, 38, 30, .09),
        stats("egpot_full_w12", 10, 36, 10, .3),
        stats("ppr", 40, 46, 40, .05),
        stats("ppr", 10, 30, 10, .2),
    ])
    assert result["A"]["held"] is True
    assert result["B"]["held"] is False
    assert result["C"]["nodes_returned"]["held"] is True
    assert result["C"]["precision"]["held"] is False
    assert result["C"]["held"] is False


def test_analyzer_rejects_unpaired_control():
    rows = [row(method, b, False) for b in followup.BUDGETS
            for method in (*followup.WIDE, *followup.REFERENCES)]
    rows[-1]["id"] = "unpaired"
    with pytest.raises(ValueError, match="not paired"):
        followup.summarize_scope(rows, {("toy", "q"): 1}, resamples=20)
