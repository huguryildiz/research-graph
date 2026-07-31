from __future__ import annotations

import pathlib

from rgraph.config import ConfigError, load_kit
from rgraph.gates import evaluate_gate, record_from
from rgraph.lint import run_static
from rgraph.provenance import invalidated_gates
from rgraph.render import render_provenance_notice, render_gate_result, render_static_report
from rgraph.run import RunError, load_run


def register(subparsers) -> None:
    parser = subparsers.add_parser("check", help="verify a gate, or lint the graph")
    parser.add_argument("gate", nargs="?", help="gate id, e.g. E1")
    parser.add_argument("--static", action="store_true", help="run Layer 1 only")
    parser.add_argument("--online", action="store_true", help="resolve DOIs over the network")
    parser.set_defaults(handler=handle)


def load(args, assignment: str = "assignment.yaml"):
    root = pathlib.Path(args.root)
    if assignment == "assignment.yaml" and not (root / "assignment.yaml").exists():
        assignment = "assignment.example.yaml"
    return load_kit(root, assignment=assignment)


def handle(args) -> int:
    try:
        kit = load(args)
    except ConfigError as exc:
        print(f"error: {exc}")
        return 2
    if args.static or args.gate is None:
        findings = run_static(kit)
        render_static_report(findings)
        return 1 if any(f.status == "FAIL" for f in findings) else 0

    if args.gate not in kit.gates:
        print(f"error: unknown gate '{args.gate}'; expected one of {', '.join(kit.gates)}")
        return 2
    try:
        run = load_run(pathlib.Path(args.run), kit)
    except RunError as exc:
        print(f"error: {exc}")
        return 2

    render_provenance_notice(run)
    result = evaluate_gate(run, kit, args.gate, online=args.online)
    invalidated = invalidated_gates(run, kit)
    render_gate_result(
        result, kit.gates[args.gate],
        invalidated.get(args.gate), sorted(invalidated),
    )
    run.write_gate_record(record_from(result, run, kit))
    return 0 if result.status in ("PASS", "CAVEAT") else 1
