"""One attributable reviewer invocation, split into prepare / begin / accept.

`rgraph challenge` runs the three in a row and prints between them. The browser
runs the same three around a background child process. Neither can write a gate
record by another route, because only `accept` builds one, and it refuses for
exactly the reasons the terminal path refuses.
"""

from __future__ import annotations

import pathlib
import uuid
from dataclasses import dataclass, field

from rgraph.config import ConfigError, Gate, Kit
from rgraph.gates import GateResult, assignment_for, evaluate_gate, now, record_from
from rgraph.hashing import file_hash
from rgraph.reviewer import END, START, allowed_reasons, decision_hash, parse_decision
from rgraph.run import Run, load_run
from rgraph.runner import Plan, build_argv
from rgraph.schemas import registry

BLOCKING_LOCAL_CHECKS = frozenset({
    "presence", "schema", "provenance", "separation", "budget",
})


class ChallengeError(Exception):
    """A refusal a caller should show verbatim; no reviewer was started.

    `kind` says what sort of refusal it is, because the terminal answers each
    one differently: `config` is a usage error, `current` means the gate already
    holds a decision, `decided` means it holds one that returns work, and
    `not_ready` means the local checks must pass first. `result` carries the
    gate evaluation a caller may want to draw.
    """

    def __init__(self, message: str, *, kind: str = "config", result=None) -> None:
        super().__init__(message)
        self.kind = kind
        self.result = result


@dataclass
class Preparation:
    gate: Gate
    plan: Plan
    readiness: GateResult
    role_path: pathlib.Path
    invocation: str
    identity: str
    prompt_path: pathlib.Path
    started_at: str | None = None
    snapshot: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Acceptance:
    status: str
    record_path: pathlib.Path | None
    error: str | None
    exit_code: int


def reviewer_role_path(kit: Kit) -> pathlib.Path:
    node = kit.graph.nodes.get("reviewer")
    if node is None or not node.role:
        raise ConfigError("graph.yaml has no reviewer role contract")
    path = kit.root / node.role
    if not path.is_file():
        raise ConfigError(f"reviewer role contract is missing: {path}")
    return path


def _artifact_lines(run: Run, gate: Gate) -> list[str]:
    lines: list[str] = []
    for artifact_id in gate.inputs:
        artifact = run.get(artifact_id)
        lines.append(
            f"- {artifact_id}: {artifact.path.resolve()} [{artifact.content_hash}]"
        )
        if artifact.payload_path is not None:
            lines.append(f"  payload: {artifact.payload_path.resolve()}")
    return lines


def build_prompt(
    run: Run, kit: Kit, gate: Gate, identity: str, local_result: GateResult,
) -> tuple[str, pathlib.Path]:
    role_path = reviewer_role_path(kit)
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


def run_snapshot(root: pathlib.Path) -> dict[str, str]:
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


def changed_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(
        name for name in before.keys() | after.keys()
        if before.get(name) != after.get(name)
    )


def prepare(
    run: Run, kit: Kit, gate_id: str, *, online: bool = False, force: bool = False,
) -> Preparation:
    """Everything decided before a reviewer may be started. Writes nothing."""
    gate = kit.gates.get(gate_id)
    if gate is None:
        raise ChallengeError(
            f"unknown gate '{gate_id}'; expected one of {', '.join(kit.gates)}"
        )  # kind defaults to config
    if gate.kind != "challenge":
        raise ChallengeError(
            f"{gate.id} is a {gate.kind} gate; challenge gates are "
            + ", ".join(g.id for g in kit.gates.values() if g.kind == "challenge")
        )
    if run.read_only:
        raise ChallengeError(
            "the bundled example-run is read-only; copy it before running a reviewer",
            kind="read_only",
        )
    current = evaluate_gate(run, kit, gate.id, online=online)
    existing = run.gate_record(gate.id)
    if existing and current.status in ("PASS", "CAVEAT") and not force:
        raise ChallengeError(
            f"{gate.id} already has a current reviewer decision; no provider was called.",
            kind="current", result=current,
        )
    if (
        existing and existing.get("outcome") in ("revise", "block") and not force
        and current.status != "STALE" and current.decision_valid
    ):
        raise ChallengeError(
            f"{gate.id} already carries a current reviewer decision to "
            f"{existing.get('outcome')}; resolve it before asking again.",
            kind="decided", result=current,
        )

    readiness = evaluate_gate(run, kit, gate.id, online=online, require_decision=False)
    blocking = [
        check for check in readiness.checks
        if check.name in BLOCKING_LOCAL_CHECKS and check.status == "FAIL"
    ]
    if blocking:
        raise ChallengeError(
            "Reviewer not started: "
            + ", ".join(check.name for check in blocking)
            + " must pass first.",
            kind="not_ready", result=readiness,
        )

    assignment = assignment_for(kit, gate.owner)
    if assignment is None:
        raise ChallengeError(f"no assignment for challenge owner '{gate.owner}'")
    provider = kit.providers.get(assignment.provider)
    if provider is None:
        raise ChallengeError(
            f"role '{gate.owner}' is assigned to unknown provider '{assignment.provider}'"
        )
    if provider.kind != "cli":
        raise ChallengeError(
            f"{assignment.provider}/{assignment.model} is manual; a decision can only "
            "be attributed to a CLI research-graph actually launches."
        )

    identity = assignment.identity(kit.providers)
    try:
        prompt, role_path = build_prompt(run, kit, gate, identity, readiness)
    except ConfigError as exc:
        raise ChallengeError(str(exc)) from exc
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
        invocation_id=invocation,
    )
    return Preparation(
        gate=gate, plan=plan, readiness=readiness, role_path=role_path,
        invocation=invocation, identity=identity,
        prompt_path=run.root / "logs" / f"review-{gate.id}-{invocation}.prompt.md",
    )


def begin(prep: Preparation, run: Run) -> Preparation:
    """Write the prompt beside the log and record the pre-invocation state."""
    prep.prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prep.prompt_path.write_text(prep.plan.stdin_text, encoding="utf-8")
    prep.snapshot = run_snapshot(run.root)
    prep.started_at = now()
    return prep


def _build_record(run: Run, kit: Kit, prep: Preparation, decision: dict) -> dict:
    assignment = assignment_for(kit, prep.gate.owner)
    record = record_from(prep.readiness, run, kit)
    record["outcome"] = decision["outcome"]
    record["reason"] = decision["reason"]
    record["decided_at"] = now()
    record["decided_by"] = {
        "role": "reviewer",
        "identity": prep.identity,
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
    record["decision_provenance"] = {
        "mode": "cli",
        "provider": assignment.provider,
        "model": assignment.model,
        "effort": assignment.effort,
        "argv": prep.plan.argv,
        "invocation_id": prep.invocation,
        "started_at": prep.started_at,
        "finished_at": record["decided_at"],
        "exit_code": 0,
        "log": prep.plan.log_path.relative_to(run.root).as_posix(),
        "log_sha256": file_hash(prep.plan.log_path),
        "prompt": prep.prompt_path.relative_to(run.root).as_posix(),
        "prompt_sha256": file_hash(prep.prompt_path),
        "role_contract_sha256": file_hash(prep.role_path),
        "decision_sha256": decision_hash(decision),
    }
    return record


def accept(
    run: Run, kit: Kit, prep: Preparation, *, exit_code: int, output: str,
    online: bool = False,
) -> Acceptance:
    """Judge one finished reviewer invocation and write a record only if it holds."""
    after = run_snapshot(run.root)
    changed = changed_paths(prep.snapshot, after)
    if changed:
        return Acceptance(
            "FAIL", None,
            "reviewer modified the read-only run boundary: " + ", ".join(changed[:8]),
            exit_code,
        )
    if exit_code != 0:
        return Acceptance(
            "FAIL", None,
            f"reviewer CLI exited {exit_code}; no gate record was written",
            exit_code,
        )
    decision, error = parse_decision(output, kit)
    if error:
        return Acceptance("FAIL", None, error, exit_code)
    reasons = allowed_reasons(kit, prep.gate.id)
    if decision["outcome"] == "revise" and decision["reason"] not in reasons:
        return Acceptance(
            "FAIL", None,
            f"reviewer reason {decision['reason']!r} is not a typed return from "
            f"{prep.gate.id}; expected {', '.join(reasons)}",
            exit_code,
        )
    local_failures = [
        check.name for check in prep.readiness.checks
        if check.status == "FAIL" and check.name != "staleness"
    ]
    if decision["outcome"] == "pass" and local_failures:
        return Acceptance(
            "FAIL", None,
            "reviewer returned pass while local checks fail: " + ", ".join(local_failures),
            exit_code,
        )

    record = _build_record(run, kit, prep, decision)
    record_errors = registry(kit.root).validate("gate_record", record)
    if record_errors:
        first = record_errors[0]
        return Acceptance(
            "FAIL", None,
            f"generated gate record is invalid: {first.path}: {first.message}",
            exit_code,
        )
    path = run.write_gate_record(record)
    verified = evaluate_gate(load_run(run.root, kit), kit, prep.gate.id, online=online)
    return Acceptance(verified.status, path, None, exit_code)
