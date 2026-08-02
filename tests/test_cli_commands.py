import json
import pathlib
import subprocess

import pytest

from rgraph.cli import main
from rgraph.config import Assignment, load_kit
from rgraph.commands.setup import capability_conflicts, detect, parse_preset, propose
from rgraph.hashing import content_hash
from rgraph.run import load_run
from rgraph.runner import build_argv, build_plan

ROOT = pathlib.Path(__file__).resolve().parents[1]
R = ["--root", str(ROOT), "--no-banner"]


def _break_doi(run_dir: pathlib.Path) -> None:
    path = run_dir / "corpus_snapshot.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["body"]["sources"][0]["doi"] = None
    document["content_hash"] = content_hash(document["body"])
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")


def _kit():
    return load_kit(ROOT, assignment="assignment.example.yaml")


# ── check ──────────────────────────────────────────────────────────────────

def test_clean_gate_exits_zero_and_prints_the_boundary(example_run, capsys):
    assert main([*R, "--run", str(example_run), "check", "E1"]) == 0
    out = capsys.readouterr().out
    assert "GATE E1" in out and "PASS" in out
    assert "[----] Scientific correctness was not determined" in out


def test_broken_doi_makes_e1_red_and_exits_one(example_run, capsys):
    _break_doi(example_run)
    assert main([*R, "--run", str(example_run), "check", "E1"]) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out and "SOURCE NOT RESOLVED" in out
    assert "rgraph revise E1" in out


def test_unknown_gate_is_a_usage_error(example_run, capsys):
    assert main([*R, "--run", str(example_run), "check", "Z9"]) == 2


# ── status ─────────────────────────────────────────────────────────────────

def test_status_reproduces_the_spec_layout(example_run, capsys):
    assert main([*R, "--run", str(example_run), "status"]) == 0
    out = capsys.readouterr().out
    assert "RESEARCH RUN" in out
    assert "RETRIEVE ---> PLAN" in out and "---> WRITE" in out
    assert "gate:E1" in out and "human:H1" in out
    assert "12 units complete" in out
    assert "Artifacts" in out
    assert "contract-gated" not in out


def test_verbose_status_lists_every_unit(example_run, capsys):
    main([*R, "--run", str(example_run), "--verbose", "status"])
    out = capsys.readouterr().out
    for unit in ("u01", "u06", "u12"):
        assert unit in out


# ── trace ──────────────────────────────────────────────────────────────────

def test_trace_prints_an_unbroken_chain(example_run, capsys):
    main([*R, "--run", str(example_run), "check", "M1"])
    capsys.readouterr()
    assert main([*R, "--run", str(example_run), "trace", "c-01"]) == 0
    out = capsys.readouterr().out
    assert "CLAIM c-01" in out
    assert "+-- manuscript.md" in out
    assert "gates/M1.json" in out
    assert "Provenance chain is complete." in out
    assert "Scientific validity still requires human review." in out


def test_trace_of_a_missing_claim_exits_one(example_run, capsys):
    assert main([*R, "--run", str(example_run), "trace", "c-99"]) == 1
    assert "not in claim_evidence_map" in capsys.readouterr().out


# ── revise ─────────────────────────────────────────────────────────────────

def test_revise_after_a_failure_spends_one_attempt(example_run, capsys):
    _break_doi(example_run)
    main([*R, "--run", str(example_run), "check", "E1"])
    capsys.readouterr()
    assert main([*R, "--run", str(example_run), "revise", "E1"]) == 0
    out = capsys.readouterr().out
    assert "evidence_gap" in out and "u01" in out
    meta = json.loads((example_run / "meta.json").read_text())
    assert meta["revisions"]["E1"]["used"] == 1
    assert meta["history"][-1]["gate"] == "E1"


def test_revise_on_a_passed_gate_exits_one(example_run, capsys):
    main([*R, "--run", str(example_run), "check", "E1"])
    capsys.readouterr()
    assert main([*R, "--run", str(example_run), "revise", "E1"]) == 1
    assert "passed" in capsys.readouterr().out


def test_revise_beyond_the_budget_is_blocked(example_run, capsys):
    meta_path = example_run / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["revisions"]["E1"] = {"max": 3, "used": 3}
    meta_path.write_text(json.dumps(meta))
    assert main([*R, "--run", str(example_run), "revise", "E1"]) == 1
    assert "BLOCKED" in capsys.readouterr().out


# ── setup ──────────────────────────────────────────────────────────────────

def test_two_clis_maximise_separation():
    plan = propose(_kit(), {"claude-code": "FOUND", "codex": "FOUND", "grok": "WEB"})
    assert plan["reviewer"].provider != plan["execution"].provider


def test_one_cli_keeps_the_producers_on_it():
    plan = propose(_kit(), {"codex": "FOUND", "claude-code": "NOT INSTALLED"})
    assert plan["execution"].provider == "codex"


def test_web_provider_cannot_take_execution():
    plan = propose(_kit(), {"grok": "WEB", "codex": "FOUND"})
    assert plan["execution"].provider == "codex"
    assert plan["reviewer"].provider == "grok"


def test_capability_conflict_is_explained():
    messages = capability_conflicts(
        _kit(), {"execution": Assignment("execution", "grok", "grok-5")}
    )
    assert any("shell" in m and "grok" in m for m in messages)


def test_preset_parsing():
    assert parse_preset("producers=claude-code,reviewer=grok") == {
        "producers": "claude-code", "reviewer": "grok"}


@pytest.mark.parametrize("preset", ["foo=bar", "producers=", "reviewer=grok"])
def test_invalid_presets_are_usage_errors_not_tracebacks(tmp_path, preset):
    assert main([
        *R, "setup", "--preset", preset, "--yes", "--here",
    ]) == 2


def test_an_unknown_preset_provider_is_reported_not_raised(capsys):
    assert main([
        *R, "setup", "--preset", "producers=does-not-exist", "--yes", "--here",
    ]) == 1
    assert "unknown provider 'does-not-exist'" in capsys.readouterr().out


def test_detect_marks_absent_binaries(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr("rgraph.commands.setup.candidate_dirs", list)
    assert set(detect(_kit()).values()) <= {"NOT FOUND", "WEB"}


def test_a_cli_off_the_path_is_not_reported_as_missing(monkeypatch, tmp_path):
    """"Not installed" is a claim about the machine that `which` cannot make."""
    binary = tmp_path / "codex"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr("rgraph.commands.setup.candidate_dirs", lambda: [tmp_path])

    states = detect(_kit())
    assert states["codex"].startswith("NOT ON PATH — found at ")
    assert str(tmp_path) in states["codex"]
    # Nothing else lives there, so every other CLI keeps the honest verdict.
    assert states["gemini"] == "NOT FOUND"


def test_a_login_check_that_never_answers_is_not_called_a_logout(monkeypatch):
    """A timeout says the question went unanswered, not that the answer was no."""
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=5)

    monkeypatch.setattr("subprocess.run", timeout)
    assert detect(_kit())["claude-code"] == "FOUND (login unknown) — /usr/bin/claude"


def test_found_names_the_copy_that_answered(monkeypatch):
    """Two installs on one PATH is how a run lands on a version nobody chose."""
    monkeypatch.setattr("shutil.which", lambda name: f"/opt/homebrew/bin/{name}")
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: subprocess.CompletedProcess(args=a, returncode=0),
    )
    states = detect(_kit())
    assert states["claude-code"] == "FOUND — /opt/homebrew/bin/claude"
    # sakana borrows codex's binary, and the screen is where that becomes visible.
    assert states["sakana"] == "FOUND — /opt/homebrew/bin/codex"


# ── next / runner ──────────────────────────────────────────────────────────

def test_plan_builds_the_verified_codex_call(example_run):
    kit = _kit()
    plan = build_plan(load_run(example_run, kit), kit, "u08")
    assert plan.argv == ["codex", "exec", "-c", "model=gpt-5.6-terra", "-"]
    assert plan.stdin_text.startswith("# research-graph context")
    assert "run/reproduction_report.json" in plan.stdin_text


def test_plan_builds_the_verified_claude_call(example_run):
    kit = _kit()
    plan = build_plan(load_run(example_run, kit), kit, "u06")
    assert plan.argv == ["claude", "-p", "--model", "claude-sonnet-5"]


def test_an_unasked_effort_leaves_the_command_line_as_it_was(example_run):
    """`{effort_argv}` is a slot, not a flag: no effort, no trace of it."""
    kit = _kit()
    plan = build_plan(load_run(example_run, kit), kit, "u08")
    assert "{effort_argv}" not in plan.argv
    assert "model_reasoning_effort" not in " ".join(plan.argv)


def test_effort_lands_where_the_provider_says_and_not_at_the_end():
    """codex reads the prompt from a trailing `-`; flags appended after it are lost."""
    kit = load_kit(ROOT)
    argv = build_argv(kit.providers["codex"],
                      Assignment("verification", "codex", "gpt-5.6-terra", "xhigh"))
    assert argv == ["codex", "exec", "-c", "model=gpt-5.6-terra",
                    "-c", "model_reasoning_effort=xhigh", "-"]
    assert argv[-1] == "-"


def test_next_shows_the_inventory_and_executes_nothing(example_run, capsys, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "S")
    called = []
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: called.append(a))
    assert main([*R, "--run", str(example_run), "next", "--unit", "u06"]) == 0
    out = capsys.readouterr().out
    assert "No command has been executed." in out
    assert "[E] Execute   [D] Dry run   [S] Stop" in out
    assert "Will produce" in out and "Required gate" in out
    assert called == []


def test_next_rejects_an_unknown_unit(example_run, capsys):
    assert main([
        *R, "--run", str(example_run), "next", "--unit", "does-not-exist",
    ]) == 2
    assert "unknown unit 'does-not-exist'" in capsys.readouterr().out


def test_dry_run_prints_the_command_without_running_it(example_run, capsys, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "D")
    called = []
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: called.append(a))
    assert main([*R, "--run", str(example_run), "next", "--unit", "u06"]) == 0
    assert "claude -p" in capsys.readouterr().out
    assert called == []


def test_execute_runs_exactly_one_subprocess(example_run, monkeypatch):
    kit = _kit()
    plan = build_plan(load_run(example_run, kit), kit, "u06")
    calls = []

    class FakeProcess:
        returncode = 0

        def __init__(self):
            self.stdin = _FakeStdin()
            self.stdout = iter(["done\n"])

        def wait(self):
            return 0

    class _FakeStdin:
        def write(self, _text):
            return None

        def close(self):
            return None

    monkeypatch.setattr("subprocess.Popen", lambda argv, **kw: calls.append(argv) or FakeProcess())
    from rgraph.runner import execute

    assert execute(plan) == 0
    assert len(calls) == 1
    assert plan.log_path.exists()


# ── review ─────────────────────────────────────────────────────────────────

def test_review_reports_and_writes_a_manifest(example_run, capsys):
    assert main([*R, "--run", str(example_run), "review", "--outcome", "release"]) == 0
    out = capsys.readouterr().out
    assert "RUN COMPLETE" in out
    assert "Units         12 / 12 complete" in out
    assert "Human release NOT APPROVED" in out
    manifest = json.loads((example_run / "release_manifest.json").read_text())
    assert manifest["body"]["outcome"] == "release"
    assert "Scientific correctness was not determined" in manifest["body"]["not_established"]
    assert (example_run / "gates" / "FINAL.json").exists()


def test_release_manifest_validates_against_its_schema(example_run):
    from rgraph.schemas import registry

    main([*R, "--run", str(example_run), "review", "--outcome", "release"])
    document = json.loads((example_run / "release_manifest.json").read_text())
    assert registry(ROOT).validate("release_manifest", document) == []


def test_stop_outcome_exits_one(example_run):
    assert main([*R, "--run", str(example_run), "review", "--outcome", "stop"]) == 1


# ── demo ───────────────────────────────────────────────────────────────────

def test_demo_runs_three_scenarios_and_exits_one(capsys):
    assert main([*R, "demo"]) == 1
    out = capsys.readouterr().out
    assert "SCENARIO 1" in out and "SCENARIO 2" in out and "SCENARIO 3" in out
    assert "SOURCE NOT RESOLVED" in out
    assert "STALE CHAIN DETECTED" in out
    assert "Invalidated: M1, T2, V1" in out


def test_demo_leaves_the_committed_example_untouched():
    target = ROOT / "example-run" / "corpus_snapshot.json"
    before = target.read_bytes()
    main([*R, "demo"])
    assert target.read_bytes() == before


def test_single_scenario_selection():
    assert main([*R, "demo", "--scenario", "1"]) == 0
