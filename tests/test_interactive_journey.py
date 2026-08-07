"""Regression tests for the guided, no-JSON first-use journey."""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys

from rgraph.cli import main
from rgraph.commands.check import load_for_run
from rgraph.commands.setup import customize_assignments, parse_choice, propose
from rgraph.config import Assignment, load_kit
from rgraph.gates import evaluate_gate, record_from
from rgraph.workflow import next_action

ROOT = pathlib.Path(__file__).resolve().parents[1]
R = ["--root", str(ROOT), "--no-banner"]


def replies(monkeypatch, values):
    answers = iter(values)
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))


def guided_init(run: pathlib.Path, monkeypatch) -> int:
    replies(monkeypatch, (
        "Does method A reduce error compared with method B?",
        "Method A; Method B",
        "Clinical deployment",
        "Public data only; 8 CPU hours",
        "Lower held-out error; reproducible result",
        "",       # guided mode
        "n",      # ethics does not apply
        "Public benchmark under its published terms",
        "",       # default legal note
        "Test Researcher",
        "",       # approve summary
    ))
    return main([*R, "--run", str(run), "init", "--guided"])


def test_guided_init_writes_real_sealed_answers_and_is_h1_ready(tmp_path, monkeypatch):
    run = tmp_path / "run"
    assert guided_init(run, monkeypatch) == 0

    meta = json.loads((run / "meta.json").read_text())
    problem = json.loads((run / "problem_spec.json").read_text())
    governance = json.loads((run / "governance_record.json").read_text())
    assert meta["question"] == problem["body"]["question"]
    assert meta["run_id"].startswith("rg-")
    assert problem["body"]["scope"]["in_scope"] == ["Method A", "Method B"]
    assert governance["body"]["approvals"][0]["name"] == "Test Researcher"

    args = type("Args", (), {"root": str(ROOT), "run": str(run)})()
    kit, loaded = load_for_run(args)
    assert evaluate_gate(loaded, kit, "H1").status == "AWAITING"


def test_terminal_decoration_falls_back_when_output_is_cp1252():
    """Decorative Unicode must never turn a valid command into a traceback."""
    env = dict(os.environ, PYTHONIOENCODING="cp1252", NO_COLOR="1")
    result = subprocess.run(
        [sys.executable, "-m", "rgraph", "--root", str(ROOT), "--no-banner",
         "demo", "--scenario", "1"],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="cp1252",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SCENARIO 1 / CLEAN EVIDENCE" in result.stdout
    assert "-" * 40 in result.stdout
    assert "Traceback" not in result.stderr


def test_guided_init_cancellation_writes_nothing(tmp_path, monkeypatch):
    run = tmp_path / "run"
    monkeypatch.setattr("builtins.input", lambda *_: (_ for _ in ()).throw(KeyboardInterrupt))
    assert main([*R, "--run", str(run), "init", "--guided"]) == 0
    assert not run.exists()


def test_edit_setup_preserves_other_run_files(tmp_path, monkeypatch):
    run = tmp_path / "run"
    assert main([*R, "--run", str(run), "init"]) == 0
    marker = run / "notes.txt"
    marker.write_text("keep me")
    assert guided_init_existing(run, monkeypatch) == 0
    assert marker.read_text() == "keep me"
    assert "Replace this with" not in (run / "meta.json").read_text()


def guided_init_existing(run: pathlib.Path, monkeypatch) -> int:
    replies(monkeypatch, (
        "Can the guided flow preserve existing work?", "Existing run files", "None",
        "No network", "All setup files validate", "", "n",
        "Local data only", "", "Test Researcher", "",
    ))
    return main([*R, "--run", str(run), "init", "--guided", "--edit"])


def test_init_from_yaml_is_the_noninteractive_path(tmp_path):
    source = tmp_path / "study.yaml"
    source.write_text(
        "question: Does A improve B?\n"
        "scope:\n"
        "  in_scope: [A, B]\n"
        "  out_of_scope: [Deployment]\n"
        "constraints: [Public data]\n"
        "success_criteria: [Lower error]\n"
        "governance:\n"
        "  ethics_applicable: false\n"
        "  data_governance: [Public benchmark terms]\n"
        "  legal_notes: [No additional restrictions]\n"
        "  approver: Test Researcher\n",
        encoding="utf-8",
    )
    run = tmp_path / "run"
    assert main([*R, "--run", str(run), "init", "--from", str(source)]) == 0
    assert json.loads((run / "meta.json").read_text())["question"] == "Does A improve B?"


def test_setup_menu_changes_a_role_without_provider_model_syntax(monkeypatch):
    kit = load_kit(ROOT, assignment="assignment.example.yaml")
    plan = propose(kit, {"claude-code": "FOUND", "codex": "FOUND"})
    replies(monkeypatch, ("execution", "codex", "gpt-5.6-sol", "", "done"))
    chosen = customize_assignments(kit, plan)
    assert chosen["execution"] == Assignment("execution", "codex", "gpt-5.6-sol")


def test_familiar_bare_provider_names_are_not_mistaken_for_models():
    kit = load_kit(ROOT)
    current = Assignment("execution", "claude-code", "claude-sonnet-5")
    assert parse_choice(kit, "codex", current, "execution").provider == "codex"
    assert parse_choice(
        kit, "claude", Assignment("execution", "codex", "x"), "execution"
    ) == current


def test_decide_without_gate_offers_a_menu(tmp_path, monkeypatch):
    run = tmp_path / "run"
    assert main([*R, "--run", str(run), "init"]) == 0
    replies(monkeypatch, ("1", "y", "y"))
    monkeypatch.setattr("rgraph.commands.decide.at_a_terminal", lambda: True)
    assert main([*R, "--run", str(run), "decide", "--as", "Test Researcher"]) == 0
    assert (run / "gates" / "H1.json").exists()


def test_trace_without_claim_offers_a_menu(example_run, monkeypatch, capsys):
    replies(monkeypatch, ("1",))
    monkeypatch.setattr("rgraph.commands.trace.is_terminal", lambda: True)
    assert main([*R, "--run", str(example_run), "trace"]) == 0
    assert "WHICH CLAIM" in capsys.readouterr().out


def test_review_without_terminal_never_invents_a_stop_decision(example_run, capsys):
    assert main([*R, "--run", str(example_run), "review"]) == 2
    out = capsys.readouterr().out
    assert "No release decision was recorded" in out
    assert "from a terminal" in out


def test_scripted_review_cannot_approve_even_with_a_name(example_run, capsys):
    assert main([
        *R, "--run", str(example_run), "review", "--outcome", "release",
        "--as", "Automated Agent",
    ]) == 2
    assert "from a terminal" in capsys.readouterr().out
    assert not (example_run / "release_manifest.json").exists()


def test_terminal_review_cannot_record_an_anonymous_decision(
    example_run, capsys, monkeypatch,
):
    from rgraph.interactive import InteractionCancelled

    monkeypatch.setattr("rgraph.commands.review.is_terminal", lambda: True)
    monkeypatch.setattr("rgraph.commands.review.git_user_name", lambda: "")

    def cancel(*args, **kwargs):
        raise InteractionCancelled

    monkeypatch.setattr("rgraph.commands.review.ask_text", cancel)
    assert main([
        *R, "--run", str(example_run), "review", "--outcome", "release",
    ]) == 0
    assert "No release decision has been recorded" in capsys.readouterr().out
    assert not (example_run / "release_manifest.json").exists()


def test_review_refuses_release_while_required_gates_are_unresolved(
    tmp_path, capsys, monkeypatch,
):
    monkeypatch.setattr("rgraph.commands.review.is_terminal", lambda: True)
    run = tmp_path / "run"
    assert main([*R, "--run", str(run), "init"]) == 0
    capsys.readouterr()
    assert main([
        *R, "--run", str(run), "review", "--outcome", "release",
        "--as", "Test Researcher",
    ]) == 1
    assert "unresolved gates remain" in capsys.readouterr().out
    assert not (run / "release_manifest.json").exists()


def test_stop_closes_an_unresolved_run_and_blocks_further_execution(
    tmp_path, capsys, monkeypatch,
):
    monkeypatch.setattr("rgraph.commands.review.is_terminal", lambda: True)
    run = tmp_path / "run"
    assert main([*R, "--run", str(run), "init"]) == 0
    capsys.readouterr()
    assert main([
        *R, "--run", str(run), "review", "--outcome", "stop",
        "--as", "Test Researcher",
    ]) == 1
    assert (run / "release_manifest.json").exists()

    capsys.readouterr()
    assert main([*R, "--run", str(run), "status"]) == 0
    out = capsys.readouterr().out
    assert "NEXT ACTION" in out
    assert "none — run closed with stop" in out

    assert main([*R, "--run", str(run), "next"]) == 0
    assert "run closed with stop" in capsys.readouterr().out


def test_final_review_refuses_an_artifact_changed_after_its_gate(
    example_run, capsys, monkeypatch,
):
    manuscript = example_run / "manuscript.md"
    manuscript.write_text(
        manuscript.read_text(encoding="utf-8") + "\nChanged after M1.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("rgraph.commands.review.is_terminal", lambda: True)
    assert main([
        *R, "--run", str(example_run), "review", "--outcome", "release",
        "--as", "Test Researcher",
    ]) == 1
    out = capsys.readouterr().out
    assert "Unresolved gates remain" in out
    assert "M1" in out
    assert not (example_run / "release_manifest.json").exists()


def test_numbered_next_menu_keeps_stop_safe(example_run, monkeypatch, capsys):
    replies(monkeypatch, ("3",))
    assert main([*R, "--run", str(example_run), "next", "--unit", "u06"]) == 0
    assert "Stopped. No command has been executed." in capsys.readouterr().out


def test_status_routes_placeholder_runs_back_to_the_wizard(tmp_path, capsys):
    run = tmp_path / "run"
    assert main([*R, "--run", str(run), "init"]) == 0
    capsys.readouterr()
    assert main([*R, "--run", str(run), "status"]) == 0
    out = capsys.readouterr().out
    assert "NEXT ACTION" in out
    assert "init --guided" in out and "--edit" in out
    assert out.count("NEXT ACTION") == 1


def test_narrow_no_color_status_stays_readable(example_run):
    env = dict(os.environ, COLUMNS="40", NO_COLOR="1")
    result = subprocess.run(
        [sys.executable, "-m", "rgraph", "--root", str(ROOT), "--run",
         str(example_run), "--no-banner", "status"],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "\x1b[" not in result.stdout
    assert max(map(len, result.stdout.splitlines())) <= 40
    for stage in ("RETRIEVE", "PLAN", "EXECUTE", "VERIFY", "WRITE"):
        assert stage in result.stdout
    assert result.stdout.count("NEXT ACTION") == 1


def test_next_keeps_artifact_state_attached_at_forty_columns(example_run):
    env = dict(os.environ, COLUMNS="40", NO_COLOR="1")
    result = subprocess.run(
        [sys.executable, "-m", "rgraph", "--root", str(ROOT), "--run",
         str(example_run), "--no-banner", "next", "--unit", "u06"],
        cwd=ROOT, env=env, input="S\n", capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert max(map(len, lines)) <= 40
    assert any(
        line.strip().startswith("run/frozen_protocol.json")
        and line.rstrip().endswith("VALID")
        for line in lines
    )
    assert any(
        line.strip().startswith("run/governance_record.json")
        and line.rstrip().endswith("VALID")
        for line in lines
    )


def test_a_failing_gate_screen_survives_a_narrow_terminal():
    """A wrapped finding must stay under its own heading, not restart the margin.

    A digest is long enough to wrap at eighty columns, so the screen that most
    needs reading was the first one to come apart.
    """
    env = dict(os.environ, COLUMNS="40", NO_COLOR="1")
    result = subprocess.run(
        [sys.executable, "-m", "rgraph", "--root", str(ROOT), "--no-banner",
         "demo", "--scenario", "2"],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False,
    )
    # Scenario 2 is a staged failure, so 1 is the expected code, not a fault.
    assert result.returncode == 1, result.stdout + result.stderr
    assert "\x1b[" not in result.stdout
    lines = result.stdout.splitlines()
    assert max(map(len, lines)) <= 40

    finding = next(i for i, line in enumerate(lines) if "SOURCE NOT RESOLVED" in line)
    for line in lines[finding + 1:]:
        if not line:
            break
        assert line.startswith("        "), line

    boundary = next(i for i, line in enumerate(lines) if "Scientific correctness" in line)
    assert lines[boundary + 1].startswith("         not determined")


def run_waiting_at_e1(tmp_path: pathlib.Path) -> pathlib.Path:
    run = tmp_path / "run"
    shutil.copytree(ROOT / "example-run", run)
    keep = {
        "problem_spec", "governance_record", "search_protocol", "corpus_snapshot",
        "kg_snapshot", "evidence_matrix",
    }
    loaded = load_for_run(type("Args", (), {"root": str(ROOT), "run": str(run)})())[1]
    for artifact_id, artifact in loaded.artifacts.items():
        if artifact_id in keep:
            continue
        artifact.path.unlink(missing_ok=True)
        if artifact.payload_path:
            artifact.payload_path.unlink(missing_ok=True)
    for record in (run / "gates").glob("*.json"):
        if record.stem != "H1":
            record.unlink()
    return run


def test_next_stops_at_each_gate_instead_of_skipping_it(tmp_path, capsys):
    run = run_waiting_at_e1(tmp_path)
    args = type("Args", (), {"root": str(ROOT), "run": str(run)})()
    kit, loaded = load_for_run(args)
    assert next_action(loaded, kit).command == "rgraph challenge E1"

    assert main([*R, "--run", str(run), "next"]) == 1
    out = capsys.readouterr().out
    assert "E1 needs its assigned reviewer" in out
    assert "rgraph challenge E1" in out

    result = evaluate_gate(loaded, kit, "E1", require_decision=False)
    loaded.write_gate_record(record_from(result, loaded, kit))
    kit, loaded = load_for_run(args)
    assert next_action(loaded, kit).command == "rgraph decide H2"


def test_explicit_unit_cannot_bypass_its_human_gate(tmp_path, capsys):
    run = run_waiting_at_e1(tmp_path)
    args = type("Args", (), {"root": str(ROOT), "run": str(run)})()
    kit, loaded = load_for_run(args)
    result = evaluate_gate(loaded, kit, "E1", require_decision=False)
    loaded.write_gate_record(record_from(result, loaded, kit))
    capsys.readouterr()
    assert main([*R, "--run", str(run), "next", "--unit", "u03"]) == 1
    out = capsys.readouterr().out
    assert "Cannot run u03 yet" in out and "rgraph decide H2" in out
