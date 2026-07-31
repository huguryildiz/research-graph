from __future__ import annotations

import pathlib

from rgraph.config import ConfigError, load_kit
from rgraph.lint import run_static
from rgraph.render import render_static_report


def register(subparsers) -> None:
    parser = subparsers.add_parser("check", help="verify a gate, or lint the graph")
    parser.add_argument("gate", nargs="?", help="gate id, e.g. E1")
    parser.add_argument("--static", action="store_true", help="run Layer 1 only")
    parser.add_argument("--online", action="store_true", help="resolve DOIs over the network")
    parser.set_defaults(handler=handle)


def handle(args) -> int:
    try:
        kit = load_kit(pathlib.Path(args.root))
    except ConfigError as exc:
        print(f"error: {exc}")
        return 2
    if args.static or args.gate is None:
        findings = run_static(kit)
        render_static_report(findings)
        return 1 if any(f.status == "FAIL" for f in findings) else 0
    raise NotImplementedError("dynamic gate check lands in Task 12")
