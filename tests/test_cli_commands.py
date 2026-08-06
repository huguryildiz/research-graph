import json
import pathlib
import subprocess

import pytest

from rgraph.cli import main
from rgraph.config import Assignment, load_kit
from rgraph.commands.setup import capability_conflicts, detect, parse_preset, propose
from rgraph.gates import evaluate_gate, record_from
from rgraph.hashing import document_hash
from rgraph.run import load_run
from rgraph.runner import build_argv, build_plan
from rgraph.schemas import registry
from rgraph.workflow import next_action

ROOT = pathlib.Path(__file__).resolve().parents[1]
R = ["--root", str(ROOT), "--no-banner"]


def _break_doi(run_dir: pathlib.Path) -> None:
    path = run_dir / "corpus_snapshot.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["body"]["sources"][0]["doi"] = None
    document["content_hash"] = document_hash(document)
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
    assert "rgraph challenge E1" in out


def test_unknown_gate_is_a_usage_error(example_run, capsys):
    assert main([*R, "--run", str(example_run), "check", "Z9"]) == 2


# ── status ─────────────────────────────────────────────────────────────────

def test_status_reproduces_the_spec_layout(example_run, capsys):
    assert main([*R, "--run", str(example_run), "status"]) == 0
    out = capsys.readouterr().out
    assert "RESEARCH RUN" in out
    assert "RETRIEVE ─── PLAN" in out and "─── WRITE" in out
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
    assert "CLAIM\n    c-01" in out
    assert "+-- manuscript.md" in out
    assert "gates/M1.json" in out
    assert "Provenance chain is complete." in out
    assert "Scientific validity still requires human review." in out
    assert "NEXT ACTION" in out and "$ rgraph status" in out


def test_trace_of_a_missing_claim_exits_one(example_run, capsys):
    assert main([*R, "--run", str(example_run), "trace", "c-99"]) == 1
    assert "not in claim_evidence_map" in capsys.readouterr().out


# ── revise ─────────────────────────────────────────────────────────────────

def test_revise_after_a_failure_spends_one_attempt(example_run, capsys):
    _break_doi(example_run)
    kit = _kit()
    run = load_run(example_run, kit)
    result = evaluate_gate(run, kit, "E1", require_decision=False)
    record = record_from(result, run, kit)
    record["outcome"] = "revise"
    record["reason"] = "evidence_gap"
    run.write_gate_record(record)
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
    # The screen abbreviates a path under $HOME, which on Windows is where the
    # temporary directory lives. Compare where it points, not how it reads.
    reported = states["codex"].removeprefix("NOT ON PATH — found at ")
    assert pathlib.Path(reported).expanduser() == tmp_path
    # Nothing else lives there, so every other CLI keeps the honest verdict.
    assert states["gemini"] == "NOT FOUND"


def test_a_login_check_that_never_answers_is_not_called_a_logout(monkeypatch):
    """A timeout says the question went unanswered, not that the answer was no."""
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=5)

    monkeypatch.setattr("subprocess.run", timeout)
    # The path is rendered by pathlib, so the separator is the platform's.
    where = pathlib.Path("/usr/bin/claude")
    assert detect(_kit())["claude-code"] == f"FOUND (login unknown) — {where}"


def test_found_names_the_copy_that_answered(monkeypatch):
    """Two installs on one PATH is how a run lands on a version nobody chose."""
    monkeypatch.setattr("shutil.which", lambda name: f"/opt/homebrew/bin/{name}")
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: subprocess.CompletedProcess(args=a, returncode=0),
    )
    states = detect(_kit())
    assert states["claude-code"] == f"FOUND — {pathlib.Path('/opt/homebrew/bin/claude')}"
    # sakana borrows codex's binary, and the screen is where that becomes visible.
    assert states["sakana"] == f"FOUND — {pathlib.Path('/opt/homebrew/bin/codex')}"


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
    assert "must not be used to refuse or skip" in plan.stdin_text
    assert "invoke check, challenge, decide, or review" in plan.stdin_text
    assert f"schema directory : {ROOT.resolve()}/schemas" in plan.stdin_text
    assert "never calculate or edit content_hash values yourself" in plan.stdin_text
    assert f'"{pathlib.Path(__import__("sys").executable).absolute()}" -m rgraph' in plan.stdin_text
    assert "do not substitute another rgraph executable" in plan.stdin_text
    assert plan.cwd == example_run.parent


def test_plan_preserves_the_active_virtualenv_entrypoint(example_run, monkeypatch, tmp_path):
    python = tmp_path / "linked-venv" / "bin" / "python"
    monkeypatch.setattr("rgraph.runner.sys.executable", str(python))
    plan = build_plan(load_run(example_run, _kit()), _kit(), "u06")
    assert f'"{python.absolute()}" -m rgraph' in plan.stdin_text


def test_revision_plan_carries_the_gate_finding_to_the_returned_unit(example_run):
    kit = _kit()
    run = load_run(example_run, kit)
    run.meta["history"].append({
        "at": "2026-08-02T00:00:00Z",
        "gate": "E1",
        "outcome": "revise",
        "reason": "evidence_gap",
        "to": "u01",
    })
    record = run.gate_record("E1")
    record["outcome"] = "revise"
    record["reason"] = "evidence_gap"
    record["findings"] = [{
        "ref": "evidence_matrix:c-04",
        "code": "SOURCE GAP",
        "detail": "the cited locator does not support the lineage claim",
        "fix": "add a direct source or narrow the claim",
    }]
    (example_run / "gates" / "E1.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8",
    )

    plan = build_plan(run, kit, "u01")
    assert "returned by gate: E1" in plan.stdin_text
    assert "typed reason: evidence_gap" in plan.stdin_text
    assert "the cited locator does not support the lineage claim" in plan.stdin_text
    assert "add a direct source or narrow the claim" in plan.stdin_text
    assert "do not edit the gate record" in plan.stdin_text

    next_same_role = build_plan(run, kit, "u02")
    assert "returned by gate: E1" in next_same_role.stdin_text
    assert "the cited locator does not support the lineage claim" in next_same_role.stdin_text

    next_other_role = build_plan(run, kit, "u03")
    assert "returned by gate: E1" not in next_other_role.stdin_text


def test_replacing_a_gate_record_archives_the_exact_previous_record(example_run):
    run = load_run(example_run, _kit())
    previous_path = example_run / "gates" / "E1.json"
    previous = previous_path.read_bytes()
    replacement = json.loads(previous)
    replacement["outcome"] = "revise"
    replacement["reason"] = "evidence_gap"

    run.write_gate_record(replacement)

    archived = list((example_run / "gates" / "history").glob("E1-*.json"))
    assert len(archived) == 1
    assert archived[0].read_bytes() == previous
    assert run.gate_record("E1")["outcome"] == "revise"


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
    assert "1  Execute" in out and "2  Dry run" in out and "3  Stop" in out
    assert "WILL PRODUCE" in out and "NEXT CHECKPOINT" in out
    assert called == []


def test_provider_exit_zero_without_declared_output_changes_is_not_success(
    example_run, capsys, monkeypatch,
):
    monkeypatch.setattr("rgraph.commands.next_.execute", lambda *a, **k: 0)

    assert main([
        *R, "--run", str(example_run), "next", "--unit", "u06", "--execute",
    ]) == 1
    out = capsys.readouterr().out
    assert "changed none of the declared outputs" in out
    assert "unit was not accepted" in out
    assert not (example_run / "logs" / ".locks" / "u06.lock").exists()


def test_concurrent_unit_execution_is_rejected_before_provider_call(
    example_run, capsys, monkeypatch,
):
    lock = example_run / "logs" / ".locks" / "u06.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text('{"pid": 123}\n', encoding="utf-8")
    called = []
    monkeypatch.setattr(
        "rgraph.commands.next_.execute", lambda *a, **k: called.append(True) or 0
    )

    assert main([
        *R, "--run", str(example_run), "next", "--unit", "u06", "--execute",
    ]) == 1
    assert "already executing" in capsys.readouterr().out
    assert called == []


def test_output_timestamp_must_match_provider_invocation_window(example_run):
    from rgraph.commands.next_ import _output_problems, _output_state, _run_boundary_state

    kit = _kit()
    run = load_run(example_run, kit)
    unit = kit.graph.node("u06")
    problems = _output_problems(
        run,
        kit,
        unit,
        _output_state(run, unit.produces),
        _run_boundary_state(run.root),
        started_at="2026-07-31T08:00:00Z",
        finished_at="2026-07-31T08:10:00Z",
    )
    assert any("produced_at" in problem and "invocation window" in problem
               for problem in problems)


def test_provider_change_outside_declared_unit_outputs_is_rejected(
    example_run, capsys, monkeypatch,
):
    def change_unrelated(_plan, **_kwargs):
        (example_run / "unexpected.txt").write_text("changed\n", encoding="utf-8")
        return 0

    monkeypatch.setattr("rgraph.commands.next_.execute", change_unrelated)

    assert main([
        *R, "--run", str(example_run), "next", "--unit", "u06", "--execute",
    ]) == 1
    assert "outside the declared unit outputs: unexpected.txt" in capsys.readouterr().out
    receipt = json.loads((example_run / "executions" / "u06.json").read_text())
    assert receipt["outcome"] == "rejected"
    assert any("unexpected.txt" in problem for problem in receipt["problems"])
    kit = _kit()
    from rgraph.workflow import next_action

    action = next_action(load_run(example_run, kit), kit)
    assert (action.kind, action.target) == ("unit", "u06")


def test_hash_bound_data_manifest_sidecar_is_an_allowed_unit_output(example_run):
    from rgraph.commands.next_ import _manifest_sidecars

    payload = example_run / "data" / "fresh-dataset.bin"
    payload.write_bytes(b"real dataset bytes\n")
    manifest_path = example_run / "data_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    dataset = manifest["body"]["datasets"][0]
    dataset.update({
        "path": "data/fresh-dataset.bin",
        "sha256": __import__("hashlib").sha256(payload.read_bytes()).hexdigest(),
        "bytes": payload.stat().st_size,
    })
    manifest["content_hash"] = document_hash(manifest)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    kit = _kit()
    run = load_run(example_run, kit)
    allowed, problems = _manifest_sidecars(run, kit.graph.node("u06"))
    assert allowed == {"data/fresh-dataset.bin"}
    assert problems == []


def test_hash_bound_code_commit_sidecar_is_an_allowed_unit_output(example_run):
    from rgraph.commands.next_ import _code_sidecars

    allowed, problems = _code_sidecars(
        load_run(example_run, _kit()), _kit().graph.node("u06")
    )
    assert "code/estimator_bench.py" in allowed
    assert problems == []


def test_v2_code_commit_bundle_is_an_allowed_verified_output(example_run, tmp_path):
    import hashlib
    import subprocess

    from rgraph.commands.next_ import _code_sidecars

    source = example_run / "code" / "estimator_bench.py"
    repo = tmp_path / "source-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test Author"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
    (repo / "estimator_bench.py").write_bytes(source.read_bytes())
    subprocess.run(["git", "add", "estimator_bench.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "Retain source"], cwd=repo, check=True)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    bundle = example_run / "code" / "source.bundle"
    subprocess.run(["git", "bundle", "create", str(bundle), "--all"], cwd=repo, check=True)
    path = example_run / "code_commit.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["version"] = 2
    document["body"].update({
        "repo": "retained-test-source",
        "commit": commit,
        "dirty": False,
        "bundle_path": "code/source.bundle",
        "bundle_sha256": "sha256:" + hashlib.sha256(bundle.read_bytes()).hexdigest(),
    })
    document["body"]["files"][0]["repo_path"] = "estimator_bench.py"
    document["content_hash"] = document_hash(document)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    allowed, problems = _code_sidecars(
        load_run(example_run, _kit()), _kit().graph.node("u06")
    )
    assert allowed == {"code/estimator_bench.py", "code/source.bundle"}
    assert problems == []


def test_hash_bound_environment_lock_sidecar_is_an_allowed_unit_output(example_run):
    from rgraph.commands.next_ import _environment_sidecars

    lock = example_run / "environment" / "requirements.lock"
    lock.parent.mkdir()
    lock.write_text("numpy==2.5.1\n", encoding="utf-8")
    path = example_run / "environment_lock.json"
    document = json.loads(path.read_text())
    document["version"] = 2
    document["body"]["lock_path"] = "environment/requirements.lock"
    document["body"]["lock_sha256"] = __import__("hashlib").sha256(
        lock.read_bytes()
    ).hexdigest()
    document["content_hash"] = document_hash(document)
    path.write_text(json.dumps(document, indent=2) + "\n")

    allowed, problems = _environment_sidecars(
        load_run(example_run, _kit()), _kit().graph.node("u06")
    )
    assert allowed == {"environment/requirements.lock"}
    assert problems == []


def test_hash_bound_run_config_sidecars_are_allowed_unit_outputs(example_run):
    from rgraph.commands.next_ import _configuration_sidecars

    config = example_run / "config" / "evaluation.json"
    config.parent.mkdir()
    config.write_text('{"block":"evaluation"}\n', encoding="utf-8")
    digest = __import__("hashlib").sha256(config.read_bytes()).hexdigest()
    path = example_run / "run_manifest.json"
    document = json.loads(path.read_text())
    document["version"] = 2
    document["inputs"].extend([
        {
            "artifact_id": artifact_id,
            "content_hash": json.loads(
                (example_run / f"{artifact_id}.json").read_text()
            )["content_hash"],
        }
        for artifact_id in ("environment_lock", "data_manifest")
    ])
    document["body"]["configurations"] = [{
        "config_id": "evaluation",
        "path": "config/evaluation.json",
        "sha256": digest,
        "argv": ["python", "code/estimator_bench.py", "--config", "config/evaluation.json"],
    }]
    for item in document["body"]["runs"]:
        item["config_sha256"] = digest
    document["content_hash"] = document_hash(document)
    path.write_text(json.dumps(document, indent=2) + "\n")

    allowed, problems = _configuration_sidecars(
        load_run(example_run, _kit()), _kit().graph.node("u07")
    )
    assert allowed == {"config/evaluation.json"}
    assert problems == []


def test_hash_bound_figure_script_is_an_allowed_unit_output(example_run):
    from rgraph.commands.next_ import _figure_sidecars

    allowed, problems = _figure_sidecars(
        load_run(example_run, _kit()), _kit().graph.node("u11")
    )
    assert allowed == {"code/plot_mse.py"}
    assert problems == []


def test_figure_script_digest_mismatch_is_rejected(example_run):
    from rgraph.commands.next_ import _figure_sidecars

    (example_run / "code" / "plot_mse.py").write_text("changed\n", encoding="utf-8")
    _, problems = _figure_sidecars(
        load_run(example_run, _kit()), _kit().graph.node("u11")
    )
    assert problems == [
        "figure_registry: script digest does not match: code/plot_mse.py"
    ]


def test_retired_run_ids_make_replacement_output_unacceptable(example_run):
    from rgraph.commands.next_ import _configuration_sidecars

    run = load_run(example_run, _kit())
    run.meta["retired_run_ids"] = [
        item["run_id"] for item in run.get("run_manifest").body["runs"]
    ]
    run.save_meta()
    _, problems = _configuration_sidecars(
        load_run(example_run, _kit()), _kit().graph.node("u07")
    )
    assert any("reuses 20 retired run_id" in problem for problem in problems)


def test_payload_preservation_detects_run_or_result_changes(example_run):
    from rgraph.commands.next_ import (
        _campaign_preservation_problems, _campaign_preservation_state,
    )

    kit = _kit()
    run = load_run(example_run, kit)
    before = _campaign_preservation_state(run)
    path = example_run / "run_manifest.json"
    document = json.loads(path.read_text())
    document["body"]["runs"][0]["run_id"] = "replacement_041"
    document["content_hash"] = document_hash(document)
    path.write_text(json.dumps(document, indent=2) + "\n")
    problems = _campaign_preservation_problems(before, load_run(example_run, kit))
    assert "preserve-payload mode: provider changed run ID set" in problems
    assert "preserve-payload mode: provider changed run_manifest body" in problems


def test_payload_preservation_option_is_u07_only(example_run, capsys):
    assert main([
        *R, "--run", str(example_run), "next", "--unit", "u06",
        "--dry-run", "--preserve-payload",
    ]) == 2
    assert "valid only for unit u07" in capsys.readouterr().out


def test_code_commit_cannot_bind_a_nested_environment(example_run):
    from rgraph.commands.next_ import _code_sidecars

    path = example_run / "code_commit.json"
    document = json.loads(path.read_text())
    document["body"]["files"][0]["path"] = "code/.venv/bin/python"
    document["body"]["entrypoint"] = "code/.venv/bin/python"
    document["content_hash"] = document_hash(document)
    path.write_text(json.dumps(document, indent=2) + "\n")

    allowed, problems = _code_sidecars(
        load_run(example_run, _kit()), _kit().graph.node("u06")
    )
    assert allowed == set()
    assert any("reserved environment directories" in problem for problem in problems)


def test_data_manifest_cannot_hide_a_path_outside_run_data(example_run):
    from rgraph.commands.next_ import _manifest_sidecars

    manifest_path = example_run / "data_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["body"]["datasets"][0]["path"] = "../unexpected.txt"
    manifest["content_hash"] = document_hash(manifest)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    kit = _kit()
    allowed, problems = _manifest_sidecars(
        load_run(example_run, kit), kit.graph.node("u06")
    )
    assert allowed == set()
    assert any("must stay below run/data" in problem for problem in problems)


def test_next_rejects_an_unknown_unit(example_run, capsys):
    assert main([
        *R, "--run", str(example_run), "next", "--unit", "does-not-exist",
    ]) == 2
    assert "unknown unit 'does-not-exist'" in capsys.readouterr().out


def test_dry_run_prints_the_command_without_running_it(example_run, capsys, monkeypatch):
    called = []
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: called.append(a))
    assert main([
        *R, "--run", str(example_run), "next", "--unit", "u07", "--dry-run",
    ]) == 0
    out = capsys.readouterr().out
    assert "claude -p" in out
    assert "CHOOSE NEXT" not in out
    assert "raw_results.meta.json" in out
    assert "raw_results.json" not in out
    assert called == []


def test_execute_runs_exactly_one_subprocess(example_run, monkeypatch):
    kit = _kit()
    plan = build_plan(load_run(example_run, kit), kit, "u06")
    calls = []
    python = example_run.parent / "linked-venv" / "bin" / "python"
    monkeypatch.setattr("rgraph.runner.sys.executable", str(python))

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

    monkeypatch.setattr(
        "subprocess.Popen", lambda argv, **kw: calls.append((argv, kw)) or FakeProcess()
    )
    from rgraph.runner import execute

    assert execute(plan) == 0
    assert len(calls) == 1
    assert calls[0][0] == plan.argv
    assert calls[0][1]["env"]["RGRAPH_ACTIVE_INVOCATION"] == "u06"
    assert calls[0][1]["env"]["PATH"].split(__import__("os").pathsep)[0] == str(
        python.absolute().parent
    )
    assert plan.log_path.exists()


# ── review ─────────────────────────────────────────────────────────────────

def test_review_reports_and_writes_a_manifest(example_run, capsys, monkeypatch):
    monkeypatch.setattr("rgraph.commands.review.is_terminal", lambda: True)
    assert main([
        *R, "--run", str(example_run), "review", "--outcome", "release",
        "--as", "Test Reviewer",
    ]) == 0
    out = capsys.readouterr().out
    assert "RUN COMPLETE" in out
    assert "Units          12 / 12 complete" in out
    assert "Human release" in out and "NOT APPROVED" in out
    manifest = json.loads((example_run / "release_manifest.json").read_text())
    assert manifest["body"]["outcome"] == "release"
    assert manifest["body"]["decided_by"] == "human/Test Reviewer"
    assert manifest["produced_by"]["identity"] == "human/Test Reviewer"
    assert "Scientific correctness was not determined" in manifest["body"]["not_established"]
    assert (example_run / "gates" / "FINAL.json").exists()


def test_release_manifest_validates_against_its_schema(example_run, monkeypatch):
    monkeypatch.setattr("rgraph.commands.review.is_terminal", lambda: True)
    main([
        *R, "--run", str(example_run), "review", "--outcome", "release",
        "--as", "Test Reviewer",
    ])
    document = json.loads((example_run / "release_manifest.json").read_text())
    assert registry(ROOT).validate("release_manifest", document) == []
    record = json.loads((example_run / "gates" / "FINAL.json").read_text())
    assert registry(ROOT).validate("gate_record", record) == []


def test_stop_outcome_exits_one(example_run, monkeypatch):
    monkeypatch.setattr("rgraph.commands.review.is_terminal", lambda: True)
    assert main([
        *R, "--run", str(example_run), "review", "--outcome", "stop",
        "--as", "Test Reviewer",
    ]) == 1


@pytest.mark.parametrize(("outcome", "target"), [("revise", "u11"), ("narrow", "u04")])
def test_terminal_preselected_review_routes_without_writing_a_release(
    example_run, capsys, monkeypatch, outcome, target,
):
    monkeypatch.setattr("rgraph.commands.review.is_terminal", lambda: True)
    assert main([
        *R, "--run", str(example_run), "review", "--outcome", outcome,
        "--as", "Test Reviewer",
    ]) == 1
    out = capsys.readouterr().out
    assert "No release manifest was written" in out
    assert f"rgraph next --unit {target}" in out
    assert not (example_run / "release_manifest.json").exists()

    record = json.loads((example_run / "gates" / "FINAL.json").read_text())
    assert registry(ROOT).validate("gate_record", record) == []
    assert record["outcome"] == outcome
    assert record["decided_by"]["identity"] == "human/Test Reviewer"
    assert record["revision_budget"]["used"] == 1
    action = next_action(load_run(example_run, _kit()), _kit())
    assert action.command == f"rgraph next --unit {target}"


# ── demo ───────────────────────────────────────────────────────────────────

def test_demo_runs_three_scenarios_and_exits_one(capsys):
    assert main([*R, "demo"]) == 1
    out = capsys.readouterr().out
    assert "SCENARIO 1" in out and "SCENARIO 2" in out and "SCENARIO 3" in out
    assert "SOURCE NOT RESOLVED" in out
    assert "STALE CHAIN DETECTED" in out
    assert "Invalidated: M1, T2, V1" in out
    assert "Exit code 1 is the expected result" in out
    assert "Your installation is fine" in out
    assert "rgraph demo --scenario 1" in out
    assert "rgraph revise E1" not in out


def test_demo_leaves_the_committed_example_untouched():
    target = ROOT / "example-run" / "corpus_snapshot.json"
    before = target.read_bytes()
    main([*R, "demo"])
    assert target.read_bytes() == before


def test_single_scenario_selection(capsys):
    assert main([*R, "demo", "--scenario", "1"]) == 0
    out = capsys.readouterr().out
    assert "Artifact presence and JSON Schema" in out
    assert "SHA-256 provenance and stale-input detection" in out
    assert "Recorded producer/reviewer separation" in out
    assert "Scientific correctness was not determined" in out
    assert "NEXT ACTION" in out and "$ rgraph setup" in out
