import pytest

from bench import analyze_test_splits as report


def toy_row(label, hits, *, rank=2):
    return {"app": "toy", "id": label, "label": {"start_node": label}, "hit": hits,
            "gold_recall": float(hits), "nodes_to_hit": rank if hits else None}


def test_strongest_baseline_is_selected_inside_each_resample():
    groups = {
        report.FULL: [toy_row("a", 1), toy_row("b", 1)],
        "ppr": [toy_row("a", 1, rank=3), toy_row("b", 0)],
        "bfs": [toy_row("a", 0), toy_row("b", 1)],
    }
    contrasts = [(report.FULL, report.STRONGEST), (report.FULL, "bfs")]
    best, fixed = report.bootstrap(groups, contrasts, resamples=1000)
    assert best["analysis_type"] == "second look, exploratory"
    for field in ("hit", "gold_recall"):
        assert best[field]["observed_baseline"] == "bfs"
        assert best[field]["difference"] == .5
        assert best[field]["interval_95"] == [0, .5]
        assert fixed[field]["interval_95"] == [0, 1]


def test_refuses_history_before_both_new_records_are_verified(monkeypatch):
    monkeypatch.setattr(report, "verify_plan", lambda: "runner")
    monkeypatch.setattr(report.locked, "read_json", lambda path: {"datasets": {app: {} for app in report.protocol.PRIOR}})

    def load(app, *_):
        if app == "train_ticket":
            raise ValueError("Uncommitted new result")
        return [], [], {}

    monkeypatch.setattr(report, "load_record", load)
    monkeypatch.setattr(report, "historical", lambda *args: pytest.fail("Historical data were opened"))
    with pytest.raises(ValueError, match="Uncommitted new result"):
        report.analyze()


def test_bootstrap_rejects_unpaired_rows():
    with pytest.raises(ValueError, match="paired"):
        report.bootstrap({report.FULL: [toy_row("a", 1)], "ppr": [toy_row("b", 1)]},
                         [(report.FULL, "ppr")], resamples=10)
