"""Single-shot approved execution. One subprocess per invocation, then control returns."""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass, field

from rgraph.config import EFFORT_SLOT, Assignment, Kit, Provider
from rgraph.run import Run

HEADER = """\
# research-graph context
# run directory : {run_dir}
# contract kit root: {kit_root}
# schema directory : {kit_root}/schemas
# unit          : {unit_id} {unit_title}
# write these artifacts, each as JSON matching schemas/<id>.schema.json:
{produce_lines}
# every artifact must carry produced_by.identity = "{identity}"
# and inputs[] with the content_hash of every artifact you read.
# the host has explicitly authorised this unit; existing gate records are
# historical context and must not be used to refuse or skip the requested work.
# do not write run/gates/ or invoke check, challenge, decide, or review; only the
# host may evaluate or cross a decision boundary after this invocation returns.
# never calculate or edit content_hash values yourself. After writing the
# declared outputs, seal only those artifact IDs with the exact command below:
#   "{python_executable}" -m rgraph --run "{run_dir}" seal {seal_artifacts}
# do not substitute another rgraph executable, even if one appears on PATH.
# if sealing fails, report the failure and leave the hashes uninvented.
# sidecar files are allowed only when an output schema declares and hashes them.
# Source sidecars must stay below run/code and be listed with their SHA-256 in
# code_commit.body.files. Version 2 also binds the host-provided Git bundle,
# its SHA-256, a full clean commit ID and each file's path inside that commit.
# The bundle SHA-256 uses ``sha256:<64 hex>`` like envelope hashes; file and
# dependency-lock SHA-256 fields retain their schema-defined unprefixed form.
# Do not alter the bundle, create a nested .git repository, .venv, __pycache__,
# package cache or unlisted helper file inside the run. Do not commit or push.
# For environment_lock version 2, write one immutable dependency-lock sidecar
# below run/environment and bind its path and SHA-256. For run_manifest version
# 2, write immutable configuration snapshots below run/config and bind each
# path, SHA-256 and exact argv; every runs[].config_sha256 must resolve to one.
# The recorded entrypoint must directly emit every declared raw-result field.
# Do not perform undocumented post-processing between the entrypoint and payload.
# Write produced_at as the actual current UTC instant with a Z suffix. Do not
# label local wall-clock time as UTC; the host checks the invocation window.

"""


def _revision_context(run: Run, kit: Kit, unit_id: str) -> str:
    """Carry an unresolved typed return through the repairing role's units."""
    current = kit.graph.nodes.get(unit_id)
    revision = None
    for item in reversed(run.meta.get("history", [])):
        if item.get("outcome") != "revise":
            continue
        target = kit.graph.nodes.get(item.get("to"))
        if current is None or target is None or target.role_name != current.role_name:
            continue
        gate_id = item.get("gate")
        record = run.gate_record(gate_id) if isinstance(gate_id, str) else None
        if record and record.get("outcome") == "revise":
            revision = item
            break
    if revision is None:
        return ""
    gate_id = revision.get("gate")
    record = run.gate_record(gate_id) if isinstance(gate_id, str) else None
    lines = [
        "# revision context (review evidence; do not edit the gate record)",
        f"# returned by gate: {gate_id}",
        f"# typed reason: {revision.get('reason', 'revision')}",
    ]
    for finding in (record or {}).get("findings", []):
        lines.extend((
            f"# finding: {finding.get('ref', 'unspecified')} / "
            f"{finding.get('code', 'FINDING')}",
            f"# detail: {finding.get('detail', '')}",
            f"# required correction: {finding.get('fix', '')}",
        ))
    lines.append("# address this return within the unit's declared output artifacts only.")
    return "\n".join(lines) + "\n\n"


@dataclass
class Plan:
    unit: str
    role_path: pathlib.Path
    provider: str
    model: str
    argv: list[str] = field(default_factory=list)
    stdin_text: str = ""
    inputs: list[tuple[str, str]] = field(default_factory=list)
    produces: tuple[str, ...] = ()
    output_paths: tuple[str, ...] = ()
    log_path: pathlib.Path | None = None
    cwd: pathlib.Path | None = None
    invocation_id: str | None = None
    manual: bool = False


@dataclass(frozen=True)
class ExecutionResult:
    """What one provider subprocess returned.

    Keeping the captured output lets commands whose contract is a structured
    response validate it before they mutate a run.  The ordinary unit runner
    still exposes only the exit code.
    """

    exit_code: int
    output: str


def resolve_executable(argv: list[str], search_path: str) -> list[str]:
    """Resolve argv[0] against the PATH the child is actually given.

    Package managers install provider CLIs as `.cmd` shims on Windows, and a
    launch that never goes through a shell does not apply PATHEXT to a bare name
    — so a provider that `doctor` reports as found can otherwise fail to start.
    `shutil.which` applies it. A name that resolves to nothing is returned
    untouched, so the failure still names the command that was configured.
    """
    if not argv:
        return argv
    found = shutil.which(argv[0], path=search_path)
    return [found, *argv[1:]] if found else list(argv)


def build_argv(provider: Provider, assignment: Assignment) -> list[str]:
    """The command line for one invocation.

    `{effort_argv}` stands where the reasoning-depth flags belong. Without an
    effort it expands to nothing, so a provider that never mentions effort — and
    an assignment that never asks for one — produces exactly the argv it did
    before this existed.
    """
    argv: list[str] = []
    for part in provider.exec_argv:
        if part != EFFORT_SLOT:
            argv.append(part.replace("{model}", assignment.model))
            continue
        if assignment.effort is None:
            continue
        argv.extend(
            flag.replace("{effort}", assignment.effort) for flag in provider.effort_argv
        )
    return argv


def _required_inputs(kit: Kit, unit_id: str) -> list[str]:
    """The artifacts this unit reads, in graph order and without repeats.

    `return` edges are skipped: what they carry is a revision reason, produced
    only when a gate sends work back, so listing it on a first pass would report
    a file nothing has any reason to have written yet. Where the incoming edge
    comes from a gate, that gate's own inputs are what the unit inherits.
    """
    seen: list[str] = []
    for edge in kit.graph.in_edges(unit_id):
        if edge.kind == "return":
            continue
        carried = list(edge.carries)
        gate = kit.gates.get(edge.frm)
        if gate is not None and not carried:
            carried = list(gate.inputs)
        for artifact_id in carried:
            if artifact_id not in seen:
                seen.append(artifact_id)
    return seen


# The same question the browser's unit detail asks, so both name one list.
required_inputs = _required_inputs


def build_plan(run: Run, kit: Kit, unit_id: str) -> Plan:
    unit = kit.graph.node(unit_id)
    assignment = kit.assignment[unit.role_name]
    provider = kit.providers[assignment.provider]
    role_path = kit.root / unit.role
    identity = assignment.identity(kit.providers)

    upstream: list[tuple[str, str]] = []
    for artifact_id in _required_inputs(kit, unit_id):
        artifact = run.artifacts.get(artifact_id)
        state = "VALID" if artifact and artifact.present and not artifact.errors else "MISSING"
        upstream.append((artifact_id, state))

    produce_paths: list[str] = []
    for artifact_id in unit.produces:
        artifact = run.artifacts[artifact_id]
        produce_paths.append(str(artifact.path.resolve()))
        if artifact.payload_path is not None:
            produce_paths.append(str(artifact.payload_path.resolve()))
    header = HEADER.format(
        run_dir=run.root.resolve(),
        kit_root=kit.root.resolve(),
        unit_id=unit.id,
        unit_title=unit.title,
        produce_lines="\n".join(f"#   {path}" for path in produce_paths),
        python_executable=pathlib.Path(os.path.abspath(sys.executable)),
        seal_artifacts=" ".join(unit.produces),
        identity=identity,
    )
    role_text = role_path.read_text(encoding="utf-8") if role_path.exists() else ""

    argv = build_argv(provider, assignment)
    logs = run.root / "logs"
    invocation_id = str(uuid.uuid4())
    return Plan(
        unit=unit_id,
        role_path=role_path,
        provider=assignment.provider,
        model=assignment.model,
        argv=argv,
        stdin_text=header + _revision_context(run, kit, unit_id) + role_text,
        inputs=upstream,
        produces=unit.produces,
        output_paths=tuple(
            run.artifacts[a].path.relative_to(run.root).as_posix()
            for a in unit.produces
        ),
        log_path=logs / f"{unit_id}-{invocation_id}.log",
        cwd=run.root.parent,
        invocation_id=invocation_id,
        manual=provider.kind == "web",
    )


def execute_capture(plan: Plan, *, verbose: bool = False) -> ExecutionResult:
    if plan.manual or not plan.argv:
        return ExecutionResult(0, "")
    plan.log_path.parent.mkdir(parents=True, exist_ok=True)
    host_bin = str(pathlib.Path(os.path.abspath(sys.executable)).parent)
    inherited_path = os.environ.get("PATH", "")
    provider_path = host_bin + (os.pathsep + inherited_path if inherited_path else "")
    process = subprocess.Popen(
        resolve_executable(plan.argv, provider_path),
        cwd=plan.cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env={
            **os.environ,
            "PATH": provider_path,
            "RGRAPH_ACTIVE_INVOCATION": plan.unit,
        },
    )
    lines: list[str] = []
    if process.stdin is not None:
        process.stdin.write(plan.stdin_text)
        process.stdin.close()
    if process.stdout is not None:
        for line in process.stdout:
            lines.append(line)
            if verbose:
                print(line, end="")
    output = "".join(lines)
    plan.log_path.write_text(output, encoding="utf-8")
    return ExecutionResult(process.wait(), output)


def execute(plan: Plan, *, verbose: bool = False) -> int:
    return execute_capture(plan, verbose=verbose).exit_code
