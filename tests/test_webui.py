import json
import pathlib
import threading
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

from rgraph.commands.check import load_for_run
from rgraph.config import Assignment
from rgraph.gates import evaluate_gate
from rgraph.runner import ExecutionResult
from rgraph.webui.actions import (
    ActionError, ApprovalStore, execute_approved, preview_challenge, preview_next,
    execute_revision, preview_revision, record_final_decision, record_human_decision,
)
from rgraph.webui.server import create_server
from rgraph.webui.views import BOUNDARY, state_view, trace_view

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(run_dir):
    return load_for_run(SimpleNamespace(root=str(ROOT), run=str(run_dir)))


def _request(url, path, *, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {}
    if body is not None:
        headers = {"Content-Type": "application/json", "X-RGraph-Token": token or ""}
    return urllib.request.urlopen(
        urllib.request.Request(url + path, data=data, headers=headers, method="POST" if data else "GET"),
        timeout=3,
    )


def test_state_view_exposes_contract_data_not_rendered_terminal_text(example_run):
    kit, run = _load(example_run)
    body = state_view(run, kit)
    assert body["boundary"] == BOUNDARY
    assert body["run"]["id"] == "rg-20260731-001"
    assert len(body["units"]) == 12
    assert len(body["gates"]) == 10
    assert len(body["artifacts"]) == 21
    assert body["next_action"]["kind"] == "review"
    assert body["gates"][0]["checks"]
    assert body["gates"][-1]["status"] == "AWAITING"


def test_trace_view_is_structured_and_keeps_the_reading_limit(example_run):
    kit, run = _load(example_run)
    body = trace_view(run, kit, "c-01")
    assert body["complete"] is True
    assert body["links"][0]["label"] == "manuscript.md"
    assert body["boundary"] == BOUNDARY


def test_human_decision_requires_exact_attestations_and_names_the_person(example_run):
    (example_run / "gates" / "H1.json").unlink()
    kit, run = _load(example_run)
    claims = list(kit.gates["H1"].proves)
    with pytest.raises(ActionError, match="do not match"):
        record_human_decision(run, kit, "H1", "Ada Researcher", [])

    result = record_human_decision(
        run, kit, "H1", "Ada Researcher",
        [{"claim": claim, "answered": "yes"} for claim in claims],
    )
    assert result["outcome"] == "pass"
    record = json.loads((example_run / "gates" / "H1.json").read_text())
    assert record["decided_by"] == {"role": "human", "identity": "human/Ada Researcher"}
    assert evaluate_gate(_load(example_run)[1], kit, "H1").status == "PASS"


def test_execution_approval_is_single_use_and_bound_to_the_plan(example_run, monkeypatch):
    kit, run = _load(example_run)
    approvals = ApprovalStore()
    preview = preview_next(run, kit, approvals, "u01")
    monkeypatch.setattr(
        "rgraph.webui.actions.execute_capture",
        lambda plan, verbose=False: ExecutionResult(0, "provider output"),
    )
    result = execute_approved(run, kit, approvals, "u01", preview["approval_token"])
    assert result["exit_code"] == 0
    with pytest.raises(ActionError, match="expired"):
        execute_approved(run, kit, approvals, "u01", preview["approval_token"])


def test_reviewer_preview_names_the_provider_and_binds_gate_inputs(example_run):
    (example_run / "gates" / "E1.json").unlink()
    kit, run = _load(example_run)
    kit.assignment["reviewer"] = Assignment("reviewer", "codex", "gpt-5.6-terra")
    body = preview_challenge(run, kit, ApprovalStore(), "E1")
    assert body["gate"] == "E1"
    assert body["provider"] == "codex"
    assert body["model"] == "gpt-5.6-terra"
    assert [item["id"] for item in body["inputs"]] == list(kit.gates["E1"].inputs)
    assert body["approval_token"]


def test_final_release_requires_boundary_acknowledgement_and_writes_manifest(example_run):
    kit, run = _load(example_run)
    with pytest.raises(ActionError, match="reading limit"):
        record_final_decision(run, kit, "Ada Researcher", "release", False)
    result = record_final_decision(run, kit, "Ada Researcher", "release", True)
    assert result["outcome"] == "release"
    manifest = json.loads((example_run / "release_manifest.json").read_text())
    assert manifest["body"]["not_established"] == ["Scientific correctness was not determined"]
    assert manifest["produced_by"]["identity"] == "human/Ada Researcher"
    assert json.loads((example_run / "gates" / "FINAL.json").read_text())["outcome"] == "release"


def test_revision_preview_and_execution_spend_exactly_one_attempt(example_run):
    record_path = example_run / "gates" / "E1.json"
    record = json.loads(record_path.read_text())
    record["outcome"] = "revise"
    record["reason"] = "evidence_gap"
    record_path.write_text(json.dumps(record))
    kit, run = _load(example_run)
    approvals = ApprovalStore()
    plan = preview_revision(run, kit, approvals, "E1")
    assert plan["return_to"] == "u01"
    before = plan["budget"]["used"]
    result = execute_revision(run, kit, approvals, "E1", plan["approval_token"])
    assert result["exit_code"] == 0
    assert result["budget"]["used"] == before + 1


def test_http_server_serves_ui_and_rejects_post_without_session_token(example_run):
    server, app = create_server(ROOT, example_run, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with _request(url, "/") as response:
            html = response.read().decode()
            assert "Research Graph · Evidence Desk" in html
            assert app.csrf_token in html
            assert response.headers["X-Frame-Options"] == "DENY"
        with _request(url, "/api/state") as response:
            assert json.load(response)["run"]["id"] == "rg-20260731-001"
        hostile = urllib.request.Request(url + "/api/state", headers={"Host": "attacker.example"})
        with pytest.raises(urllib.error.HTTPError) as refused_host:
            urllib.request.urlopen(hostile, timeout=3)
        assert refused_host.value.code == 403
        with pytest.raises(urllib.error.HTTPError) as refused:
            _request(url, "/api/check", body={"gate": "H1"})
        assert refused.value.code == 403
        with _request(url, "/api/check", token=app.csrf_token, body={"gate": "H1"}) as response:
            assert json.load(response)["gate"]["id"] == "H1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_server_refuses_non_loopback_binding(example_run):
    with pytest.raises(ValueError, match="loopback"):
        create_server(ROOT, example_run, host="0.0.0.0", port=0)
