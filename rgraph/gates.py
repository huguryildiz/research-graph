"""Gate evaluation. Generic checks first, then the gate's content check."""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field

from rgraph import separation as sep
from rgraph.checks import CONTENT_CHECKS, CheckFinding
from rgraph.config import Kit
from rgraph.provenance import hash_mismatch, invalidated_gates, payload_mismatch
from rgraph.run import Run

_REASON_BY_GATE = {
    "E1": "evidence_gap",
    "H2": "evidence_gap",
    "H3": "hypothesis_defect",
    "T2": "code_run_defect",
    "M1": "claim_support_gap",
}


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str = ""


@dataclass
class GateResult:
    gate_id: str
    status: str
    checks: list[CheckResult] = field(default_factory=list)
    findings: list[CheckFinding] = field(default_factory=list)
    separation: sep.SeparationVerdict | None = None
    producer_identity: str | None = None
    budget: tuple[int, int] = (0, 3)
    reason: str | None = None
    return_to: str | None = None
    proves: tuple[str, ...] = ()


def now() -> str:
    return (
        _dt.datetime.now(_dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _assignment_for(kit: Kit, node_id: str | None):
    if node_id is None:
        return None
    if node_id in ("reviewer", "human"):
        return kit.assignment.get("reviewer")
    if node_id in kit.assignment:
        return kit.assignment[node_id]
    node = kit.graph.nodes.get(node_id)
    return kit.assignment.get(node.role_name) if node and node.role_name else None


def recorded_producer_identity(run: Run, kit: Kit, gate) -> str | None:
    """The identity the producing unit's own artifacts claim, not the one configured.

    This is the string the separation check must use. `assignment.yaml` says who
    you *intended* to run a role; only the artifact says who the run recorded.
    """
    node = kit.graph.nodes.get(gate.producer) if gate.producer else None
    if node is None:
        return None
    for artifact_id in node.produces:
        artifact = run.artifacts.get(artifact_id)
        if artifact is not None and artifact.present and artifact.identity:
            return artifact.identity
    return None


def evaluate_gate(run: Run, kit: Kit, gate_id: str, *, online: bool = False) -> GateResult:
    gate = kit.gates[gate_id]
    result = GateResult(gate_id=gate_id, status="PASS", proves=gate.proves)

    missing = [a for a in gate.inputs if not run.get(a).present]
    result.checks.append(CheckResult(
        "presence", "FAIL" if missing else "PASS",
        f"missing: {', '.join(missing)}" if missing else f"{len(gate.inputs)} inputs present"))

    invalid = [a for a in gate.inputs if run.get(a).errors]
    result.checks.append(CheckResult(
        "schema", "FAIL" if invalid else "PASS",
        f"invalid: {', '.join(invalid)}" if invalid else "all inputs validate"))
    for artifact_id in invalid:
        for error in run.get(artifact_id).errors[:3]:
            result.findings.append(CheckFinding(
                artifact_id, "SCHEMA VIOLATION", f"{error.path}: {error.message}",
                f"correct {artifact_id}.json against schemas/{artifact_id}.schema.json"))

    provenance_problems: list[str] = []
    for artifact_id in gate.inputs:
        artifact = run.get(artifact_id)
        provenance_problems += [
            f"{artifact_id}: {name} changed" for name, _, _ in hash_mismatch(run, artifact)
        ]
        payload = payload_mismatch(run, artifact)
        if payload:
            provenance_problems.append(f"{artifact_id}: {payload}")
    result.checks.append(CheckResult(
        "provenance", "FAIL" if provenance_problems else "PASS",
        "; ".join(provenance_problems) or "input hashes match"))

    invalidated = invalidated_gates(run, kit).get(gate_id, [])
    result.checks.append(CheckResult(
        "staleness", "FAIL" if invalidated else "PASS",
        "; ".join(invalidated) or "no upstream artifact changed"))

    if "separation" in gate.checks:
        reviewer = _assignment_for(kit, gate.owner)
        reviewer_identity = reviewer.identity(kit.providers) if reviewer else None
        recorded = recorded_producer_identity(run, kit, gate)
        result.producer_identity = recorded
        verdict = sep.evaluate(
            gate, _assignment_for(kit, gate.producer), reviewer,
            recorded_producer=recorded, reviewer_identity=reviewer_identity,
        )
        result.separation = verdict
        result.checks.append(CheckResult(
            "separation", verdict.status, sep.LABELS.get(verdict.level or "", "n/a")))
        if verdict.status == "FAIL" and recorded and recorded == reviewer_identity:
            result.findings.append(CheckFinding(
                gate.producer or "producer", "REVIEWER IS THE PRODUCER",
                f"the reviewed artifact records produced_by.identity = {recorded},\n"
                f"which is the identity deciding this gate",
                "decide this gate from a separate session, model or provider"))

    budget = run.meta.get("revisions", {}).get(
        gate_id, {"max": gate.max_revisions, "used": 0}
    )
    result.budget = (budget["used"], budget["max"])
    exhausted = budget["used"] >= budget["max"]
    result.checks.append(CheckResult(
        "budget", "FAIL" if exhausted else "PASS",
        f"{budget['max'] - budget['used']} of {budget['max']} attempts remain"))

    for name in gate.checks:
        check = CONTENT_CHECKS.get(name)
        if check is None:
            continue
        if missing or invalid:
            result.checks.append(CheckResult(name, "SKIP", "inputs are not usable"))
            continue
        findings = check(run, kit, gate, online=online)
        result.findings.extend(findings)
        result.checks.append(CheckResult(
            name, "FAIL" if findings else "PASS",
            f"{len(findings)} findings" if findings else "clean"))

    failed = [c for c in result.checks if c.status == "FAIL"]
    if exhausted and len(failed) == 1 and failed[0].name == "budget":
        result.status = "BLOCKED"
    elif any(c.name == "staleness" and c.status == "FAIL" for c in result.checks):
        result.status = "STALE"
    elif failed:
        result.status = "FAIL"
    elif result.separation and result.separation.status == "CAVEAT":
        result.status = "CAVEAT"

    if result.status in ("FAIL", "STALE"):
        result.reason = _reason_for(gate, result)
        routes = gate.routes.get("revise")
        if isinstance(routes, dict):
            result.return_to = routes.get(result.reason, routes.get("default"))
        else:
            result.return_to = routes
    return result


def _reason_for(gate, result: GateResult) -> str:
    codes = {f.code for f in result.findings}
    if gate.id == "V1":
        if codes & {"DIGEST MISMATCH", "N MISMATCH", "SEED SET MISMATCH"}:
            return "code_run_defect"
        if codes & {"CI MISSING"}:
            return "assumption_violation"
        return "scope_plan_defect"
    return _REASON_BY_GATE.get(gate.id, "revision")


def record_from(result: GateResult, run: Run, kit: Kit) -> dict:
    gate = kit.gates[result.gate_id]
    reviewer = _assignment_for(kit, gate.owner)
    producer = _assignment_for(kit, gate.producer)
    outcome = {"PASS": "pass", "CAVEAT": "pass", "STALE": "revise",
               "FAIL": "revise", "BLOCKED": "block"}[result.status]
    return {
        "gate_id": result.gate_id,
        "outcome": outcome,
        "decided_at": now(),
        "decided_by": {
            "role": "reviewer" if gate.kind == "challenge" else "human",
            "identity": reviewer.identity(kit.providers) if reviewer else "human/manual",
        },
        "producer_identity": (
            result.producer_identity
            or recorded_producer_identity(run, kit, gate)
            or (producer.identity(kit.providers) if producer else None)
        ),
        "separation_level": result.separation.level if result.separation else None,
        "separation_caveat": bool(result.separation and result.separation.status == "CAVEAT"),
        "inputs": [
            {"artifact_id": a, "content_hash": run.get(a).content_hash}
            for a in gate.inputs
            if run.get(a).present
        ],
        "checks": [
            {"name": c.name, "status": c.status, "detail": c.detail} for c in result.checks
        ],
        "reason": result.reason,
        "findings": [
            {"ref": f.ref, "code": f.code, "detail": f.detail, "fix": f.fix}
            for f in result.findings
        ],
        "revision_budget": {"max": result.budget[1], "used": result.budget[0]},
    }
