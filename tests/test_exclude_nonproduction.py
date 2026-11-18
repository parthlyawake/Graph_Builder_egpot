import pytest

from multi_repo import WorkspaceCKGBuilder, WorkspaceConfig


@pytest.mark.parametrize("enabled", [None, False, True], ids=["default", "off", "on"])
def test_workspace_excludes_nonproduction_at_child_discovery(tmp_path, enabled):
    production = {
        "app.py": "",
        "src/contest/solver.py": "",
        "src/late_marker.py": "# " + "x" * 5000 + "\n# Automatically generated\n",
    }
    nonproduction = {
        "src/Test/helper.py": "",
        "checks/app_test.py": "",
        "generated/client.py": "",
        "src/wrapper.py": "# Code generated from templates. DO NOT EDIT.\n",
    }
    for path, header in {**production, **nonproduction}.items():
        source = tmp_path / "service" / path
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(header + "def run():\n    return 1\n", encoding="utf-8")

    manifest = tmp_path / "workspace.yaml"
    contents = "repositories:\n  - id: svc\n    path: service\n"
    if enabled is not None:
        contents += f"exclude_nonproduction: {str(enabled).lower()}\n"
    manifest.write_text(contents, encoding="utf-8")

    workspace = WorkspaceCKGBuilder(str(manifest))
    graph = workspace.build()
    child = workspace.repo_builders["svc"]
    expected_paths = set(production) if enabled else set(production) | set(nonproduction)
    assert set(child.raw_file_lines) == expected_paths
    for path in production.keys() | nonproduction.keys():
        expected = path in expected_paths
        assert (f"file::svc/{path}" in graph) is expected
        assert (f"svc/{path}:run" in graph) is expected

    child.build()
    assert set(child.raw_file_lines) == expected_paths


def test_simple_yaml_fallback_reads_production_filter():
    parse = WorkspaceConfig._parse_simple_yaml
    assert WorkspaceConfig.from_dict(parse("exclude_nonproduction: true # opt in")).exclude_nonproduction
    assert not WorkspaceConfig.from_dict(parse("exclude_nonproduction: false")).exclude_nonproduction
