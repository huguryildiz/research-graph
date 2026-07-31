"""`rgraph status` — the summary pipeline of spec section 9.0.2."""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field

from rgraph.config import ConfigError, Kit
from rgraph.provenance import stale_artifacts
from rgraph.render import render_status
from rgraph.run import Run, RunError, load_run

STAGE_ORDER = ("retrieve", "plan", "execute", "verify", "write")
STAGE_GATE = {"retrieve": "E1", "plan": "T1", "execute": "T2", "verify": "V1", "write": "M1"}
STAGE_HUMAN = {"retrieve": "H1", "plan": "H4", "execute": "", "verify": "", "write": ""}


@dataclass
class StatusView:
    run_id: str
    question: str
    mode: str
    protocol: str
    revision_line: str
    stages: list[tuple[str, str]] = field(default_factory=list)
    gate_row: list[tuple[str, str]] = field(default_factory=list)
    human_row: list[tuple[str, str]] = field(default_factory=list)
    units: list[tuple[str, str, str]] = field(default_factory=list)
    units_complete: int = 0
    artifact_counts: tuple[int, int, int] = (0, 0, 0)
    last_gate: str = "none"
    next_unit: str | None = None


def register(subparsers) -> None:
    parser = subparsers.add_parser("status", help="where the run stands")
    parser.set_defaults(handler=handle)


def unit_state(run: Run, unit, stale: dict) -> str:
    produced = list(unit.produces)
    if any(a in stale for a in produced):
        return "STALE"
    if produced and all(run.get(a).present and not run.get(a).errors for a in produced):
        return "PASS"
    if any(run.get(a).present for a in produced):
        return "READY"
    return "WAIT"


def build_view(run: Run, kit: Kit) -> StatusView:
    stale = stale_artifacts(run)
    units = sorted(kit.graph.units(), key=lambda n: n.id)
    states = {u.id: unit_state(run, u, stale) for u in units}

    stages: list[tuple[str, str]] = []
    for stage in STAGE_ORDER:
        members = [states[u.id] for u in units if u.stage == stage]
        if all(s == "PASS" for s in members):
            stages.append((stage, "PASS"))
        elif "STALE" in members:
            stages.append((stage, "STALE"))
        elif "READY" in members or "PASS" in members:
            stages.append((stage, "READY"))
        else:
            stages.append((stage, "WAIT"))

    def gate_state(gate_id: str) -> str:
        if not gate_id:
            return "----"
        record = run.gate_record(gate_id)
        if record is None:
            return "----"
        return {"pass": "PASS", "revise": "FAIL", "block": "BLOCKED"}.get(
            record["outcome"], record["outcome"].upper()
        )

    gate_row = [(STAGE_GATE[s], gate_state(STAGE_GATE[s])) for s in STAGE_ORDER]
    human_row = [
        (STAGE_HUMAN[s], "APPROVED" if gate_state(STAGE_HUMAN[s]) == "PASS" else "----")
        for s in STAGE_ORDER
    ]

    valid = sum(1 for a in run.artifacts.values() if a.present and not a.errors and a.id not in stale)
    stale_count = len(stale)
    pending = sum(1 for a in run.artifacts.values() if not a.present)

    history = run.meta.get("history", [])
    last_gate = (
        f"{history[-1]['gate']} {history[-1]['outcome'].upper()}" if history else "none"
    )
    for gate_id in ("M1", "V1", "T2", "H4", "T1", "H3", "H2", "E1", "H1"):
        record = run.gate_record(gate_id)
        if record is not None:
            last_gate = f"{gate_id} {record['outcome'].upper()}"
            break

    next_unit = next(
        (f"{u.id[1:]} {u.title}" for u in units if states[u.id] in ("READY", "WAIT")), None
    )

    revisions = run.meta.get("revisions", {})
    if revisions:
        gate_id, budget = min(
            revisions.items(), key=lambda kv: kv[1]["max"] - kv[1]["used"]
        )
        remaining = budget["max"] - budget["used"]
    else:
        remaining = 3
    revision_line = f"{remaining} of 3 attempts remain"

    return StatusView(
        run_id=run.meta["run_id"], question=run.meta["question"], mode=run.meta["mode"],
        protocol=run.meta["protocol"], revision_line=revision_line, stages=stages,
        gate_row=gate_row, human_row=human_row,
        units=[(u.id, u.title, states[u.id]) for u in units],
        units_complete=sum(1 for s in states.values() if s == "PASS"),
        artifact_counts=(valid, stale_count, pending),
        last_gate=last_gate, next_unit=next_unit,
    )


def handle(args) -> int:
    from rgraph.commands.check import load

    try:
        kit = load(args)
        run = load_run(pathlib.Path(args.run), kit)
    except (ConfigError, RunError) as exc:
        print(f"error: {exc}")
        return 2
    render_status(build_view(run, kit), verbose=args.verbose)
    return 0
