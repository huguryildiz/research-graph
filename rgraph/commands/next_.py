"""`rgraph next` — show the inventory, then run exactly one approved command."""

from __future__ import annotations


from rgraph.config import ConfigError
from rgraph.render import (
    body_text, console, key_value, muted, prompt_input, render_command,
    render_error, render_next, render_next_action, render_provenance_notice, section,
)
from rgraph.run import RunError
from rgraph.runner import build_plan, execute
from rgraph.workflow import next_action, next_checkpoint, prerequisite_action


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "next",
        help="the next unit of work",
        description=(
            "Inspect the next ready unit and its inputs before optionally running "
            "the assigned provider command."
        ),
        epilog=(
            "Examples:\n"
            "  rgraph next\n"
            "  rgraph next --unit u06 --dry-run\n"
            "  rgraph next --unit u06 --execute"
        ),
    )
    parser.add_argument("--unit", help="run a specific unit instead of the next one")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--execute", action="store_true",
                        help="run the displayed provider command without prompting")
    action.add_argument("--dry-run", action="store_true",
                        help="print the provider command without running it")
    parser.set_defaults(handler=handle)


def handle(args) -> int:
    from rgraph.commands.check import load_for_run

    try:
        kit, run = load_for_run(args)
    except (ConfigError, RunError) as exc:
        render_error(str(exc))
        return 2

    render_provenance_notice(run)
    if args.unit:
        unit = kit.graph.nodes.get(args.unit)
        if unit is None or not unit.is_unit:
            expected = ", ".join(sorted(node.id for node in kit.graph.units()))
            render_error(f"unknown unit '{args.unit}'; expected one of {expected}")
            return 2
        blocked_by = prerequisite_action(run, kit, unit)
        if blocked_by is not None:
            body_text(f"Cannot run {unit.id} yet: {blocked_by.detail}.")
            if blocked_by.command:
                console.print()
                render_next_action(blocked_by.command)
            return 1
    else:
        action = next_action(run, kit)
        if action.kind != "unit":
            body_text(f"No unit can run yet: {action.detail}.")
            if action.command:
                console.print()
                render_next_action(action.command)
            return 0 if action.kind in ("review", "complete") else 1
        unit = kit.graph.nodes[action.target]

    plan = build_plan(run, kit, unit.id)
    gate_id = next_checkpoint(kit, unit.id) or "none"
    render_next(plan, unit, gate_id, plan.manual)

    if args.execute:
        answer = "E"
    elif args.dry_run:
        answer = "D"
    else:
        while True:
            try:
                answer = prompt_input("Choose", suffix=" [1-3]", marker=": ").strip().upper()
            except (EOFError, KeyboardInterrupt):
                console.print()
                muted("No choice was made. Re-run with --execute or --dry-run.")
                return 2
            answer = {"1": "E", "2": "D", "3": "S", "EXECUTE": "E",
                      "DRY": "D", "DRY-RUN": "D", "STOP": "S", "": "S"}.get(
                          answer, answer
                      )
            if answer in ("E", "D", "S"):
                break
            muted("Choose 1 (execute), 2 (dry run), or 3 (stop).")

    if answer == "D":
        console.print()
        section("Would run")
        render_command(" ".join(plan.argv) + f" < {plan.role_path}")
        return 0
    if answer != "E":
        console.print()
        muted("Stopped. No command has been executed.")
        return 0
    if plan.manual:
        console.print()
        muted("This provider is web-only; there is nothing to execute.")
        return 0

    console.print()
    code = execute(plan, verbose=args.verbose)
    console.print()
    section("Provider result")
    key_value("Exit code", code)
    key_value("Log", plan.log_path)
    console.print()
    render_next_action("rgraph status")
    return 0 if code == 0 else 1
