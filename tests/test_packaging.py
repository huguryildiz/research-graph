import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_claude_manifest_points_at_the_shared_roles_directory():
    manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["skills"] == ["./roles"]
    assert manifest["version"] == "0.2.0"


def test_codex_manifest_references_roles_without_copying_them():
    path = ROOT / "plugins" / "research-graph" / ".codex-plugin" / "plugin.json"
    manifest = json.loads(path.read_text())
    assert len(manifest["prompts"]) == 6
    for entry in manifest["prompts"]:
        target = (path.parent / entry["path"]).resolve()
        assert target.is_relative_to(ROOT / "roles"), entry
        assert target.exists(), entry


def test_marketplace_lists_the_plugin():
    manifest = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text())
    assert manifest["plugins"][0]["name"] == "research-graph"
    assert (ROOT / manifest["plugins"][0]["source"].lstrip("./")).is_dir()


def test_no_role_file_is_duplicated_anywhere():
    copies = [
        path for path in ROOT.rglob("retrieval.md")
        if path.parent.name != "roles" and ".venv" not in path.parts
    ]
    assert copies == []


def test_readme_states_the_claim_boundary_and_the_honesty_limit():
    text = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    assert "does not judge scientific correctness" in text
    assert "discipline mechanism" in text
    assert "codejunkie99/graph-engineering" in text
    assert "subscription" in text and "api" in text
