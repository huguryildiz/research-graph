from __future__ import annotations

import json
import pathlib

from rgraph.config import ConfigError, load_kit, resolve_assignment
from rgraph.gates import evaluate_gate
from rgraph.lint import run_static
from rgraph.provenance import invalidated_gates
from rgraph.render import (
    render_error, render_gate_result, render_next_action,
    render_provenance_notice, render_static_report,
)
from rgraph.run import RunError, load_run


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "check",
        help="verify a gate, or lint the graph",
        description=(
            "Run static topology checks or evaluate one gate against validated "
            "artifacts and recorded provenance."
        ),
        epilog=(
            "Examples:\n"
            "  rgraph check --static\n"
            "  rgraph check T2\n"
            "  rgraph check E1 --online\n"
            "  rgraph challenge E1"
        ),
    )
    parser.add_argument("gate", nargs="?", help="gate id, e.g. E1")
    parser.add_argument("--static", action="store_true", help="run Layer 1 only")
    parser.add_argument("--online", action="store_true", help="resolve DOIs over the network")
    parser.set_defaults(handler=handle)


def load(args, assignment: str = "assignment.yaml"):
    root = pathlib.Path(args.root)
    if assignment == "assignment.yaml":
        found = resolve_assignment(root)
        assignment = found if found is not None else "assignment.example.yaml"
    return load_kit(root, assignment=assignment)


def load_for_run(args):
    """The kit and the run together, with the assignment the run belongs to.

    A synthetic fixture records identities that came from
    `assignment.example.yaml`. Judging them against whatever the user later
    configured for their own work compares two unrelated runs, so the fixture
    keeps its own assignment.
    """
    run_dir = pathlib.Path(args.run)
    assignment: str | pathlib.Path = "assignment.yaml"
    meta_path = run_dir / "meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            meta = {}
        if meta.get("provenance") == "synthetic":
            assignment = "assignment.example.yaml"
    if assignment == "assignment.yaml":
        run_assignment = run_dir.parent / "assignment.yaml"
        if run_assignment.is_file():
            # An explicit --run may point outside cwd and --root. The assignment
            # beside that study is the only one that can describe who produced
            # and reviews this run; machine or checkout defaults are unrelated.
            assignment = run_assignment.resolve()
    kit = load(args, assignment=assignment)
    run = load_run(run_dir, kit)
    # Verifying the shipped example must never rewrite it. A copy of it is yours.
    run.read_only = run.root.resolve() == (kit.root / "example-run").resolve()
    return kit, run


def handle(args) -> int:
    try:
        kit = load(args)
    except ConfigError as exc:
        render_error(str(exc))
        return 2
    if args.static or args.gate is None:
        findings = run_static(kit)
        render_static_report(findings)
        return 1 if any(f.status == "FAIL" for f in findings) else 0

    if args.gate not in kit.gates:
        render_error(f"unknown gate '{args.gate}'; expected one of {', '.join(kit.gates)}")
        return 2
    try:
        kit, run = load_for_run(args)
    except (ConfigError, RunError) as exc:
        render_error(str(exc))
        return 2

    render_provenance_notice(run)
    result = evaluate_gate(run, kit, args.gate, online=args.online)
    invalidated = invalidated_gates(run, kit)
    render_gate_result(
        result, kit.gates[args.gate],
        invalidated.get(args.gate), sorted(invalidated),
        show_next=False,
    )
    gate = kit.gates[args.gate]
    if result.status in ("PASS", "CAVEAT"):
        render_next_action("rgraph status")
    elif gate.kind == "human" and result.status in ("AWAITING", "STALE"):
        render_next_action(f"rgraph decide {args.gate}")
    elif gate.kind == "challenge":
        record = run.gate_record(args.gate)
        if (
            record and record.get("outcome") == "revise"
            and result.status != "STALE" and result.decision_valid
        ):
            render_next_action(f"rgraph revise {args.gate}")
        elif record and record.get("outcome") == "block" and result.decision_valid:
            pass
        else:
            render_next_action(f"rgraph challenge {args.gate}")
    return 0 if result.status in ("PASS", "CAVEAT") else 1
