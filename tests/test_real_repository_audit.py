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


def test_unbalanced_proto_fails_syntax_and_graph_coverage(tmp_path):
    from graft_ckg import CKGBuilder
    (tmp_path / "broken.proto").write_text(
        'syntax = "proto3";\nservice Broken {\n  rpc Ping (Req) returns (Resp);\n',
        encoding="utf-8",
    )
    syntax = run_audit(tmp_path)
    assert syntax["schemas"][".proto"]["discovered"] == 1
    assert syntax["schemas"][".proto"]["failed"] == 1
    assert not syntax["source_coverage_complete"]
    builder = CKGBuilder(str(tmp_path))
    builder.build()
    report = builder.get_language_report()
    assert report["proto_contracts"]["discovered"] == 1
    assert report["proto_contracts"]["failed"] == 1
    assert not report["full_source_coverage"]
    assert any(entry["language"] == "protobuf" for entry in report["parse_errors"])


def test_valid_proto_is_counted_in_both_audits(tmp_path):
    from graft_ckg import CKGBuilder
    (tmp_path / "healthy.proto").write_text(
        'syntax = "proto3";\nmessage Req {}\nmessage Resp {}\n'
        'service Health { rpc Check (Req) returns (Resp); }\n',
        encoding="utf-8",
    )
    assert run_audit(tmp_path)["schemas"][".proto"]["parsed"] == 1
    builder = CKGBuilder(str(tmp_path))
    builder.build()
    report = builder.get_language_report()
    assert report["proto_contracts"]["parsed"] == 1
    assert report["proto_contracts"]["failed"] == 0
    assert report["full_source_coverage"]
