"""`rgraph next` — show the inventory, then run exactly one approved command."""

from __future__ import annotations


from rgraph.commands.status import STAGE_GATE, unit_state
from rgraph.config import ConfigError, Kit
from rgraph.provenance import stale_artifacts
from rgraph.render import console, render_next, render_provenance_notice
from rgraph.run import Run, RunError
from rgraph.runner import build_plan, execute


def register(subparsers) -> None:
    parser = subparsers.add_parser("next", help="the next unit of work")
    parser.add_argument("--unit", help="run a specific unit instead of the next one")
    parser.set_defaults(handler=handle)


def select_unit(run: Run, kit: Kit):
    stale = stale_artifacts(run)
    for unit in sorted(kit.graph.units(), key=lambda n: n.id):
        if unit_state(run, unit, stale) != "PASS":
            return unit
    return None


def handle(args) -> int:
    from rgraph.commands.check import load_for_run

    try:
        kit, run = load_for_run(args)
    except (ConfigError, RunError) as exc:
        print(f"error: {exc}")
        return 2

    render_provenance_notice(run)
    unit = kit.graph.nodes.get(args.unit) if args.unit else select_unit(run, kit)
    if unit is None:
        console.print("Every unit is complete. Run next:")
        console.print("  rgraph review")
        return 0

    plan = build_plan(run, kit, unit.id)
    gate_id = STAGE_GATE.get(unit.stage, "")
    render_next(plan, unit, gate_id, plan.manual)

    try:
        answer = input("> ").strip().upper()
    except EOFError:
        answer = "S"

    if answer == "D":
        console.print()
        console.print("Would run:")
        console.print("  " + " ".join(plan.argv) + f" < {plan.role_path}")
        return 0
    if answer != "E":
        console.print()
        console.print("Stopped. No command has been executed.")
        return 0
    if plan.manual:
        console.print()
        console.print("This provider is web-only; there is nothing to execute.")
        return 0

    console.print()
    code = execute(plan, verbose=args.verbose)
    console.print()
    console.print(f"Provider exited with code {code}. Log: {plan.log_path}")
    console.print()
    console.print("Run next:")
    console.print(f"  rgraph check {gate_id}")
    return 0 if code == 0 else 1
