import json
import pathlib
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_public_version_and_pypi_install_commands_are_consistent():
    from rgraph import __version__

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["name"] == "rgraph"
    assert project["project"]["version"] == __version__ == "0.4.1"
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    landing = (ROOT / "index.html").read_text(encoding="utf-8")
    for text in (readme, landing):
        assert "uv tool install rgraph==0.4.1" in text
        assert "uv tool install" in text
    assert "uvx --isolated" in readme
    historical_release = (ROOT / "docs" / "releases" / "v0.2.1.md").read_text(
        encoding="utf-8"
    )
    assert "research-graph@v0.2.1" in historical_release


def test_pypi_publish_is_manual_and_uses_trusted_publishing():
    workflow = (ROOT / ".github" / "workflows" / "publish-pypi.yml").read_text(
        encoding="utf-8"
    )
    assert "workflow_dispatch:" in workflow
    assert "release:" not in workflow and "push:" not in workflow
    assert "environment:\n      name: pypi" in workflow
    assert "id-token: write" in workflow
    assert "pypa/gh-action-pypi-publish@release/v1" in workflow


def test_ci_keeps_wheel_uv_and_empty_repository_gates():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for contract in (
        "uv tool install --force dist/*.whl",
        "uvx --isolated --from dist/*.whl",
        "rgraph --no-banner ui --no-open",
        "empty Git repo reaches its first agent dry-run",
        "rgraph --no-banner doctor",
        "rgraph --no-banner next --dry-run",
        # Every packaged front-end asset, and the launcher a wheel opens when
        # the directory holds no study at all.
        "/workspace.js | grep -q \"function gateContent\"",
        "/launcher.js | grep -q \"function renderLauncher\"",
        "/console.js | grep -q \"function openConsole\"",
        "/app.css | grep -q \"wizard-steps\"",
        "/architecture.html | grep -q 'id=\"plate\"'",
        '/plate-live.js | grep -q "live-marks"',
        '"mode": "launcher"',
        "real Chromium regression",
        "python -m playwright install --with-deps chromium",
        'RGRAPH_BROWSER_TESTS: "1"',
        "tests/test_browser_regression.py",
    ):
        assert contract in ci

    tagged = (
        ROOT / ".github" / "workflows" / "release-verification.yml"
    ).read_text(encoding="utf-8")
    assert 'tags: ["v*"]' in tagged
    assert "@${GITHUB_REF_NAME}" in tagged


def test_published_releases_receive_checked_wheel_and_sdist_assets():
    workflow = (
        ROOT / ".github" / "workflows" / "release-verification.yml"
    ).read_text(encoding="utf-8")
    for contract in (
        "release:\n    types: [published]",
        "python -m build",
        "python -m twine check dist/*",
        'gh release upload "$RELEASE_TAG" dist/* --clobber',
        "contents: write",
    ):
        assert contract in workflow


def test_editable_install_finds_the_source_kit_away_from_checkout(tmp_path, monkeypatch):
    from rgraph.cli import default_root

    monkeypatch.chdir(tmp_path)
    assert pathlib.Path(default_root()).resolve() == ROOT


def test_claude_manifest_points_at_the_shared_roles_directory():
    manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["skills"] == ["./roles"]
    assert manifest["version"] == "0.3.0"


def test_codex_manifest_references_roles_without_copying_them():
    path = ROOT / "plugins" / "research-graph" / ".codex-plugin" / "plugin.json"
    manifest = json.loads(path.read_text())
    assert manifest["version"] == "0.3.0"
    assert len(manifest["prompts"]) == 6
    for entry in manifest["prompts"]:
        target = (path.parent / entry["path"]).resolve()
        assert target.is_relative_to(ROOT / "roles"), entry
        assert target.exists(), entry


def test_marketplace_lists_the_plugin():
    manifest = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text())
    assert manifest["plugins"][0]["name"] == "research-graph"
    assert manifest["plugins"][0]["version"] == "0.3.0"
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
