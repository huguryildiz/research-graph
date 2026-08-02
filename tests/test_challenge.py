"""A challenge advances only after the assigned reviewer process actually ran."""

import json
import pathlib
import shutil

from rgraph.cli import main
from rgraph.config import load_kit
from rgraph.gates import evaluate_gate
from rgraph.hashing import document_hash
from rgraph.run import load_run
from rgraph.runner import ExecutionResult

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _recorded_kit(tmp_path: pathlib.Path) -> pathlib.Path:
    kit = tmp_path / "kit"
    kit.mkdir()
    for name in ("graph.yaml", "gates.yaml", "providers.yaml"):
        shutil.copy2(ROOT / name, kit / name)
    for name in ("schemas", "roles"):
        (kit / name).symlink_to(ROOT / name, target_is_directory=True)
    (kit / "assignment.yaml").write_text(
        "retrieval:    {provider: claude-code, model: claude-sonnet-5}\n"
        "planning:     {provider: claude-code, model: claude-opus-5}\n"
        "execution:    {provider: claude-code, model: claude-sonnet-5}\n"
        "verification: {provider: codex, model: gpt-5.6-terra}\n"
        "synthesis:    {provider: claude-code, model: claude-fable-5}\n"
        "reviewer:     {provider: codex, model: gpt-5.6-terra}\n",
        encoding="utf-8",
    )
    return kit


def _recorded_run(tmp_path: pathlib.Path, gate: str = "E1") -> pathlib.Path:
    run = tmp_path / "run"
    shutil.copytree(ROOT / "example-run", run)
    meta_path = run / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["provenance"] = "recorded"
    meta["content_hash"] = document_hash(meta)
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    (run / "gates" / f"{gate}.json").unlink()
    return run


def _decision(outcome="pass", reason=None):
    status = "PASS" if outcome == "pass" else "FAIL"
    return {
        "outcome": outcome,
        "reason": reason,
        "checks": [{
            "name": "artifact review",
            "status": status,
            "detail": "read every gate input against the declared contract",
        }],
        "findings": [] if outcome == "pass" else [{
            "ref": "evidence_matrix",
            "code": "EVIDENCE GAP",
            "detail": "one source claim lacks direct support",
            "fix": "add a directly located source or narrow the claim",
        }],
    }


def _fake_provider(monkeypatch, calls, decision=None, raw=None, mutate=None, exit_code=0):
    payload = raw
    if payload is None:
        payload = (
            "provider prelude\n<rgraph-decision>\n"
            + json.dumps(decision or _decision())
            + "\n</rgraph-decision>\n"
        )

    def execute(plan, *, verbose=False):
        calls.append(plan)
        plan.log_path.parent.mkdir(parents=True, exist_ok=True)
        plan.log_path.write_text(payload, encoding="utf-8")
        if mutate:
            mutate(plan)
        return ExecutionResult(exit_code, payload)

    monkeypatch.setattr("rgraph.commands.challenge.execute_capture", execute)


def _argv(kit, run, *tail):
    return ["--root", str(kit), "--run", str(run), "--no-banner", *tail]


def _isolate_assignment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty-config"))


def test_check_is_read_only_and_points_to_the_reviewer(tmp_path, capsys, monkeypatch):
    kit = _recorded_kit(tmp_path)
    run = _recorded_run(tmp_path)
    _isolate_assignment(tmp_path, monkeypatch)
    record = run / "gates" / "E1.json"

    assert main(_argv(kit, run, "check", "E1")) == 1
    out = capsys.readouterr().out
    assert "AWAITING" in out
    assert "rgraph challenge E1" in out
    assert not record.exists()


def test_active_producer_cannot_start_a_nested_reviewer(tmp_path, capsys, monkeypatch):
    kit = _recorded_kit(tmp_path)
    run = _recorded_run(tmp_path)
    _isolate_assignment(tmp_path, monkeypatch)
    monkeypatch.setenv("RGRAPH_ACTIVE_INVOCATION", "u02")

    assert main(_argv(kit, run, "challenge", "E1")) == 2
    out = capsys.readouterr().out
    assert "return" in out and "control to the host" in out
    assert not (run / "gates" / "E1.json").exists()


def test_challenge_runs_one_assigned_cli_and_binds_log_and_hashes(
    tmp_path, capsys, monkeypatch,
):
    kit = _recorded_kit(tmp_path)
    run = _recorded_run(tmp_path)
    _isolate_assignment(tmp_path, monkeypatch)
    calls = []
    _fake_provider(monkeypatch, calls)

    assert main(_argv(kit, run, "challenge", "E1")) == 0
    assert len(calls) == 1
    assert calls[0].argv == ["codex", "exec", "-c", "model=gpt-5.6-terra", "-"]
    assert "Do not edit, create, delete" in calls[0].stdin_text
    assert str((run / "evidence_matrix.json").resolve()) in calls[0].stdin_text

    record = json.loads((run / "gates" / "E1.json").read_text(encoding="utf-8"))
    assert record["decided_by"] == {
        "role": "reviewer", "identity": "codex/gpt-5.6-terra",
        "provider": "codex", "model": "gpt-5.6-terra",
    }
    assert [item["artifact_id"] for item in record["inputs"]] == [
        "search_protocol", "corpus_snapshot", "kg_snapshot", "evidence_matrix",
    ]
    provenance = record["decision_provenance"]
    assert provenance["provider"] == "codex"
    assert provenance["model"] == "gpt-5.6-terra"
    assert provenance["log"].startswith("logs/review-E1-")
    assert provenance["log"].endswith(".log")
    assert provenance["log_sha256"].startswith("sha256:")
    assert provenance["prompt"].startswith("logs/review-E1-")
    assert provenance["prompt"].endswith(".prompt.md")
    assert provenance["prompt_sha256"].startswith("sha256:")
    assert provenance["decision_sha256"].startswith("sha256:")
    assert "rgraph status" in capsys.readouterr().out


def test_explicit_run_uses_the_assignment_beside_that_study(
    tmp_path, capsys, monkeypatch,
):
    kit = _recorded_kit(tmp_path)
    study = tmp_path / "study"
    study.mkdir()
    run = _recorded_run(study)
    (study / "assignment.yaml").write_text(
        "retrieval: {provider: claude-code, model: study-producer}\n"
        "reviewer: {provider: codex, model: study-reviewer}\n",
        encoding="utf-8",
    )
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "assignment.yaml").write_text(
        "reviewer: {provider: codex, model: unrelated-reviewer}\n",
        encoding="utf-8",
    )
    _isolate_assignment(elsewhere, monkeypatch)
    calls = []
    _fake_provider(monkeypatch, calls)

    assert main(_argv(kit, run, "challenge", "E1")) == 0
    assert calls[0].argv == ["codex", "exec", "-c", "model=study-reviewer", "-"]
    record = json.loads((run / "gates" / "E1.json").read_text(encoding="utf-8"))
    assert record["decided_by"]["identity"] == "codex/study-reviewer"
    assert "codex/study-reviewer" in capsys.readouterr().out


def test_t2_uses_the_verification_assignment(tmp_path, monkeypatch):
    kit = _recorded_kit(tmp_path)
    run = _recorded_run(tmp_path, gate="T2")
    _isolate_assignment(tmp_path, monkeypatch)
    calls = []
    _fake_provider(monkeypatch, calls)

    assert main(_argv(kit, run, "challenge", "T2")) == 0
    assert len(calls) == 1
    assert calls[0].provider == "codex"
    assert calls[0].model == "gpt-5.6-terra"


def test_malformed_provider_output_is_exit_two_and_records_nothing(
    tmp_path, capsys, monkeypatch,
):
    kit = _recorded_kit(tmp_path)
    run = _recorded_run(tmp_path)
    _isolate_assignment(tmp_path, monkeypatch)
    calls = []
    _fake_provider(monkeypatch, calls, raw="not a decision")

    assert main(_argv(kit, run, "challenge", "E1")) == 2
    assert "contains no <rgraph-decision>" in capsys.readouterr().out
    assert not (run / "gates" / "E1.json").exists()


def test_reviewer_cannot_pass_a_failed_local_contract(tmp_path, capsys, monkeypatch):
    kit = _recorded_kit(tmp_path)
    run = _recorded_run(tmp_path)
    _isolate_assignment(tmp_path, monkeypatch)
    corpus = run / "corpus_snapshot.json"
    document = json.loads(corpus.read_text(encoding="utf-8"))
    document["body"]["sources"][0]["doi"] = None
    document["content_hash"] = document_hash(document)
    corpus.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    assert main(_argv(kit, run, "seal")) == 0
    calls = []
    _fake_provider(monkeypatch, calls, decision=_decision("pass"))

    assert main(_argv(kit, run, "challenge", "E1")) == 2
    assert "reviewer returned pass while local checks fail" in capsys.readouterr().out
    assert not (run / "gates" / "E1.json").exists()


def test_reviewer_run_boundary_modification_is_rejected(tmp_path, capsys, monkeypatch):
    kit = _recorded_kit(tmp_path)
    run = _recorded_run(tmp_path)
    _isolate_assignment(tmp_path, monkeypatch)
    calls = []

    def mutate(_plan):
        (run / "unexpected.json").write_text("{}\n", encoding="utf-8")

    _fake_provider(monkeypatch, calls, mutate=mutate)
    assert main(_argv(kit, run, "challenge", "E1")) == 2
    assert "modified the read-only run boundary" in capsys.readouterr().out
    assert not (run / "gates" / "E1.json").exists()


def test_tampered_provider_log_retires_the_decision(tmp_path, capsys, monkeypatch):
    kit = _recorded_kit(tmp_path)
    run = _recorded_run(tmp_path)
    _isolate_assignment(tmp_path, monkeypatch)
    calls = []
    _fake_provider(monkeypatch, calls)
    assert main(_argv(kit, run, "challenge", "E1")) == 0
    capsys.readouterr()

    record = json.loads((run / "gates" / "E1.json").read_text(encoding="utf-8"))
    (run / record["decision_provenance"]["log"]).write_text(
        "changed\n", encoding="utf-8",
    )
    assert main(_argv(kit, run, "check", "E1")) == 1
    out = capsys.readouterr().out
    assert "reviewer log no longer matches its recorded digest" in out
    assert "rgraph challenge E1" in out


def test_gate_outcome_cannot_disagree_with_the_captured_decision(
    tmp_path, capsys, monkeypatch,
):
    kit = _recorded_kit(tmp_path)
    run = _recorded_run(tmp_path)
    _isolate_assignment(tmp_path, monkeypatch)
    calls = []
    _fake_provider(monkeypatch, calls)
    assert main(_argv(kit, run, "challenge", "E1")) == 0
    capsys.readouterr()

    path = run / "gates" / "E1.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["outcome"] = "revise"
    record["reason"] = "evidence_gap"
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    assert main(_argv(kit, run, "check", "E1")) == 1
    out = capsys.readouterr().out
    assert "rgraph challenge E1" in out

    loaded_kit = load_kit(kit)
    result = evaluate_gate(load_run(run, loaded_kit), loaded_kit, "E1")
    decision = next(check for check in result.checks if check.name == "decision")
    assert decision.status == "FAIL"
    assert "gate outcome does not match the captured reviewer decision" in decision.detail
    assert "gate reason does not match the captured reviewer decision" in decision.detail


def test_codex_style_transcript_may_echo_prompt_and_repeat_one_decision(
    tmp_path, monkeypatch,
):
    kit = _recorded_kit(tmp_path)
    run = _recorded_run(tmp_path)
    _isolate_assignment(tmp_path, monkeypatch)
    valid = json.dumps(_decision())
    raw = (
        "user prompt\n<rgraph-decision>\n"
        '{"outcome":"pass|revise|block"}\n</rgraph-decision>\n'
        f"codex event\n<rgraph-decision>\n{valid}\n</rgraph-decision>\n"
        f"final output\n<rgraph-decision>\n{valid}\n</rgraph-decision>\n"
    )
    calls = []
    _fake_provider(monkeypatch, calls, raw=raw)

    assert main(_argv(kit, run, "challenge", "E1")) == 0
    assert (run / "gates" / "E1.json").exists()


def test_conflicting_valid_decision_blocks_are_rejected(tmp_path, capsys, monkeypatch):
    kit = _recorded_kit(tmp_path)
    run = _recorded_run(tmp_path)
    _isolate_assignment(tmp_path, monkeypatch)
    first = json.dumps(_decision())
    second = json.dumps(_decision("revise", "evidence_gap"))
    raw = (
        f"<rgraph-decision>\n{first}\n</rgraph-decision>\n"
        f"<rgraph-decision>\n{second}\n</rgraph-decision>\n"
    )
    calls = []
    _fake_provider(monkeypatch, calls, raw=raw)

    assert main(_argv(kit, run, "challenge", "E1")) == 2
    assert "conflicting valid decision blocks" in capsys.readouterr().out
    assert not (run / "gates" / "E1.json").exists()


def test_reviewer_replacing_a_stale_decision_sees_current_artifact_readiness(
    tmp_path, monkeypatch,
):
    kit = _recorded_kit(tmp_path)
    run = _recorded_run(tmp_path)
    _isolate_assignment(tmp_path, monkeypatch)
    calls = []
    _fake_provider(monkeypatch, calls)
    assert main(_argv(kit, run, "challenge", "E1")) == 0

    kg_path = run / "kg_snapshot.json"
    kg = json.loads(kg_path.read_text(encoding="utf-8"))
    kg["body"]["claims"][0]["text"] += " Revised."
    kg["content_hash"] = document_hash(kg)
    kg_path.write_text(json.dumps(kg, indent=2) + "\n", encoding="utf-8")
    matrix_path = run / "evidence_matrix.json"
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    next(ref for ref in matrix["inputs"] if ref["artifact_id"] == "kg_snapshot")[
        "content_hash"
    ] = kg["content_hash"]
    matrix["content_hash"] = document_hash(matrix)
    matrix_path.write_text(json.dumps(matrix, indent=2) + "\n", encoding="utf-8")

    assert main(_argv(kit, run, "challenge", "E1")) == 0
    assert len(calls) == 2
    assert "staleness: PASS" in calls[1].stdin_text
    assert "recorded decision inputs do not match" not in calls[1].stdin_text


def test_force_starts_one_fresh_review_when_the_current_gate_passes(
    tmp_path, monkeypatch,
):
    kit = _recorded_kit(tmp_path)
    run = _recorded_run(tmp_path)
    _isolate_assignment(tmp_path, monkeypatch)
    calls = []
    _fake_provider(monkeypatch, calls)

    assert main(_argv(kit, run, "challenge", "E1")) == 0
    first = json.loads((run / "gates" / "E1.json").read_text(encoding="utf-8"))
    assert main(_argv(kit, run, "challenge", "E1", "--force")) == 0

    assert len(calls) == 2
    second = json.loads((run / "gates" / "E1.json").read_text(encoding="utf-8"))
    assert first["decision_provenance"]["invocation_id"] != second[
        "decision_provenance"
    ]["invocation_id"]
    archived = list((run / "gates" / "history").glob("E1-*.json"))
    assert any(json.loads(path.read_text()) == first for path in archived)


def test_reviewer_reason_must_be_a_typed_return_from_that_gate(
    tmp_path, capsys, monkeypatch,
):
    kit = _recorded_kit(tmp_path)
    run = _recorded_run(tmp_path)
    _isolate_assignment(tmp_path, monkeypatch)
    calls = []
    _fake_provider(
        monkeypatch, calls,
        decision=_decision("revise", "claim_support_gap"),
    )

    assert main(_argv(kit, run, "challenge", "E1")) == 2
    out = capsys.readouterr().out
    assert "not a typed return from E1" in out
    assert "expected evidence_gap" in out
    assert not (run / "gates" / "E1.json").exists()
