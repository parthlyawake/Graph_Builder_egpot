"""Workspace GraphQL parser failures must be reported, not silently swallowed."""
from multi_repo import WorkspaceCKGBuilder


def test_graphql_syntax_failure_invalidates_coverage(tmp_path):
    source = tmp_path / "service"
    source.mkdir()
    (source / "valid.graphql").write_text(
        "type Query { status: String }\n", encoding="utf8")
    (source / "broken.graphql").write_text(
        "type Query { invalid: \n", encoding="utf8")
    workspace = WorkspaceCKGBuilder({
        "name": "schemas",
        "repositories": [{"id": "service", "path": str(source)}],
    })
    # Need a base_dir containing the schema files for workspace spec indexing.
    workspace.config.base_dir = str(source)
    workspace.build()
    result = workspace.verify_graph()
    assert result["contract_spec_diagnostics"]["graphql"]["discovered"] == 2
    assert result["contract_spec_diagnostics"]["graphql"]["failed"] >= 1
    assert not result["source_coverage_complete"]
    assert any(x["file"] == "broken.graphql"
               for x in result["contract_spec_diagnostics"]["graphql_issues"])
