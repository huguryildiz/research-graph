"""`rgraph next` — show the inventory, then run exactly one approved command."""

from __future__ import annotations

from rgraph.config import ConfigError
from rgraph.campaigns import retire_current_campaign
from rgraph.render import (
    body_text, console, key_value, muted, prompt_input, render_command,
    render_error, render_next, render_next_action, render_provenance_notice, section,
)
from rgraph.run import RunError, load_run
from rgraph.runner import build_plan, execute
from rgraph.services.execution import (
    acquire_unit_lock, campaign_preservation_problems, campaign_preservation_state,
    now, output_problems, output_state, run_boundary_state, write_execution_record,
)
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
    parser.add_argument(
        "--preserve-payload", action="store_true",
        help=("for a u07 metadata-only repair, reject changes to payload bytes, "
              "run IDs, run records, configurations, or result metadata"),
    )
    parser.set_defaults(handler=handle)


def handle(args) -> int:
    from rgraph.commands.check import load_for_run

    if args.unit is not None and not args.unit.strip():
        render_error("--unit cannot be empty")
        return 2
    try:
        kit, run = load_for_run(args)
    except (ConfigError, RunError) as exc:
        render_error(str(exc))
        return 2

    render_provenance_notice(run)
    if args.unit is not None:
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
    if args.preserve_payload and unit.id != "u07":
        render_error("--preserve-payload is valid only for unit u07")
        return 2
    if args.preserve_payload:
        plan.stdin_text += """
# HOST PAYLOAD-PRESERVATION MODE
# This is a metadata-only provenance repair. Do not execute the experiment and
# do not change raw_results.jsonl, either artifact body, any run ID, run record,
# configuration snapshot, or argv. Update only required envelope inputs,
# produced_at values and their host-sealed content hashes. Before sealing, set
# produced_at on BOTH run_manifest and raw_results to the actual current UTC
# instant inside this invocation; an unchanged old timestamp is rejected. The
# host compares all protected content before accepting this invocation.

"""
    gate_id = next_checkpoint(kit, unit.id) or "none"
    render_next(
        plan, unit, gate_id, plan.manual,
        show_choices=not (args.execute or args.dry_run),
    )

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
    if run.read_only:
        render_error("the bundled example-run is read-only; copy it before executing a unit")
        return 2

    try:
        lock_path = acquire_unit_lock(run, unit.id)
    except RunError as exc:
        render_error(str(exc))
        return 1
    try:
        console.print()
        preserved_campaign = (
            campaign_preservation_state(run) if args.preserve_payload else None
        )
        if unit.id == "u07" and not args.preserve_payload:
            archive = retire_current_campaign(run)
            if archive is not None:
                key_value("Retired prior campaign", archive)
        before = output_state(run, unit.produces)
        boundary_before = run_boundary_state(run.root)
        started_at = now()
        code = execute(plan, verbose=args.verbose)
        finished_at = now()
        console.print()
        section("Provider result")
        key_value("Exit code", code)
        key_value("Log", plan.log_path)
        problems = [] if code == 0 else [f"provider CLI exited {code}"]
        try:
            refreshed = load_run(run.root, kit)
        except RunError as exc:
            problems.append(f"provider left an unreadable run: {exc}")
            refreshed = run
        if code == 0:
            problems.extend(output_problems(
                refreshed, kit, unit, before, boundary_before,
                started_at=started_at, finished_at=finished_at,
            ))
            if preserved_campaign is not None:
                problems.extend(
                    campaign_preservation_problems(preserved_campaign, refreshed)
                )
        if plan.log_path is None or not plan.log_path.is_file():
            problems.append("provider log is missing")
        try:
            receipt = write_execution_record(
                run, refreshed, kit, unit, plan,
                started_at=started_at, finished_at=finished_at,
                exit_code=code, problems=problems,
            )
        except RunError as exc:
            render_error(str(exc))
            return 2
        key_value("Receipt", receipt)
        if problems:
            for problem in problems:
                render_error(problem)
            muted(
                "The unit was not accepted. Inspect the provider log and retry "
                "explicitly."
            )
            return 1
        console.print()
        render_next_action("rgraph status")
        return 0 if code == 0 else 1
    finally:
        lock_path.unlink(missing_ok=True)
