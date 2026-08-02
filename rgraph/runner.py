"""Single-shot approved execution. One subprocess per invocation, then control returns."""

from __future__ import annotations

import pathlib
import subprocess
from dataclasses import dataclass, field

from rgraph.config import EFFORT_SLOT, Assignment, Kit, Provider
from rgraph.run import Run

HEADER = """\
# research-graph context
# run directory : {run_dir}
# unit          : {unit_id} {unit_title}
# write these artifacts, each as JSON matching schemas/<id>.schema.json:
{produce_lines}
# every artifact must carry produced_by.identity = "{identity}"
# and inputs[] with the content_hash of every artifact you read.

"""


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
    log_path: pathlib.Path | None = None
    manual: bool = False


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

    header = HEADER.format(
        run_dir=run.root.resolve(),
        unit_id=unit.id,
        unit_title=unit.title,
        produce_lines="\n".join(f"#   run/{a}.json" for a in unit.produces),
        identity=identity,
    )
    role_text = role_path.read_text(encoding="utf-8") if role_path.exists() else ""

    argv = build_argv(provider, assignment)
    logs = run.root / "logs"
    return Plan(
        unit=unit_id,
        role_path=role_path,
        provider=assignment.provider,
        model=assignment.model,
        argv=argv,
        stdin_text=header + role_text,
        inputs=upstream,
        produces=unit.produces,
        log_path=logs / f"{unit_id}.log",
        manual=provider.kind == "web",
    )


def execute(plan: Plan, *, verbose: bool = False) -> int:
    if plan.manual or not plan.argv:
        return 0
    plan.log_path.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(
        plan.argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
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
    plan.log_path.write_text("".join(lines), encoding="utf-8")
    return process.wait()
