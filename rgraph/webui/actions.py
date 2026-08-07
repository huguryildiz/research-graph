"""Guarded mutations exposed by the local browser interface."""

from __future__ import annotations

import hashlib
import json
import pathlib
import secrets
from dataclasses import dataclass, field
from types import SimpleNamespace

from rgraph.campaigns import retire_current_campaign
from rgraph.config import Kit
from rgraph.gates import assignment_for, evaluate_gate
from rgraph.hashing import file_hash
from rgraph.jobs import JobError, JobManager
from rgraph.run import Run, RunError, load_run
from rgraph.runner import Plan, build_argv, build_plan, execute_capture
from rgraph.services import challenge as challenge_service
from rgraph.services.execution import (
    acquire_unit_lock, allowed_output_paths, now, output_problems, output_state,
    run_boundary_state, write_execution_record,
)
from rgraph.workflow import next_action, next_checkpoint, prerequisite_action


class ActionError(Exception):
    """A safe, user-facing refusal from a UI action."""

    def __init__(self, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _plan_fingerprint(plan: Plan) -> str:
    body = json.dumps({
        "unit": plan.unit,
        "argv": plan.argv,
        "stdin": plan.stdin_text,
        "produces": plan.produces,
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def plan_view(plan: Plan) -> dict:
    return {
        "unit": plan.unit,
        "provider": plan.provider,
        "model": plan.model,
        "command": list(plan.argv),
        "inputs": [{"id": key, "state": state} for key, state in plan.inputs],
        "produces": list(plan.produces),
        "manual": plan.manual,
        "log": str(plan.log_path),
    }


@dataclass
class ApprovalStore:
    """Single-use approvals tie execution to the exact plan the person saw."""

    tokens: dict[str, tuple[str, str]] = field(default_factory=dict)

    def issue(self, plan: Plan) -> str:
        token = secrets.token_urlsafe(24)
        self.tokens[token] = (plan.unit, _plan_fingerprint(plan))
        return token

    def consume(self, token: str, plan: Plan) -> None:
        expected = self.tokens.pop(token, None)
        actual = (plan.unit, _plan_fingerprint(plan))
        if expected is None or not secrets.compare_digest(expected[1], actual[1]) \
                or expected[0] != actual[0]:
            raise ActionError("This execution approval is missing, expired, or no longer matches the plan.", status=409)


def preview_next(run: Run, kit: Kit, approvals: ApprovalStore, unit_id: str | None = None) -> dict:
    if unit_id:
        unit = kit.graph.nodes.get(unit_id)
        if unit is None or not unit.is_unit:
            raise ActionError(f"Unknown work unit: {unit_id}")
        blocked = prerequisite_action(run, kit, unit)
        if blocked is not None:
            raise ActionError(f"{unit_id} cannot run yet: {blocked.detail}", status=409)
    else:
        action = next_action(run, kit)
        if action.kind != "unit" or not action.target:
            raise ActionError(f"No work unit can run yet: {action.detail}", status=409)
        unit_id = action.target
    plan = build_plan(run, kit, unit_id)
    body = plan_view(plan)
    body["approval_token"] = approvals.issue(plan) if not plan.manual else None
    return body


def execute_approved(
    run: Run, kit: Kit, approvals: ApprovalStore, unit_id: str, token: str,
) -> dict:
    if run.read_only:
        raise ActionError("The bundled example is read-only. Copy it before running a provider.", status=409)
    unit = kit.graph.nodes.get(unit_id)
    if unit is None or not unit.is_unit:
        raise ActionError(f"Unknown work unit: {unit_id}")
    blocked = prerequisite_action(run, kit, unit)
    if blocked is not None:
        raise ActionError(f"{unit_id} cannot run yet: {blocked.detail}", status=409)
    plan = build_plan(run, kit, unit_id)
    if plan.manual:
        raise ActionError("This provider is web-only and cannot be launched by research-graph.", status=409)
    approvals.consume(token, plan)
    result = execute_capture(plan, verbose=False)
    return {
        "exit_code": result.exit_code,
        "log": str(plan.log_path),
        "output": result.output[-12000:],
    }


def _challenge_preparation(run: Run, kit: Kit, gate_id: str):
    try:
        return challenge_service.prepare(run, kit, gate_id)
    except challenge_service.ChallengeError as exc:
        raise ActionError(str(exc), status=409 if exc.kind != "config" else 400) from exc


def _challenge_plan(run: Run, kit: Kit, gate_id: str) -> Plan:
    return _challenge_preparation(run, kit, gate_id).plan


def preview_challenge(run: Run, kit: Kit, approvals: ApprovalStore, gate_id: str) -> dict:
    plan = _challenge_plan(run, kit, gate_id)
    body = plan_view(plan)
    body["gate"] = gate_id
    body["approval_token"] = approvals.issue(plan)
    return body


def execute_challenge(
    run: Run, kit: Kit, approvals: ApprovalStore, gate_id: str, token: str,
) -> dict:
    from rgraph.commands import challenge

    plan = _challenge_plan(run, kit, gate_id)
    approvals.consume(token, plan)
    code = challenge.handle(SimpleNamespace(
        root=str(kit.root), run=str(run.root), gate=gate_id, online=False, verbose=False,
    ))
    refreshed = evaluate_gate(load_run(run.root, kit), kit, gate_id)
    return {
        "exit_code": code,
        "gate": gate_id,
        "status": refreshed.status,
        "log": str(plan.log_path),
    }


def _revision_plan(run: Run, kit: Kit, gate_id: str) -> tuple[Plan, str, dict]:
    gate = kit.gates.get(gate_id)
    if gate is None:
        raise ActionError(f"Unknown gate: {gate_id}")
    if run.read_only:
        raise ActionError("The bundled example is read-only. Copy it before using a revision.", status=409)
    record = run.gate_record(gate_id)
    if record is None or record.get("outcome") != "revise":
        raise ActionError(f"{gate_id} has no current revision decision.", status=409)
    budget = run.meta.get("revisions", {}).get(
        gate_id, {"max": gate.max_revisions, "used": 0}
    )
    if budget["used"] >= budget["max"]:
        raise ActionError(f"{gate_id} has spent its revision budget.", status=409)
    reason = record.get("reason") or "revision"
    routes = gate.routes.get("revise")
    target = routes.get(reason, routes.get("default")) if isinstance(routes, dict) else routes
    plan = Plan(
        unit=f"revise-{gate_id}", role_path=kit.root / "gates.yaml",
        provider="local", model="deterministic",
        argv=["rgraph", "revise", gate_id], stdin_text="",
        inputs=[(gate_id, "REVISION")], produces=(),
        log_path=run.root / "meta.json",
    )
    return plan, target, budget


def preview_revision(run: Run, kit: Kit, approvals: ApprovalStore, gate_id: str) -> dict:
    plan, target, budget = _revision_plan(run, kit, gate_id)
    body = plan_view(plan)
    body.update({
        "gate": gate_id, "return_to": target,
        "budget": {"used": budget["used"], "max": budget["max"]},
        "approval_token": approvals.issue(plan),
    })
    return body


def execute_revision(
    run: Run, kit: Kit, approvals: ApprovalStore, gate_id: str, token: str,
) -> dict:
    from rgraph.commands import revise

    plan, target, _ = _revision_plan(run, kit, gate_id)
    approvals.consume(token, plan)
    code = revise.handle(SimpleNamespace(root=str(kit.root), run=str(run.root), gate=gate_id))
    refreshed = load_run(run.root, kit)
    budget = refreshed.meta.get("revisions", {}).get(gate_id, {})
    return {"exit_code": code, "gate": gate_id, "return_to": target, "budget": budget}


# ── background execution ───────────────────────────────────────────────────
#
# Everything below turns an approval a person gave into a child process the
# browser can watch. The approval is consumed *after* the plan has been rebuilt
# and compared, so a study that changed under the preview cannot be executed
# against the plan somebody actually read.


def _artifact_references(run: Run, artifact_ids) -> list[dict]:
    references = []
    for artifact_id in artifact_ids:
        artifact = run.artifacts.get(artifact_id)
        references.append({
            "artifact_id": artifact_id,
            "content_hash": artifact.content_hash if artifact is not None else None,
            "state": (
                "MISSING" if artifact is None or not artifact.present
                else "INVALID" if artifact.errors else "VALID"
            ),
        })
    return references


def _validation_view(problems: list[str], produced: list[str], stages: list[dict]) -> dict:
    return {
        "ok": not problems,
        "problems": problems,
        "produced": produced,
        "stages": stages,
        "boundary": (
            "These stages establish only what they name. Scientific correctness "
            "was not determined."
        ),
    }


def _stage(name: str, status: str, detail: str) -> dict:
    return {"name": name, "status": status, "detail": detail}


def start_unit_job(
    run: Run, kit: Kit, approvals: ApprovalStore, jobs: JobManager,
    unit_id: str, token: str,
) -> dict:
    """Re-verify everything the preview showed, then start one child process."""
    if run.read_only:
        raise ActionError(
            "The bundled example is read-only. Copy it before running a provider.",
            status=409,
        )
    unit = kit.graph.nodes.get(unit_id)
    if unit is None or not unit.is_unit:
        raise ActionError(f"Unknown work unit: {unit_id}")
    blocked = prerequisite_action(run, kit, unit)
    if blocked is not None:
        raise ActionError(f"{unit_id} cannot run yet: {blocked.detail}", status=409)
    plan = build_plan(run, kit, unit_id)
    if plan.manual:
        raise ActionError(
            "This provider is web-only and cannot be launched by research-graph.",
            status=409,
        )
    approvals.consume(token, plan)

    try:
        lock_path = acquire_unit_lock(run, unit.id)
    except RunError as exc:
        raise ActionError(str(exc), status=409) from exc

    try:
        if unit.id == "u07":
            retire_current_campaign(run)
        before = output_state(run, unit.produces)
        boundary_before = run_boundary_state(run.root)
        started_at = now()

        def finish(job, exit_code: int, output: str) -> dict:
            try:
                return _accept_unit(
                    run, kit, unit, plan, exit_code,
                    before=before, boundary_before=boundary_before,
                    started_at=started_at,
                )
            finally:
                pathlib.Path(lock_path).unlink(missing_ok=True)

        try:
            job = jobs.start(
                run_root=run.root, kind="unit", target=unit.id, title=unit.title,
                role=unit.role_name, plan=plan,
                inputs=_artifact_references(run, [item for item, _ in plan.inputs]),
                expected_outputs=list(unit.produces),
                declared_paths=sorted(allowed_output_paths(run, unit)),
                prompt_sha256=hashlib.sha256(
                    plan.stdin_text.encode("utf-8")
                ).hexdigest(),
                finish=finish,
            )
        except JobError as exc:
            pathlib.Path(lock_path).unlink(missing_ok=True)
            raise ActionError(str(exc), status=exc.status) from exc
    except Exception:
        pathlib.Path(lock_path).unlink(missing_ok=True)
        raise
    return job_view(job, kit)


def _accept_unit(
    run: Run, kit: Kit, unit, plan, exit_code: int, *, before, boundary_before,
    started_at: str,
) -> dict:
    """The `rgraph next` acceptance rules, applied to a background invocation."""
    finished_at = now()
    stages = [_stage(
        "process exited", "PASS" if exit_code == 0 else "FAIL",
        f"the provider CLI returned exit code {exit_code}",
    )]
    problems = [] if exit_code == 0 else [f"provider CLI exited {exit_code}"]
    try:
        refreshed = load_run(run.root, kit)
        stages.append(_stage("run readable", "PASS", "every artifact parsed and validated"))
    except RunError as exc:
        problems.append(f"provider left an unreadable run: {exc}")
        stages.append(_stage("run readable", "FAIL", str(exc)))
        refreshed = run
    if exit_code == 0:
        found = output_problems(
            refreshed, kit, unit, before, boundary_before,
            started_at=started_at, finished_at=finished_at,
        )
        problems.extend(found)
        stages.append(_stage(
            "declared outputs", "FAIL" if found else "PASS",
            "; ".join(found[:4]) if found
            else "every declared artifact is present, schema-valid, hash-linked and "
                 "produced by the assigned identity",
        ))
    else:
        stages.append(_stage(
            "declared outputs", "SKIPPED",
            "a non-zero exit means the outputs were not accepted",
        ))
    if plan.log_path is None or not pathlib.Path(plan.log_path).is_file():
        problems.append("provider log is missing")

    receipt = None
    try:
        receipt = write_execution_record(
            run, refreshed, kit, unit, plan,
            started_at=started_at, finished_at=finished_at,
            exit_code=exit_code, problems=problems,
        )
        stages.append(_stage(
            "execution receipt", "PASS" if not problems else "RECORDED",
            f"written to {receipt}" if receipt else "not written for a read-only run",
        ))
    except RunError as exc:
        problems.append(str(exc))
        stages.append(_stage("execution receipt", "FAIL", str(exc)))

    produced = [
        artifact_id for artifact_id in unit.produces
        if refreshed.artifacts[artifact_id].present
    ]
    view = _validation_view(problems, produced, stages)
    view["receipt"] = str(receipt) if receipt else None
    view["next_gate"] = next_checkpoint(kit, unit.id)
    return view


def start_challenge_job(
    run: Run, kit: Kit, approvals: ApprovalStore, jobs: JobManager,
    gate_id: str, token: str,
) -> dict:
    prep = _challenge_preparation(run, kit, gate_id)
    approvals.consume(token, prep.plan)
    challenge_service.begin(prep, run)

    def finish(job, exit_code: int, output: str) -> dict:
        stages = [_stage(
            "process exited", "PASS" if exit_code == 0 else "FAIL",
            f"the reviewer CLI returned exit code {exit_code}",
        )]
        outcome = challenge_service.accept(
            run, kit, prep, exit_code=exit_code, output=output,
        )
        if outcome.error:
            stages.append(_stage("reviewer decision", "FAIL", outcome.error))
            view = _validation_view([outcome.error], [], stages)
            view["gate"] = gate_id
            view["gate_status"] = None
            return view
        stages.append(_stage(
            "reviewer decision", "PASS",
            "the returned decision parsed, named an allowed reason and did not "
            "contradict a failing local check",
        ))
        stages.append(_stage(
            "gate record", "PASS", f"written to {outcome.record_path}",
        ))
        view = _validation_view([], [], stages)
        view["gate"] = gate_id
        view["gate_status"] = outcome.status
        view["record"] = str(outcome.record_path) if outcome.record_path else None
        return view

    try:
        job = jobs.start(
            run_root=run.root, kind="challenge", target=gate_id,
            title=prep.gate.title, role="reviewer", plan=prep.plan,
            inputs=_artifact_references(run, prep.gate.inputs),
            expected_outputs=[f"gates/{gate_id}.json"],
            # A reviewer is read-only: nothing it writes is declared, so every
            # change it makes shows up as one.
            declared_paths=[],
            prompt_sha256=file_hash(prep.prompt_path).removeprefix("sha256:"),
            finish=finish,
        )
    except JobError as exc:
        raise ActionError(str(exc), status=exc.status) from exc
    return job_view(job, kit)


def job_view(job, kit: Kit | None = None) -> dict:
    body = job.as_dict()
    body["log_note"] = (
        "The complete provider log is written to the study's logs/ directory. It is "
        "not redacted and is readable by anyone with access to this computer."
    )
    body["redaction_note"] = (
        "Live output has control sequences removed and known credential shapes "
        "replaced. This reduces exposure; it does not establish that the output "
        "contains no secret."
    )
    if kit is not None and job.kind == "challenge":
        gate = kit.gates.get(job.target)
        body["title"] = gate.title if gate else job.title
    return body
