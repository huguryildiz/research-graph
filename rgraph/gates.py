"""Gate evaluation. Generic checks first, then the gate's content check."""

from __future__ import annotations

import datetime as _dt
import pathlib
from dataclasses import dataclass, field

from rgraph import separation as sep
from rgraph.checks import CONTENT_CHECKS, CheckFinding
from rgraph.config import Kit
from rgraph.hashing import file_hash
from rgraph.provenance import (
    body_mismatch, hash_mismatch, invalidated_gates, payload_mismatch,
    stale_artifacts,
)
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
    attested_by: str | None = None
    decision_valid: bool | None = None


def now() -> str:
    return (
        _dt.datetime.now(_dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def assignment_for(kit: Kit, node_id: str | None):
    if node_id is None:
        return None
    if node_id in ("reviewer", "human"):
        return kit.assignment.get("reviewer")
    if node_id in kit.assignment:
        return kit.assignment[node_id]
    node = kit.graph.nodes.get(node_id)
    return kit.assignment.get(node.role_name) if node and node.role_name else None


def _expected_input_refs(run: Run, gate) -> list[dict]:
    return [
        {"artifact_id": artifact_id, "content_hash": run.get(artifact_id).content_hash}
        for artifact_id in gate.inputs
        if run.get(artifact_id).present
    ]


def _challenge_decision_errors(run: Run, kit: Kit, gate, record: dict | None) -> list[str]:
    """Verify that a challenge decision came from the invocation it names.

    The command line is still a local provenance assertion, not remote
    attestation by a provider.  It is nevertheless materially stronger than
    copying the configured reviewer identity into a record when no reviewer
    process ran at all.
    """
    if record is None:
        return ["no reviewer decision recorded"]

    errors: list[str] = []
    assignment = assignment_for(kit, gate.owner)
    expected_identity = assignment.identity(kit.providers) if assignment else None
    actor = record.get("decided_by") or {}
    synthetic_legacy = run.meta.get("provenance") == "synthetic" \
        and record.get("decision_provenance") is None
    if actor.get("role") != "reviewer":
        errors.append("decided_by.role is not reviewer")
    if not expected_identity and not synthetic_legacy:
        errors.append(f"no assignment for challenge owner {gate.owner}")
    elif not synthetic_legacy and actor.get("identity") != expected_identity:
        errors.append(
            f"record names {actor.get('identity') or 'no identity'}; "
            f"assignment requires {expected_identity}"
        )
    if record.get("inputs") != _expected_input_refs(run, gate):
        errors.append("decision inputs do not match the gate's current artifact hashes")

    provenance = record.get("decision_provenance")
    if synthetic_legacy:
        # The bundled fixture predates executable reviewer provenance and says
        # prominently that none of its identities is a real invocation.
        return errors
    if not isinstance(provenance, dict):
        errors.append("no reviewer invocation provenance recorded")
        return errors
    if provenance.get("mode") != "cli":
        errors.append(f"reviewer invocation mode is {provenance.get('mode')!r}, not 'cli'")
        return errors
    if assignment:
        if provenance.get("provider") != assignment.provider:
            errors.append("invocation provider does not match the assignment")
        if provenance.get("model") != assignment.model:
            errors.append("invocation model does not match the assignment")
        from rgraph.runner import build_argv

        expected_argv = build_argv(kit.providers[assignment.provider], assignment)
        if provenance.get("argv") != expected_argv:
            errors.append("invocation argv does not match providers.yaml and assignment.yaml")
    if provenance.get("exit_code") != 0:
        errors.append("reviewer invocation did not exit successfully")

    resolved_files: dict[str, pathlib.Path] = {}
    for label, path_key, hash_key in (
        ("reviewer log", "log", "log_sha256"),
        ("reviewer prompt", "prompt", "prompt_sha256"),
    ):
        path_ref = provenance.get(path_key)
        if not isinstance(path_ref, str) or not path_ref:
            errors.append(f"{label} path is missing")
            continue
        candidate = (run.root / pathlib.PurePosixPath(path_ref)).resolve()
        try:
            candidate.relative_to(run.root.resolve())
        except ValueError:
            errors.append(f"{label} path escapes the run directory")
        else:
            if not candidate.is_file():
                errors.append(f"{label} is missing: {path_ref}")
            elif provenance.get(hash_key) != file_hash(candidate):
                errors.append(f"{label} no longer matches its recorded digest")
            else:
                resolved_files[path_key] = candidate

    reviewer_node = kit.graph.nodes.get("reviewer")
    role_path = kit.root / reviewer_node.role if reviewer_node and reviewer_node.role else None
    if role_path is None or not role_path.is_file():
        errors.append("reviewer role contract is missing")
    elif provenance.get("role_contract_sha256") != file_hash(role_path):
        errors.append("reviewer role contract changed after the decision")

    log_path = resolved_files.get("log")
    if log_path is not None:
        from rgraph.reviewer import allowed_reasons, decision_hash, parse_decision

        try:
            output = log_path.read_text(encoding="utf-8")
        except UnicodeError:
            errors.append("reviewer log is not UTF-8 text")
        else:
            decision, parse_error = parse_decision(output, kit)
            if parse_error:
                errors.append(parse_error)
            elif decision is not None:
                if (
                    decision["outcome"] == "revise"
                    and decision["reason"] not in allowed_reasons(kit, gate.id)
                ):
                    errors.append(
                        f"reviewer reason {decision['reason']!r} is not a typed "
                        f"return from {gate.id}"
                    )
                if provenance.get("decision_sha256") != decision_hash(decision):
                    errors.append("reviewer decision no longer matches its recorded digest")
                if record.get("outcome") != decision["outcome"]:
                    errors.append("gate outcome does not match the captured reviewer decision")
                if record.get("reason") != decision["reason"]:
                    errors.append("gate reason does not match the captured reviewer decision")
                recorded_checks = record.get("checks") or []
                expected_checks = [
                    {
                        "name": f"reviewer:{item['name']}",
                        "status": item["status"],
                        "detail": item["detail"],
                    }
                    for item in decision["checks"]
                ]
                if any(item not in recorded_checks for item in expected_checks):
                    errors.append("gate checks do not contain the captured reviewer checks")
                if any(item not in (record.get("findings") or []) for item in decision["findings"]):
                    errors.append("gate findings do not contain the captured reviewer findings")

    peers = set(gate.distinct_actor_from)
    peers.update(
        other.id for other in kit.gates.values()
        if gate.id in other.distinct_actor_from
    )
    invocation_id = provenance.get("invocation_id")
    for peer_id in peers:
        peer = run.gate_record(peer_id)
        peer_invocation = (peer or {}).get("decision_provenance") or {}
        if invocation_id and peer_invocation.get("invocation_id") == invocation_id:
            errors.append(f"reviewer invocation was reused from challenge {peer_id}")
    return errors


def recorded_producer_identities(run: Run, kit: Kit, gate) -> tuple[str, ...]:
    """Every identity the producing unit's own artifacts claim, in `produces` order.

    These are the strings the separation check must use. `assignment.yaml` says
    who you *intended* to run a role; only the artifact says who the run
    recorded. A unit that produces two artifacts can have the reviewer author
    the second one, so all of them are read rather than the first.
    """
    node = kit.graph.nodes.get(gate.producer) if gate.producer else None
    if node is None:
        return ()
    seen: list[str] = []
    for artifact_id in node.produces:
        artifact = run.artifacts.get(artifact_id)
        if artifact is not None and artifact.present and artifact.identity:
            if artifact.identity not in seen:
                seen.append(artifact.identity)
    return tuple(seen)


def recorded_producer_identity(run: Run, kit: Kit, gate) -> str | None:
    """The identity a gate record names for the producer: the first one recorded."""
    identities = recorded_producer_identities(run, kit, gate)
    return identities[0] if identities else None


def evaluate_gate(
    run: Run,
    kit: Kit,
    gate_id: str,
    *,
    online: bool = False,
    require_decision: bool = True,
) -> GateResult:
    gate = kit.gates[gate_id]
    result = GateResult(gate_id=gate_id, status="PASS", proves=gate.proves)
    record = run.gate_record(gate_id)

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
        body = body_mismatch(artifact)
        if body:
            provenance_problems.append(f"{artifact_id}: {body}")
            result.findings.append(CheckFinding(
                artifact_id, "BODY EDITED AFTER HASHING", body,
                f"re-run the unit that produces {artifact_id}, or `rgraph seal "
                f"{artifact_id}` if you edited it on purpose"))
        payload = payload_mismatch(run, artifact)
        if payload:
            provenance_problems.append(f"{artifact_id}: {payload}")
    result.checks.append(CheckResult(
        "provenance", "FAIL" if provenance_problems else "PASS",
        "; ".join(provenance_problems) or "input hashes match"))

    if require_decision:
        invalidated = invalidated_gates(run, kit).get(gate_id, [])
        if record and record.get("inputs") != _expected_input_refs(run, gate):
            invalidated = [*invalidated, "recorded decision inputs do not match current hashes"]
    else:
        # Readiness is about the current artifacts, not the decision that this
        # invocation exists to replace. Feeding an old record's staleness to the
        # reviewer creates a self-referential revise decision that disappears as
        # soon as its replacement is written.
        stale = stale_artifacts(run)
        invalidated = [
            f"{artifact_id}: {'; '.join(stale[artifact_id])}"
            for artifact_id in gate.inputs if artifact_id in stale
        ]
    result.checks.append(CheckResult(
        "staleness", "FAIL" if invalidated else "PASS",
        "; ".join(invalidated) or "no upstream artifact changed"))

    if "separation" in gate.checks:
        reviewer = assignment_for(kit, gate.owner)
        recorded_reviewer = ((record or {}).get("decided_by") or {}).get("identity")
        reviewer_identity = (
            recorded_reviewer
            if gate.kind == "challenge" and require_decision and record
            else reviewer.identity(kit.providers) if reviewer else None
        )
        recorded = recorded_producer_identities(run, kit, gate)
        result.producer_identity = recorded[0] if recorded else None
        verdict = sep.evaluate(
            gate, assignment_for(kit, gate.producer), reviewer,
            recorded_producers=recorded, reviewer_identity=reviewer_identity,
        )
        result.separation = verdict
        result.checks.append(CheckResult(
            "separation", verdict.status, sep.LABELS.get(verdict.level or "", "n/a")))
        if verdict.status == "FAIL" and reviewer_identity and reviewer_identity in recorded:
            result.findings.append(CheckFinding(
                gate.producer or "producer", "REVIEWER IS THE PRODUCER",
                f"a reviewed artifact records produced_by.identity = {reviewer_identity},\n"
                f"which is the identity deciding this gate",
                "decide this gate from a separate session, model or provider"))

    if gate.kind == "human":
        # A human gate that passes on file presence alone proves only that files
        # exist. The thing it is named for is somebody having read them.
        attestation = (run.gate_record(gate_id) or {}).get("attestation")
        answers = (attestation or {}).get("answers") or []
        claims = {a["claim"] for a in answers if a.get("answered") == "yes"}
        outstanding = [c for c in gate.proves if c not in claims]
        result.attested_by = (attestation or {}).get("identity")
        result.checks.append(CheckResult(
            "decision", "PASS" if attestation and not outstanding else "FAIL",
            f"attested by {result.attested_by}" if attestation and not outstanding
            else ("no human decision recorded" if not attestation
                  else "not attested: " + "; ".join(outstanding))))
    elif gate.kind == "challenge" and require_decision:
        decision_errors = _challenge_decision_errors(run, kit, gate, record)
        result.decision_valid = not decision_errors
        outcome = (record or {}).get("outcome")
        if not decision_errors and outcome == "revise":
            decision_errors.append("reviewer requested revision")
        elif not decision_errors and outcome == "block":
            decision_errors.append("reviewer blocked the gate")
        result.checks.append(CheckResult(
            "decision", "FAIL" if decision_errors else "PASS",
            "; ".join(decision_errors) or (
                f"decided by {((record or {}).get('decided_by') or {}).get('identity')}"
            ),
        ))

    budget = run.meta.get("revisions", {}).get(
        gate_id, {"max": gate.max_revisions, "used": 0}
    )
    result.budget = (budget["used"], budget["max"])
    exhausted = budget["used"] >= budget["max"]
    # The budget is only as trustworthy as the file holding it.
    meta_edited = run.meta_mismatch
    if meta_edited:
        result.findings.append(CheckFinding(
            "meta.json", "META EDITED AFTER HASHING", meta_edited,
            "restore meta.json, or `rgraph seal` if you edited it on purpose"))
    result.checks.append(CheckResult(
        "budget", "FAIL" if exhausted or meta_edited else "PASS",
        meta_edited or f"{budget['max'] - budget['used']} of {budget['max']} attempts remain"))

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
    elif (
        not any(
            c.name in ("presence", "schema") and c.status == "FAIL"
            for c in result.checks
        )
        and any(c.name == "staleness" and c.status == "FAIL" for c in result.checks)
    ):
        result.status = "STALE"
    elif (
        len(failed) == 1
        and failed[0].name == "decision"
        and failed[0].detail in ("no human decision recorded", "no reviewer decision recorded")
    ):
        # Nothing is wrong; nobody has looked yet. Worth its own word, so that
        # "not decided" never reads as "found a problem".
        result.status = "AWAITING"
    elif (
        gate.kind == "challenge" and result.decision_valid
        and record and record.get("outcome") == "block"
    ):
        result.status = "BLOCKED"
    elif failed:
        result.status = "FAIL"
    elif result.separation and result.separation.status == "CAVEAT":
        result.status = "CAVEAT"

    if result.status in ("FAIL", "STALE"):
        result.reason = (
            record.get("reason")
            if gate.kind == "challenge" and record and record.get("reason")
            else _reason_for(gate, result)
        )
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
    reviewer = assignment_for(kit, gate.owner)
    producer = assignment_for(kit, gate.producer)
    outcome = {"PASS": "pass", "CAVEAT": "pass", "STALE": "revise", "AWAITING": "revise",
               "FAIL": "revise", "BLOCKED": "block"}[result.status]
    # A human gate is decided by whoever attested to it. Naming the reviewer
    # provider here would record a model as the person who read the artifact.
    decider = (
        {"role": "human", "identity": result.attested_by}
        if gate.kind == "human" and result.attested_by
        else {"role": "human", "identity": "human/unattested"} if gate.kind == "human"
        else {
            "role": "reviewer" if gate.kind == "challenge" else "human",
            "identity": reviewer.identity(kit.providers) if reviewer else "human/manual",
        }
    )
    return {
        "gate_id": result.gate_id,
        "outcome": outcome,
        "decided_at": now(),
        "decided_by": decider,
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
