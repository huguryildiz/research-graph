"""`rgraph challenge <GATE>` — one attributable reviewer invocation.

The verifier and the reviewer do different jobs.  Local checks recompute
schemas, hashes and declared content contracts; a configured provider reads the
gate inputs and returns a bounded decision proposal.  Only this command and its
browser equivalent join the two, and both go through
`rgraph.services.challenge`, so neither can write a gate record the other would
have refused.
"""

from __future__ import annotations

import os

from rgraph.config import ConfigError
from rgraph.gates import evaluate_gate
from rgraph.render import (
    body_text, console, key_value, muted, render_error, render_gate_result,
    render_next_action, render_provenance_notice, section,
)
from rgraph.run import RunError, load_run
from rgraph.runner import execute_capture
from rgraph.services.challenge import (  # noqa: F401  (public surface of `rgraph challenge`)
    BLOCKING_LOCAL_CHECKS, ChallengeError, accept, begin,
    build_prompt as _prompt, prepare, run_snapshot as _run_snapshot,
)


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

    try:
        prep = prepare(run, kit, args.gate, online=args.online, force=args.force)
    except ChallengeError as exc:
        gate = kit.gates.get(args.gate)
        if exc.kind == "current":
            render_provenance_notice(run)
            render_gate_result(exc.result, gate)
            muted(str(exc))
            return 0
        if exc.kind == "decided":
            render_provenance_notice(run)
            render_gate_result(exc.result, gate)
            return 1
        if exc.kind == "not_ready":
            render_provenance_notice(run)
            render_gate_result(exc.result, gate, show_next=False)
            body_text("Reviewer not started: the gate inputs or assignment are not usable.")
            muted(f"Fix the failed local checks, then run `rgraph challenge {gate.id}`.")
            return 1
        render_error(str(exc))
        if "manual" in str(exc):
            muted("Assign a logged-in CLI reviewer, run `rgraph doctor`, then retry.")
        return 2

    render_provenance_notice(run)
    section(f"Reviewer challenge {prep.gate.id}")
    key_value("Identity", prep.identity)
    key_value("Provider", prep.plan.provider)
    key_value("Model", prep.plan.model)
    key_value("Inputs", f"{len(prep.gate.inputs)} current artifact hashes")
    body_text("Starting exactly one reviewer CLI invocation.")
    console.print()

    begin(prep, run)
    execution = execute_capture(prep.plan, verbose=args.verbose)
    outcome = accept(
        run, kit, prep, exit_code=execution.exit_code, output=execution.output,
        online=args.online,
    )
    if outcome.error:
        render_error(outcome.error)
        muted(f"No gate record was written. Provider log: {prep.plan.log_path}")
        return 2

    verified = evaluate_gate(load_run(run.root, kit), kit, prep.gate.id, online=args.online)
    render_gate_result(verified, prep.gate, show_next=False)
    key_value("Record", outcome.record_path)
    key_value("Provider log", prep.plan.log_path)
    console.print()
    if verified.status in ("PASS", "CAVEAT"):
        render_next_action("rgraph status")
        return 0
    if verified.status == "BLOCKED":
        return 1
    render_next_action(f"rgraph revise {prep.gate.id}")
    return 1
