"""JSON-safe views shared by the local UI endpoints.

Every value here is either read from the run or computed by the same functions
the CLI uses. Nothing is phrased more confidently than what produced it: a gate
carries its plain-English title beside its code, a work unit's state says what
was observed rather than what was clicked, and the claim boundary travels with
every gate surface.
"""

from __future__ import annotations

import pathlib

from rgraph.commands.status import STAGE_ORDER, build_view
from rgraph.config import ROLES, Kit
from rgraph.gates import GateResult, evaluate_gate
from rgraph.provenance import invalidated_gates, stale_artifacts, trace
from rgraph.run import Run
from rgraph.separation import level_for
from rgraph.services.install import installation
from rgraph.workflow import (
    next_action,
    next_checkpoint,
    ordered_workflow,
    prerequisite_action,
    unit_state,
)

BOUNDARY = "Scientific correctness was not determined."
MECHANICAL_LIMIT = "Mechanical checks establish only their declared conditions."
GATE_ORDER = ("H1", "E1", "H2", "H3", "T1", "H4", "T2", "V1", "M1", "FINAL")

STAGE_TITLES = {
    "retrieve": "Find the literature",
    "plan": "Register hypotheses and design",
    "execute": "Write and run the code",
    "verify": "Reproduce and re-check",
    "write": "Draw figures and write it up",
    "audit": "Review",
}

# What every state on a work unit means, in words a reader who has never seen
# this tool can act on. A code without one of these lines must not be shown.
UNIT_STATE_MEANING = {
    "BLOCKED": "Something earlier in the study has to finish first.",
    "READY": "This can run now.",
    "APPROVAL REQUIRED": "You have opened a plan for this; approve it to start.",
    "QUEUED": "Accepted and waiting for its process to start.",
    "RUNNING": "A provider process is running right now.",
    "VALIDATING": "The process has exited; its files are being checked.",
    "REVIEW": "Its outputs exist and the next checkpoint is waiting on a decision.",
    "COMPLETE": "Its declared outputs exist, validate, and match their recorded run.",
    "FAILED": "The last attempt did not produce acceptable outputs.",
    "CANCELLED": "The last attempt was stopped before it finished.",
    "STALE": "Something it depends on changed after it ran.",
    "INTERRUPTED": "An earlier server started this and its outcome cannot be observed.",
}

GATE_STATUS_MEANING = {
    "PASS": "The declared conditions held.",
    "CAVEAT": "The conditions held, at a weaker producer/reviewer separation than preferred.",
    "AWAITING": "Nobody has answered yet. This is not a problem that was found.",
    "STALE": "It passed once, but a file it was decided on has changed since.",
    "BLOCKED": "The revision budget is spent; this needs narrowing, escalation or a stop.",
    "REVISION": "A decision returned work to an earlier unit.",
    "FAIL": "At least one declared condition did not hold.",
}


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
        "status_meaning": GATE_STATUS_MEANING.get(status, ""),
        "criterion": gate.criterion,
        "owner": gate.owner,
        "inputs": list(gate.inputs),
        "proves": list(gate.proves),
        "requires": list(gate.requires),
        "outcome": record.get("outcome") if record else None,
        "decided_by": (record.get("decided_by") or {}).get("identity") if record else None,
        "decided_at": record.get("decided_at") if record else None,
        "human": gate.kind in ("human", "release"),
        "budget": {"used": result.budget[0], "max": result.budget[1]},
        "boundary": BOUNDARY,
        "mechanical_limit": MECHANICAL_LIMIT,
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


def human_decision_view(gate_id: str, kit: Kit, run: Run, result: GateResult) -> dict:
    """What a person needs in front of them before they answer a human gate.

    The command is the boundary, not a convenience: research-graph records a
    human decision only from a real terminal prompt, and this screen is the
    handoff to it.
    """
    gate = kit.gates[gate_id]
    record = run.gate_record(gate_id)
    approvals = run.get("governance_record").body.get("approvals", [])
    responsible = approvals[0].get("name") if approvals else None
    command = (
        f"rgraph --run {run.root} review" if gate.kind == "release"
        else f"rgraph --run {run.root} decide {gate_id}"
    )
    return {
        "gate": gate_id,
        "title": gate.title,
        "criterion": gate.criterion,
        "attestations": list(gate.proves),
        "checked": [
            {"name": item.name, "status": item.status, "detail": item.detail}
            for item in result.checks if item.name != "decision"
        ],
        "not_checked": [
            "Whether the recorded scope is the right scope for this question.",
            "Whether the evidence actually supports the reading it is given.",
            BOUNDARY,
        ],
        "responsible": responsible,
        "state": record.get("outcome") if record else "AWAITING",
        "command": command,
        "why_terminal": (
            "A human gate is answered by a named person at a terminal. A button, a "
            "file, or an agent's output cannot stand in for that, so research-graph "
            "will not record one here — this handoff is the integrity boundary."
        ),
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


def _unit_control_state(run: Run, kit: Kit, unit, stale: dict, job) -> str:
    """The state to show, derived from what was observed and never from a click."""
    if job is not None and job.get("active"):
        return job["state"]
    base = unit_state(run, unit, stale)
    if base == "PASS":
        return "COMPLETE"
    if base == "STALE":
        return "STALE"
    if job is not None and job["state"] in ("FAILED", "CANCELLED", "INTERRUPTED"):
        return job["state"]
    if prerequisite_action(run, kit, unit) is not None:
        return "BLOCKED"
    if base == "READY":
        return "REVIEW"
    return "READY"


def _assignment_for_role(kit: Kit, role: str | None) -> dict | None:
    if role is None:
        return None
    assignment = kit.assignment.get(role)
    if assignment is None:
        return {"role": role, "provider": None, "model": None, "identity": None}
    return {
        "role": role,
        "provider": assignment.provider,
        "model": assignment.model,
        "effort": assignment.effort,
        "identity": (
            assignment.identity(kit.providers)
            if assignment.provider in kit.providers else None
        ),
    }


def unit_view(run: Run, kit: Kit, unit, stale: dict, job: dict | None) -> dict:
    state = _unit_control_state(run, kit, unit, stale, job)
    return {
        "id": unit.id,
        "title": unit.title,
        "stage": unit.stage,
        "stage_title": STAGE_TITLES.get(unit.stage, unit.stage or ""),
        "role": unit.role_name,
        "state": state,
        "state_meaning": UNIT_STATE_MEANING.get(state, ""),
        "produces": list(unit.produces),
        "assignment": _assignment_for_role(kit, unit.role_name),
        "next_gate": next_checkpoint(kit, unit.id),
        "job": job,
    }


def unit_detail_view(run: Run, kit: Kit, unit_id: str, job: dict | None = None) -> dict:
    """Everything the control room shows about one work unit, without running it."""
    from rgraph.runner import required_inputs

    unit = kit.graph.nodes.get(unit_id)
    if unit is None or not unit.is_unit:
        raise KeyError(unit_id)
    stale = stale_artifacts(run)
    body = unit_view(run, kit, unit, stale, job)
    blocked = prerequisite_action(run, kit, unit)
    inputs = []
    for artifact_id in required_inputs(kit, unit_id):
        artifact = run.artifacts.get(artifact_id)
        inputs.append({
            "id": artifact_id,
            "state": (
                "MISSING" if artifact is None or not artifact.present
                else "INVALID" if artifact.errors
                else "STALE" if artifact_id in stale else "VALID"
            ),
            "content_hash": artifact.content_hash if artifact is not None else None,
            "producer": (
                kit.graph.producer_of(artifact_id).id
                if kit.graph.producer_of(artifact_id) else None
            ),
        })
    outputs = []
    for artifact_id in unit.produces:
        artifact = run.artifacts[artifact_id]
        outputs.append({
            "id": artifact_id,
            "path": str(artifact.path.relative_to(run.root)),
            "present": artifact.present,
            "payload": (
                str(artifact.payload_path.relative_to(run.root))
                if artifact.payload_path is not None else None
            ),
        })
    gate_id = next_checkpoint(kit, unit_id)
    record = run.execution_record(unit_id)
    prerequisites = [
        edge.frm for edge in kit.graph.in_edges(unit_id) if edge.kind != "return"
    ]
    body.update({
        "blocked_reason": blocked.detail if blocked is not None else None,
        "blocked_command": blocked.command if blocked is not None else None,
        "prerequisites": prerequisites,
        "inputs": inputs,
        "outputs": outputs,
        "downstream_gate": (
            {"id": gate_id, "title": kit.gates[gate_id].title}
            if gate_id in kit.gates else None
        ),
        "last_execution": (
            {
                "outcome": record.get("outcome"),
                "finished_at": record.get("finished_at"),
                "exit_code": record.get("exit_code"),
                "log": record.get("log"),
                "problems": record.get("problems", []),
            }
            if record else None
        ),
        "logs_directory": str((run.root / "logs").resolve()),
    })
    return body


def map_view(kit: Kit) -> dict:
    """The spine of the study: every work unit and checkpoint in production order.

    The order is derived from the graph by the same function the workflow uses,
    so a node added to graph.yaml appears here without anyone editing a list.
    A checkpoint carries the stage of the work it closes, which is what a reader
    scanning for "where am I" is actually looking for; a checkpoint that opens
    the study takes the stage of the first unit that follows it.
    """
    order = ordered_workflow(kit)
    stages: dict[str, str | None] = {}
    carried: str | None = None
    for node_id in order:
        node = kit.graph.nodes.get(node_id)
        if node is not None and node.is_unit:
            carried = node.stage
        stages[node_id] = carried
    opening = next((stage for stage in stages.values() if stage), None)
    spine = [
        {
            "id": node_id,
            "kind": "gate" if node_id in kit.gates else "unit",
            "stage": stages[node_id] or opening,
        }
        for node_id in order
    ]
    returns = [
        {
            "from": edge.frm,
            "to": edge.to,
            "carries": edge.carries[0] if edge.carries else None,
            "budget": (
                edge.budget if edge.budget is not None
                else kit.gates[edge.frm].max_revisions
            ),
        }
        for edge in kit.graph.edges
        if edge.kind == "return" and edge.frm in kit.gates
    ]
    return {"spine": spine, "returns": returns}


def state_view(run: Run, kit: Kit, jobs_by_unit: dict | None = None,
               job_records: list[dict] | None = None) -> dict:
    jobs_by_unit = jobs_by_unit or {}
    stale = stale_artifacts(run)
    retired = invalidated_gates(run, kit)
    status = build_view(run, kit)
    action = next_action(run, kit)
    results = {
        gate_id: evaluate_gate(run, kit, gate_id)
        for gate_id in GATE_ORDER if gate_id in kit.gates
    }
    gates = [gate_result_view(results[gate_id], kit, run) for gate_id in results]
    units = [
        unit_view(run, kit, unit, stale, jobs_by_unit.get(unit.id))
        for unit in kit.graph.units()
    ]
    artifacts = []
    for artifact in run.artifacts.values():
        # Order matters: a file that exists but will not parse has no document,
        # and reporting that as "not written yet" would hide a real defect.
        if artifact.errors:
            state = "INVALID"
        elif not artifact.present:
            state = "PENDING"
        elif artifact.id in stale:
            state = "STALE"
        else:
            state = "VALID"
        producer = kit.graph.producer_of(artifact.id)
        artifacts.append({
            "id": artifact.id,
            "state": state,
            "path": str(artifact.path.relative_to(run.root)),
            "identity": artifact.identity,
            "producer": producer.id if producer else None,
            "content_hash": artifact.content_hash,
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
    unit_ids = {item["id"] for item in units}
    edges = [
        {
            "from": edge.frm,
            "to": edge.to,
            "kind": edge.kind,
            "carries": list(edge.carries),
        }
        for edge in kit.graph.edges
        if edge.frm in unit_ids | set(kit.gates) and edge.to in unit_ids | set(kit.gates)
    ]
    awaiting = next(
        (
            gate["id"] for gate in gates
            if gate["human"] and gate["status"] in ("AWAITING", "STALE", "FAIL")
        ),
        None,
    )
    approvals = run.get("governance_record").body.get("approvals", [])
    execution = kit.assignment.get("execution")
    reviewer = kit.assignment.get("reviewer")
    return {
        "boundary": BOUNDARY,
        "mechanical_limit": MECHANICAL_LIMIT,
        "read_only": run.read_only,
        "run": {
            "id": status.run_id,
            "question": status.question,
            "mode": status.mode,
            "protocol": status.protocol,
            "provenance": run.meta.get("provenance", "recorded"),
            "root": str(run.root.resolve()),
            "revision_line": status.revision_line,
            "responsible": approvals[0].get("name") if approvals else None,
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
            "stage": next(
                (unit["stage_title"] for unit in units if unit["state"] != "COMPLETE"),
                "Complete",
            ),
        },
        "stages": [
            {
                "id": stage,
                "title": STAGE_TITLES.get(stage, stage),
                "status": dict(status.stages).get(stage, "WAIT"),
            }
            for stage in STAGE_ORDER
        ],
        "map": map_view(kit),
        "units": units,
        "gates": gates,
        "artifacts": artifacts,
        "claims": claims,
        "edges": edges,
        "invalidated_gates": retired,
        "revisions": run.meta.get("revisions", {}),
        "assignment": [
            _assignment_for_role(kit, role) for role in ROLES
        ],
        "separation": (
            {
                "level": level_for(execution, reviewer),
                "label": level_for(execution, reviewer).replace("_", " ").upper(),
                "between": "execution and reviewer",
            }
            if execution is not None and reviewer is not None else None
        ),
        "human_decision": (
            human_decision_view(awaiting, kit, run, results[awaiting])
            if awaiting else None
        ),
        "jobs": job_records or [],
        "install": installation(kit.root, run.root),
        "next_action": {
            "kind": action.kind,
            "target": action.target,
            "command": action.command,
            "detail": action.detail,
            "title": _action_title(action, kit),
        },
    }


def _action_title(action, kit: Kit) -> str:
    """The next step in a sentence, with any gate code carrying its own title."""
    if action.target in kit.gates:
        gate = kit.gates[action.target]
        verbs = {
            "decide": f"Record a human decision on {gate.id} — {gate.title}",
            "challenge": f"Run the assigned reviewer for {gate.id} — {gate.title}",
            "revise": f"Return work from {gate.id} — {gate.title}",
            "check": f"Verify {gate.id} — {gate.title}",
            "review": f"Record the release decision — {gate.title}",
            "blocked": f"{gate.id} — {gate.title} is blocked",
            "complete": "The run is closed",
        }
        return verbs.get(action.kind, f"{gate.id} — {gate.title}")
    node = kit.graph.nodes.get(action.target) if action.target else None
    if node is not None:
        return f"Run {node.id} — {node.title}"
    if action.kind == "setup":
        return "Finish the study setup"
    return action.detail


def launcher_view(root: pathlib.Path, run: pathlib.Path | None, recent: list[dict],
                  default_destination: pathlib.Path) -> dict:
    """What the browser shows before a study is chosen."""
    selected = None
    if run is not None and (pathlib.Path(run) / "meta.json").is_file():
        selected = str(pathlib.Path(run).resolve())
    here = pathlib.Path.cwd() / "run"
    return {
        "mode": "workspace" if selected else "launcher",
        "run": selected,
        "cwd": str(pathlib.Path.cwd()),
        "here": {
            "path": str(here.resolve()),
            "exists": (here / "meta.json").is_file(),
        },
        "default_destination": str(default_destination),
        "recent": recent,
        "install": installation(root, run),
        "boundary": BOUNDARY,
    }
