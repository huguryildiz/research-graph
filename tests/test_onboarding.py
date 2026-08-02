"""What a stranger runs, in the order they run it.

Every test here stands for a way the kit used to mislead someone arriving for
the first time. They are behavioural, not unit: each one drives the CLI the way
the README tells a newcomer to drive it.
"""

import json
import pathlib
import subprocess
import sys

import pytest

from rgraph.checks import resolve_doi
from rgraph.cli import main
from rgraph.commands.setup import propose, separation_warnings
from rgraph.config import load_kit

ROOT = pathlib.Path(__file__).resolve().parents[1]
R = ["--root", str(ROOT), "--no-banner"]


# ── the first real run ──────────────────────────────────────────────────────

def test_init_then_seal_then_h1_is_green(tmp_path):
    """Three commands, no hand-written JSON, and the first gate opens."""
    run = tmp_path / "run"
    assert main([*R, "--run", str(run), "init"]) == 0
    assert (run / "problem_spec.json").exists()
    assert (run / "governance_record.json").exists()
    assert main([*R, "--run", str(run), "seal"]) == 0
    assert main([*R, "--run", str(run), "check", "H1"]) == 0


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

def test_editing_a_body_without_resealing_is_caught(tmp_path, capsys):
    """The edit a human actually makes: change the file, leave the hash alone."""
    run = tmp_path / "run"
    main([*R, "--run", str(run), "init"])
    main([*R, "--run", str(run), "seal"])
    assert main([*R, "--run", str(run), "check", "H1"]) == 0
    capsys.readouterr()

    path = run / "problem_spec.json"
    document = json.loads(path.read_text())
    document["body"]["question"] = "A different question entirely."
    path.write_text(json.dumps(document, indent=2))  # content_hash untouched

    assert main([*R, "--run", str(run), "check", "H1"]) == 1
    assert "BODY EDITED AFTER HASHING" in capsys.readouterr().out


def test_sealing_the_edit_makes_the_gate_green_again(tmp_path):
    run = tmp_path / "run"
    main([*R, "--run", str(run), "init"])
    path = run / "problem_spec.json"
    document = json.loads(path.read_text())
    document["body"]["question"] = "A different question entirely."
    path.write_text(json.dumps(document, indent=2))
    assert main([*R, "--run", str(run), "check", "H1"]) == 1
    assert main([*R, "--run", str(run), "seal"]) == 0
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


def test_setup_will_not_write_when_it_cannot_ask(tmp_path, capsys, monkeypatch):
    _kit_copy(tmp_path)

    def no_terminal(*_):
        raise EOFError

    monkeypatch.setattr("builtins.input", no_terminal)
    assert main(["--root", str(tmp_path), "--no-banner", "setup", *PRESET]) == 2
    assert "--yes" in capsys.readouterr().out
    assert not (tmp_path / "assignment.yaml").exists()


def test_setup_backs_up_an_assignment_it_replaces(tmp_path):
    _kit_copy(tmp_path)
    mine = "reviewer:     {provider: grok, model: grok-5}\n"
    original = (ROOT / "assignment.example.yaml").read_text(encoding="utf-8") + mine
    (tmp_path / "assignment.yaml").write_text(original, encoding="utf-8")

    assert main(["--root", str(tmp_path), "--no-banner", "setup", "--yes", *PRESET]) == 0
    assert (tmp_path / "assignment.yaml.bak").read_text(encoding="utf-8") == original


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
