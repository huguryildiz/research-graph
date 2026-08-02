"""Regression tests for the guided, no-JSON first-use journey."""

from __future__ import annotations

import json
import pathlib
import shutil

from rgraph.cli import main
from rgraph.commands.check import load_for_run
from rgraph.commands.setup import customize_assignments, parse_choice, propose
from rgraph.config import Assignment, load_kit
from rgraph.gates import evaluate_gate
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
    current = Assignment("execution", "claude-code", "claude-sonnet-5")
    assert parse_choice("codex", current, "execution").provider == "codex"
    assert parse_choice("claude", Assignment("execution", "codex", "x"), "execution") == current


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
    assert "Which claim" in capsys.readouterr().out


def test_review_without_terminal_never_invents_a_stop_decision(example_run, capsys):
    assert main([*R, "--run", str(example_run), "review"]) == 2
    assert "No release decision was recorded" in capsys.readouterr().out


def test_review_refuses_release_while_required_gates_are_unresolved(tmp_path, capsys):
    run = tmp_path / "run"
    assert main([*R, "--run", str(run), "init"]) == 0
    capsys.readouterr()
    assert main([*R, "--run", str(run), "review", "--outcome", "release"]) == 1
    assert "unresolved gates remain" in capsys.readouterr().out
    assert not (run / "release_manifest.json").exists()


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
    assert "Next action" in out and "init --guided --edit" in out


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
    assert next_action(loaded, kit).command == "rgraph check E1"

    assert main([*R, "--run", str(run), "next"]) == 1
    out = capsys.readouterr().out
    assert "E1 is ready to be checked" in out
    assert "rgraph check E1" in out

    assert main([*R, "--run", str(run), "check", "E1"]) == 0
    kit, loaded = load_for_run(args)
    assert next_action(loaded, kit).command == "rgraph decide H2"


def test_explicit_unit_cannot_bypass_its_human_gate(tmp_path, capsys):
    run = run_waiting_at_e1(tmp_path)
    assert main([*R, "--run", str(run), "check", "E1"]) == 0
    capsys.readouterr()
    assert main([*R, "--run", str(run), "next", "--unit", "u03"]) == 1
    out = capsys.readouterr().out
    assert "Cannot run u03 yet" in out and "rgraph decide H2" in out
