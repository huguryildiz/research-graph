"""JSON-safe views shared by the local UI endpoints."""

from __future__ import annotations

from rgraph.commands.status import STAGE_ORDER, build_view
from rgraph.config import Kit
from rgraph.gates import GateResult, evaluate_gate
from rgraph.provenance import invalidated_gates, stale_artifacts, trace
from rgraph.run import Run
from rgraph.workflow import next_action, unit_state

BOUNDARY = "Scientific correctness was not determined."
GATE_ORDER = ("H1", "E1", "H2", "H3", "T1", "H4", "T2", "V1", "M1", "FINAL")


def gate_result_view(result: GateResult, kit: Kit, run: Run) -> dict:
    gate = kit.gates[result.gate_id]
    record = run.gate_record(gate.id)
    status = result.status
    if gate.kind == "release":
        if record is None:
            status = "AWAITING"
        elif record.get("outcome") in ("revise", "narrow"):
            status = "REVISION"
    return {
        "id": gate.id,
        "title": gate.title,
        "kind": gate.kind,
        "status": status,
        "owner": gate.owner,
        "inputs": list(gate.inputs),
        "proves": list(gate.proves),
        "outcome": record.get("outcome") if record else None,
        "decided_by": (record.get("decided_by") or {}).get("identity") if record else None,
        "budget": {"used": result.budget[0], "max": result.budget[1]},
        "separation": (
            {
                "level": result.separation.level,
                "status": result.separation.status,
                "label": (result.separation.level or "none").replace("_", " ").upper(),
            }
            if result.separation else None
        ),
        "checks": [
            {"name": item.name, "status": item.status, "detail": item.detail}
            for item in result.checks
        ],
        "findings": [
            {
                "artifact": item.ref,
                "code": item.code,
                "detail": item.detail,
                "fix": item.fix,
            }
            for item in result.findings
        ],
    }


def trace_view(run: Run, kit: Kit, claim_id: str) -> dict:
    chain = trace(run, kit, claim_id)
    claims = run.get("claim_evidence_map").body.get("claims", [])
    claim = next((item for item in claims if item.get("claim_id") == claim_id), None)
    return {
        "claim_id": claim_id,
        "text": claim.get("text") if claim else None,
        "complete": chain.complete,
        "links": [
            {"label": link.label, "detail": link.detail, "status": link.status}
            for link in chain.links
        ],
        "missing": chain.missing,
        "boundary": BOUNDARY,
    }


def state_view(run: Run, kit: Kit) -> dict:
    stale = stale_artifacts(run)
    retired = invalidated_gates(run, kit)
    status = build_view(run, kit)
    action = next_action(run, kit)
    gates = [
        gate_result_view(evaluate_gate(run, kit, gate_id), kit, run)
        for gate_id in GATE_ORDER if gate_id in kit.gates
    ]
    units = []
    for unit in kit.graph.units():
        units.append({
            "id": unit.id,
            "title": unit.title,
            "stage": unit.stage,
            "role": unit.role_name,
            "state": unit_state(run, unit, stale),
            "produces": list(unit.produces),
        })
    artifacts = []
    for artifact in run.artifacts.values():
        if not artifact.present:
            state = "PENDING"
        elif artifact.errors:
            state = "INVALID"
        elif artifact.id in stale:
            state = "STALE"
        else:
            state = "VALID"
        artifacts.append({
            "id": artifact.id,
            "state": state,
            "path": str(artifact.path.relative_to(run.root)),
            "identity": artifact.identity,
            "causes": stale.get(artifact.id, []),
            "errors": [
                {"path": error.path, "message": error.message}
                for error in artifact.errors[:5]
            ],
        })
    claims = [
        {"id": item.get("claim_id"), "text": item.get("text", "")}
        for item in run.get("claim_evidence_map").body.get("claims", [])
    ]
    edges = [
        {
            "from": edge.frm,
            "to": edge.to,
            "kind": edge.kind,
            "carries": list(edge.carries),
        }
        for edge in kit.graph.edges
        if edge.frm in {item["id"] for item in units} | set(kit.gates)
        and edge.to in {item["id"] for item in units} | set(kit.gates)
    ]
    return {
        "boundary": BOUNDARY,
        "read_only": run.read_only,
        "run": {
            "id": status.run_id,
            "question": status.question,
            "mode": status.mode,
            "protocol": status.protocol,
            "provenance": run.meta.get("provenance", "recorded"),
            "root": str(run.root.resolve()),
            "revision_line": status.revision_line,
        },
        "summary": {
            "units_complete": status.units_complete,
            "units_total": len(units),
            "artifacts": {
                "valid": status.artifact_counts[0],
                "stale": status.artifact_counts[1],
                "pending": status.artifact_counts[2],
            },
            "last_gate": status.last_gate,
        },
        "stages": [
            {"id": stage, "status": dict(status.stages).get(stage, "WAIT")}
            for stage in STAGE_ORDER
        ],
        "units": units,
        "gates": gates,
        "artifacts": artifacts,
        "claims": claims,
        "edges": edges,
        "invalidated_gates": retired,
        "next_action": {
            "kind": action.kind,
            "target": action.target,
            "command": action.command,
            "detail": action.detail,
        },
    }
