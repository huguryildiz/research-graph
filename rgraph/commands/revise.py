"""`rgraph revise <GATE>` — spend one attempt and route back to a unit."""

from __future__ import annotations


from rgraph.config import ConfigError
from rgraph.gates import now
from rgraph.provenance import invalidated_gates
from rgraph.render import console, render_revise, status_text
from rgraph.run import RunError


def register(subparsers) -> None:
    parser = subparsers.add_parser("revise", help="return from a failed gate")
    parser.add_argument("gate", help="gate id, e.g. E1")
    parser.set_defaults(handler=handle)


def handle(args) -> int:
    from rgraph.commands.check import load_for_run

    try:
        kit, run = load_for_run(args)
    except (ConfigError, RunError) as exc:
        print(f"error: {exc}")
        return 2
    if args.gate not in kit.gates:
        print(f"error: unknown gate '{args.gate}'")
        return 2
    gate = kit.gates[args.gate]

    budget = run.meta.setdefault("revisions", {}).setdefault(
        args.gate, {"max": gate.max_revisions, "used": 0}
    )
    if budget["used"] >= budget["max"]:
        console.print(status_text("BLOCKED"))
        console.print(
            f"  Gate {args.gate} has spent its revision budget "
            f"({budget['used']} of {budget['max']})."
        )
        console.print("  It may only block or escalate. Narrow the scope or stop.")
        return 1

    record = run.gate_record(args.gate)
    if record is None:
        print(f"error: gate {args.gate} has no record; run `rgraph check {args.gate}` first")
        return 2
    if record["outcome"] in ("pass", "release"):
        # The record says pass; the digests may since have said otherwise. Reading
        # only the record here once answered "nothing to revise" at a gate `check`
        # had just called STALE, which left the newcomer with no move at all.
        retired = invalidated_gates(run, kit).get(args.gate)
        if retired:
            console.print(status_text("STALE"))
            console.print(f"  Gate {args.gate} passed, but that decision no longer covers")
            console.print("  the files it was made on:")
            for cause in retired:
                console.print(f"    {cause}")
            reopen = "decide" if gate.kind == "human" else "check"
            console.print(f"  No revision is owed. Run `rgraph {reopen} {args.gate}`.")
            return 1
        print(f"gate {args.gate} passed; there is nothing to revise")
        return 1

    reason = record.get("reason") or "revision"
    routes = gate.routes.get("revise")
    target = routes.get(reason, routes.get("default")) if isinstance(routes, dict) else routes

    budget["used"] += 1
    run.meta.setdefault("history", []).append({
        "at": now(), "gate": args.gate, "outcome": "revise", "reason": reason, "to": target,
    })
    run.save_meta()

    node = kit.graph.nodes.get(target)
    render_revise(
        args.gate, reason, target, budget["max"] - budget["used"],
        node.title if node else "",
    )
    return 0
