"""Provider preflight is explicit about what it did and did not verify."""

import pathlib
import subprocess

from rgraph.cli import main

ROOT = pathlib.Path(__file__).resolve().parents[1]
R = ["--root", str(ROOT), "--no-banner"]


def assignment(path: pathlib.Path, *, missing_role: bool = False) -> None:
    rows = {
        "retrieval": ("claude-code", "claude-sonnet-5"),
        "planning": ("claude-code", "claude-sonnet-5"),
        "execution": ("claude-code", "claude-sonnet-5"),
        "verification": ("codex", "gpt-5.6-terra"),
        "synthesis": ("claude-code", "claude-sonnet-5"),
        "reviewer": ("codex", "gpt-5.6-terra"),
    }
    if missing_role:
        rows.pop("reviewer")
    path.write_text(
        "\n".join(
            f"{role}: {{provider: {provider}, model: {model}}}"
            for role, (provider, model) in rows.items()
        ) + "\n",
        encoding="utf-8",
    )


def ready_environment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    assignment(tmp_path / "assignment.yaml")
    monkeypatch.setattr(
        "rgraph.commands.doctor.shutil.which", lambda name: f"/fake/bin/{name}"
    )
    monkeypatch.setattr(
        "rgraph.commands.doctor.subprocess.run",
        lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, stdout="logged in", stderr=""),
    )


def test_doctor_requires_an_effective_assignment(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    assert main([*R, "doctor"]) == 2
    out = capsys.readouterr().out
    assert "no assignment found" in out
    assert "rgraph setup" in out


def test_doctor_reports_unprobed_models_as_unverified(tmp_path, monkeypatch, capsys):
    ready_environment(tmp_path, monkeypatch)
    assert main([*R, "doctor"]) == 0
    out = capsys.readouterr().out
    assert "[UNVERIFIED] claude-code/claude-sonnet-5 model" in out
    assert "[UNVERIFIED] codex/gpt-5.6-terra model" in out
    assert "[PASS] claude-code/claude-sonnet-5 model" not in out
    assert "READY" in out


def test_doctor_surfaces_a_draft_provider_as_a_nonblocking_caveat(
    tmp_path, monkeypatch, capsys,
):
    ready_environment(tmp_path, monkeypatch)
    path = tmp_path / "assignment.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "execution: {provider: claude-code, model: claude-sonnet-5}",
            "execution: {provider: qwen, model: qwen3-coder-plus}",
        ),
        encoding="utf-8",
    )
    assert main([*R, "doctor"]) == 0
    out = capsys.readouterr().out
    assert "[CAVEAT] qwen support" in out
    assert "draft integration" in out
    assert "READY" in out


def test_doctor_probes_each_distinct_model_with_the_real_template(
    tmp_path, monkeypatch, capsys,
):
    calls = []
    ready_environment(tmp_path, monkeypatch)

    def completed(argv, **kwargs):
        if kwargs.get("input"):
            calls.append((argv, kwargs["input"], kwargs["cwd"]))
        return subprocess.CompletedProcess(argv, 0, stdout="RGRAPH_MODEL_OK", stderr="")

    monkeypatch.setattr("rgraph.commands.doctor.subprocess.run", completed)
    assert main([*R, "doctor", "--probe-models"]) == 0
    out = capsys.readouterr().out
    assert "[PASS] claude-code/claude-sonnet-5 model" in out
    assert "[PASS] codex/gpt-5.6-terra model" in out
    assert len(calls) == 2
    assert all("RGRAPH_MODEL_OK" in prompt for _, prompt, _ in calls)
    assert all(path != tmp_path for _, _, path in calls)


def test_doctor_turns_a_missing_cli_into_actionable_exit_two(
    tmp_path, monkeypatch, capsys,
):
    ready_environment(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "rgraph.commands.doctor.shutil.which",
        lambda name: None if name == "codex" else f"/fake/bin/{name}",
    )
    assert main([*R, "doctor"]) == 2
    out = capsys.readouterr().out
    assert "[FAIL] codex executable" in out
    assert "not on PATH" in out
    assert "Traceback" not in out


def test_doctor_turns_login_failure_into_actionable_exit_two(
    tmp_path, monkeypatch, capsys,
):
    ready_environment(tmp_path, monkeypatch)

    def completed(argv, **kwargs):
        code = 1 if argv[:3] == ["codex", "login", "status"] else 0
        return subprocess.CompletedProcess(argv, code, stdout="", stderr="not logged in")

    monkeypatch.setattr("rgraph.commands.doctor.subprocess.run", completed)
    assert main([*R, "doctor"]) == 2
    out = capsys.readouterr().out
    assert "[FAIL] codex login" in out
    assert "codex login status" in out


def test_doctor_rejects_an_incomplete_assignment(tmp_path, monkeypatch, capsys):
    ready_environment(tmp_path, monkeypatch)
    assignment(tmp_path / "assignment.yaml", missing_role=True)
    assert main([*R, "doctor"]) == 2
    assert "missing reviewer" in capsys.readouterr().out


def test_doctor_rejects_an_assignment_that_can_never_pass_separation(
    tmp_path, monkeypatch, capsys,
):
    ready_environment(tmp_path, monkeypatch)
    (tmp_path / "assignment.yaml").write_text(
        "\n".join(
            f"{role}: {{provider: codex, model: gpt-5.6-terra}}"
            for role in ("retrieval", "planning", "execution", "verification", "synthesis", "reviewer")
        ) + "\n",
        encoding="utf-8",
    )
    assert main([*R, "doctor"]) == 2
    out = capsys.readouterr().out
    assert "[FAIL] Gate viability" in out
    assert "T2 cannot pass" in out and "M1 cannot pass" in out
