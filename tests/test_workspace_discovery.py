"""Workspace discovery is language/build driven, not hardcoded to a microservice suite."""
from workspace_discovery import workspace_manifest, discover_modules


def test_spring_and_other_modules_discover_by_source_and_declared_identity(tmp_path):
    java = tmp_path / "app-one"
    (java / "src/main/resources").mkdir(parents=True)
    (java / "pom.xml").write_text("<project/>", encoding="utf-8")
    (java / "src/main/resources/application.yml").write_text(
        "spring:\n  application:\n    name: catalogue\n", encoding="utf-8"
    )
    node = tmp_path / "frontend"
    node.mkdir()
    (node / "package.json").write_text('{"name":"frontend"}')
    go = tmp_path / "payment"
    go.mkdir()
    (go / "go.mod").write_text("module example.com/payment")
    (tmp_path / "node_modules" / "dependency").mkdir(parents=True)
    (tmp_path / "node_modules" / "dependency" / "package.json").write_text("{}")
    manifest = workspace_manifest(tmp_path)
    assert {x["id"] for x in manifest["repositories"]} == {
        "catalogue", "frontend", "payment"
    }
    assert all(x["path"] != "." for x in manifest["repositories"])


def test_duplicate_service_identity_is_not_silently_merged(tmp_path):
    for suffix in ("a", "b"):
        module = tmp_path / suffix
        (module / "src/main/resources").mkdir(parents=True)
        (module / "pom.xml").write_text("<project/>")
        (module / "src/main/resources/application.properties").write_text(
            "spring.application.name=duplicate\n")
    import pytest
    with pytest.raises(ValueError, match="duplicate"):
        discover_modules(tmp_path)
