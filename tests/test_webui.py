import json
import pathlib
import re
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

from rgraph.cli import main
from rgraph.commands.check import load_for_run
from rgraph.config import Assignment
from rgraph.gates import evaluate_gate
from rgraph.runner import ExecutionResult
from rgraph.webui.actions import (
    ActionError, ApprovalStore, execute_approved, preview_challenge, preview_next,
    execute_revision, preview_revision,
)
import rgraph.webui.server as webui_server
from rgraph.webui.server import create_server
from rgraph.webui.views import BOUNDARY, state_view, trace_view

ROOT = pathlib.Path(__file__).resolve().parents[1]
R = ["--root", str(ROOT), "--no-banner"]


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
            assert '<link rel="icon" type="image/svg+xml" href="/icon.svg">' in html
            assert response.headers["X-Frame-Options"] == "DENY"
        with _request(url, "/icon.svg") as response:
            assert response.headers["Content-Type"] == "image/svg+xml"
            assert b"research-graph mark" in response.read()
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


def test_removed_decision_routes_leave_a_clean_human_gate_awaiting(tmp_path):
    run_dir = tmp_path / "run"
    assert main([*R, "--run", str(run_dir), "init"]) == 0
    assert main([*R, "--run", str(run_dir), "seal"]) == 0
    kit, run = _load(run_dir)
    assert evaluate_gate(run, kit, "H1").status == "AWAITING"
    before = {path.name for path in (run_dir / "gates").glob("*.json")}

    server, app = create_server(ROOT, run_dir, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        attempts = (
            ("/api/decide", {"gate": "H1", "identity": "Script", "answers": []}),
            ("/api/review", {"identity": "Script", "outcome": "stop", "acknowledged": True}),
        )
        for path, body in attempts:
            with pytest.raises(urllib.error.HTTPError) as refused:
                _request(url, path, token=app.csrf_token, body=body)
            assert refused.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    kit, run = _load(run_dir)
    assert evaluate_gate(run, kit, "H1").status == "AWAITING"
    assert {path.name for path in (run_dir / "gates").glob("*.json")} == before
    assert not (run_dir / "release_manifest.json").exists()


def test_three_noninteractive_execute_routes_remain_available(example_run, monkeypatch):
    monkeypatch.setattr(
        webui_server, "execute_approved",
        lambda run, kit, approvals, unit, token: {"exit_code": 0},
    )
    monkeypatch.setattr(
        webui_server, "execute_challenge",
        lambda run, kit, approvals, gate, token: {"exit_code": 0},
    )
    monkeypatch.setattr(
        webui_server, "execute_revision",
        lambda run, kit, approvals, gate, token: {"exit_code": 0},
    )
    server, app = create_server(ROOT, example_run, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        attempts = (
            ("/api/next/execute", {"unit": "u01", "approval_token": "token"}, "execution"),
            ("/api/challenge/execute", {"gate": "E1", "approval_token": "token"}, "execution"),
            ("/api/revise/execute", {"gate": "E1", "approval_token": "token"}, "revision"),
        )
        for path, body, key in attempts:
            with _request(url, path, token=app.csrf_token, body=body) as response:
                assert json.load(response)[key]["exit_code"] == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_bundled_example_still_refuses_execute_routes():
    server, app = create_server(ROOT, ROOT / "example-run", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        attempts = (
            ("/api/next/execute", {"unit": "u01", "approval_token": "token"}),
            ("/api/challenge/execute", {"gate": "E1", "approval_token": "token"}),
            ("/api/revise/execute", {"gate": "E1", "approval_token": "token"}),
        )
        for path, body in attempts:
            with pytest.raises(urllib.error.HTTPError) as refused:
                _request(url, path, token=app.csrf_token, body=body)
            assert refused.value.code == 409
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_unexpected_get_and_post_failures_are_written_to_stderr(
    example_run, monkeypatch, capfd,
):
    def fail(*args, **kwargs):
        raise RuntimeError("request diagnostic")

    monkeypatch.setattr(webui_server, "state_view", fail)
    monkeypatch.setattr(webui_server, "evaluate_gate", fail)
    server, app = create_server(ROOT, example_run, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with pytest.raises(urllib.error.HTTPError) as get_error:
            _request(url, "/api/state")
        assert get_error.value.code == 500
        assert b"request diagnostic" not in get_error.value.read()
        with pytest.raises(urllib.error.HTTPError) as post_error:
            _request(url, "/api/check", token=app.csrf_token, body={"gate": "H1"})
        assert post_error.value.code == 500
        assert b"request diagnostic" not in post_error.value.read()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert capfd.readouterr().err.count("RuntimeError: request diagnostic") == 2


def _client_source() -> str:
    """Every packaged script, so a rule cannot be dodged by moving a function."""
    static = ROOT / "rgraph" / "webui" / "static"
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(static.glob("*.js"))
    )


def test_gate_drawer_only_points_human_decisions_to_terminal_and_traps_focus():
    source = _client_source()
    html = (ROOT / "rgraph" / "webui" / "static" / "index.html").read_text(encoding="utf-8")
    assert "/api/decide" not in source and "/api/review" not in source
    assert "decision-form" not in source and "review-form" not in source
    assert "rgraph decide ${esc(gate.id)}" in source
    assert '<div class="plan-command">rgraph review</div>' in source
    assert "Boundary" in source
    assert "ui.drawerTrigger = document.activeElement" in source
    assert "trigger.focus()" in source
    assert 'role="dialog" aria-modal="true"' in html
    assert 'aria-labelledby="drawer-title" inert' in html
    assert 'id="stage-rule" role="region" tabindex="0"' in html
    assert "drawer.inert = false" in source and "drawer.inert = true" in source
    assert "keepDrawerFocus" in source
    assert 'event.key !== "Tab"' in source
    assert "event.preventDefault()" in source


def test_local_ui_uses_quiet_visuals_and_accessible_target_sizes():
    css = (ROOT / "rgraph" / "webui" / "static" / "app.css").read_text(encoding="utf-8")
    for noisy_effect in ("#5ad0ff", "radial-gradient", "text-shadow", "filter:drop-shadow"):
        assert noisy_effect not in css
    assert "h1{font-family:var(--display)" in css
    assert "min-height:44px" in css
    assert ":focus-visible{outline:2px solid var(--amber)" in css


def test_client_html_escape_rejects_an_element_and_event_handler_payload():
    source = (ROOT / "rgraph" / "webui" / "static" / "app.js").read_text(encoding="utf-8")
    definition = re.search(r"const esc = .*?;\n", source, flags=re.DOTALL)
    assert definition is not None
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is unavailable; client escape execution was not checked")
    payload = '<img src=x onerror="alert(\'x\')">&'
    completed = subprocess.run(
        [node, "-e", definition.group(0) + f"process.stdout.write(esc({json.dumps(payload)}));"],
        check=True, capture_output=True, text=True,
    )
    assert completed.stdout == "&lt;img src=x onerror=&quot;alert(&#039;x&#039;)&quot;&gt;&amp;"
