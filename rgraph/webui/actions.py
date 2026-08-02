"""Guarded mutations exposed by the local browser interface."""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass, field
from types import SimpleNamespace

from rgraph.commands.decide import MECHANICAL
from rgraph.config import Kit
from rgraph.gates import assignment_for, evaluate_gate, now, record_from
from rgraph.hashing import document_hash
from rgraph.run import Run, load_run
from rgraph.runner import Plan, build_argv, build_plan, execute_capture
from rgraph.workflow import next_action, prerequisite_action


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


def _challenge_plan(run: Run, kit: Kit, gate_id: str) -> Plan:
    from rgraph.commands.challenge import BLOCKING_LOCAL_CHECKS, _prompt

    gate = kit.gates.get(gate_id)
    if gate is None or gate.kind != "challenge":
        raise ActionError(f"{gate_id} is not a reviewer challenge gate.")
    if run.read_only:
        raise ActionError("The bundled example is read-only. Copy it before running a reviewer.", status=409)
    current = evaluate_gate(run, kit, gate_id)
    existing = run.gate_record(gate_id)
    if existing and current.status in ("PASS", "CAVEAT"):
        raise ActionError(f"{gate_id} already has a current reviewer decision.", status=409)
    readiness = evaluate_gate(run, kit, gate_id, require_decision=False)
    blocking = [
        item for item in readiness.checks
        if item.name in BLOCKING_LOCAL_CHECKS and item.status == "FAIL"
    ]
    if blocking:
        raise ActionError(
            "Reviewer not started: " + ", ".join(item.name for item in blocking) + " must pass first.",
            status=409,
        )
    assignment = assignment_for(kit, gate.owner)
    if assignment is None:
        raise ActionError(f"No assignment for challenge owner {gate.owner}.", status=409)
    provider = kit.providers[assignment.provider]
    if provider.kind != "cli":
        raise ActionError("The assigned reviewer is manual and cannot be launched from the local UI.", status=409)
    identity = assignment.identity(kit.providers)
    prompt, role_path = _prompt(run, kit, gate, identity, readiness)
    return Plan(
        unit=f"challenge-{gate_id}", role_path=role_path,
        provider=assignment.provider, model=assignment.model,
        argv=build_argv(provider, assignment), stdin_text=prompt,
        inputs=[(artifact_id, "VALID") for artifact_id in gate.inputs],
        log_path=run.root / "logs" / f"review-{gate_id}.log",
    )


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


def record_human_decision(
    run: Run, kit: Kit, gate_id: str, identity: str, answers: list[dict],
) -> dict:
    if run.read_only:
        raise ActionError("The bundled example is read-only. Copy it before recording a decision.", status=409)
    gate = kit.gates.get(gate_id)
    if gate is None or gate.kind != "human":
        raise ActionError(f"{gate_id} is not a human gate.")
    identity = identity.strip()
    if not identity:
        raise ActionError("Name the person making this decision.")
    expected = list(gate.proves)
    if [item.get("claim") for item in answers] != expected:
        raise ActionError("The attestations do not match the current gate contract.", status=409)
    if any(item.get("answered") not in ("yes", "no") for item in answers):
        raise ActionError("Every attestation must be answered yes or no.")

    result = evaluate_gate(run, kit, gate_id)
    broken = [item for item in result.checks if item.name in MECHANICAL and item.status == "FAIL"]
    if broken:
        raise ActionError("The gate inputs are missing, invalid, or fail provenance checks.", status=409)

    outcome = "pass" if all(item["answered"] == "yes" for item in answers) else "revise"
    record = record_from(result, run, kit)
    record["outcome"] = outcome
    record["decided_at"] = now()
    record["decided_by"] = {"role": "human", "identity": f"human/{identity}"}
    record["attestation"] = {
        "identity": f"human/{identity}",
        "answers": [{"claim": item["claim"], "answered": item["answered"]} for item in answers],
    }
    if outcome == "revise":
        record["reason"] = record.get("reason") or "revision"
    path = run.write_gate_record(record)
    return {"gate": gate_id, "outcome": outcome, "record": str(path)}


def record_final_decision(
    run: Run, kit: Kit, identity: str, outcome: str, acknowledged: bool,
) -> dict:
    """Record the same attributable final decision as the terminal review flow."""
    if run.read_only:
        raise ActionError("The bundled example is read-only. Copy it before recording a release decision.", status=409)
    if outcome not in ("release", "revise", "narrow", "null-result", "stop"):
        raise ActionError("Choose a valid release outcome.")
    identity = identity.strip()
    if not identity:
        raise ActionError("Name the person making the release decision.")
    if acknowledged is not True:
        raise ActionError("Confirm the scientific-correctness reading limit before deciding.")

    gate_order = ("H1", "E1", "H2", "H3", "T1", "H4", "T2", "V1", "M1")
    results = {gate_id: evaluate_gate(run, kit, gate_id) for gate_id in gate_order}
    caveats = [gate_id for gate_id, result in results.items() if result.status == "CAVEAT"]
    blocked = [
        gate_id for gate_id, result in results.items()
        if result.status not in ("PASS", "CAVEAT")
    ]
    if outcome in ("release", "null-result") and blocked:
        raise ActionError("Unresolved gates remain: " + ", ".join(blocked), status=409)

    actor = f"human/{identity}"
    decided_at = now()
    gate = kit.gates["FINAL"]
    inputs = [
        {"artifact_id": artifact_id, "content_hash": run.get(artifact_id).content_hash}
        for artifact_id in gate.inputs if run.get(artifact_id).present
    ]
    final_result = evaluate_gate(run, kit, "FINAL")
    checks = [
        {"name": item.name, "status": item.status, "detail": item.detail}
        for item in final_result.checks
    ]
    levels = {
        gate_id: result.separation.level for gate_id, result in results.items()
        if result.separation and result.separation.level
    }

    if outcome in ("revise", "narrow"):
        budget = run.meta.setdefault("revisions", {}).setdefault(
            "FINAL", {"max": gate.max_revisions, "used": 0}
        )
        if budget["used"] >= budget["max"]:
            raise ActionError("FINAL has spent its revision budget.", status=409)
        route = gate.routes[outcome]
        target = route.get("default") if isinstance(route, dict) else route
        budget["used"] += 1
        run.meta.setdefault("history", []).append({
            "at": decided_at, "gate": "FINAL", "outcome": outcome, "to": target,
        })
        run.save_meta()
        path = run.write_gate_record({
            "gate_id": "FINAL", "outcome": outcome, "decided_at": decided_at,
            "decided_by": {"role": "human", "identity": actor},
            "producer_identity": None, "separation_level": None,
            "separation_caveat": bool(caveats), "inputs": inputs, "checks": checks,
            "attestation": {"identity": actor, "answers": [{
                "claim": "Human release decision recorded", "answered": "yes",
            }]},
            "reason": None, "findings": [], "revision_budget": budget,
        })
        return {"outcome": outcome, "record": str(path), "return_to": target}

    body = {
        "outcome": outcome, "decided_by": actor, "decided_at": decided_at,
        "revision_counts": {
            gate_id: value["used"] for gate_id, value in run.meta.get("revisions", {}).items()
        },
        "scope_changes": [], "separation_levels": levels,
        "caveats": [
            f"{gate_id} decided at {levels.get(gate_id, 'unknown').replace('_', ' ').upper()}"
            for gate_id in caveats
        ],
        "not_established": ["Scientific correctness was not determined"],
    }
    document = {
        "artifact_id": "release_manifest", "version": 1,
        "produced_by": {"role": "human", "identity": actor},
        "produced_at": decided_at, "inputs": inputs, "body": body,
    }
    document["content_hash"] = document_hash(document)
    manifest_path = run.root / "release_manifest.json"
    manifest_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    path = run.write_gate_record({
        "gate_id": "FINAL", "outcome": outcome, "decided_at": decided_at,
        "decided_by": {"role": "human", "identity": actor},
        "producer_identity": None, "separation_level": None,
        "separation_caveat": bool(caveats), "inputs": inputs, "checks": checks,
        "attestation": {"identity": actor, "answers": [{
            "claim": "Human release decision recorded", "answered": "yes",
        }]},
        "reason": None, "findings": [],
        "revision_budget": {"max": gate.max_revisions, "used": 0},
    })
    return {"outcome": outcome, "record": str(path), "manifest": str(manifest_path)}
