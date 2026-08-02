"""`rgraph challenge <GATE>` — one attributable reviewer invocation.

The verifier and the reviewer do different jobs.  Local checks recompute
schemas, hashes and declared content contracts; a configured provider reads the
gate inputs and returns a bounded decision proposal.  Only this command joins
the two and writes the canonical gate record.
"""

from __future__ import annotations

import json
import os
import pathlib
import uuid

from rgraph.config import ConfigError
from rgraph.gates import assignment_for, evaluate_gate, now, record_from
from rgraph.hashing import file_hash
from rgraph.render import (
    body_text, console, key_value, muted, render_error, render_gate_result,
    render_next_action, render_provenance_notice, section,
)
from rgraph.reviewer import END, START, allowed_reasons, decision_hash, parse_decision
from rgraph.run import RunError, load_run
from rgraph.runner import Plan, build_argv, execute_capture
from rgraph.schemas import registry

BLOCKING_LOCAL_CHECKS = frozenset({
    "presence", "schema", "provenance", "separation", "budget",
})


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "challenge",
        help="run the assigned reviewer for one challenge gate",
        description=(
            "Invoke exactly one assigned reviewer CLI, validate its structured "
            "decision, and bind the gate record to the current artifact hashes "
            "and captured provider log."
        ),
        epilog=(
            "Examples:\n"
            "  rgraph challenge E1\n"
            "  rgraph challenge V1 --online"
        ),
    )
    parser.add_argument("gate", help="challenge gate id, e.g. E1")
    parser.add_argument("--online", action="store_true", help="resolve DOIs over the network")
    parser.add_argument(
        "--force", action="store_true",
        help="run one fresh review even when the current challenge already passes",
    )
    parser.set_defaults(handler=handle)


def _reviewer_role_path(kit) -> pathlib.Path:
    node = kit.graph.nodes.get("reviewer")
    if node is None or not node.role:
        raise ConfigError("graph.yaml has no reviewer role contract")
    path = kit.root / node.role
    if not path.is_file():
        raise ConfigError(f"reviewer role contract is missing: {path}")
    return path


def _artifact_lines(run, gate) -> list[str]:
    lines: list[str] = []
    for artifact_id in gate.inputs:
        artifact = run.get(artifact_id)
        lines.append(
            f"- {artifact_id}: {artifact.path.resolve()} [{artifact.content_hash}]"
        )
        if artifact.payload_path is not None:
            lines.append(f"  payload: {artifact.payload_path.resolve()}")
    return lines


def _prompt(run, kit, gate, identity: str, local_result) -> tuple[str, pathlib.Path]:
    role_path = _reviewer_role_path(kit)
    local_lines = [
        f"- {check.name}: {check.status} — {check.detail}"
        for check in local_result.checks
    ]
    finding_lines = [
        f"- {finding.ref} / {finding.code}: {finding.detail} | fix: {finding.fix}"
        for finding in local_result.findings
    ] or ["- none"]
    role_text = role_path.read_text(encoding="utf-8")
    reasons = allowed_reasons(kit, gate.id)
    prompt = f"""# research-graph challenge invocation
# gate: {gate.id} / {gate.title}
# assigned reviewer identity: {identity}
# run directory: {run.root.resolve()}

You are the read-only reviewer for exactly this gate. Read the files listed
below. Do not edit, create, delete, seal, or rename any file. Do not run
`rgraph check`, `rgraph challenge`, `rgraph decide`, or `rgraph review`.
The host has already run its deterministic checks; those results are context,
not a substitute for your review. A local FAIL may not be returned as PASS.

Gate inputs (the hashes below are the decision boundary):
{chr(10).join(_artifact_lines(run, gate))}

Local checks:
{chr(10).join(local_lines)}

Local findings:
{chr(10).join(finding_lines)}

Return exactly one JSON object between the two literal markers below. Do not
wrap it in a Markdown fence and do not write a gate record yourself.

{START}
{{
  "outcome": "pass|revise|block",
  "reason": null,
  "checks": [{{"name": "review scope", "status": "PASS", "detail": "what was examined"}}],
  "findings": [{{"ref": "artifact or locator", "code": "SHORT CODE", "detail": "specific defect", "fix": "specific correction"}}]
}}
{END}

For `pass`, reason must be null and no check may be FAIL. For `revise`, name an
allowed reason and include at least one FAIL check. The only typed reason(s)
this gate can carry: {', '.join(reasons)}. Findings may be empty on pass.

The decision establishes only the gate conditions in gates.yaml. It does not
establish scientific correctness, epistemic independence, or fitness for
deployment.

--- reviewer role contract ---
{role_text}
"""
    return prompt, role_path


def _run_snapshot(root: pathlib.Path) -> dict[str, str]:
    """Integrity-bearing run files, excluding append-only provider logs."""
    snapshot: dict[str, str] = {}
    if not root.exists():
        return snapshot
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] == "logs":
            continue
        snapshot[relative.as_posix()] = file_hash(path)
    return snapshot


def _changed(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(
        name for name in before.keys() | after.keys()
        if before.get(name) != after.get(name)
    )


def _build_record(
    run, kit, gate, readiness, decision, plan, prompt_path, invocation, started_at, role_path,
):
    assignment = assignment_for(kit, gate.owner)
    identity = assignment.identity(kit.providers)
    record = record_from(readiness, run, kit)
    record["outcome"] = decision["outcome"]
    record["reason"] = decision["reason"]
    record["decided_at"] = now()
    record["decided_by"] = {
        "role": "reviewer",
        "identity": identity,
        "provider": assignment.provider,
        "model": assignment.model,
    }
    record["checks"] += [
        {
            "name": f"reviewer:{item['name']}",
            "status": item["status"],
            "detail": item["detail"],
        }
        for item in decision["checks"]
    ]
    record["findings"] += decision["findings"]
    relative_log = plan.log_path.relative_to(run.root).as_posix()
    record["decision_provenance"] = {
        "mode": "cli",
        "provider": assignment.provider,
        "model": assignment.model,
        "effort": assignment.effort,
        "argv": plan.argv,
        "invocation_id": invocation,
        "started_at": started_at,
        "finished_at": record["decided_at"],
        "exit_code": 0,
        "log": relative_log,
        "log_sha256": file_hash(plan.log_path),
        "prompt": prompt_path.relative_to(run.root).as_posix(),
        "prompt_sha256": file_hash(prompt_path),
        "role_contract_sha256": file_hash(role_path),
        "decision_sha256": decision_hash(decision),
    }
    return record


def handle(args) -> int:
    from rgraph.commands.check import load_for_run

    active = os.environ.get("RGRAPH_ACTIVE_INVOCATION")
    if active:
        render_error(
            f"challenge cannot run from active provider invocation {active!r}; "
            "return control to the host first"
        )
        return 2
    try:
        kit, run = load_for_run(args)
    except (ConfigError, RunError) as exc:
        render_error(str(exc))
        return 2
    gate = kit.gates.get(args.gate)
    if gate is None:
        render_error(f"unknown gate '{args.gate}'; expected one of {', '.join(kit.gates)}")
        return 2
    if gate.kind != "challenge":
        render_error(
            f"{gate.id} is a {gate.kind} gate; challenge gates are "
            + ", ".join(g.id for g in kit.gates.values() if g.kind == "challenge")
        )
        return 2
    if run.read_only:
        render_error("the bundled example-run is read-only; copy it before running a reviewer")
        return 2

    current = evaluate_gate(run, kit, gate.id, online=args.online)
    existing = run.gate_record(gate.id)
    if existing and current.status in ("PASS", "CAVEAT") and not args.force:
        render_provenance_notice(run)
        render_gate_result(current, gate)
        muted("This challenge already has a current reviewer decision; no provider was called.")
        return 0
    if existing and existing.get("outcome") in ("revise", "block") \
            and not args.force \
            and current.status != "STALE" and current.decision_valid:
        render_provenance_notice(run)
        render_gate_result(current, gate)
        return 1

    readiness = evaluate_gate(
        run, kit, gate.id, online=args.online, require_decision=False,
    )
    blocking = [
        check for check in readiness.checks
        if check.name in BLOCKING_LOCAL_CHECKS and check.status == "FAIL"
    ]
    if blocking:
        render_provenance_notice(run)
        render_gate_result(readiness, gate, show_next=False)
        body_text("Reviewer not started: the gate inputs or assignment are not usable.")
        muted(f"Fix the failed local checks, then run `rgraph challenge {gate.id}`.")
        return 1

    assignment = assignment_for(kit, gate.owner)
    if assignment is None:
        render_error(f"no assignment for challenge owner '{gate.owner}'")
        return 2
    provider = kit.providers[assignment.provider]
    if provider.kind != "cli":
        render_error(
            f"{assignment.provider}/{assignment.model} is manual; this public-beta "
            "command can only attribute a decision to a CLI it actually launches"
        )
        muted("Assign a logged-in CLI reviewer, run `rgraph doctor`, then retry.")
        return 2

    identity = assignment.identity(kit.providers)
    try:
        prompt, role_path = _prompt(run, kit, gate, identity, readiness)
    except ConfigError as exc:
        render_error(str(exc))
        return 2
    invocation = str(uuid.uuid4())
    plan = Plan(
        unit=f"challenge-{gate.id}",
        role_path=role_path,
        provider=assignment.provider,
        model=assignment.model,
        argv=build_argv(provider, assignment),
        stdin_text=prompt,
        inputs=[(artifact_id, "VALID") for artifact_id in gate.inputs],
        log_path=run.root / "logs" / f"review-{gate.id}-{invocation}.log",
        cwd=run.root.parent,
    )

    render_provenance_notice(run)
    section(f"Reviewer challenge {gate.id}")
    key_value("Identity", identity)
    key_value("Provider", assignment.provider)
    key_value("Model", assignment.model)
    key_value("Inputs", f"{len(gate.inputs)} current artifact hashes")
    body_text("Starting exactly one reviewer CLI invocation.")
    console.print()

    before = _run_snapshot(run.root)
    started_at = now()
    prompt_path = run.root / "logs" / f"review-{gate.id}-{invocation}.prompt.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(plan.stdin_text, encoding="utf-8")
    execution = execute_capture(plan, verbose=args.verbose)
    after = _run_snapshot(run.root)
    changed = _changed(before, after)
    if changed:
        render_error(
            "reviewer modified the read-only run boundary: " + ", ".join(changed[:8])
        )
        muted(f"No gate record was written. Inspect {plan.log_path} and restore intentionally.")
        return 2
    if execution.exit_code != 0:
        render_error(f"reviewer CLI exited {execution.exit_code}; no gate record was written")
        muted(f"Provider log: {plan.log_path}")
        return 2

    decision, error = parse_decision(execution.output, kit)
    if error:
        render_error(error)
        muted(f"No gate record was written. Provider log: {plan.log_path}")
        return 2
    reasons = allowed_reasons(kit, gate.id)
    if decision["outcome"] == "revise" and decision["reason"] not in reasons:
        render_error(
            f"reviewer reason {decision['reason']!r} is not a typed return from "
            f"{gate.id}; expected {', '.join(reasons)}"
        )
        muted(f"No gate record was written. Provider log: {plan.log_path}")
        return 2
    local_failures = [
        check.name for check in readiness.checks
        if check.status == "FAIL" and check.name != "staleness"
    ]
    if decision["outcome"] == "pass" and local_failures:
        render_error(
            "reviewer returned pass while local checks fail: " + ", ".join(local_failures)
        )
        muted(f"No gate record was written. Provider log: {plan.log_path}")
        return 2

    record = _build_record(
        run, kit, gate, readiness, decision, plan, prompt_path, invocation, started_at,
        role_path,
    )
    record_errors = registry(kit.root).validate("gate_record", record)
    if record_errors:
        first = record_errors[0]
        render_error(f"generated gate record is invalid: {first.path}: {first.message}")
        return 2
    path = run.write_gate_record(record)

    verified = evaluate_gate(load_run(run.root, kit), kit, gate.id, online=args.online)
    render_gate_result(verified, gate, show_next=False)
    key_value("Record", path)
    key_value("Provider log", plan.log_path)
    console.print()
    if verified.status in ("PASS", "CAVEAT"):
        render_next_action("rgraph status")
        return 0
    if verified.status == "BLOCKED":
        return 1
    render_next_action(f"rgraph revise {gate.id}")
    return 1
