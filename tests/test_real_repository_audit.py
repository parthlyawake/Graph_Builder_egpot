"""Real-repository audit must not conflate distinct grammar variants."""
from pathlib import Path

from bench.real_repository_coverage import run_audit


def test_mixed_typescript_and_tsx_use_distinct_grammars(tmp_path):
    (tmp_path / "plain.ts").write_text(
        "export const value: number = 3;\n", encoding="utf-8"
    )
    (tmp_path / "render.tsx").write_text(
        'export function Render() { return <div className="tile">Ok</div>; }\n',
        encoding="utf-8",
    )
    report = run_audit(tmp_path)
    assert report["languages"]["typescript"]["discovered"] == 2
    assert report["languages"]["typescript"]["parsed"] == 2
    assert report["parse_issue_count"] == 0
    assert report["source_coverage_complete"]


def test_real_audit_syntax_failure_prevents_completeness(tmp_path):
    (tmp_path / "broken.py").write_text("def bad(:\n", encoding="utf-8")
    report = run_audit(tmp_path)
    assert report["languages"]["python"]["failed"] == 1
    assert not report["source_coverage_complete"]
    assert report["issues"][0]["path"] == "broken.py"
