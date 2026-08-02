"""What a stranger runs, in the order they run it.

Every test here stands for a way the kit used to mislead someone arriving for
the first time. They are behavioural, not unit: each one drives the CLI the way
the README tells a newcomer to drive it.
"""

import argparse
import json
import pathlib
import subprocess
import sys

import pytest

from rgraph.checks import resolve_doi
from rgraph.cli import main
from rgraph.commands.check import load
from rgraph.commands.setup import propose, separation_warnings
from rgraph.config import load_kit, machine_assignment_path

ROOT = pathlib.Path(__file__).resolve().parents[1]
R = ["--root", str(ROOT), "--no-banner"]


# ── the first real run ──────────────────────────────────────────────────────

def decide(run, monkeypatch, gate="H1", answers=("y", "y"), identity="Test Human"):
    """Answer a human gate the way a person at a terminal would."""
    replies = iter(answers)
    monkeypatch.setattr("builtins.input", lambda *_: next(replies))
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


def test_a_no_answer_sends_the_gate_back(tmp_path, monkeypatch):
    run = tmp_path / "run"
    main([*R, "--run", str(run), "init"])
    assert decide(run, monkeypatch, answers=("y", "n")) == 1

    record = json.loads((run / "gates" / "H1.json").read_text())
    assert record["outcome"] == "revise"
    assert record["attestation"]["answers"][1]["answered"] == "no"
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
    main([*R, "--run", str(run), "init"])
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
    assert "Sealed 0 artifact(s)." in capsys.readouterr().out


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
        "retrieval:    {provider: claude-code, model: sonnet-5}\n"
        "planning:     {provider: claude-code, model: sonnet-5}\n"
        "execution:    {provider: claude-code, model: sonnet-5}\n"
        "verification: {provider: claude-code, model: sonnet-5}\n"
        "synthesis:    {provider: claude-code, model: sonnet-5}\n"
        "reviewer:     {provider: claude-code, model: sonnet-5}\n"
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


def test_setup_writes_where_an_upgrade_cannot_delete_it(tmp_path, elsewhere):
    """Not into the installed package: `uv tool upgrade` replaces that whole tree."""
    _kit_copy(tmp_path)
    assert main(["--root", str(tmp_path), "--no-banner", "setup", "--yes", *PRESET]) == 0
    assert machine_assignment_path().exists()
    assert not (tmp_path / "assignment.yaml").exists()
    assert not (elsewhere / "assignment.yaml").exists()


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


def test_an_unreachable_doi_is_not_a_fabricated_one(monkeypatch):
    """Offline must never advise deleting a citation it could not check."""
    import urllib.error

    def offline(*_, **__):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr("urllib.request.urlopen", offline)
    assert resolve_doi("10.1109/lwc.2020.3019321") == "unreachable"


def test_online_e1_passes_when_the_network_is_gone(tmp_path, capsys, monkeypatch):
    import shutil
    import urllib.error

    run = tmp_path / "run"
    shutil.copytree(ROOT / "example-run", run)

    def offline(*_, **__):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr("urllib.request.urlopen", offline)
    assert main([*R, "--run", str(run), "check", "E1", "--online"]) == 0
    out = capsys.readouterr().out
    assert "could not be reached" in out
    assert "replace or remove" not in out


# ── the shipped fixture stays shipped ───────────────────────────────────────

def test_checking_the_committed_example_run_writes_nothing():
    before = (ROOT / "example-run" / "gates" / "M1.json").read_text(encoding="utf-8")
    assert main([*R, "--run", str(ROOT / "example-run"), "check", "M1"]) == 0
    assert (ROOT / "example-run" / "gates" / "M1.json").read_text(encoding="utf-8") == before


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
    for required in ("graph.yaml", "gates.yaml", "providers.yaml", "assignment.example.yaml"):
        assert f"rgraph/kit/{required}" in names, required
    for directory in ("schemas", "roles", "example-run", "template-run"):
        assert any(n.startswith(f"rgraph/kit/{directory}/") for n in names), directory
    assert any(n.endswith("licenses/LICENSE") for n in names)
