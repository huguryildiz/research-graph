"""`rgraph revise <GATE>` — spend one attempt and route back to a unit."""

from __future__ import annotations


from rgraph.config import ConfigError
from rgraph.gates import now
from rgraph.interactive import InteractionCancelled, choose, is_terminal
from rgraph.provenance import invalidated_gates
from rgraph.render import (
    body_text, console, muted, render_error, render_next_action, render_revise,
    section,
)
from rgraph.run import RunError


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "revise",
        help="return from a failed gate",
        description=(
            "Spend one bounded revision attempt and route the run back to the unit "
            "declared by the failed gate."
        ),
        epilog=(
            "Examples:\n"
            "  rgraph revise\n"
            "  rgraph revise E1"
        ),
    )
    parser.add_argument("gate", nargs="?", help="gate id, e.g. E1; omit for a menu")
    parser.set_defaults(handler=handle)


def handle(args) -> int:
    from rgraph.commands.check import load_for_run

    try:
        kit, run = load_for_run(args)
    except (ConfigError, RunError) as exc:
        render_error(str(exc))
        return 2
    gate_id = args.gate
    if gate_id is None:
        candidates = []
        blocked = []
        for item in kit.gates.values():
            record = run.gate_record(item.id)
            if record and record.get("outcome") == "revise":
                candidates.append((item.id, f"{item.id} — {item.title} [{record['outcome'].upper()}]"))
            elif record and record.get("outcome") == "block":
                blocked.append(item.id)
        if not candidates:
            if blocked:
                section("No revision available")
                body_text("No gate is eligible for revision.")
                muted(
                    "Blocked gates require scope narrowing, escalation, or stopping: "
                    + ", ".join(blocked)
                )
                return 1
            section("No revision required")
            muted("Run `rgraph status` to see the next action.")
            return 0
        if not is_terminal():
            expected = ", ".join(gate for gate, _ in candidates)
            render_error(f"choose a gate: rgraph revise <GATE> ({expected})")
            return 2
        try:
            gate_id = choose("Which failed gate are you revising?", candidates, allow_cancel=True)
        except InteractionCancelled:
            gate_id = None
        if gate_id is None:
            muted("Stopped. No revision attempt has been used.")
            return 0
    if gate_id not in kit.gates:
        render_error(f"unknown gate '{gate_id}'")
        return 2
    gate = kit.gates[gate_id]

    budget = run.meta.setdefault("revisions", {}).setdefault(
        gate_id, {"max": gate.max_revisions, "used": 0}
    )
    if budget["used"] >= budget["max"]:
        section("Blocked", "bold red")
        body_text(
            f"Gate {gate_id} has spent its revision budget "
            f"({budget['used']} of {budget['max']})."
        )
        muted("It may only block or escalate. Narrow the scope or stop.")
        return 1

    record = run.gate_record(gate_id)
    if record is None:
        verb = "decide" if gate.kind == "human" else "challenge"
        render_error(f"gate {gate_id} has no record; run `rgraph {verb} {gate_id}` first")
        return 2
    if record["outcome"] == "block":
        section("Blocked", "bold red")
        body_text(f"Gate {gate_id} was blocked, not returned for revision.")
        muted("Narrow the scope, escalate the decision, or stop the run.")
        return 1
    if record["outcome"] in ("pass", "release"):
        # The record says pass; the digests may since have said otherwise. Reading
        # only the record here once answered "nothing to revise" at a gate `check`
        # had just called STALE, which left the newcomer with no move at all.
        retired = invalidated_gates(run, kit).get(gate_id)
        if retired:
            section("Stale", "bold yellow")
            body_text(f"Gate {gate_id} passed, but that decision no longer covers its files:")
            for cause in retired:
                body_text(cause, indent="        ")
            reopen = "decide" if gate.kind == "human" else "challenge"
            muted("No revision is owed.")
            console.print()
            render_next_action(f"rgraph {reopen} {gate_id}")
            return 1
        body_text(f"Gate {gate_id} passed; there is nothing to revise.")
        return 1

    reason = record.get("reason") or "revision"
    routes = gate.routes.get("revise")
    target = routes.get(reason, routes.get("default")) if isinstance(routes, dict) else routes

    budget["used"] += 1
    run.meta.setdefault("history", []).append({
        "at": now(), "gate": gate_id, "outcome": "revise", "reason": reason, "to": target,
    })
    run.save_meta()

    node = kit.graph.nodes.get(target)
    render_revise(
        gate_id, reason, target, budget["max"] - budget["used"],
        node.title if node else "",
    )
    return 0
