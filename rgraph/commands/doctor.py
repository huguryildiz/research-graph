"""`rgraph doctor` — preflight the assignment before a provider is trusted."""

from __future__ import annotations

import pathlib
import shutil  # noqa: F401  (tests patch provider discovery through this name)
import subprocess  # noqa: F401  (tests patch login and probe calls through this name)

from rgraph.config import ConfigError
from rgraph.render import (
    body_text,
    console,
    marked,
    muted,
    render_error,
    render_next_action,
    section,
)
from rgraph.services.preflight import (  # noqa: F401  (public surface of `rgraph doctor`)
    PROBE_TEXT, Finding, inspect_assignment,
)


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "doctor",
        help="preflight providers, login, assignment and models",
        description=(
            "Check the effective assignment, provider executables, login state and "
            "role capabilities before a unit runs. Model names remain UNVERIFIED "
            "unless --probe-models makes a small real provider call."
        ),
        epilog=(
            "Examples:\n"
            "  rgraph doctor\n"
            "  rgraph doctor --probe-models\n"
            "  rgraph doctor --probe-models --timeout 90"
        ),
    )
    parser.add_argument(
        "--probe-models",
        action="store_true",
        help="make one minimal real call per distinct provider/model assignment",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        metavar="SECONDS",
        help="timeout for each login or model probe (default: 60)",
    )
    parser.set_defaults(handler=handle)


def inspect(args) -> list[Finding]:
    return inspect_assignment(
        pathlib.Path(args.root), timeout=args.timeout, probe_models=args.probe_models,
    )


def handle(args) -> int:
    try:
        findings = inspect(args)
    except ConfigError as exc:
        render_error(str(exc))
        console.print()
        render_next_action("rgraph setup")
        return 2

    section("Provider preflight")
    for finding in findings:
        console.print(marked(finding.status, finding.label))
        muted(finding.detail, indent="        ")
    blockers = [finding for finding in findings if finding.blocking]
    console.print()
    section("Result")
    if blockers:
        body_text(f"BLOCKED — {len(blockers)} preflight failure(s) must be fixed.")
        console.print()
        render_next_action("rgraph setup")
        return 2
    body_text("READY — the assignment can be invoked with the caveats shown above.")
    console.print()
    run = pathlib.Path(args.run)
    render_next_action("rgraph status" if (run / "meta.json").exists() else "rgraph init")
    return 0
