"""`rgraph decide` — the human act a human gate is named after.

`rgraph check` verifies. It reads files, recomputes digests and compares strings,
and it can do all of that while nobody is watching. A human gate asks for
something else: that a person read the artifact and say whether it holds. Nothing
mechanical can stand in for that, so this command does not try — it asks, records
the answers verbatim, and records who gave them.

The questions are not invented here. Each gate already declares what it proves in
`gates.yaml`; those lines are the questions.
"""

from __future__ import annotations

import subprocess
import sys

from rgraph.config import ConfigError
from rgraph.gates import evaluate_gate, now, record_from
from rgraph.interactive import InteractionCancelled, choose
from rgraph.render import console, render_gate_result, rule
from rgraph.run import RunError

# Whether the artifacts can be read at all. Staleness is deliberately not here:
# a stale human gate is one whose own past decision no longer covers the file,
# and deciding again is the cure rather than the thing being blocked.
MECHANICAL = ("presence", "schema", "provenance")


def register(subparsers) -> None:
    parser = subparsers.add_parser("decide", help="record a human decision at a human gate")
    parser.add_argument("gate", nargs="?", help="gate id, e.g. H1; omit for a menu")
    parser.add_argument("--as", dest="identity", help="who is deciding; default is git user.name")
    parser.set_defaults(handler=handle)


def at_a_terminal() -> bool:
    """Whether there is a person on the other end of stdin.

    `yes y | rgraph decide H1` answers every question a human gate asks, in
    order, without anybody reading anything. That is the one thing this command
    exists to prevent, so a pipe is refused rather than believed. `rgraph setup`
    offers `--yes` for the same situation; a human gate gets no such flag,
    because the answer is the point.
    """
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def git_user_name() -> str:
    """The name this machine already signs commits with. A default, not an answer."""
    try:
        completed = subprocess.run(
            ["git", "config", "user.name"], capture_output=True, text=True, timeout=3, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout.strip()


def ask(claim: str, index: int, total: int, artifacts: list[str]) -> str | None:
    """Return 'yes', 'no', or None if the person walked away."""
    console.print(f"  {index}/{total}  {claim}")
    console.print(f"         Have you read {', '.join(artifacts)} and does this hold?")
    while True:
        try:
            answer = input("         [y] yes  [n] no  [s] stop > ").strip().lower()
        except EOFError:
            return None
        if answer in ("y", "yes"):
            return "yes"
        if answer in ("n", "no"):
            return "no"
        if answer in ("s", "stop", ""):
            return None
        console.print("         Answer y, n, or s.")


def handle(args) -> int:
    from rgraph.commands.check import load_for_run

    try:
        kit, run = load_for_run(args)
    except (ConfigError, RunError) as exc:
        print(f"error: {exc}")
        return 2

    gate_id = args.gate
    if gate_id is None:
        if not at_a_terminal():
            human = ", ".join(g.id for g in kit.gates.values() if g.kind == "human")
            print(f"error: choose a human gate: rgraph decide <GATE> ({human})")
            return 2
        choices = []
        for item in kit.gates.values():
            if item.kind == "human":
                state = evaluate_gate(run, kit, item.id).status
                choices.append((item.id, f"{item.id} — {item.title} [{state}]", state))
        actionable = [row for row in choices if row[2] in ("AWAITING", "STALE")]
        shown = actionable or choices
        try:
            gate_id = choose(
                "Which human gate are you deciding?",
                [(key, label) for key, label, _ in shown],
                allow_cancel=True,
            )
        except InteractionCancelled:
            gate_id = None
        if gate_id is None:
            console.print("Stopped. No decision has been recorded.")
            return 0

    gate = kit.gates.get(gate_id)
    if gate is None:
        print(f"error: unknown gate '{gate_id}'; expected one of {', '.join(kit.gates)}")
        return 2
    if gate.kind != "human":
        print(
            f"error: {gate.id} is a {gate.kind} gate; `rgraph check {gate.id}` decides it. "
            f"Human gates are {', '.join(g.id for g in kit.gates.values() if g.kind == 'human')}."
        )
        return 2

    result = evaluate_gate(run, kit, gate.id)
    broken = [c for c in result.checks if c.name in MECHANICAL and c.status == "FAIL"]
    if broken:
        # Attesting to an artifact that does not validate would record a reading
        # of something nobody can read. The mechanical failure comes first.
        render_gate_result(result, gate)
        console.print("Nothing to decide yet: the inputs do not hold up.")
        console.print(f"Fix the above, then `rgraph decide {gate.id}`.")
        return 1

    if not at_a_terminal():
        console.print(f"GATE {gate.id} / {gate.title.upper()}")
        console.print()
        console.print("No terminal to answer on, and a human gate is not a form to fill.")
        console.print(f"  Run `rgraph decide {gate.id}` from a terminal, where somebody")
        console.print("  can read the artifacts before answering for them.")
        return 2

    rule(f"GATE {gate.id} / {gate.title.upper()}")
    console.print()
    console.print(f"This gate proves {len(gate.proves)} thing(s). It cannot prove them for you.")
    console.print()

    answers = []
    for index, claim in enumerate(gate.proves, start=1):
        answered = ask(claim, index, len(gate.proves), list(gate.inputs))
        if answered is None:
            console.print()
            console.print("Stopped. No decision has been recorded.")
            return 0
        answers.append({"claim": claim, "answered": answered})
        console.print()

    default = args.identity or git_user_name()
    if args.identity:
        identity = args.identity
    else:
        try:
            identity = (input(f"  Decided by [{default}]: ").strip() or default)
        except EOFError:
            identity = default
    if not identity:
        print("error: no identity given, and git has no user.name to fall back on")
        print("       re-run with --as 'Your Name'")
        return 2

    outcome = "pass" if all(a["answered"] == "yes" for a in answers) else "revise"
    record = record_from(result, run, kit)
    record["outcome"] = outcome
    record["decided_at"] = now()
    record["decided_by"] = {"role": "human", "identity": f"human/{identity}"}
    record["attestation"] = {"identity": f"human/{identity}", "answers": answers}
    if outcome == "revise":
        record["reason"] = record.get("reason") or "revision"
    path = run.write_gate_record(record)

    console.print()
    console.print(f"Recorded: {outcome}  ·  decided_by human/{identity}")
    console.print(f"          {path}")
    console.print()
    console.print("Run next:")
    if outcome == "pass":
        console.print(f"  rgraph check {gate.id}")
    else:
        console.print(f"  rgraph revise {gate.id}")
    return 0 if outcome == "pass" else 1
