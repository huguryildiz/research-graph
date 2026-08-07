"""What a stranger runs, in the order they run it.

Every test here stands for a way the kit used to mislead someone arriving for
the first time. They are behavioural, not unit: each one drives the CLI the way
the README tells a newcomer to drive it.
"""

import argparse
import io
import json
import os
import pathlib
import subprocess
import sys

import pytest

from rgraph.checks import resolve_doi
from rgraph.cli import main
from rgraph.commands.check import load
from rgraph.commands.setup import (
    choose_assignments, detect, parse_choice, propose, separation_warnings, unregistered,
)
from rgraph.config import Assignment, load_kit, machine_assignment_path

ROOT = pathlib.Path(__file__).resolve().parents[1]
R = ["--root", str(ROOT), "--no-banner"]


# ── the first real run ──────────────────────────────────────────────────────

def decide(run, monkeypatch, gate="H1", answers=("y", "y"), identity="Test Human"):
    """Answer a human gate the way a person at a terminal would."""
    replies = iter(answers)
    monkeypatch.setattr("builtins.input", lambda *_: next(replies))
    monkeypatch.setattr("rgraph.commands.decide.at_a_terminal", lambda: True)
    return main([*R, "--run", str(run), "decide", gate, "--as", identity])


def test_init_seal_decide_then_h1_is_green(tmp_path, monkeypatch):
    """Four commands, no hand-written JSON, and the first gate opens."""
    run = tmp_path / "run"
    assert main([*R, "--run", str(run), "init"]) == 0
    assert (run / "problem_spec.json").exists()
    assert (run / "governance_record.json").exists()
    assert main([*R, "--run", str(run), "seal"]) == 0
    assert decide(run, monkeypatch) == 0
    assert main([*R, "--run", str(run), "check", "H1"]) == 0


def test_a_human_gate_will_not_pass_until_a_human_says_so(tmp_path, capsys, monkeypatch):
    """Files existing is not a decision, and the screen must not call it one."""
    run = tmp_path / "run"
    main([*R, "--run", str(run), "init"])
    main([*R, "--run", str(run), "seal"])
    capsys.readouterr()

    assert main([*R, "--run", str(run), "check", "H1"]) == 1
    out = capsys.readouterr().out
    assert "AWAITING" in out
    assert "no human decision recorded" in out
    assert "rgraph decide H1" in out
    assert not (run / "gates" / "H1.json").exists()

    assert decide(run, monkeypatch) == 0
    assert main([*R, "--run", str(run), "check", "H1"]) == 0


def test_the_decision_records_who_answered_what(tmp_path, monkeypatch):
    run = tmp_path / "run"
    main([*R, "--run", str(run), "init"])
    decide(run, monkeypatch, identity="H. U. Yildiz")

    record = json.loads((run / "gates" / "H1.json").read_text())
    assert record["decided_by"] == {"role": "human", "identity": "human/H. U. Yildiz"}
    assert record["attestation"]["identity"] == "human/H. U. Yildiz"
    claims = [a["claim"] for a in record["attestation"]["answers"]]
    assert claims == list(load_kit(ROOT, assignment="assignment.example.yaml").gates["H1"].proves)
    assert all(a["answered"] == "yes" for a in record["attestation"]["answers"])
    decision = next(check for check in record["checks"] if check["name"] == "decision")
    assert decision == {
        "name": "decision",
        "status": "PASS",
        "detail": "attested by human/H. U. Yildiz",
    }


def test_a_no_answer_sends_the_gate_back(tmp_path, monkeypatch):
    run = tmp_path / "run"
    main([*R, "--run", str(run), "init"])
    assert decide(run, monkeypatch, answers=("y", "n")) == 1

    record = json.loads((run / "gates" / "H1.json").read_text())
    assert record["outcome"] == "revise"
    assert record["attestation"]["answers"][1]["answered"] == "no"
    decision = next(check for check in record["checks"] if check["name"] == "decision")
    assert decision["status"] == "FAIL"
    assert "not attested" in decision["detail"]
    assert main([*R, "--run", str(run), "check", "H1"]) == 1


def test_walking_away_records_nothing(tmp_path, monkeypatch):
    run = tmp_path / "run"
    main([*R, "--run", str(run), "init"])
    assert decide(run, monkeypatch, answers=("y", "s")) == 0
    assert not (run / "gates" / "H1.json").exists()


def test_decide_refuses_a_gate_no_human_owns(tmp_path, capsys, monkeypatch):
    run = tmp_path / "run"
    main([*R, "--run", str(run), "init"])
    monkeypatch.setattr("builtins.input", lambda *_: "y")
    assert main([*R, "--run", str(run), "decide", "E1", "--as", "Test Human"]) == 2
    assert "challenge gate" in capsys.readouterr().out


def test_decide_will_not_attest_to_an_artifact_that_does_not_validate(tmp_path, capsys, monkeypatch):
    """You cannot have read a file that does not parse."""
    run = tmp_path / "run"
    main([*R, "--run", str(run), "init"])
    (run / "governance_record.json").unlink()
    capsys.readouterr()
    monkeypatch.setattr("builtins.input", lambda *_: "y")
    assert main([*R, "--run", str(run), "decide", "H1", "--as", "Test Human"]) == 1
    assert "Nothing to decide yet" in capsys.readouterr().out
    assert not (run / "gates" / "H1.json").exists()


def test_check_never_writes_a_human_gate_record(tmp_path, monkeypatch):
    """`check` verifies. If it could write the attestation, it could forge one."""
    run = tmp_path / "run"
    main([*R, "--run", str(run), "init"])
    decide(run, monkeypatch, identity="H. U. Yildiz")
    before = (run / "gates" / "H1.json").read_text()
    assert main([*R, "--run", str(run), "check", "H1"]) == 0
    assert (run / "gates" / "H1.json").read_text() == before


def test_active_provider_cannot_decide_a_human_gate(tmp_path, capsys, monkeypatch):
    run = tmp_path / "run"
    main([*R, "--run", str(run), "init"])
    monkeypatch.setenv("RGRAPH_ACTIVE_INVOCATION", "u01")
    monkeypatch.setattr("rgraph.commands.decide.at_a_terminal", lambda: True)

    assert main([*R, "--run", str(run), "decide", "H1", "--as", "Agent"]) == 2
    assert "active provider invocation" in capsys.readouterr().out
    assert not (run / "gates" / "H1.json").exists()


def test_active_provider_cannot_make_the_final_human_decision(
    example_run, capsys, monkeypatch,
):
    monkeypatch.setenv("RGRAPH_ACTIVE_INVOCATION", "u12")
    monkeypatch.setattr("rgraph.commands.review.is_terminal", lambda: True)

    assert main([
        *R, "--run", str(example_run), "review", "--outcome", "release", "--as", "Agent",
    ]) == 2
    assert "active provider invocation" in capsys.readouterr().out
    assert not (example_run / "release_manifest.json").exists()


def test_every_human_gate_in_the_fixture_carries_an_attestation():
    """The fixture used to name a model as the human who decided."""
    kit = load_kit(ROOT, assignment="assignment.example.yaml")
    for gate in kit.gates.values():
        if gate.kind != "human":
            continue
        record = json.loads((ROOT / "example-run" / "gates" / f"{gate.id}.json").read_text())
        attestation = record["attestation"]
        assert attestation["identity"].startswith("human/"), gate.id
        assert record["decided_by"]["identity"] == attestation["identity"], gate.id
        answered = {a["claim"] for a in attestation["answers"]}
        assert answered == set(gate.proves), gate.id


def test_init_refuses_to_replace_a_run_without_force(tmp_path, capsys):
    run = tmp_path / "run"
    assert main([*R, "--run", str(run), "init"]) == 0
    (run / "problem_spec.json").write_text('{"mine": true}')
    assert main([*R, "--run", str(run), "init"]) == 2
    assert "already exists" in capsys.readouterr().out
    assert json.loads((run / "problem_spec.json").read_text()) == {"mine": True}
    assert main([*R, "--run", str(run), "init", "--force"]) == 0


def test_a_failing_presence_check_names_what_is_missing(tmp_path, capsys):
    run = tmp_path / "run"
    main([*R, "--run", str(run), "init"])
    (run / "governance_record.json").unlink()
    assert main([*R, "--run", str(run), "check", "H1"]) == 1
    assert "governance_record" in capsys.readouterr().out


def test_next_lists_real_prerequisites_and_no_return_payload(tmp_path, capsys, monkeypatch):
    run = tmp_path / "run"
    main([*R, "--run", str(run), "init", "--from", str(ROOT / "study.example.yaml")])
    assert decide(run, monkeypatch) == 0
    capsys.readouterr()
    monkeypatch.setattr("builtins.input", lambda *_: "S")
    assert main([*R, "--run", str(run), "next"]) == 0
    out = capsys.readouterr().out
    # `evidence_gap` rides a return edge: it exists only after a gate sends work
    # back, so a first pass must not report it as a file you failed to provide.
    assert "evidence_gap" not in out
    assert out.count("problem_spec") == 1
    assert "governance_record" in out


# ── the digest actually anchors the chain ───────────────────────────────────

def test_editing_a_body_without_resealing_is_caught(tmp_path, capsys, monkeypatch):
    """The edit a human actually makes: change the file, leave the hash alone."""
    run = tmp_path / "run"
    main([*R, "--run", str(run), "init"])
    main([*R, "--run", str(run), "seal"])
    decide(run, monkeypatch)
    assert main([*R, "--run", str(run), "check", "H1"]) == 0
    capsys.readouterr()

    path = run / "problem_spec.json"
    document = json.loads(path.read_text())
    document["body"]["question"] = "A different question entirely."
    path.write_text(json.dumps(document, indent=2))  # content_hash untouched

    assert main([*R, "--run", str(run), "check", "H1"]) == 1
    assert "BODY EDITED AFTER HASHING" in capsys.readouterr().out


def test_sealing_the_edit_makes_the_gate_green_again(tmp_path):
    """Without a human gate in the way, sealing is all it takes."""
    run = tmp_path / "run"
    main([*R, "--run", str(run), "init"])
    path = run / "problem_spec.json"
    document = json.loads(path.read_text())
    document["body"]["question"] = "A different question entirely."
    path.write_text(json.dumps(document, indent=2))
    assert main([*R, "--run", str(run), "check", "H1"]) == 1   # BODY EDITED
    assert main([*R, "--run", str(run), "seal"]) == 0
    assert main([*R, "--run", str(run), "check", "H1"]) == 1   # AWAITING, not FAIL


def test_sealing_a_payload_artifact_re_digests_the_payload(example_run, capsys):
    """`seal` exists for the hand-edited artifact, and the manuscript is one.

    `manuscript` and `raw_results` keep their bodies in a companion file and
    carry only its digest. Sealing used to hash the body without refreshing
    that digest first, so editing the manuscript and sealing produced a true
    hash of a stale pointer -- M1 stayed red and the command that was supposed
    to fix it reported "already sealed".
    """
    payload = example_run / "manuscript.md"
    payload.write_text(payload.read_text() + "\nA sentence added by hand.\n")

    assert main([*R, "--run", str(example_run), "check", "M1"]) == 1
    assert "digest changed" in capsys.readouterr().out

    assert main([*R, "--run", str(example_run), "seal"]) == 0
    assert "payload manuscript.md" in capsys.readouterr().out

    meta = json.loads((example_run / "manuscript.meta.json").read_text())
    import hashlib
    assert meta["body"]["payload_sha256"] == hashlib.sha256(payload.read_bytes()).hexdigest()


def test_rewriting_what_was_attested_to_retires_the_attestation(tmp_path, capsys, monkeypatch):
    """A person vouched for one version of the file, not for whatever follows it.

    Resealing repairs the digest, which is a mechanical fact. It cannot repair
    the reading, so the gate goes stale and asks for the decision again.
    """
    run = tmp_path / "run"
    main([*R, "--run", str(run), "init"])
    decide(run, monkeypatch)
    assert main([*R, "--run", str(run), "check", "H1"]) == 0

    path = run / "problem_spec.json"
    document = json.loads(path.read_text())
    document["body"]["question"] = "A different question entirely."
    path.write_text(json.dumps(document, indent=2))
    assert main([*R, "--run", str(run), "seal"]) == 0
    capsys.readouterr()

    assert main([*R, "--run", str(run), "check", "H1"]) == 1
    assert "problem_spec changed after H1 passed" in capsys.readouterr().out

    assert decide(run, monkeypatch) == 0
    assert main([*R, "--run", str(run), "check", "H1"]) == 0


def test_seal_is_idempotent(tmp_path, capsys):
    run = tmp_path / "run"
    main([*R, "--run", str(run), "init"])
    main([*R, "--run", str(run), "seal"])
    capsys.readouterr()
    assert main([*R, "--run", str(run), "seal"]) == 0
    out = capsys.readouterr().out
    assert "SEAL RESULT" in out
    assert "sealed          0 artifact(s)" in out


# ── setup does not break what came before it ────────────────────────────────

def test_setup_keeps_verification_apart_from_execution():
    """T2 is decided by verification over what execution produced."""
    kit = load_kit(ROOT, assignment="assignment.example.yaml")
    detected = {"claude-code": "FOUND"}          # a single provider, worst case
    plan = propose(kit, detected)
    warnings = separation_warnings(kit, plan)
    assert plan["execution"].identity(kit.providers) != plan["verification"].identity(kit.providers)
    assert warnings == [], warnings


def test_setup_says_so_when_a_plan_collapses_a_required_pair():
    """One provider with one model cannot separate T2, and must admit it."""
    kit = load_kit(ROOT, assignment="assignment.example.yaml")
    plan = propose(kit, {"codex": "FOUND"}, {"producers": "codex"})
    assert plan["execution"].identity(kit.providers) == plan["verification"].identity(kit.providers)
    assert any("T2 cannot pass" in w for w in separation_warnings(kit, plan))


def test_demo_ignores_the_users_own_assignment(tmp_path, monkeypatch):
    """The fixture's identities belong to assignment.example.yaml, not to you."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "assignment.yaml").write_text(
        "retrieval:    {provider: claude-code, model: claude-sonnet-5}\n"
        "planning:     {provider: claude-code, model: claude-sonnet-5}\n"
        "execution:    {provider: claude-code, model: claude-sonnet-5}\n"
        "verification: {provider: claude-code, model: claude-sonnet-5}\n"
        "synthesis:    {provider: claude-code, model: claude-sonnet-5}\n"
        "reviewer:     {provider: claude-code, model: claude-sonnet-5}\n"
    )
    assert main([*R, "demo", "--scenario", "1"]) == 0


def _kit_copy(tmp_path: pathlib.Path) -> pathlib.Path:
    for name in ("graph.yaml", "gates.yaml", "providers.yaml", "assignment.example.yaml"):
        (tmp_path / name).write_text((ROOT / name).read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


# A preset, so the plan does not depend on which CLIs happen to be installed on
# the machine running the tests.
PRESET = ["--preset", "producers=claude-code,reviewer=codex"]


@pytest.fixture
def elsewhere(tmp_path, monkeypatch):
    """A user standing in their own study directory, off any checkout.

    The config home moves with them, so a test never reads or writes the real
    `~/.config/rgraph/assignment.yaml` of whoever runs the suite.
    """
    study = tmp_path / "study"
    study.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.chdir(study)
    return study


def test_setup_will_not_write_when_it_cannot_ask(tmp_path, capsys, monkeypatch, elsewhere):
    _kit_copy(tmp_path)

    def no_terminal(*_):
        raise EOFError

    monkeypatch.setattr("builtins.input", no_terminal)
    assert main(["--root", str(tmp_path), "--no-banner", "setup", *PRESET]) == 2
    assert "--yes" in capsys.readouterr().out
    assert not machine_assignment_path().exists()


def test_setup_backs_up_an_assignment_it_replaces(tmp_path, elsewhere):
    _kit_copy(tmp_path)
    mine = "reviewer:     {provider: grok, model: grok-5}\n"
    original = (ROOT / "assignment.example.yaml").read_text(encoding="utf-8") + mine
    target = machine_assignment_path()
    target.parent.mkdir(parents=True)
    target.write_text(original, encoding="utf-8")

    assert main(["--root", str(tmp_path), "--no-banner", "setup", "--yes", *PRESET]) == 0
    assert target.with_suffix(".yaml.bak").read_text(encoding="utf-8") == original


def test_setup_writes_where_an_upgrade_cannot_delete_it(tmp_path, elsewhere, capsys):
    """Not into the installed package: `uv tool upgrade` replaces that whole tree."""
    _kit_copy(tmp_path)
    assert main(["--root", str(tmp_path), "--no-banner", "setup", "--yes", *PRESET]) == 0
    out = capsys.readouterr().out
    assert "DETECTED\n" in out
    assert "PROPOSED ASSIGNMENT\n" in out
    assert "ASSIGNMENT WRITTEN\n" in out
    assert "NEXT ACTION\n    $ rgraph init" in out
    assert machine_assignment_path().exists()
    assert not (tmp_path / "assignment.yaml").exists()
    assert not (elsewhere / "assignment.yaml").exists()


def test_setup_warns_before_writing_an_unverified_default_model(
    tmp_path, elsewhere, capsys, monkeypatch,
):
    _kit_copy(tmp_path)
    providers = tmp_path / "providers.yaml"
    providers.write_text(
        providers.read_text(encoding="utf-8")
        + """
new-provider:
  kind: cli
  invoke: new-provider
  exec_argv: [new-provider, "--model", "{model}"]
  stdin: role_file
  identity: "new-provider/{model}"
  capabilities: [filesystem, shell, read_files]
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "rgraph.commands.setup.detect", lambda kit: {"new-provider": "FOUND"},
    )

    assert main([
        "--root", str(tmp_path), "--no-banner", "setup", "--yes", "--here",
    ]) == 0
    out = capsys.readouterr().out
    assert out.index("has no verified setup model default") < out.index("ASSIGNMENT WRITTEN")
    assert "model: default" in (elsewhere / "assignment.yaml").read_text(encoding="utf-8")


def test_setup_uses_the_shared_terminal_hierarchy(tmp_path, elsewhere, capsys):
    _kit_copy(tmp_path)
    assert main(["--root", str(tmp_path), "--no-banner", "setup", "--yes", *PRESET]) == 0
    out = capsys.readouterr().out
    assert "DETECTED\n    claude-code" in out
    assert "PROPOSED ASSIGNMENT\n    retrieval" in out
    assert "ASSIGNMENT WRITTEN\n    " in out
    assert "NEXT ACTION\n    $ rgraph init" in out


def test_a_study_directory_overrides_the_machine_default(tmp_path, elsewhere):
    """One study on a different pair of providers than the rest of the machine."""
    _kit_copy(tmp_path)
    main(["--root", str(tmp_path), "--no-banner", "setup", "--yes", *PRESET])
    assert main(["--root", str(tmp_path), "--no-banner", "setup", "--yes", "--here",
                 "--preset", "producers=claude-code,reviewer=claude-code"]) == 0

    args = argparse.Namespace(root=str(tmp_path))
    assert load(args).assignment["reviewer"].provider == "claude-code"
    (elsewhere / "assignment.yaml").unlink()
    assert load(args).assignment["reviewer"].provider == "codex"


def test_the_machine_default_reaches_a_study_that_never_saw_setup(tmp_path, elsewhere, monkeypatch):
    _kit_copy(tmp_path)
    main(["--root", str(tmp_path), "--no-banner", "setup", "--yes", *PRESET])
    second = elsewhere.parent / "another-study"
    second.mkdir()
    monkeypatch.chdir(second)

    args = argparse.Namespace(root=str(tmp_path))
    assert load(args).assignment["reviewer"].provider == "codex"


# ── failure modes a first-hour user hits ────────────────────────────────────

def test_malformed_meta_json_reports_an_error_not_a_traceback(tmp_path, capsys):
    run = tmp_path / "run"
    run.mkdir()
    (run / "meta.json").write_text("{")
    for command in (["status"], ["check", "H1"], ["trace", "c-01"], ["review"], ["revise", "H1"]):
        assert main([*R, "--run", str(run), *command]) == 2, command
        assert "not valid JSON" in capsys.readouterr().out


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="chmod(0) does not take a file away from its owner on Windows",
)
def test_unreadable_config_reports_a_usage_error(tmp_path, capsys):
    graph = tmp_path / "graph.yaml"
    graph.write_text("nodes: []\nedges: []\n", encoding="utf-8")
    graph.chmod(0)
    try:
        assert main(["--root", str(tmp_path), "--no-banner", "check", "--static"]) == 2
        assert "Permission denied" in capsys.readouterr().err
    finally:
        graph.chmod(0o600)


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="chmod(0) does not take a file away from its owner on Windows",
)
def test_unreadable_run_metadata_reports_a_usage_error(tmp_path, capsys):
    run = tmp_path / "run"
    run.mkdir()
    meta = run / "meta.json"
    meta.write_text("{}", encoding="utf-8")
    meta.chmod(0)
    try:
        assert main([*R, "--run", str(run), "status"]) == 2
        assert "Permission denied" in capsys.readouterr().err
    finally:
        meta.chmod(0o600)


@pytest.mark.parametrize(
    "command",
    (["status"], ["check", "H1"], ["revise", "H1"], ["review", "--outcome", "stop"]),
)
def test_truncated_gate_records_are_usage_errors(tmp_path, capsys, command):
    import shutil

    run = tmp_path / "run"
    shutil.copytree(ROOT / "example-run", run)
    (run / "gates" / "H1.json").write_text("{", encoding="utf-8")
    assert main([*R, "--run", str(run), *command]) == 2
    assert "not valid JSON" in capsys.readouterr().out


def test_schema_invalid_gate_records_are_usage_errors(tmp_path, capsys):
    import shutil

    run = tmp_path / "run"
    shutil.copytree(ROOT / "example-run", run)
    path = run / "gates" / "H1.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record.pop("outcome")
    path.write_text(json.dumps(record), encoding="utf-8")
    assert main([*R, "--run", str(run), "status"]) == 2
    assert "H1.json is invalid" in capsys.readouterr().out


def test_trace_refuses_a_schema_invalid_claim_map(tmp_path, capsys):
    import shutil

    run = tmp_path / "run"
    shutil.copytree(ROOT / "example-run", run)
    path = run / "claim_evidence_map.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["body"]["claims"] = [{}]
    path.write_text(json.dumps(document), encoding="utf-8")
    assert main([*R, "--run", str(run), "trace", "c-03"]) == 2
    assert "claim_evidence_map is invalid" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("filename", "content"),
    (
        ("providers.yaml", "codex:\n"),
        ("gates.yaml", "H1:\n"),
        ("assignment.example.yaml", "retrieval:\n"),
    ),
)
def test_truncated_yaml_records_are_config_errors(tmp_path, capsys, filename, content):
    import shutil

    kit = tmp_path / "kit"
    shutil.copytree(ROOT, kit, ignore=shutil.ignore_patterns(".git", ".venv", "dist"))
    (kit / filename).write_text(content, encoding="utf-8")
    assert main([
        "--root", str(kit), "--run", str(kit / "example-run"),
        "--no-banner", "status",
    ]) == 2
    assert "must be a mapping" in capsys.readouterr().out


def test_an_unreachable_doi_is_not_a_fabricated_one(monkeypatch):
    """Offline must never advise deleting a citation it could not check."""
    import urllib.error

    def offline(*_, **__):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr("urllib.request.urlopen", offline)
    assert resolve_doi("10.1109/lwc.2020.3019321") == "unreachable"


def test_online_e1_fails_cleanly_when_the_network_is_gone(tmp_path, capsys, monkeypatch):
    import shutil
    import urllib.error

    run = tmp_path / "run"
    shutil.copytree(ROOT / "example-run", run)

    def offline(*_, **__):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr("urllib.request.urlopen", offline)
    assert main([*R, "--run", str(run), "check", "E1", "--online"]) == 1
    out = capsys.readouterr().out
    assert "could not be reached" in out
    assert "DOI CHECK INCOMPLETE" in out
    assert "replace or remove" not in out


# ── the shipped fixture stays shipped ───────────────────────────────────────

def test_checking_the_committed_example_run_writes_nothing():
    before = (ROOT / "example-run" / "gates" / "M1.json").read_text(encoding="utf-8")
    assert main([*R, "--run", str(ROOT / "example-run"), "check", "M1"]) == 0
    assert (ROOT / "example-run" / "gates" / "M1.json").read_text(encoding="utf-8") == before


# ── choosing who runs what ──────────────────────────────────────────────────

def test_a_bare_model_keeps_the_provider_it_had():
    """`claude-opus-5` means "same CLI, other model"; `codex/…` means both."""
    kit = load_kit(ROOT)
    current = Assignment("planning", "claude-code", "claude-sonnet-5")
    assert parse_choice(kit, "claude-opus-5", current, "planning") == Assignment(
        "planning", "claude-code", "claude-opus-5")
    assert parse_choice(kit, "codex/gpt-5.6-terra", current, "planning") == Assignment(
        "planning", "codex", "gpt-5.6-terra")


def test_an_effort_alone_changes_the_depth_and_nothing_else():
    """The one case where what you type is not the whole answer."""
    kit = load_kit(ROOT)
    current = Assignment("planning", "claude-code", "claude-opus-5")
    assert parse_choice(kit, "@max", current, "planning") == Assignment(
        "planning", "claude-code", "claude-opus-5", "max")
    assert parse_choice(
        kit, "codex/gpt-5.6-sol@ultra", current, "planning"
    ) == Assignment(
        "planning", "codex", "gpt-5.6-sol", "ultra")
    # Naming a model without an effort leaves the provider at its own default.
    assert parse_choice(kit, "claude-fable-5", current, "planning").effort is None


def test_an_effort_the_provider_will_not_take_is_refused_on_the_spot(monkeypatch, capsys):
    """Refused on the line it was typed, like an unassignable role."""
    kit = load_kit(ROOT, assignment="assignment.example.yaml")
    plan = propose(kit, detect(kit))
    #        retrieval ×2                      the rest keep the proposal
    replies = iter(["claude-code/claude-opus-5@ultra", "", "", "", "", "", ""])
    monkeypatch.setattr("builtins.input", lambda *_: next(replies))

    chosen = choose_assignments(kit, plan)
    out = capsys.readouterr().out
    assert "takes low, medium, high, xhigh, max, not 'ultra'" in out
    assert chosen["retrieval"] == plan["retrieval"]


def test_every_role_can_be_moved_off_the_plates_pairing(monkeypatch, capsys):
    """The diagram recommends; the person paying for the subscriptions decides."""
    kit = load_kit(ROOT, assignment="assignment.example.yaml")
    plan = propose(kit, detect(kit))
    replies = iter(["codex/gpt-5.6-sol", "", "", "", "claude-code/claude-haiku-4-5-20251001", ""])
    monkeypatch.setattr("builtins.input", lambda *_: next(replies))

    chosen = choose_assignments(kit, plan)
    assert chosen["retrieval"] == Assignment("retrieval", "codex", "gpt-5.6-sol")
    assert chosen["synthesis"] == Assignment(
        "synthesis", "claude-code", "claude-haiku-4-5-20251001")
    assert chosen["planning"] == plan["planning"]


def test_a_provider_that_cannot_take_the_role_is_refused_on_the_spot(monkeypatch, capsys):
    """`grok` has no shell, so it cannot be the one running the experiments."""
    kit = load_kit(ROOT, assignment="assignment.example.yaml")
    plan = propose(kit, detect(kit))
    #        retrieval ×2          planning  execution ×2         rest
    replies = iter(["nosuch/x", "", "", "grok/grok-5", "", "", "", ""])
    monkeypatch.setattr("builtins.input", lambda *_: next(replies))

    chosen = choose_assignments(kit, plan)
    out = capsys.readouterr().out
    assert "'nosuch' is not in providers.yaml" in out
    assert "cannot take execution" in out
    assert "shell" in out
    assert chosen["execution"] == plan["execution"]


def test_setup_names_a_cli_it_has_no_entry_for(monkeypatch):
    """Detection answers "which of mine are installed"; this answers the rest."""
    kit = load_kit(ROOT, assignment="assignment.example.yaml")
    monkeypatch.setattr(
        "rgraph.services.providers.shutil.which",
        lambda name: "/usr/bin/aider" if name == "aider" else None,
    )
    assert unregistered(kit) == ["aider"]


# ── an edit that outlives the decision it was made under ────────────────────

def retire_h1(run, monkeypatch):
    """Pass H1, then edit and reseal the artifact that decision was made on."""
    main([*R, "--run", str(run), "init"])
    main([*R, "--run", str(run), "seal"])
    assert decide(run, monkeypatch) == 0
    spec = run / "problem_spec.json"
    document = json.loads(spec.read_text(encoding="utf-8"))
    document["body"]["question"] += " (narrowed after the gate opened)"
    spec.write_text(json.dumps(document, indent=2), encoding="utf-8")
    assert main([*R, "--run", str(run), "seal"]) == 0


def test_a_stale_human_gate_is_sent_back_to_decide_not_revise(tmp_path, capsys, monkeypatch):
    """Resealing repairs the hash. Only a person can repair the reading."""
    run = tmp_path / "run"
    retire_h1(run, monkeypatch)
    capsys.readouterr()

    assert main([*R, "--run", str(run), "check", "H1"]) == 1
    out = capsys.readouterr().out
    assert "STALE" in out
    assert "rgraph decide H1" in out
    assert "rgraph revise H1" not in out


def test_revise_names_the_command_that_can_reopen_a_retired_gate(tmp_path, capsys, monkeypatch):
    """It used to answer `nothing to revise` at a gate `check` had just called stale."""
    run = tmp_path / "run"
    retire_h1(run, monkeypatch)
    capsys.readouterr()

    main([*R, "--run", str(run), "revise", "H1"])
    out = capsys.readouterr().out
    assert "nothing to revise" not in out
    assert "rgraph decide H1" in out


def test_status_does_not_report_a_retired_decision_as_passed(tmp_path, capsys, monkeypatch):
    """The summary screen reads the same digests the gate screen reads."""
    run = tmp_path / "run"
    retire_h1(run, monkeypatch)
    capsys.readouterr()

    assert main([*R, "--run", str(run), "status"]) == 0
    out = capsys.readouterr().out
    assert "H1 PASS" not in out
    assert "H1 STALE" in out


def test_decide_will_not_take_its_answers_from_a_pipe(tmp_path, capsys, monkeypatch):
    """`yes y | rgraph decide H1` would automate the one step that cannot be."""
    run = tmp_path / "run"
    main([*R, "--run", str(run), "init"])
    main([*R, "--run", str(run), "seal"])
    capsys.readouterr()

    monkeypatch.setattr("sys.stdin", io.StringIO("y\ny\n"))
    assert main([*R, "--run", str(run), "decide", "H1", "--as", "Test Human"]) == 2
    assert "No terminal to answer on" in capsys.readouterr().out
    assert not (run / "gates" / "H1.json").exists()


# ── the CLI itself ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("argv", [
    ["--no-banner", "--run", "example-run", "status"],
    ["--no-banner", "status", "--run", "example-run"],
    ["status", "--no-banner", "--run", "example-run"],
])
def test_global_flags_are_accepted_on_either_side_of_the_command(argv, capsys):
    assert main(["--root", str(ROOT), *argv]) == 0
    assert "RESEARCH RUN" in capsys.readouterr().out


def test_the_packaged_kit_is_complete(tmp_path):
    """Everything the CLI reads at runtime must survive `python -m build`."""
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(tmp_path)],
        cwd=ROOT, check=True, capture_output=True,
    )
    import zipfile

    wheel = next(tmp_path.glob("*.whl"))
    names = set(zipfile.ZipFile(wheel).namelist())
    for required in (
        "graph.yaml", "gates.yaml", "providers.yaml", "assignment.example.yaml",
        "study.example.yaml",
    ):
        assert f"rgraph/kit/{required}" in names, required
    for directory in ("schemas", "roles", "example-run", "template-run"):
        assert any(n.startswith(f"rgraph/kit/{directory}/") for n in names), directory
    assert any(n.endswith("licenses/LICENSE") for n in names)

    # Install the built artifact itself, not the checkout, and exercise the
    # generated console entry point. The subprocess borrows only the current
    # environment's already-tested dependencies, keeping this smoke test
    # offline; rgraph itself resolves from the newly installed wheel.
    venv = tmp_path / "venv"
    subprocess.run(
        [sys.executable, "-m", "venv", str(venv)],
        cwd=ROOT, check=True, capture_output=True,
    )
    bindir = venv / ("Scripts" if sys.platform == "win32" else "bin")
    python = bindir / ("python.exe" if sys.platform == "win32" else "python")
    subprocess.run(
        [str(python), "-m", "pip", "install", "--no-deps", str(wheel)],
        cwd=ROOT, check=True, capture_output=True,
    )
    command = bindir / ("rgraph.exe" if sys.platform == "win32" else "rgraph")
    result = subprocess.run(
        [str(command), "--help"], cwd=tmp_path, capture_output=True, text=True,
        check=False,
        env=dict(
            os.environ,
            PYTHONPATH=str(pathlib.Path(pytest.__file__).resolve().parent.parent),
        ),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Start here:  rgraph demo" in result.stdout


@pytest.mark.skipif(sys.platform == "win32", reason="the rig opens a POSIX terminal")
def test_ci_reaches_a_green_gate_only_the_way_a_person_could(tmp_path):
    """CI's newcomer path runs `decide` for real, and this is what carries it.

    `.github/at_a_terminal.py` is the one piece of that journey the suite does
    not otherwise execute, so a break there would surface as a hung or cryptic
    CI job rather than a failing test. Both halves are asserted, because the
    refusal is the guarantee and the rig is only allowed to work around it.
    """
    rig = ROOT / ".github" / "at_a_terminal.py"
    run = tmp_path / "run"
    assert main([*R, "--run", str(run), "init"]) == 0
    assert main([*R, "--run", str(run), "seal"]) == 0
    decide = [sys.executable, "-m", "rgraph", "--root", str(ROOT), "--no-banner",
              "--run", str(run), "decide", "H1", "--as", "CI Smoke Test"]

    piped = subprocess.run(decide, input="y\ny\n", cwd=ROOT, timeout=60,
                           capture_output=True, text=True, check=False)
    assert piped.returncode == 2
    assert not (run / "gates" / "H1.json").exists()

    at_a_terminal = subprocess.run(
        [sys.executable, str(rig), "y", "y", "--", *decide], cwd=ROOT, timeout=60,
        capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL,
    )
    assert at_a_terminal.returncode == 0, at_a_terminal.stdout + at_a_terminal.stderr
    assert main([*R, "--run", str(run), "check", "H1"]) == 0

    # A prompt the rig cannot answer has to end rather than wait, or a CI job
    # hangs to its own timeout instead of failing with a reason.
    unanswered = subprocess.run(
        [sys.executable, str(rig), "--", *decide], cwd=ROOT, timeout=60,
        capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL,
    )
    assert unanswered.returncode == 0
    assert "No decision has been recorded" in unanswered.stdout
